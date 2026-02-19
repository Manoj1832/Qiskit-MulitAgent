"""
PDF extraction utilities using PyPDF2.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import PyPDF2
    _PYPDF2_AVAILABLE = True
except ImportError:
    _PYPDF2_AVAILABLE = False


def extract_text_from_pdf(pdf_bytes: bytes) -> Optional[str]:
    """Extract all text from a PDF file."""
    if not _PYPDF2_AVAILABLE:
        logger.error("PyPDF2 not installed.")
        return None

    try:
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            content = page.extract_text()
            if content:
                text += content + "\n"
        return text.strip()
    except Exception as e:
        logger.error("Failed to extract text from PDF: %s", e)
        return None
