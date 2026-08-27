"""The on-disk format for an editable review draft.

A draft is a Markdown file: a small frontmatter block (book identity + status) followed by
the review body and a human-facing guard reminding that nothing is ever posted
automatically — the user edits the body and flips `status: draft -> approved` by hand.

No YAML dependency: the frontmatter is a flat `key: value` block, parsed by splitting on the
first `: ` so titles may contain colons.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FENCE = "---"
_GUARD = (
    "<!-- Edit the review above in your own words. Nothing is posted automatically. "
    "When you're happy with it, change `status: draft` to `status: approved`. -->"
)
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_COMMENT = re.compile(r"<!--.*?-->", re.S)


def review_text(body: str) -> str:
    """The review itself: the draft body with the editing guard (any HTML comment) removed."""
    return _COMMENT.sub("", body).strip()


@dataclass(frozen=True)
class DraftMeta:
    book_id: int
    title: str
    author: str
    my_rating: int
    status: str = "draft"
    source: str = "claude-loop"


def slug(title: str) -> str:
    """URL/filename-safe slug: lowercased, non-alphanumerics collapsed to single hyphens."""
    return _SLUG_STRIP.sub("-", title.lower()).strip("-")


def render_draft(meta: DraftMeta, body: str) -> str:
    front = [
        _FENCE,
        f"book_id: {meta.book_id}",
        f"title: {meta.title}",
        f"author: {meta.author}",
        f"my_rating: {meta.my_rating}",
        f"status: {meta.status}",
        f"source: {meta.source}",
        _FENCE,
    ]
    return "\n".join(front) + "\n\n" + body.strip() + "\n\n" + _GUARD + "\n"


def parse_draft(text: str) -> tuple[DraftMeta, str]:
    """Parse a draft file back into (meta, body). Body is everything after the frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        raise ValueError("draft is missing its frontmatter fence")
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == _FENCE)
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if ": " in line:
            key, value = line.split(": ", 1)
            value = value.strip()
            # A value wrapping a colon is quoted so the split above can't truncate it;
            # those outer quotes are syntax, not part of the title.
            if len(value) > 1 and value[0] == value[-1] == '"':
                value = value[1:-1]
            fields[key.strip()] = value
    body = "\n".join(lines[end + 1 :]).strip()
    meta = DraftMeta(
        book_id=int(fields["book_id"]),
        title=fields.get("title", ""),
        author=fields.get("author", ""),
        my_rating=int(fields.get("my_rating", "0")),
        status=fields.get("status", "draft"),
        source=fields.get("source", "claude-loop"),
    )
    return meta, body
