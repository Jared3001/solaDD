#!/usr/bin/env python3
"""
om_extract.py — pull deal facts out of an Offering Memorandum (OM) PDF with Google Gemini.

OMs are unstructured (often scanned) marketing PDFs, so extraction uses the
Gemini API (the same model the ModularZ tool uses): the PDF is sent to
gemini-2.5-flash, which reads it natively, and returns a validated, structured
list of deal facts via Gemini's JSON-schema response mode. Each extracted value
carries a confidence and a short verbatim source quote for provenance.

Small PDFs are sent inline (base64) in the generateContent request; larger decks
go through the Gemini Files API (resumable upload), referenced by URI, and the
uploaded file is deleted as soon as extraction returns. This lets the module
handle large, scanned OM decks without inlining megabytes into every request.

These map onto the schema's `fill_method: desk_om` fields — the deal facts the OM
is authoritative for (price, land size, unit/tenant mix, escrow dates, …). The
caller (jobs.py) reconciles them against the DD readers: default to the OM, switch
to a DD answer only when the DD process produces a different, cited value.

Requires GEMINI_API_KEY (the same key the ModularZ page uses). Model is
GEMINI_OM_MODEL (default gemini-2.5-flash).
"""
import base64
import json
import os
from typing import Optional

import requests

GEMINI_OM_MODEL = os.environ.get("GEMINI_OM_MODEL", "gemini-2.5-flash")
_API_ROOT = "https://generativelanguage.googleapis.com"
# Generous cap (well above typical OM decks). PDFs at/below this go inline; larger
# decks use the Files API. The Gemini request limit for inline data is ~20 MB.
MAX_PDF_BYTES = int(os.environ.get("OM_MAX_MB", "150")) * 1024 * 1024
_INLINE_MAX_BYTES = int(os.environ.get("OM_INLINE_MB", "15")) * 1024 * 1024
_HTTP_TIMEOUT = int(os.environ.get("OM_HTTP_TIMEOUT", "180"))

# Deal-fact fields the OM is authoritative for (schema fill_method: desk_om),
# field_id -> human description that guides extraction.
OM_FIELDS = {
    "address": "Street address of the subject property",
    "apn": "Assessor Parcel Number(s) (APN / AIN)",
    "acquisition_price": "Asking / list / offering price in USD (the headline deal price)",
    "land_sf": "Lot / land area in SQUARE FEET (convert acres x 43,560; note if converted)",
    "estimated_unit_count": "Proposed or estimated total unit count for the development",
    "existing_residential_units": "Existing residential units currently on site",
    "units_to_vacate_at_coe": "Units to be delivered vacant at close of escrow",
    "units_rent_stabilized": "Number of rent-stabilized / rent-controlled units",
    "units_owner_occupied": "Number of owner-occupied units",
    "units_requiring_replacement_sb8": "Units requiring replacement under SB8/SB330",
    "commercial_tenants": "Commercial tenants / ground-floor retail in place",
    "gross_rents_in_place": "Gross scheduled / in-place rents (USD, period as stated)",
    "longest_remaining_lease_expiry": "Latest / longest remaining lease expiration date",
    "sb8": "SB8/SB330 replacement-housing status or applicability, as stated",
    "status": "Deal stage (Offer / Escrow / Non-refundable / Closed), if stated",
    "revenue_classification": "Revenue type (Section 8 / ED1 / Workforce / LIHTC), if stated",
    "entitlement_strategy": "Entitlement strategy / pathway described (e.g. ED1, TOC, density bonus)",
    "contingency_removal_date": "Contingency / due-diligence removal date",
    "est_close_of_escrow": "Estimated close of escrow date",
    "county": "County, if explicitly stated",
    "city_jurisdiction": "City / jurisdiction, if explicitly stated",
}

_FIELD_IDS = list(OM_FIELDS.keys())

# Gemini response schema (subset of OpenAPI): one validated entry per OM field.
_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_id": {"type": "string", "enum": _FIELD_IDS},
                    "value": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "source_quote": {"type": "string"},
                },
                "required": ["field_id", "value", "confidence", "source_quote"],
                "propertyOrdering": ["field_id", "value", "confidence", "source_quote"],
            },
        },
    },
    "required": ["fields"],
}


def _prompt() -> str:
    lines = "\n".join(f"  - {fid}: {desc}" for fid, desc in OM_FIELDS.items())
    return (
        "You are extracting deal facts from a commercial real estate Offering Memorandum (OM) "
        "for an affordable-housing acquisition. Extract ONLY values explicitly stated in the "
        "document — never guess or infer. Omit any field not present.\n\n"
        "For each value, return: field_id (from the allowed list below), the value as a clean "
        "string, your confidence (high/medium/low), and a short verbatim source_quote (the exact "
        "phrase/figure from the OM the value came from).\n\n"
        "Normalization rules:\n"
        "  - acquisition_price / gross_rents_in_place: keep the number; you may keep the $ and commas.\n"
        "  - land_sf: report SQUARE FEET. If the OM gives acres only, multiply by 43,560 and say "
        "'(converted from N acres)' in the source_quote.\n"
        "  - counts (units_*): integers.\n"
        "  - dates: as written.\n"
        "Return at most one entry per field_id (the most authoritative figure if several appear).\n\n"
        "Allowed field_id values and meanings:\n" + lines
    )


