#!/usr/bin/env python3
"""
om_extract.py — pull deal facts out of an Offering Memorandum (OM) PDF with Claude.

OMs are unstructured (often scanned) marketing PDFs, so extraction uses the
Anthropic API: the PDF is uploaded via the Files API, Claude reads it natively
(document content block referencing the file_id), and returns a validated,
structured list of deal facts via structured outputs. Each extracted value
carries a confidence and a short verbatim source quote for provenance. The
uploaded file is deleted as soon as extraction returns.

Using the Files API (rather than inlining base64) lets this handle large,
scanned OM decks — up to the Files API's 500 MB limit.

These map onto the schema's `fill_method: desk_om` fields — the deal facts the OM
is authoritative for (price, land size, unit/tenant mix, escrow dates, …). The
caller (jobs.py) reconciles them against the DD readers: default to the OM, switch
to a DD answer only when the DD process produces a different, cited value.

Requires ANTHROPIC_API_KEY. Model is OM_MODEL (default claude-opus-4-8; set to
claude-sonnet-4-6 / claude-haiku-4-5 to cut cost).
"""
import io
import os
from typing import Literal, Optional

from pydantic import BaseModel

OM_MODEL = os.environ.get("OM_MODEL", "claude-opus-4-8")
FILES_BETA = "files-api-2025-04-14"
# Generous cap (well above typical OM decks); the Files API itself allows up to 500 MB.
MAX_PDF_BYTES = int(os.environ.get("OM_MAX_MB", "150")) * 1024 * 1024

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

_FieldId = Literal[
    "address", "apn", "acquisition_price", "land_sf", "estimated_unit_count",
    "existing_residential_units", "units_to_vacate_at_coe", "units_rent_stabilized",
    "units_owner_occupied", "units_requiring_replacement_sb8", "commercial_tenants",
    "gross_rents_in_place", "longest_remaining_lease_expiry", "sb8", "status",
    "revenue_classification", "entitlement_strategy", "contingency_removal_date",
    "est_close_of_escrow", "county", "city_jurisdiction",
]


class OMField(BaseModel):
    field_id: _FieldId
    value: str                                  # the extracted value, normalized to a clean string
    confidence: Literal["high", "medium", "low"]
    source_quote: str                           # short verbatim snippet from the OM (provenance)


class OMExtract(BaseModel):
    fields: list[OMField]


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


def extract(pdf_bytes: bytes, filename: str = "om.pdf") -> list[dict]:
    """Extract OM deal facts. Returns [{field_id, value, confidence, source_quote}, ...].

    Raises OMExtractError on a missing API key, an oversized PDF, or an API failure."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise OMExtractError("OM extraction needs ANTHROPIC_API_KEY set on the server.")
    if not pdf_bytes:
        raise OMExtractError("Empty OM upload.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise OMExtractError(
            f"OM is {len(pdf_bytes) / 1e6:.0f} MB; the limit is {MAX_PDF_BYTES // (1024*1024)} MB. "
            "Compress or trim the PDF and retry.")

    import anthropic   # imported lazily so the app runs without the dep until OM is used

    client = anthropic.Anthropic()

    # Upload via the Files API, reference by file_id, delete when done.
    uploaded = client.beta.files.upload(
        file=(filename or "om.pdf", io.BytesIO(pdf_bytes), "application/pdf"),
    )
    try:
        msg = client.beta.messages.parse(
            betas=[FILES_BETA],
            model=OM_MODEL,
            max_tokens=8192,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _prompt()},
                    {"type": "document", "source": {"type": "file", "file_id": uploaded.id}},
                ],
            }],
            output_format=OMExtract,
        )
    except anthropic.APIError as e:
        raise OMExtractError(f"Claude API error during OM extraction: {e}") from e
    finally:
        try:
            client.beta.files.delete(uploaded.id)
        except Exception:
            pass

    parsed: Optional[OMExtract] = msg.parsed_output
    if not parsed:
        return []
    # De-dupe to one entry per field_id (first wins — the model is told to pick the authoritative one).
    seen, out = set(), []
    for f in parsed.fields:
        if f.field_id in OM_FIELDS and f.field_id not in seen:
            seen.add(f.field_id)
            out.append({"field_id": f.field_id, "value": f.value.strip(),
                        "confidence": f.confidence, "source_quote": f.source_quote.strip()[:300]})
    return out


if __name__ == "__main__":
    import sys, json
    data = open(sys.argv[1], "rb").read()
    print(json.dumps(extract(data, os.path.basename(sys.argv[1])), indent=2))
