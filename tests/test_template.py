import importlib.resources
import re

FORBIDDEN = [
    r"<script[^>]+src=",
    r"<link[^>]+href=[\"']https?://",
    r"@import\s+url\(",
    r"\bfetch\s*\(",
    r"\bXMLHttpRequest\b",
    r"\bnew\s+WebSocket\b",
    r"fonts\.(googleapis|gstatic)\.com",
    r"\binnerHTML\b",
    r"\bouterHTML\b",
    r"\binsertAdjacentHTML\b",
    r"\bdocument\.write\b",
]


def template_text():
    return (importlib.resources.files("archmap") / "template.html").read_text(encoding="utf-8")


def test_placeholder_occurs_once():
    assert template_text().count("/*__ARCHMAP_DATA__*/") == 1


def test_data_script_block_present():
    assert '<script id="archmap-data" type="application/json">/*__ARCHMAP_DATA__*/</script>' in template_text()


def test_no_forbidden_patterns():
    text = template_text()
    for pattern in FORBIDDEN:
        assert re.search(pattern, text) is None, pattern
