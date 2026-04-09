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

_openai_client: OpenAI | None = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


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
    return response.output_text.strip()
