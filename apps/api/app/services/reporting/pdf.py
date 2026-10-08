"""Dependency-free PDF writer for the impact report export (Phase 5).

The report is a fixed shape — a title, a header block, a score line, and two
tables — so a purpose-built writer is more predictable than pulling in a PDF
library: it emits a valid, paginated PDF using only the standard Courier fonts,
so columns align without font metrics. Output is escaped for the PDF string
delimiters and paginated so long monthly tables split cleanly.
"""

from __future__ import annotations

_PAGE_WIDTH = 595.0  # A4 portrait, points.
_PAGE_HEIGHT = 842.0
_MARGIN = 48.0
_HEADER_FONT = "/F2"  # Courier-Bold
_BODY_FONT = "/F1"  # Courier
_FONT_SIZE = 9


_TRANSLATED_SPECIAL = {
    "\u2014": "-",  # em dash
    "\u2013": "-",  # en dash
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
    "\u2026": "...",  # ellipsis
    "\u00ab": "<<",
    "\u00bb": ">>",
    "\u00a0": " ",
}


def _to_latin1(text: str) -> str:
    """Map unicode beyond Latin-1 to Courier-safe ASCII ('?' otherwise)."""
    translated = "".join(_TRANSLATED_SPECIAL.get(ch, ch) for ch in text)
    return translated.encode("latin-1", errors="replace").decode("latin-1")


def _escape(text: str) -> str:
    safe = _to_latin1(text)
    return safe.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _line(font: str, size: float, x: float, y: float, text: str) -> str:
    return f"BT {font} {size} Tf {x:.1f} {y:.1f} Td ({_escape(text)}) Tj ET"


def _paginate(
    lines: list[tuple[bool, str]],
    *,
    repeat_first: int = 1,
    max_chars_per_line: int = 118,
) -> list[list[tuple[bool, str]]]:
    """Split lines into pages by page height; a wrapped ``repeat_first`` header
    block is prepended to every page so a table's column headings stay visible.

    Lines longer than the page width are hard-truncated: fixed-pitch columns
    must keep their shape or the report would be unreadable.
    """
    truncated: list[tuple[bool, str]] = []
    for bold, text in lines:
        truncated.append((bold, text[:max_chars_per_line]))

    line_height = _FONT_SIZE * 1.35
    max_lines = int((_PAGE_HEIGHT - 2 * _MARGIN) // line_height)
    body = truncated[repeat_first:]
    if max_lines - repeat_first <= 0:
        return [truncated]

    pages: list[list[tuple[bool, str]]] = []
    current: list[tuple[bool, str]] = list(truncated[:repeat_first])
    for line in body:
        if len(current) >= max_lines:
            pages.append(current)
            current = list(truncated[:repeat_first])
        current.append(line)
    if current:
        pages.append(current)
    return pages or [truncated]


def build_pdf(
    lines: list[tuple[bool, str]],
    *,
    repeat_first: int = 1,
) -> bytes:
    """Render ``lines`` as a paginated PDF.

    ``lines`` is a list of ``(bold, text)`` rows. The first ``repeat_first``
    rows (the title/heading block) are repeated at the top of every page.
    """
    pages = _paginate(lines, repeat_first=repeat_first)
    n = len(pages)
    # Object layout: 1 Catalog, 2 Pages, 3.. Page/Contents pairs, then two
    # fonts. Object numbers are computed up front so every reference is exact.
    font_bold = 3 + 2 * n + 1
    font_body = 3 + 2 * n + 2

    objects: list[bytes] = [b""]  # object 0 is unused in the xref.
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    objects.append(
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode()
    )

    for index in range(n):
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_WIDTH:.0f} {_PAGE_HEIGHT:.0f}] "
                f"/Resources << /Font << /F1 {font_body} 0 R /F2 {font_bold} 0 R >> >> "
                f"/Contents {4 + index * 2} 0 R >>"
            ).encode()
        )

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>")

    line_height = _FONT_SIZE * 1.35
    start_y = _PAGE_HEIGHT - _MARGIN
    for index, page in enumerate(pages):
        stream_lines: list[str] = []
        y = start_y
        for bold, text in page:
            stream_lines.append(_line(_HEADER_FONT if bold else _BODY_FONT, _FONT_SIZE, _MARGIN, y, text))
            y -= line_height
        content = ("\n".join(stream_lines) + "\n").encode("latin-1")
        objects.append(f"<< /Length {len(content)} >>".encode())
        objects.append(b"stream\n" + content + b"endstream")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects[1:], start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode()
        out += obj + b"\nendobj\n"

    xref_pos = len(out)
    out += f"xref\n0 {len(objects)}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)