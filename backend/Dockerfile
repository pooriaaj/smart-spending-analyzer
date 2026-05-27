FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.py .

ENV LOCAL_OCR_ENABLED=true
ENV LOCAL_OCR_COMMAND=tesseract
ENV LOCAL_OCR_LANGUAGE=eng
ENV PDF_OCR_RENDER_DPI=200

CMD ["python", "run.py"]
