"""Thin wrapper around Black for formatting Python inside Jinja tags.

Adapted from sqlfmt (Copyright 2021 Ted Conbeer, Apache-2.0).
Original: https://github.com/tconbeer/sqlfmt/blob/main/src/sqlfmt/jinjafmt.py
"""

from __future__ import annotations

import keyword
import re
from importlib import import_module
from types import ModuleType


class BlackWrapper:
    """Format Python expressions with Black, plus Jinja-specific pre/post processing."""

    # Sentinel template for Python reserved words used as Jinja identifiers.
    _KW_SENTINEL = "__jfmt_kw_{}__"
    # Single compiled regex matching any Python keyword used as a function
    # call or kwarg name (followed by ``(`` or ``=``).
    _KW_RE = re.compile(r"\b(" + "|".join(keyword.kwlist) + r")(?=\s*[=(])")
    # Binary operators tried in order to stand in for Jinja's ``~``.
    _TILDE_OPS = ("+", "-", "*", "/", "%", "|", "&", "^", "@")

    def __init__(self, enabled: bool = True) -> None:
        if not enabled:
            self._black: ModuleType | None = None
            return
        try:
            self._black = import_module("black")
        except ImportError:
            self._black = None

    @property
    def available(self) -> bool:
        return self._black is not None

    def format_string(self, code: str, max_length: int = 88) -> str:
        """Format *code* with Black.  Returns the original on failure."""
        if not self._black or not code.strip():
            return code

        processed, kw_repls = self._replace_reserved(code)
        processed, tilde_repls = self._replace_tildes(processed)

        has_nl = "\n" in code
        mode = self._black.Mode(line_length=max_length)
        formatted = self._try_format(processed, mode)
        if formatted is None and has_nl:
            # Jinja allows linebreaks where Python doesn't — retry flat.
            formatted = self._try_format(processed.replace("\n", " "), mode)
        if formatted is None:
            return code

        # Reverse preprocessing substitutions.  On count mismatch the
        # reversal is unsafe — fall back to the original code.
        for word, n in kw_repls.items():
            sentinel = self._KW_SENTINEL.format(word)
            if formatted.count(sentinel) != n:
                return code
            formatted = formatted.replace(sentinel, word)
        for op, n in tilde_repls.items():
            if formatted.count(op) != n:
                return code
            formatted = formatted.replace(op, "~")
        return formatted

    def _try_format(self, code: str, mode: object) -> str | None:
        """Run Black; return formatted text or *None* on parse failure."""
        assert self._black is not None
        try:
            return self._black.format_str(code, mode=mode).rstrip()
        except (ValueError, SyntaxError):
            return None

    # -- pre / post processing ------------------------------------------------

    @classmethod
    def _replace_reserved(cls, code: str) -> tuple[str, dict[str, int]]:
        """Replace Python reserved words used as Jinja identifiers."""
        kw_repls: dict[str, int] = {}

        def _sub(m: re.Match) -> str:
            word = m.group(1)
            kw_repls[word] = kw_repls.get(word, 0) + 1
            return cls._KW_SENTINEL.format(word)

        processed = cls._KW_RE.sub(_sub, code)
        return processed, kw_repls

    @classmethod
    def _replace_tildes(cls, code: str) -> tuple[str, dict[str, int]]:
        """Replace Jinja ``~`` (concat) with a Python binary operator."""
        if "~" not in code:
            return code, {}
        for op in cls._TILDE_OPS:
            if op not in code:
                return code.replace("~", op), {op: code.count("~")}
        return code, {}
