"""Text hygiene helpers shared by the Docling ingestion path."""

import re

_SOFT_HYPHEN = "\u00ad"


def _fix_fraction_equals(content: str) -> str:
    content = re.sub(r"(?i)\bn\s*1/4\s*(\d+)\b", r"n = \1", content)
    content = re.sub(r"(?i)\bn\s*¼\s*(\d+)\b", r"n = \1", content)
    return content


def _dehyphenate_linebreaks(content: str) -> str:
    content = content.replace(_SOFT_HYPHEN, "")
    content = re.sub(r"-\s*\n\s*", "", content)
    content = re.sub(r"(\w)-\s+(\w)", r"\1\2", content)
    content = re.sub(r"(?<=\d)\s+(?=\d)", "", content)
    content = re.sub(r"(?<=\d\.)\s+(?=\d)", "", content)
    return content


def _strip_headers_inline(content: str) -> str:
    return re.sub(
        r"(?i)downloaded from .*?(?:rights reserved|copyright).*?$",
        "",
        content,
    )


def _strip_print_artifacts(content: str) -> str:
    content = re.sub(r"\b\d+\s*C/FPO\b", " ", content, flags=re.IGNORECASE)
    content = re.sub(r"\bC/FPO\b", " ", content, flags=re.IGNORECASE)
    content = re.sub(r"\bFPO\b", " ", content, flags=re.IGNORECASE)
    return content


def normalize_text(content: str) -> str:
    """Apply lightweight cleanup passes to Docling text."""

    content = content.replace(_SOFT_HYPHEN, "")
    content = _fix_fraction_equals(content)
    content = _dehyphenate_linebreaks(content)
    content = _strip_headers_inline(content)
    content = _strip_print_artifacts(content)
    content = re.sub(r"[ \t]+", " ", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


__all__ = ["normalize_text"]
