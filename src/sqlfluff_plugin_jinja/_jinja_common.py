"""Shared Jinja tag scanning, parsing, and formatting utilities.

Extracted from ``scripts/format_jinja_blocks.py`` for reuse across
SQLFluff plugin rules.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator

from sqlfluff.core.parser.segments import BaseSegment

if TYPE_CHECKING:
    from sqlfluff_plugin_jinja._black_wrapper import BlackWrapper

# ---------------------------------------------------------------------------
# Keyword tables
# ---------------------------------------------------------------------------

# Mapping of Jinja keyword -> role for block-splitting.
#   open   - opens a new block (increases indent depth)
#   mid    - continues a block at the same depth (else/elif)
#   close  - closes a block (decreases indent depth)
#   inline - single statement, no depth change (do, inline set)
KEYWORD_ROLES: dict[str, str] = {
    # openers
    "if": "open",
    "for": "open",
    "macro": "open",
    "test": "open",
    "materialization": "open",
    "snapshot": "open",
    "call": "open",
    "filter": "open",
    "block": "open",
    "with": "open",
    "autoescape": "open",
    # mid
    "else": "mid",
    "elif": "mid",
    # closers
    "endif": "close",
    "endfor": "close",
    "endmacro": "close",
    "endtest": "close",
    "endmaterialization": "close",
    "endsnapshot": "close",
    "endcall": "close",
    "endfilter": "close",
    "endblock": "close",
    "endset": "close",
    "endwith": "close",
    "endautoescape": "close",
    # inline
    "do": "inline",
    "set": "inline",
}

# Verbs whose dbt-Jinja definitions cannot carry trailing commas.
MACRO_VERBS = frozenset({"macro", "test", "materialization", "call"})

# Extracts the leading verb from a statement tag's inner code.
VERB_RE = re.compile(
    r"\s*(" + "|".join(sorted(KEYWORD_ROLES, key=len, reverse=True)) + r")\b",
)
_RAW_END_RE = re.compile(r"\{%[-+]?\s*endraw\s*[-+]?%\}")


# ---------------------------------------------------------------------------
# Unified tag scanner
# ---------------------------------------------------------------------------


def iter_jinja_tags(source: str) -> Iterator[tuple[int, int, str]]:
    """Yield ``(start, end, kind)`` for every Jinja construct in *source*.

    *kind* is one of:

    - ``"stmt"``    - statement tag ``{% ... %}``
    - ``"expr"``    - expression tag ``{{ ... }}``
    - ``"comment"`` - Jinja comment ``{# ... #}``
    - ``"raw"``     - a full ``{% raw %}...{% endraw %}`` block

    The scanner is quote-aware: closers occurring inside Python string
    literals (including triple-quoted strings) are correctly skipped.
    """
    i = 0
    n = len(source)
    while i < n - 1:
        if source[i] != "{":
            i += 1
            continue
        nxt = source[i + 1]
        # Comments
        if nxt == "#":
            end = source.find("#}", i + 2)
            stop = end + 2 if end != -1 else n
            yield (i, stop, "comment")
            i = stop
            continue
        if nxt not in ("{", "%"):
            i += 1
            continue
        # Statement / expression tag — scan for closing marker, skipping
        # closers inside Python string literals (single or triple-quoted).
        close = "}}" if nxt == "{" else "%}"
        j = i + 2
        quote: str | None = None
        triple = False
        while j < n - 1:
            ch = source[j]
            if quote:
                if ch == "\\":
                    j += 2
                    continue
                if triple:
                    if source[j : j + 3] == quote * 3:
                        quote = None
                        triple = False
                        j += 3
                        continue
                elif ch == quote:
                    quote = None
            elif ch in ('"', "'"):
                if j + 2 < n and source[j + 1] == ch and source[j + 2] == ch:
                    quote = ch
                    triple = True
                    j += 3
                    continue
                quote = ch
            elif source[j : j + 2] == close:
                end = j + 2
                if nxt == "%":
                    inner = source[i + 2 : j].strip().lstrip("-+").strip()
                    head = inner.split(None, 1)[0] if inner else ""
                    if head == "raw":
                        m = _RAW_END_RE.search(source, end)
                        if m:
                            yield (i, m.end(), "raw")
                            i = m.end()
                            break
                yield (i, end, "expr" if nxt == "{" else "stmt")
                i = end
                break
            j += 1
        else:
            # Unterminated tag — stop scanning.
            return


# ---------------------------------------------------------------------------
# JinjaTag dataclass
# ---------------------------------------------------------------------------


@dataclass
class JinjaTag:
    """Parsed Jinja tag: ``{opener}{verb}{code}{closer}``.

    *verb* is empty for expression tags (``{{ }}``) and for statement tags
    whose first token is not a recognised keyword.
    """

    opener: str
    verb: str
    code: str
    closer: str

    @classmethod
    def from_text(cls, text: str) -> "JinjaTag":
        op_len = 3 if len(text) > 2 and text[2] in "-+" else 2
        cl_len = 3 if len(text) > 2 and text[-3] in "-+" else 2
        opener = text[:op_len]
        closer = text[-cl_len:]
        inner = text[op_len:-cl_len]
        verb = ""
        code = inner.strip()
        if text[1] == "%":
            m = VERB_RE.match(inner)
            if m:
                verb = m.group(1).lower()
                code = inner[m.end() :].strip()
        return cls(opener, verb, code, closer)

    @property
    def is_macro_def(self) -> bool:
        return self.verb in MACRO_VERBS

    @property
    def role(self) -> str | None:
        """Block-splitting role, or ``None`` for non-block tags."""
        if not self.verb:
            return None
        # Block-form set ({% set x %}...{% endset %}) acts as an opener;
        # inline set ({% set x = v %}) keeps its declared "inline" role.
        if self.verb == "set" and "=" not in self.code:
            return "open"
        return KEYWORD_ROLES.get(self.verb)

    def render_single_line(self) -> str:
        if self.verb and self.code:
            return f"{self.opener} {self.verb} {self.code} {self.closer}"
        if self.verb:
            return f"{self.opener} {self.verb} {self.closer}"
        return f"{self.opener} {self.code} {self.closer}"

    def render_multiline(
        self,
        base_indent: str,
        indent_size: int,
        no_indent_lines: frozenset[int],
    ) -> str:
        """Render a multi-line ``code`` body with proper indentation."""
        pad = " " * indent_size
        lines = self.code.splitlines()
        head = f"{self.opener} {self.verb} {lines[0]}" if self.verb else self.opener
        body_start = 1 if self.verb else 0
        body: list[str] = []
        for i, ln in enumerate(lines[body_start:], start=body_start):
            if not ln.strip():
                body.append("")
            elif i in no_indent_lines:
                body.append(ln)
            else:
                body.append(f"{base_indent}{pad}{ln}")
        if self.verb:
            if not body:
                return self.render_single_line()
            tail = f"{base_indent}{body.pop().lstrip()} {self.closer}"
        else:
            tail = f"{base_indent}{self.closer}"
        return "\n".join([head, *body, tail])

    def format(
        self,
        wrapper: "BlackWrapper",
        max_line_length: int,
        base_indent: str,
        indent_size: int,
    ) -> str | None:
        """Return formatted tag text, or ``None`` if nothing should change.

        .. note:: Mutates ``self.code`` as a side effect.  Each ``JinjaTag``
           instance should only be formatted once.
        """
        if not self.code:
            return None

        original_code = self.code
        # Remove only the outer call trailing comma in macro-like defs so
        # Black's "magic trailing comma" doesn't force an unwanted split.
        code = (
            _strip_outer_call_trailing_comma(original_code)
            if self.is_macro_def
            else original_code
        )

        # Width budget: tighter of single-line and multi-line overheads.
        single_overhead = len(self.opener) + len(self.closer) + 2
        if self.verb:
            single_overhead += len(self.verb) + 1
        multi_overhead = indent_size
        max_code = (
            max_line_length - len(base_indent) - max(single_overhead, multi_overhead)
        )

        formatted = wrapper.format_string(code, max_code)

        if self.is_macro_def:
            formatted = _strip_outer_call_trailing_comma(formatted)

        # Black turns "" / '' into triple-quoted strings, which break Jinja.
        if ('"""' in formatted and '"""' not in original_code) or (
            "'''" in formatted and "'''" not in original_code
        ):
            return None
        if formatted == original_code:
            return None

        self.code = formatted
        if "\n" not in formatted:
            return self.render_single_line()
        return self.render_multiline(
            base_indent,
            indent_size,
            _triple_quoted_string_lines(formatted),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _triple_quoted_string_lines(code: str) -> frozenset[int]:
    """1-indexed lines inside multi-line triple-quoted strings."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return frozenset()
    raw_lines = code.splitlines()
    out: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.end_lineno is not None
            and node.end_lineno > node.lineno
            and "\n" in node.value
            and node.lineno - 1 < len(raw_lines)
            and node.end_lineno - 1 < len(raw_lines)
            and (
                '"""' in raw_lines[node.lineno - 1]
                or "'''" in raw_lines[node.lineno - 1]
            )
            and (
                '"""' in raw_lines[node.end_lineno - 1]
                or "'''" in raw_lines[node.end_lineno - 1]
            )
        ):
            out.update(range(node.lineno, node.end_lineno))
    return frozenset(out)


