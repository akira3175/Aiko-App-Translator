"""Small, safe Markdown emphasis renderer shared by exported books and shares."""

import html
import re


_PATTERNS = (
    (re.compile(r"(\*\*\*|___)(?=\S)(.+?)(?<=\S)\1"), True, True),
    (re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1"), True, False),
    (re.compile(r"(?<!\w)(\*|_)(?=\S)(.+?)(?<=\S)\1(?!\w)"), False, True),
)


def inline_runs(text):
    """Return (text, bold, italic) runs for supported Markdown emphasis."""
    runs, cursor = [], 0
    while cursor < len(text):
        matches = []
        for priority, (pattern, bold, italic) in enumerate(_PATTERNS):
            match = pattern.search(text, cursor)
            if match:
                matches.append((match.start(), priority, match, bold, italic))
        if not matches:
            runs.append((text[cursor:], False, False))
            break
        _start, _priority, match, bold, italic = min(
            matches, key=lambda item: (item[0], item[1])
        )
        if match.start() > cursor:
            runs.append((text[cursor:match.start()], False, False))
        runs.append((match.group(2), bold, italic))
        cursor = match.end()
    return [run for run in runs if run[0]]


def inline_html(text):
    parts = []
    for value, bold, italic in inline_runs(text):
        escaped = html.escape(value)
        if italic:
            escaped = f"<em>{escaped}</em>"
        if bold:
            escaped = f"<strong>{escaped}</strong>"
        parts.append(escaped)
    return "".join(parts)
