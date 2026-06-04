from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


PDF_IMPORT_REQUIREMENTS = {
    "cryptography": "AES-encrypted PDF statements require pypdf's crypto backend.",
    "pymupdf": "Scanned PDF statement pages require PyMuPDF before OCR can run.",
}


def load_runtime_requirement_names() -> set[str]:
    requirements_path = Path(__file__).resolve().parents[1] / "requirements.txt"
    names: set[str] = set()

    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = line
        for separator in ("==", ">=", "<=", "~=", "!=", ">"):
            if separator in name:
                name = name.split(separator, 1)[0]
                break
        names.add(name.split("[", 1)[0].strip().lower().replace("-", "_"))

    return names


class RuntimeDependencyTests(unittest.TestCase):
    def test_pdf_import_runtime_dependencies_are_declared(self) -> None:
        requirement_names = load_runtime_requirement_names()

        for package_name, reason in PDF_IMPORT_REQUIREMENTS.items():
            with self.subTest(package_name=package_name):
                self.assertIn(package_name, requirement_names, reason)

    def test_pdf_import_runtime_dependencies_are_importable(self) -> None:
        self.assertIsNotNone(
            importlib.util.find_spec("cryptography"),
            "cryptography must be importable for AES-encrypted PDFs.",
        )
        self.assertTrue(
            importlib.util.find_spec("pymupdf") is not None
            or importlib.util.find_spec("fitz") is not None,
            "PyMuPDF must be importable for scanned PDF page rendering.",
        )


if __name__ == "__main__":
    unittest.main()