def _strip_outer_call_trailing_comma(code: str) -> str:
    """Remove a trailing comma from the outermost call only."""
    end = len(code) - len(code.rstrip())
    close_idx = len(code) - end - 1
    if close_idx < 0 or code[close_idx] != ")":
        return code

    depth = 0
    quote: str | None = None
    triple = False
    escape = False
    matching_open_idx: int | None = None

    for i in range(close_idx, -1, -1):
        ch = code[i]
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif triple and i >= 2 and code[i - 2 : i + 1] == quote * 3:
                quote = None
                triple = False
            elif not triple and ch == quote:
                quote = None
            continue
        if ch in ('"', "'"):
            if i >= 2 and code[i - 2 : i + 1] == ch * 3:
                quote = ch
                triple = True
            else:
                quote = ch
            continue
        if ch in ")]}":
            depth += 1
        elif ch in "([{":
            depth -= 1
            if depth == 0 and ch == "(":
                matching_open_idx = i
                break

    if matching_open_idx is None:
        return code

    comma_idx = close_idx - 1
    while comma_idx > matching_open_idx and code[comma_idx].isspace():
        comma_idx -= 1
    if comma_idx <= matching_open_idx or code[comma_idx] != ",":
        return code
    return code[:comma_idx] + code[comma_idx + 1 :]


def find_raw_at_src_idx(
    segment: BaseSegment, src_idx: int
) -> BaseSegment | None:
    """Recursively search to find a raw segment for a position in the source.

    Returns ``None`` if no matching segment is found.

    Based on the same utility in SQLFluff's JJ01 rule.
    """
    if not segment.segments:
        return None
    for seg in segment.segments:
        if not seg.pos_marker:
            continue
        src_slice = seg.pos_marker.source_slice
        # If it's before, skip onward.
        if src_slice.stop <= src_idx:
            continue
        # Is the current segment raw?
        if seg.is_raw():
            return seg
        # Otherwise recurse
        return find_raw_at_src_idx(seg, src_idx)
    return None
