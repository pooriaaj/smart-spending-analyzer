FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.py .

ENV LOCAL_OCR_ENABLED=true
ENV LOCAL_OCR_COMMAND=tesseract
ENV LOCAL_OCR_LANGUAGE=eng
ENV PDF_OCR_RENDER_DPI=200

# Run as non-root for container security
RUN useradd -m -r appuser && chown -R appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:${PORT:-10000}/health || exit 1

CMD ["python", "run.py"]
