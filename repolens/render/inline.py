"""Tiny inline markup shared by renderers: `code`, **bold**, *italic*."""

from __future__ import annotations

import re

TOKEN = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*)")


def segments(text: str) -> list[tuple[str, str]]:
    """Split text into (content, style) pairs where style is '', 'code', 'bold', or 'italic'."""
    out = []
    for part in TOKEN.split(text or ""):
        if not part:
            continue
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append((part[1:-1], "code"))
        elif part.startswith("**") and part.endswith("**") and len(part) > 3:
            out.append((part[2:-2], "bold"))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append((part[1:-1], "italic"))
        else:
            out.append((part, ""))
    return out


def plain(text: str) -> str:
    return "".join(t for t, _ in segments(text))
