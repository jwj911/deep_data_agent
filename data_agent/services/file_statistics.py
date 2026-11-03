"""Bounded, deterministic statistics over complete managed table bytes."""

import csv
import hashlib
import io
import json
import re
from decimal import Decimal, InvalidOperation, localcontext
from time import perf_counter

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 50_000
MAX_COLUMNS = 64
MAX_CELLS = 250_000
MAX_SECONDS = 5
ANALYSIS_VERSION = "column-sum-v1"
PARSER_VERSION = "strict-table-v1"
_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", re.ASCII)


class StatisticsError(ValueError):
    """A public error code without input data or filesystem details."""

    def __init__(self, code: str, status_code: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, str) and len(value) <= 128 and _NUMBER.fullmatch(value):
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise StatisticsError("analysis_numeric_range") from exc
    else:
        raise StatisticsError("analysis_non_numeric")
    if (
        not number.is_finite()
        or len(number.as_tuple().digits) > 38
        or number.adjusted() >= 38
        or number.as_tuple().exponent < -18
    ):
        raise StatisticsError("analysis_numeric_range")
    return number


def _decimal_text(number: Decimal) -> str:
    if not number:
        return "0"
    value = format(number, "f")
    return value.rstrip("0").rstrip(".") if "." in value else value


def _reject_constant(_value: str):
    raise StatisticsError("analysis_non_finite")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise StatisticsError("analysis_duplicate_key")
        result[key] = value
    return result


def _columns(names: list) -> list[str]:
    if not names or len(names) > MAX_COLUMNS:
        raise StatisticsError("analysis_table_limit", 413)
    if any(
        not isinstance(name, str)
        or not name.strip()
        or len(name) > 128
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
        for name in names
    ) or len(set(names)) != len(names):
        raise StatisticsError("analysis_invalid_columns")
    return names


def _table(text: str, media_type: str):
    if media_type == "text/csv":
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        names = _columns(next(reader, []))
        if any(name.lstrip().startswith(("=", "+", "-", "@")) for name in names):
            raise StatisticsError("unsafe_csv_formula", 400)
        return names, reader
    if media_type != "application/json":
        raise StatisticsError("analysis_unsupported_type")
    data = json.loads(
        text,
        parse_int=_decimal,
        parse_float=_decimal,
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_object,
    )
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise StatisticsError("analysis_invalid_table")
    if len(data) > MAX_ROWS:
        raise StatisticsError("analysis_table_limit", 413)
    names = _columns(sorted(data[0]))

    def rows():
        for row in data:
            if not isinstance(row, dict) or set(row) != set(names):
                raise StatisticsError("analysis_invalid_table")
            yield [row[name] for name in names]

    return names, rows()


def _kind(value: object) -> str:
    if value is None or value == "":
        return "missing"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, Decimal):
        return "number"
    if isinstance(value, str):
        try:
            _decimal(value)
            return "number"
        except StatisticsError:
            return "string"
    raise StatisticsError("analysis_invalid_table")


def canonical_json(value: dict) -> bytes:
    """Version 1 hash representation; the hash field itself is excluded."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def calculate_statistics(
    content: bytes, media_type: str, column: str,
) -> dict:
    """Calculate one column sum; no storage, identity, model or cache access."""
    started = perf_counter()

    def check_deadline():
        if perf_counter() - started > MAX_SECONDS:
            raise StatisticsError("analysis_timeout", 503)

    if len(content) > MAX_BYTES:
        raise StatisticsError("analysis_table_limit", 413)
    if not isinstance(column, str) or not column or len(column) > 128:
        raise StatisticsError("analysis_invalid_column")
    try:
        names, rows = _table(content.decode("utf-8-sig"), media_type)
        check_deadline()
        if column not in names:
            raise StatisticsError("analysis_column_not_found")
        selected = names.index(column)
        missing = [0] * len(names)
        kinds = [set() for _ in names]
        seen = set()
        row_count = duplicate_count = valid_count = 0
        total = Decimal(0)
        minimum = maximum = None
        # At most 38 integer + 18 fractional + 5 carry digits are needed.
        with localcontext() as context:
            context.prec = 80
            for row in rows:
                check_deadline()
                row_count += 1
                if row_count > MAX_ROWS or row_count * len(names) > MAX_CELLS:
                    raise StatisticsError("analysis_table_limit", 413)
                if len(row) != len(names):
                    raise StatisticsError("analysis_invalid_table")
                if media_type == "text/csv" and any(
                    cell.lstrip().startswith(("=", "+", "-", "@")) for cell in row
                ):
                    raise StatisticsError("unsafe_csv_formula", 400)
                for index, value in enumerate(row):
                    kind = _kind(value)
                    if kind == "missing":
                        missing[index] += 1
                    else:
                        kinds[index].add(kind)
                # Preserve scalar types; JSON 1 and true must not compare equal.
                key = tuple((type(value), value) for value in row)
                duplicate_count += key in seen
                seen.add(key)
                if row[selected] is None or row[selected] == "":
                    continue
                value = _decimal(row[selected])
                total += value
                valid_count += 1
                minimum = value if minimum is None else min(minimum, value)
                maximum = value if maximum is None else max(maximum, value)
        check_deadline()
    except (UnicodeError, csv.Error, json.JSONDecodeError, RecursionError) as exc:
        raise StatisticsError("analysis_invalid_table") from exc
    if not row_count:
        raise StatisticsError("analysis_invalid_table")
    if not valid_count:
        raise StatisticsError("analysis_no_numeric_values")
    warnings = ["unit_unspecified"]
    if missing[selected]:
        warnings.append("missing_values_excluded")
    if duplicate_count:
        warnings.append("duplicate_rows_included")
    value = _decimal_text(total)
    return {
        "analysis_version": ANALYSIS_VERSION,
        "parser_version": PARSER_VERSION,
        "parameters": {"metric": "sum", "column": column},
        "row_count": row_count,
        "columns": [
            {"name": name, "types": sorted(kinds[index]), "missing_count": missing[index]}
            for index, name in enumerate(names)
        ],
        "duplicate_row_count": duplicate_count,
        "result": {
            "value": value,
            "unit": "unspecified",
            "valid_count": valid_count,
            "missing_count": missing[selected],
            "minimum": _decimal_text(minimum),
            "maximum": _decimal_text(maximum),
        },
        "warnings": warnings,
        "summary": (
            f"完整文件共 {row_count} 行；列「{column}」的 {valid_count} 个有效数值"
            f"之和为 {value}，缺失 {missing[selected]} 行；"
            f"重复行 {duplicate_count} 行，保留参与计算；单位未指定。"
        ),
    }


def attach_source(result: dict, *, file_id: str, sha256: str, size_bytes: int) -> dict:
    """Bind the canonical values to the exact verified source bytes."""
    payload = {
        **result,
        "source": {
            "file_id": file_id,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "semantics": "current_file_at_read",
        },
    }
    payload["result_sha256"] = hashlib.sha256(canonical_json(payload)).hexdigest()
    return payload
