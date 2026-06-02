"""Rule EJ02: Format Python expressions inside Jinja tags.

Uses Black (when available) to format the Python code inside ``{{ }}``
and ``{% %}`` tags for consistent style.
"""

from __future__ import annotations

from sqlfluff.core.parser.segments import SourceFix
from sqlfluff.core.rules import BaseRule, LintFix, LintResult, RuleContext
from sqlfluff.core.rules.crawlers import RootOnlyCrawler
from sqlfluff.core.templaters import JinjaTemplater


class Rule_EJ02(BaseRule):
    """Jinja tag content should be formatted with Black.

    Formats the Python expressions inside Jinja tags using Black for
    consistent style.  Handles macro definitions, reserved-word
    identifiers, and Jinja's tilde (``~``) operator.

    This rule requires the ``black`` package to be installed.  When
    Black is not available, the rule is silently skipped.

    **Anti-pattern**

    Inconsistently formatted Jinja expressions:

    .. code-block:: jinja
       :force:

        {{ config(materialized="incremental", unique_key="order_id",
                    partition_by={"field": "order_date", "data_type": "date"}) }}

    **Best practice**

    Formatted with consistent style:

    .. code-block:: jinja
       :force:

        {{
            config(
                materialized="incremental",
                unique_key="order_id",
                partition_by={"field": "order_date", "data_type": "date"},
            )
        }}
    """

    name = "extended_jinja.content_format"
    groups = ("all", "extended_jinja")
    crawl_behaviour = RootOnlyCrawler()
    targets_templated = True
    is_fix_compatible = True
    config_keywords = [
        "jinja_indent_size",
        "jinja_line_length",
        "jinja_black_enabled",
    ]

    def _eval(self, context: RuleContext) -> list[LintResult]:
        """Format Python inside every Jinja tag in the source."""
        # Import here to avoid circular / early-import issues.
        from sqlfluff_plugin_extended_jinja._black_wrapper import BlackWrapper
        from sqlfluff_plugin_extended_jinja._jinja_common import (
            JinjaTag,
            find_raw_at_src_idx,
            iter_jinja_tags,
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

        enabled = str(self.jinja_black_enabled).lower() not in (  # type: ignore[attr-defined]
            "false",
            "0",
            "no",
        )
        wrapper = BlackWrapper(enabled=enabled)
        if not wrapper.available:
            return []

        source = context.templated_file.source_str
        indent_size = int(self.jinja_indent_size)  # type: ignore[attr-defined]
        line_length = int(self.jinja_line_length)  # type: ignore[attr-defined]

        # Collect formattable tag spans (skip raws and comments).
        spans = [(s, e) for s, e, k in iter_jinja_tags(source) if k in ("stmt", "expr")]

        results: list[LintResult] = []
        for start, end in spans:
            tag_text = source[start:end]

            # Compute base indent from the whitespace prefix of the line.
            line_start = source.rfind("\n", 0, start) + 1
            prefix = source[line_start:start]
            base_indent = prefix[: len(prefix) - len(prefix.lstrip(" \t"))]

            tag = JinjaTag.from_text(tag_text)
            formatted = tag.format(wrapper, line_length, base_indent, indent_size)

            if formatted is None or formatted == tag_text:
                continue

            # Anchor the fix to a raw segment near this source position.
            raw_seg = find_raw_at_src_idx(context.segment, start)
            if raw_seg is None:
                continue
            if raw_seg.source_fixes:
                continue
            assert raw_seg.pos_marker is not None

            source_fixes = [
                SourceFix(
                    formatted,
                    slice(start, end),
                    raw_seg.pos_marker.templated_slice,
                )
            ]

            # Truncate tag text for the description.
            preview = tag_text.replace("\n", " ")
            if len(preview) > 60:
                preview = preview[:57] + "..."

            results.append(
                LintResult(
                    anchor=raw_seg,
                    description=(f"Jinja tag content should be formatted: {preview}"),
                    fixes=[
                        LintFix.replace(
                            raw_seg,
                            [raw_seg.edit(source_fixes=source_fixes)],
                        )
                    ],
                )
            )

        return results
