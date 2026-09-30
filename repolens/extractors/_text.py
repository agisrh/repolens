"""Helpers for reading source code as text, shared by the extractors.

The extractors use regular expressions rather than real parsers, so they can read any
language without its toolchain installed. These helpers cover what regular expressions
cannot do well on their own: matching brackets, skipping comments, and picking out
string literals.
"""

from __future__ import annotations

import re

# A Java/Kotlin class declaration with its annotations and modifiers.
# Groups: 1 "class"/"interface", 2 the name, 3 the parent class after `extends`.
JAVA_CLASS_DECL = re.compile(
    r"^[ \t]*(?:@\w+(?:\([^)]*\))?\s+)*"  # annotations
    r"(?:(?:public|protected|private|abstract|final|open|data|sealed|internal)\s+)*"  # modifiers
    r"(class|interface)\s+(\w+)(?:<[^>]*>)?(?:\s+extends\s+(\w+))?",
    re.M,
)


def strings(args: str) -> list[str]:
    """The quoted string literals in a piece of code, in order."""
    return re.findall(r"[\"']([^\"']*)[\"']", args or "")


def balanced(text: str, start: int) -> tuple[str, int]:
    """Contents of the parenthesised group opening at text[start] == "(", and the offset after it.

    Parentheses inside string literals are ignored."""
    depth = 0
    in_string = None
    for i in range(start, len(text)):
        char = text[i]
        if in_string:
            if char == in_string and text[i - 1] != "\\":
                in_string = None
            continue
        if char in "\"'`":
            in_string = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i + 1
    return text[start + 1 :], len(text)


def block_end(text: str, brace: int) -> int:
    """Offset of the "}" that closes the "{" at text[brace] (or the end of the text)."""
    depth, i = 0, brace
    while i < len(text):
        depth += (text[i] == "{") - (text[i] == "}")
        if depth == 0:
            break
        i += 1
    return i


def uncommented(text: str) -> str:
    """Drop lines that are comments (//, #, /* and * continuation lines)."""
    lines = text.splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith(("//", "#", "*", "/*")))


def closing_offset(text: str, start: int, open_char: str, close_char: str) -> int:
    """Offset just after the bracket that closes a block whose opening bracket is before `start`."""
    depth, i = 1, start
    while i < len(text) and depth:
        depth += (text[i] == open_char) - (text[i] == close_char)
        i += 1
    return i
