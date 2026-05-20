from __future__ import annotations

import base64
import os

from dotenv import load_dotenv
from openai import OpenAI


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=ENV_PATH)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OCR_VISION_MODEL = os.getenv("OCR_VISION_MODEL", "gpt-4.1-mini")


def _bounded_float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


OCR_TIMEOUT_SECONDS = _bounded_float_env("OCR_TIMEOUT_SECONDS", 30.0, 5.0, 180.0)
OCR_MAX_RETRIES = _bounded_int_env("OCR_MAX_RETRIES", 1, 0, 5)
OCR_RESPONSE_MAX_CHARS = _bounded_int_env("OCR_RESPONSE_MAX_CHARS", 20000, 2000, 50000)

_openai_client: OpenAI | None = (
    OpenAI(api_key=OPENAI_API_KEY, timeout=OCR_TIMEOUT_SECONDS, max_retries=OCR_MAX_RETRIES)
    if OPENAI_API_KEY
    else None
)


def is_vision_ocr_enabled() -> bool:
    return _openai_client is not None


def build_image_data_url(file_bytes: bytes, mime_type: str) -> str:
    base64_image = base64.b64encode(file_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{base64_image}"


def build_input_image_part(file_bytes: bytes, mime_type: str) -> dict[str, str]:
    return {
        "type": "input_image",
        "image_url": build_image_data_url(file_bytes, mime_type),
    }


def run_vision_prompt(prompt: str, image_parts: list[dict[str, str]]) -> str:
    if _openai_client is None:
        raise ValueError(
            "Vision OCR is not enabled yet. Add a valid OPENAI_API_KEY to enable image parsing."
        )

    response = _openai_client.responses.create(
        model=OCR_VISION_MODEL,
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}, *image_parts],
            }
        ],
    )
    output_text = response.output_text.strip()
    if len(output_text) <= OCR_RESPONSE_MAX_CHARS:
        return output_text
    return f"{output_text[:OCR_RESPONSE_MAX_CHARS].rstrip()}..."
