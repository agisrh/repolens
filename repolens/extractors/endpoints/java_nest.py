"""Server endpoints declared with annotations/decorators: Spring (Java/Kotlin) and NestJS.

Spring: `@RequestMapping("/api")` on the class gives the prefix, and every
`@GetMapping("/x")`, `@PostMapping`, ... on a method adds an endpoint.
NestJS: `@Controller("users")` gives the prefix, `@Get(":id")`, `@Post()`, ... add endpoints.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from repolens.extractors.endpoints._common import FileScan, balanced, join_paths, strings
from repolens.repo import Repo

CLASS_DECL = re.compile(
    r"^[ \t]*(?:@\w+(?:\([^)]*\))?\s+)*"  # annotations
    r"(?:(?:public|protected|private|abstract|final|open|data|sealed|internal)\s+)*"  # modifiers
    r"(class|interface)\s+(\w+)(?:<[^>]*>)?(?:\s+extends\s+(\w+))?",
    re.M,
)
MAPPING = re.compile(r"@(Get|Post|Put|Delete|Patch|Request)Mapping\b")
HANDLER_JAVA = re.compile(r"(?:public|protected|private|fun)\s+(?:[\w<>\[\],.?\s]+?\s+)?(\w+)\s*\(")
# Mapping attributes that are not paths.
NOT_A_PATH = re.compile(
    r"\b(produces|consumes|headers|params|name)\s*=\s*(\{[^}]*\}|\"[^\"]*\"|[\w.]+)"
)
NOT_A_CLASS_PATH = re.compile(r"\b(produces|consumes|headers|params)\s*=\s*\{?[^,)]*\}?")

NEST_METHOD = re.compile(r"@(Get|Post|Put|Delete|Patch|Options|Head|All)\(\s*([^)]*)\)")


def spring(repo: Repo) -> list[dict]:
    out = []
    for path in repo.by_ext(".java", ".kt"):
        text = repo.read(path)
        if "Mapping" not in text or not re.search(r"@(Rest)?Controller\b", text):
            continue
        class_match = CLASS_DECL.search(text)
        # Offset of the `class` keyword itself, so class-level annotations come before it.
        class_pos = class_match.start(1) if class_match else 0
        class_name = class_match.group(2) if class_match else PurePosixPath(path).stem
        prefix = _class_prefix(text[:class_pos], text)
        found = FileScan(path, text, "Spring", group=class_name)
        for match in MAPPING.finditer(text, class_pos):
            args, end = ("", match.end())
            if text[match.end() : match.end() + 1] == "(":
                args, end = balanced(text, match.end())
            paths = strings(NOT_A_PATH.sub("", args)) or [""]
            if match.group(1) == "Request":
                methods = re.findall(r"RequestMethod\.(\w+)", args) or ["ANY"]
            else:
                methods = [match.group(1).upper()]
            method_name = HANDLER_JAVA.search(text, end)
            handler = f"{class_name}.{method_name.group(1)}()" if method_name else class_name
            for sub_path in paths:
                for method in methods:
                    found.add(method, join_paths(prefix, sub_path), handler, match.start())
        out += found.items
    return out


def _class_prefix(before_class: str, text: str) -> str:
    """Path of the last @...Mapping placed on the class itself ("" when there is none)."""
    prefix = ""
    for match in MAPPING.finditer(before_class):
        if text[match.end() : match.end() + 1] == "(":
            args, _ = balanced(text, match.end())
            found = strings(NOT_A_CLASS_PATH.sub("", args))
            prefix = found[0] if found else ""
    return prefix


def nestjs(repo: Repo) -> list[dict]:
    out = []
    for path in repo.by_ext(".ts"):
        text = repo.read(path)
        controller = re.search(r"@Controller\(\s*([^)]*)\)", text)
        if not controller:
            continue
        prefix = (strings(controller.group(1)) or [""])[0]
        class_match = re.search(r"class\s+(\w+)", text)
        class_name = class_match.group(1) if class_match else None
        found = FileScan(path, text, "NestJS", group=class_name)
        for match in NEST_METHOD.finditer(text):
            method_name = re.search(r"(\w+)\s*\(", text[match.end() :])
            handler = f"{class_name or ''}.{method_name.group(1) if method_name else ''}()"
            route = join_paths(prefix, (strings(match.group(2)) or [""])[0])
            found.add(match.group(1).upper(), route, handler, match.start())
        out += found.items
    return out
