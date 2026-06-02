"""SQLFluff plugin — Extended Jinja formatting rules.

Rules:
    EJ01  Jinja block tags must be on their own lines.
    EJ02  Format Python expressions inside Jinja tags (requires Black).
"""

from __future__ import annotations

from typing import Any

from sqlfluff.core.config import load_config_resource
from sqlfluff.core.plugin import hookimpl
from sqlfluff.core.rules import BaseRule, ConfigInfo


@hookimpl
def get_rules() -> list[type[BaseRule]]:
    """Get plugin rules.

    Rules are imported lazily so that all ``get_configs_info()`` hooks
    have already run before the ``BaseRule`` metaclass validates config.
    """
    from sqlfluff_plugin_extended_jinja.rules.EJ01 import Rule_EJ01
    from sqlfluff_plugin_extended_jinja.rules.EJ02 import Rule_EJ02

    return [Rule_EJ01, Rule_EJ02]


@hookimpl
def load_default_config() -> dict[str, Any]:
    """Load the default configuration for the plugin."""
    return load_config_resource(
        package="sqlfluff_plugin_extended_jinja",
        file_name="plugin_default_config.cfg",
    )


@hookimpl
def get_configs_info() -> dict[str, ConfigInfo]:
    """Get rule config validations and descriptions."""
    return {
        "jinja_indent_size": {
            "definition": "Spaces per indent level inside Jinja blocks (default: 2)",
        },
        "jinja_line_length": {
            "definition": "Max line length for Jinja content formatting (default: 120)",
        },
        "jinja_black_enabled": {
            "definition": "Enable Black-based formatting of Jinja tag content (default: True)",
        },
    }
