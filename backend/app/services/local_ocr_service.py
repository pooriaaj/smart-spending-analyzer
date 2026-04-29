from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
IMAGE_SUFFIX_BY_MIME_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        parsed = int(raw_value)
    except ValueError:
        return default

    return max(minimum, min(parsed, maximum))


def is_local_ocr_config_enabled() -> bool:
    return _env_bool("LOCAL_OCR_ENABLED", True)


def get_tesseract_command() -> str | None:
    if not is_local_ocr_config_enabled():
        return None

    configured_command = os.getenv("LOCAL_OCR_COMMAND", "tesseract").strip()
    if not configured_command:
        return None

    configured_path = Path(configured_command)
    if configured_path.exists():
        return str(configured_path)

    return shutil.which(configured_command)


def is_local_ocr_enabled() -> bool:
    return get_tesseract_command() is not None


def run_local_ocr_image(file_bytes: bytes, mime_type: str) -> str:
    command = get_tesseract_command()
    if command is None:
        raise ValueError(
            "Free local OCR is not available because the Tesseract command was not found."
        )

    language = os.getenv("LOCAL_OCR_LANGUAGE", "eng").strip() or "eng"
    page_segmentation_mode = os.getenv("LOCAL_OCR_PAGE_SEGMENTATION_MODE", "6").strip() or "6"
    timeout_seconds = _env_int("LOCAL_OCR_TIMEOUT_SECONDS", default=25, minimum=5, maximum=120)
    suffix = IMAGE_SUFFIX_BY_MIME_TYPE.get(mime_type.lower(), ".png")

    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary_image:
            temporary_image.write(file_bytes)
            temporary_path = temporary_image.name

        completed_process = subprocess.run(
            [
                command,
                temporary_path,
                "stdout",
                "-l",
                language,
                "--psm",
                page_segmentation_mode,
            ],
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Free local OCR timed out while reading the scanned PDF page.") from exc
    finally:
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass

    if completed_process.returncode != 0:
        error_text = completed_process.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(error_text or "Free local OCR could not read the scanned PDF page.")

    return completed_process.stdout.decode("utf-8", errors="replace").strip()
