# Railway build for the SOLA DD web app + ModularZ.
#
# We use a Dockerfile (not Nixpacks/Railpack) so the runtime image deterministically
# includes LibreOffice. web/modularz_calc.py shells out to headless `soffice` to
# recalc the LIHTC v28 workbook (the model uses XLOOKUP/LET/LAMBDA, which the
# in-browser engine can't compute). We pin Debian trixie because its LibreOffice
# (25.x) supports LET/LAMBDA — older LibreOffice (e.g. bookworm's 7.4) returns
# #NAME? on the model's LET cell and poisons the returns chain.
FROM python:3.12-slim-trixie

# Headless LibreOffice Calc + fonts for faithful rendering/recalc.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-calc \
        libreoffice-core \
        fonts-liberation \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# soffice is at /usr/bin/soffice on PATH; pin it explicitly for the calc engine.
ENV LIBREOFFICE_BIN=/usr/bin/soffice \
    HOME=/root \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Port comes from $PORT at runtime via gunicorn.conf.py (NOT the command line —
# Railway runs custom start commands without a shell, so a literal "$PORT" on the
# command line is never expanded and crashes the app).
CMD ["gunicorn", "web.app:app", "-c", "gunicorn.conf.py"]
