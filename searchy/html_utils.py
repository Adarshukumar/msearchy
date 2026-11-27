from __future__ import annotations

import html
import re
from typing import Any

from lxml import etree
from lxml import html as lxml_html

_XML_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def extract_text(el: Any) -> str:
    """Extract normalized plain text from an lxml element or string."""
    if el is None:
        return ""
    if isinstance(el, str):
        return _WHITESPACE_RE.sub(" ", html.unescape(el)).strip()
    return _WHITESPACE_RE.sub(" ", "".join(el.itertext())).strip()


def clean_snippet(raw: str | None) -> str:
    """Strip HTML tags, unescape entities, and normalize whitespace."""
    if not raw:
        return ""
    without_tags = _HTML_TAG_RE.sub("", raw)
    return _WHITESPACE_RE.sub(" ", html.unescape(without_tags)).strip()


def clean_str(value: Any) -> str:
    """Convert optional JSON values safely to str without turning None into 'None'."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def clean_int(value: Any) -> int | None:
    """Convert optional width/height values to int, returning None on invalid input."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None
    return None


def parse_html(content: str | bytes) -> Any:
    """Parse HTML safely, handling empty documents and XML encoding declarations.

    Always returns a valid lxml element so XPath queries on empty responses
    return empty lists instead of raising ``ParserError`` or ``ValueError``.
    """
    if not content:
        return lxml_html.fromstring("<html><body></body></html>")

    if isinstance(content, bytes):
        if not content.strip():
            return lxml_html.fromstring("<html><body></body></html>")
        try:
            return lxml_html.fromstring(content)
        except (etree.ParserError, etree.XMLSyntaxError):
            return lxml_html.fromstring("<html><body></body></html>")

    stripped = content.strip()
    if not stripped:
        return lxml_html.fromstring("<html><body></body></html>")

    # lxml refuses Unicode strings with an <?xml ... encoding="..."?> declaration.
    sanitized = _XML_DECL_RE.sub("", stripped, count=1).strip()
    if not sanitized:
        return lxml_html.fromstring("<html><body></body></html>")

    try:
        return lxml_html.fromstring(sanitized)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        return lxml_html.fromstring("<html><body></body></html>")


def compile_xpath(expr: str) -> etree.XPath:
    """Compile an XPath expression once for repeated high-speed evaluation."""
    return etree.XPath(expr)
