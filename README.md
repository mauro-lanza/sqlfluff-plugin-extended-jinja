# sqlfluff-plugin-extended-jinja

SQLFluff plugin that adds extended Jinja formatting rules. Ensures block-level tags are isolated on their own lines and formats Python expressions inside Jinja tags using Black.

Uses the `EJ` (Extended Jinja) prefix to avoid conflicts with SQLFluff's built-in `JJ` rules.

| Code | Name | Description |
|------|------|-------------|
| EJ01 | `extended_jinja.block_solo_line` | Block tags (`if`, `for`, `else`, `endif`, ...) must be on their own lines |
| EJ02 | `extended_jinja.content_format` | Format Python expressions inside Jinja tags with Black |

## Installation

```bash
pip install sqlfluff-plugin-extended-jinja
```

For Black-based formatting (EJ02):

```bash
pip install "sqlfluff-plugin-extended-jinja[jinjafmt]"
```

## Usage

Once installed, the rules are automatically available to SQLFluff:

```bash
# Lint
sqlfluff lint my_model.sql --rules EJ01,EJ02

# Fix
sqlfluff fix my_model.sql --rules EJ01,EJ02
```

## Configuration

Add to your `.sqlfluff` config file:

```ini
[sqlfluff:rules:extended_jinja.block_solo_line]
# Spaces per indent level for content inside block tags
jinja_indent_size = 2

[sqlfluff:rules:extended_jinja.content_format]
# Spaces per indent level inside formatted Jinja tags
jinja_indent_size = 2
# Max line length for Jinja content formatting
jinja_line_length = 120
# Enable/disable Black formatting
jinja_black_enabled = True
```

## Rules

### EJ01 — `extended_jinja.block_solo_line`

Block-level Jinja tags (`if`, `for`, `else`, `elif`, `endif`, `endfor`, `macro`, `endmacro`, etc.) must not share a line with SQL content or other tags.

**Anti-pattern:**

```sql
SELECT * FROM foo WHERE 1=1 {% if true %} AND x > 1 {% endif %}
```

**Best practice:**

```sql
SELECT * FROM foo WHERE 1=1
{% if true %}
  AND x > 1
{% endif %}
```

### EJ02 — `extended_jinja.content_format`

Python expressions inside `{{ }}` and `{% %}` tags are formatted with Black for consistent style. Handles macro definitions, reserved-word identifiers (e.g. `return()`), and Jinja's tilde (`~`) concatenation operator.

Requires the `black` package. When Black is unavailable, the rule is silently skipped.

**Anti-pattern:**

```sql
{{ config(materialized="incremental", unique_key="order_id",
            partition_by={"field": "order_date", "data_type": "date"}) }}
```

**Best practice:**

```sql
{{
    config(
        materialized="incremental",
        unique_key="order_id",
        partition_by={"field": "order_date", "data_type": "date"},
    )
}}
```

## Pre-commit

```yaml
- repo: https://github.com/sqlfluff/sqlfluff
  rev: 4.2.1
  hooks:
    - id: sqlfluff-fix
      additional_dependencies:
        - sqlfluff-plugin-extended-jinja[jinjafmt]
```

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## Attribution

The Black formatting wrapper is adapted from [sqlfmt](https://github.com/tconbeer/sqlfmt) (Copyright 2021 Ted Conbeer, Apache-2.0).

## License

Apache-2.0
