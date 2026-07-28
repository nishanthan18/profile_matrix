"""Extract plain text from an uploaded resume file (PDF, DOCX or TXT)."""

import io
import re
import docx2txt
import pdfplumber

# A run of 4+ short (1-3 letter) tokens separated by whitespace is almost
# always a stylised, letter-spaced heading or name (e.g. "S K I L L S",
# "A J I T H K U M A R") rather than real prose -- collapse it back together.
# Layout-preserving extraction uses proportional (variable-width) gaps, so we
# allow one-or-more whitespace between tokens, not just a single space.
_LETTER_SPACED_RUN_RE = re.compile(r"(?<![\w])(?:[A-Za-z]{1,3}[ \t]+){3,}[A-Za-z]{1,3}(?![\w])")


def _collapse_letter_spacing(text: str) -> str:
    def _collapse(m):
        return re.sub(r"\s+", "", m.group(0))
    return _LETTER_SPACED_RUN_RE.sub(_collapse, text)


def extract_text(uploaded_file) -> str:
    """
    uploaded_file: a Streamlit UploadedFile (has .name and behaves like a file object)
    Returns extracted plain text, preserving line breaks as much as possible.
    """
    name = uploaded_file.name.lower()
    raw_bytes = uploaded_file.read()
    uploaded_file.seek(0)

    if name.endswith(".pdf"):
        text = _extract_pdf(raw_bytes)
    elif name.endswith(".docx"):
        text = _extract_docx(raw_bytes)
    elif name.endswith(".txt"):
        text = raw_bytes.decode("utf-8", errors="ignore")
    else:
        raise ValueError(f"Unsupported file type: {uploaded_file.name}. "
                          f"Please upload a .pdf, .docx or .txt resume.")

    return _collapse_letter_spacing(text)


def _extract_pdf(raw_bytes: bytes) -> str:
    """
    Uses layout-preserving extraction, then -- for pages that are laid out in
    two columns (common in designed/creative resume templates) -- splits each
    physical line on its large internal whitespace gap and reassembles the
    left-column text as one coherent block followed by the right-column text,
    instead of leaving the two interleaved line-by-line (which otherwise makes
    unrelated content, e.g. a skills list and a profile paragraph, look like
    one jumbled block).

    Also pulls out embedded PDF hyperlink annotations (e.g. a "LinkedIn: View
    Profile" line where the actual URL is only present as a clickable link,
    not as visible text) and appends them so downstream regex-based contact
    extraction can still find them.
    """
    text_parts = []
    hyperlink_uris = []
    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        for page in pdf.pages:
            layout_text = page.extract_text(layout=True) or ""
            layout_text = _collapse_letter_spacing(layout_text)
            text_parts.append(_split_columns(layout_text))
            try:
                for link in page.hyperlinks:
                    uri = link.get("uri")
                    if uri and not uri.lower().startswith("mailto:"):
                        hyperlink_uris.append(uri)
            except Exception:
                pass

    full_text = "\n".join(text_parts)
    if hyperlink_uris:
        full_text += "\n\n" + "\n".join(sorted(set(hyperlink_uris)))
    return full_text


_LABEL_LEFT_TEXT_RE = re.compile(
    r"^(project(?:\s*title)?[\s\-\d]*|year|role|client|technolog(?:y|ies)|"
    r"techniques?|library\s*used|environment|description|responsibilities|"
    r"duration|team\s*size|language|microcontroller|robots?|"
    r"operating\s*platform|organization|designation)\s*:?\s*$",
    re.IGNORECASE,
)


_GAP_LINE_RE = re.compile(r"^(\s*)(\S.*?)( {4,})(\S.*)$")


def _split_columns(layout_text: str) -> str:
    """
    Only reorganises CONTIGUOUS, DENSE runs of gap-lines into separate
    left/right column blocks. A genuine two-column template produces a long,
    dense run spanning most of a page. A single-column resume that merely
    contains a short embedded table (e.g. "Organization | Designation |
    Duration", or a contact banner like "Naveen    Subramaniam") also matches
    the same per-line gap pattern, but only for a handful of lines -- those
    are left completely untouched so company names stay attached to their
    own dates, etc.
    """
    raw_lines = layout_text.split("\n")
    n = len(raw_lines)
    is_gap = [bool(_GAP_LINE_RE.match(line)) for line in raw_lines]

    # A single-column "Label : value" list (Role:, Client:, Year:, ...) can
    # also read as a dense run -- exclude those lines from run detection.
    def _is_label_line(line):
        m = _GAP_LINE_RE.match(line)
        return bool(m) and bool(_LABEL_LEFT_TEXT_RE.match(m.group(2).strip()))

    is_gap = [g and not _is_label_line(raw_lines[i]) for i, g in enumerate(is_gap)]

    runs = []
    i = 0
    while i < n:
        if is_gap[i]:
            j, last_gap, miss_streak = i, i, 0
            while j < n:
                if is_gap[j]:
                    last_gap = j
                    miss_streak = 0
                else:
                    miss_streak += 1
                    if miss_streak > 2:
                        break
                j += 1
            run_end = last_gap + 1
            run_len = run_end - i
            gap_count = sum(is_gap[i:run_end])
            if run_len >= 8 and gap_count >= 6 and (gap_count / run_len) >= 0.45:
                runs.append((i, run_end))
                i = run_end
                continue
        i += 1

    if not runs:
        return layout_text

    result_parts = []
    cursor = 0
    for start, end in runs:
        if cursor < start:
            result_parts.append("\n".join(raw_lines[cursor:start]))

        run_lines = raw_lines[start:end]
        indents = []
        for line in run_lines:
            m = _GAP_LINE_RE.match(line)
            if m:
                leading, left_text, gap, right_text = m.groups()
                indents.append(len(leading) + len(left_text) + len(gap))
        threshold = (min(indents) - 2) if indents else 0

        left_col, right_col = [], []
        for line in run_lines:
            if not line.strip():
                continue
            m = _GAP_LINE_RE.match(line)
            if m:
                leading, left_text, gap, right_text = m.groups()
                left_col.append(left_text.strip())
                right_col.append(right_text.strip())
            else:
                leading_spaces = len(line) - len(line.lstrip(" "))
                if leading_spaces >= threshold:
                    right_col.append(line.strip())
                else:
                    left_col.append(line.strip())

        result_parts.append("\n".join(left_col) + "\n\n" + "\n".join(right_col))
        cursor = end

    if cursor < n:
        result_parts.append("\n".join(raw_lines[cursor:]))

    return "\n\n".join(result_parts)


def _extract_docx(raw_bytes: bytes) -> str:
    with io.BytesIO(raw_bytes) as buf:
        # docx2txt needs a path or file-like object saved to disk; use a temp file
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(buf.read())
            tmp_path = tmp.name
    try:
        text = docx2txt.process(tmp_path) or ""
        hyperlinks = _extract_docx_hyperlinks(tmp_path)
        if hyperlinks:
            text += "\n\n" + "\n".join(sorted(set(hyperlinks)))
    finally:
        import os
        os.remove(tmp_path)
    return text


def _extract_docx_hyperlinks(path: str):
    """Reads hyperlink relationship targets that docx2txt silently drops
    (e.g. 'LinkedIn' text linked to a URL, with no visible URL in the text)."""
    try:
        from docx import Document
        doc = Document(path)
        uris = []
        for rel in doc.part.rels.values():
            if "hyperlink" in rel.reltype and rel.target_ref.startswith("http"):
                uris.append(rel.target_ref)
        return uris
    except Exception:
        return []