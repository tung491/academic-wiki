"""Read and write YAML frontmatter at the top of markdown files."""
from __future__ import annotations

import os
import re
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n?---\n?(.*)$", re.DOTALL)


def read_frontmatter(path) -> tuple[dict[str, Any], str]:
    """Read YAML frontmatter and body from a markdown file.

    Returns ({}, body) if there is no frontmatter block.
    Accepts str or any os.PathLike.
    """
    with open(os.fspath(path), "r", encoding="utf-8") as f:
        content = f.read()

    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}, content

    yaml_text = m.group(1)
    body = m.group(2)
    data = yaml.safe_load(yaml_text) if yaml_text.strip() else None
    return (data or {}), body


def write_frontmatter(path, frontmatter: dict[str, Any], body: str) -> None:
    """Write a markdown file with YAML frontmatter + body. Preserves key insertion order.

    Accepts str or any os.PathLike for `path`.
    """
    yaml_text = yaml.dump(frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False)
    with open(os.fspath(path), "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(yaml_text)
        f.write("---\n")
        f.write(body)
