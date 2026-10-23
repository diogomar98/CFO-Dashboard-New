"""Decode Genie SQL result rows across Databricks SDK / API response versions.

Real Data only. Nothing here queries or modifies Synthetic Genie, or executes
SQL on its own. The caller supplies the governed Genie query attachment result.
"""
from __future__ import annotations

import pandas as pd


def _field(obj, *names):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return next((obj[k] for k in names if obj.get(k) is not None), None)
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    if hasattr(obj, "as_dict"):
        try:
            data = obj.as_dict()
            if isinstance(data, dict):
                return next((data[k] for k in names if data.get(k) is not None), None)
        except (AttributeError, TypeError, ValueError):
            pass
    return None


def _typed_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if _field(value, "is_null", "isNull") is True:
        return None
    for kind in (
        "str", "string", "long", "int", "short", "double", "float",
        "decimal", "bool", "boolean", "binary", "value",
    ):
        item = _field(value, kind)
        if item is not None:
            return item
    # An empty typed value represents SQL NULL, but a nonempty unknown value
    # must not silently become NULL (that would hide data loss).
    if isinstance(value, dict):
        if not value or set(value) <= {"is_null", "isNull"}:
            return None
    else:
        try:
            if not {k: v for k, v in vars(value).items() if v is not None}:
                return None
        except TypeError:
            pass
    raise ValueError("Unsupported SQL typed-value shape")


def decode_genie_rows(response, *, max_rows=50):
    """Return (DataFrame, status) without making up missing observations."""
    statement = _field(response, "statement_response", "statementResponse")
    if statement is None:
        return pd.DataFrame(), "missing_statement_response"
    result = _field(statement, "result")
    if result is None:
        return pd.DataFrame(), "missing_result_payload"
    manifest = _field(statement, "manifest")
    schema = _field(manifest, "schema")
    columns = _field(schema, "columns") or []
    names = [
        str(_field(column, "name") or f"col_{idx}")
        for idx, column in enumerate(columns)
    ]
    column_types = [
        str(_field(column, "type_name", "typeName") or "").upper()
        for column in columns
    ]
    raw_rows = _field(result, "data_array", "dataArray")
    typed_rows = _field(result, "data_typed_array", "dataTypedArray")
    rows = None
    try:
        if raw_rows:
            rows = list(raw_rows)
        elif typed_rows:
            rows = []
            for typed in typed_rows:
                values = _field(typed, "values")
                if not isinstance(values, (list, tuple)):
                    return pd.DataFrame(), "typed_row_missing_values"
                rows.append([_typed_value(value) for value in values])
    except (ValueError, TypeError):
        return pd.DataFrame(), "typed_result_parse_failed"
    if rows:
        if names and any(len(row) != len(names) for row in rows):
            return pd.DataFrame(), "result_column_count_mismatch"
        frame = pd.DataFrame(rows[:max_rows], columns=names or None)
        for idx, kind in enumerate(column_types[:len(frame.columns)]):
            if kind.startswith((
                "INT", "LONG", "SHORT", "BYTE", "BIGINT", "SMALLINT",
                "TINYINT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC",
            )):
                try:
                    converted = pd.to_numeric(frame.iloc[:, idx], errors="raise")
                    frame[frame.columns[idx]] = converted
                except (ValueError, TypeError):
                    # Preserve the exact source string rather than lose a value.
                    pass
        return frame, "rows_retrieved"
    count = _field(manifest, "total_row_count", "totalRowCount")
    if count is None:
        count = _field(result, "row_count", "rowCount")
    try:
        if count is not None and int(count) == 0:
            return pd.DataFrame(), "zero_query_rows"
    except (ValueError, TypeError):
        pass
    if _field(result, "external_links", "externalLinks"):
        return pd.DataFrame(), "external_links_only"
    if raw_rows is not None or typed_rows is not None:
        return pd.DataFrame(), "inline_rows_empty"
    return pd.DataFrame(), "unknown_result_format"
