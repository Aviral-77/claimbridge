# ClaimBridge backend image — serves BOTH the FastAPI api and the Celery worker
# (the compose file overrides `command` for the worker). One image, two roles.

FROM python:3.12-slim

# poppler-utils provides pdftoppm/pdftocairo, which pdf2image shells out to for
# rendering scanned PDFs. This is the system dependency that was "poppler on
# PATH" in the local Windows setup — baked into the image so it's always present.
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first so the pip layer is cached and only re-runs when deps
# change — not on every code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source. In dev, compose bind-mounts ./extraction over /app so live
# edits reflect without a rebuild; this COPY is what a production image ships.
COPY . .

EXPOSE 8000

# Default role = API. The worker service overrides this with a celery command.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