class OMExtractError(RuntimeError):
    pass


def _generate(api_key: str, pdf_part: dict) -> dict:
    """POST one generateContent request and return the parsed JSON response."""
    url = f"{_API_ROOT}/v1beta/models/{GEMINI_OM_MODEL}:generateContent?key={api_key}"
    body = {
        "contents": [{
            "role": "user",
            "parts": [{"text": _prompt()}, pdf_part],
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
            "temperature": 0,
        },
    }
    r = requests.post(url, json=body, timeout=_HTTP_TIMEOUT)
    if r.status_code != 200:
        raise OMExtractError(f"Gemini API error during OM extraction ({r.status_code}): {r.text[:400]}")
    return r.json()


def _upload_via_files_api(api_key: str, pdf_bytes: bytes, filename: str) -> str:
    """Resumable-upload a PDF to the Gemini Files API; return (file_name, file_uri)."""
    start = requests.post(
        f"{_API_ROOT}/upload/v1beta/files?key={api_key}",
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(pdf_bytes)),
            "X-Goog-Upload-Header-Content-Type": "application/pdf",
            "Content-Type": "application/json",
        },
        json={"file": {"display_name": filename or "om.pdf"}},
        timeout=_HTTP_TIMEOUT,
    )
    if start.status_code != 200:
        raise OMExtractError(f"Gemini Files API upload-start failed ({start.status_code}): {start.text[:300]}")
    upload_url = start.headers.get("X-Goog-Upload-URL")
    if not upload_url:
        raise OMExtractError("Gemini Files API did not return an upload URL.")

    up = requests.post(
        upload_url,
        headers={
            "Content-Length": str(len(pdf_bytes)),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
        data=pdf_bytes,
        timeout=_HTTP_TIMEOUT,
    )
    if up.status_code != 200:
        raise OMExtractError(f"Gemini Files API upload failed ({up.status_code}): {up.text[:300]}")
    info = (up.json() or {}).get("file") or {}
    name, uri, state = info.get("name"), info.get("uri"), info.get("state")
    if not uri or not name:
        raise OMExtractError("Gemini Files API upload returned no file URI.")

    # PDFs are usually ACTIVE immediately; poll briefly while PROCESSING.
    tries = 0
    while state == "PROCESSING" and tries < 15:
        import time
        time.sleep(2)
        poll = requests.get(f"{_API_ROOT}/v1beta/{name}?key={api_key}", timeout=_HTTP_TIMEOUT)
        info = poll.json() if poll.status_code == 200 else {}
        state = info.get("state", state)
        tries += 1
    if state == "FAILED":
        raise OMExtractError("Gemini failed to process the uploaded OM PDF.")
    return name, uri


def _delete_file(api_key: str, name: str) -> None:
    try:
        requests.delete(f"{_API_ROOT}/v1beta/{name}?key={api_key}", timeout=30)
    except Exception:
        pass


def _parse_response(resp: dict) -> list[dict]:
    """Pull the model's JSON text out of a generateContent response and validate it."""
    candidates = resp.get("candidates") or []
    if not candidates:
        return []
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        return []
    # responseMimeType=application/json should give clean JSON; strip fences defensively.
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise OMExtractError(f"Gemini returned non-JSON OM output: {e}") from e

    seen, out = set(), []
    for f in (data.get("fields") or []):
        fid = f.get("field_id")
        if fid not in OM_FIELDS or fid in seen:
            continue
        value = str(f.get("value", "")).strip()
        if not value:
            continue
        conf = f.get("confidence")
        if conf not in ("high", "medium", "low"):
            conf = "medium"
        seen.add(fid)
        out.append({
            "field_id": fid,
            "value": value,
            "confidence": conf,
            "source_quote": str(f.get("source_quote", "")).strip()[:300],
        })
    return out


def extract(pdf_bytes: bytes, filename: str = "om.pdf") -> list[dict]:
    """Extract OM deal facts. Returns [{field_id, value, confidence, source_quote}, ...].

    Raises OMExtractError on a missing API key, an oversized PDF, or an API failure."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise OMExtractError("OM extraction needs GEMINI_API_KEY set on the server.")
    if not pdf_bytes:
        raise OMExtractError("Empty OM upload.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise OMExtractError(
            f"OM is {len(pdf_bytes) / 1e6:.0f} MB; the limit is {MAX_PDF_BYTES // (1024*1024)} MB. "
            "Compress or trim the PDF and retry.")

    if len(pdf_bytes) <= _INLINE_MAX_BYTES:
        # Small enough to inline as base64 — one request, no upload/cleanup.
        part = {"inlineData": {"mimeType": "application/pdf",
                               "data": base64.b64encode(pdf_bytes).decode("ascii")}}
        return _parse_response(_generate(api_key, part))

    # Large deck: upload via the Files API, reference by URI, delete when done.
    name, uri = _upload_via_files_api(api_key, pdf_bytes, filename)
    try:
        part = {"fileData": {"mimeType": "application/pdf", "fileUri": uri}}
        return _parse_response(_generate(api_key, part))
    finally:
        _delete_file(api_key, name)


if __name__ == "__main__":
    import sys
    data = open(sys.argv[1], "rb").read()
    print(json.dumps(extract(data, os.path.basename(sys.argv[1])), indent=2))
