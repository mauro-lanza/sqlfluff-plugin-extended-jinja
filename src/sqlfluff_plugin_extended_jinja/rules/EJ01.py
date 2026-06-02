"""Rule EJ01: Jinja block tags must be on their own lines.

Ensures that block-level Jinja tags (``if``, ``for``, ``else``, ``endif``,
etc.) do not share a line with SQL content or other tags.

Fixes are applied per-boundary so that each ``SourceFix`` stays within a
single template block (literal text), avoiding the "spans multiple template
blocks" rejection.
"""

from __future__ import annotations

from sqlfluff.core.parser.segments import SourceFix
from sqlfluff.core.rules import BaseRule, LintFix, LintResult, RuleContext
from sqlfluff.core.rules.crawlers import RootOnlyCrawler
from sqlfluff.core.templaters import JinjaTemplater


class Rule_EJ01(BaseRule):
    """Jinja block tags must be on their own lines.

    Block-level Jinja tags (``if``, ``for``, ``else``, ``endif``, etc.)
    should not share a line with SQL content or other tags.

    **Anti-pattern**

    Block tags sharing a line with SQL content:

    .. code-block:: jinja
       :force:

        SELECT * FROM foo WHERE 1=1 {% if true %} AND x > 1 {% endif %}

    **Best practice**

    Each block tag on its own line:

    .. code-block:: jinja
       :force:

        SELECT * FROM foo WHERE 1=1
        {% if true %}
          AND x > 1
        {% endif %}
    """

    name = "extended_jinja.block_solo_line"
    groups = ("all", "extended_jinja")
    crawl_behaviour = RootOnlyCrawler()
    targets_templated = True
    is_fix_compatible = True
    config_keywords = ["jinja_indent_size"]

    def _eval(self, context: RuleContext) -> list[LintResult]:
        """Find block tags that share a line with other content."""
        from sqlfluff_plugin_extended_jinja._jinja_common import (
            JinjaTag,
            find_raw_at_src_idx,
        )

        # Guard: no templated code at all.
        assert context.segment.pos_marker
        if context.segment.pos_marker.is_literal():
            return []
        if not context.templated_file:
            return []

        # Only active for Jinja-family templaters (jinja, dbt).
        _templater_class = context.config.get_templater_class()
        if not issubclass(_templater_class, JinjaTemplater):
            return []

        source = context.templated_file.source_str
        indent_size = int(self.jinja_indent_size)  # type: ignore[attr-defined]
        raw_sliced = context.templated_file.raw_sliced

        # ----------------------------------------------------------------
        # Build a list of (raw_slice, tag, role) for every block tag, plus
        # the line-level context we need to decide whether a fix is needed.
        # ----------------------------------------------------------------
        block_types = ("block_start", "block_end", "block_mid")

        results: list[LintResult] = []

        for rs in raw_sliced:
            if rs.slice_type not in block_types:
                continue

            tag_text = rs.raw.strip()
            if not tag_text:
                continue

            tag = JinjaTag.from_text(tag_text)
            if tag.role not in ("open", "mid", "close"):
                continue

            tag_src_start = rs.source_idx
            tag_src_end = rs.source_idx + len(rs.raw)

            # --- What is on the SAME LINE before this tag? ---------------
            line_start = source.rfind("\n", 0, tag_src_start) + 1
            before_tag = source[line_start:tag_src_start]
            base_indent = before_tag[: len(before_tag) - len(before_tag.lstrip())]

            has_content_before = bool(before_tag.strip())

            # --- What is on the SAME LINE after this tag? ----------------
            line_end_pos = source.find("\n", tag_src_end)
            if line_end_pos == -1:
                line_end_pos = len(source)
            after_tag = source[tag_src_end:line_end_pos]
            has_content_after = bool(after_tag.strip())

            if not has_content_before and not has_content_after:
                # Tag is already alone on its line — nothing to do.
                continue

            # --- FIX 1: newline BEFORE the block tag ---------------------
            if has_content_before:
                # We modify only the literal whitespace gap between the last
                # non-whitespace character and the tag opening.
                content_end = line_start + len(before_tag.rstrip())
                ws_start = content_end
                ws_end = tag_src_start

                replacement = "\n" + base_indent

                raw_seg = find_raw_at_src_idx(context.segment, ws_start)
                if raw_seg is not None and not raw_seg.source_fixes:
                    assert raw_seg.pos_marker is not None
                    source_fixes = [
                        SourceFix(
                            replacement,
                            slice(ws_start, ws_end),
                            raw_seg.pos_marker.templated_slice,
                        )
                    ]
                    results.append(
                        LintResult(
                            anchor=raw_seg,
                            description=(f"Jinja block tag '{tag.verb}' should start on its own line."),
                            fixes=[
                                LintFix.replace(
                                    raw_seg,
                                    [raw_seg.edit(source_fixes=source_fixes)],
                                )
                            ],
                        )
                    )

            # --- FIX 2: newline AFTER the block tag ----------------------
            if has_content_after:
                # Determine indent level for the content after the tag.
                after_indent = base_indent
                if tag.role in ("open", "mid"):
                    after_indent = base_indent + " " * indent_size

                # Find the next non-whitespace character after the tag.
                after_stripped = after_tag.lstrip()
                ws_chars = len(after_tag) - len(after_stripped)
                ws_start_after = tag_src_end
                ws_end_after = tag_src_end + ws_chars

                replacement = "\n" + after_indent

                raw_seg = find_raw_at_src_idx(context.segment, ws_start_after)
                if raw_seg is not None and not raw_seg.source_fixes:
                    assert raw_seg.pos_marker is not None
                    source_fixes = [
                        SourceFix(
                            replacement,
                            slice(ws_start_after, ws_end_after),
                            raw_seg.pos_marker.templated_slice,
                        )
                    ]
                    results.append(
                        LintResult(
                            anchor=raw_seg,
                            description=(f"Content after Jinja block tag '{tag.verb}' should start on a new line."),
                            fixes=[
                                LintFix.replace(
                                    raw_seg,
                                    [raw_seg.edit(source_fixes=source_fixes)],
                                )
                            ],
                        )
                    )

        return results
