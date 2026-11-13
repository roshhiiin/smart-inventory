import csv
import io
import re

from flask import Response, request

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def validate(data, rules):
    """Validate a JSON object against simple per-field rules; returns cleaned values.

    Rule keys: type (str|int|float|bool), required, default, min, max,
    min_len, max_len, choices, email.
    """
    if not isinstance(data, dict):
        raise ApiError(400, "bad_request", "Request body must be a JSON object")
    clean, errors = {}, {}
    for name, rule in rules.items():
        value = data.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            if rule.get("required"):
                errors[name] = "This field is required"
            else:
                clean[name] = rule.get("default")
            continue
        kind = rule.get("type", str)
        if kind is str:
            if not isinstance(value, str):
                errors[name] = "Must be text"
                continue
            value = value.strip()
            if len(value) < rule.get("min_len", 0):
                errors[name] = f"Must be at least {rule['min_len']} characters"
            elif len(value) > rule.get("max_len", 10_000):
                errors[name] = f"Must be at most {rule['max_len']} characters"
            elif rule.get("email") and not EMAIL_RE.match(value):
                errors[name] = "Must be a valid email address"
            elif "choices" in rule and value not in rule["choices"]:
                errors[name] = "Must be one of: " + ", ".join(rule["choices"])
        elif kind is bool:
            if not isinstance(value, bool):
                errors[name] = "Must be true or false"
                continue
        else:
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            if kind is int:
                ok = isinstance(value, int) and not isinstance(value, bool)
            if not ok:
                errors[name] = "Must be a whole number" if kind is int else "Must be a number"
                continue
            value = kind(value)
            if "min" in rule and value < rule["min"]:
                errors[name] = f"Must be at least {rule['min']}"
            elif "max" in rule and value > rule["max"]:
                errors[name] = f"Must be at most {rule['max']}"
        if name not in errors:
            clean[name] = value
    if errors:
        raise ApiError(422, "validation_error", "Some fields are invalid", errors)
    return clean


def page_args():
    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = min(200, max(1, int(request.args.get("limit", 25))))
    except ValueError:
        raise ApiError(400, "bad_request", "page and limit must be integers")
    return page, limit, (page - 1) * limit


def paged(db, base_sql, where, params, order_by, row_fn=dict):
    """Run `base_sql + where` with pagination; returns the standard list envelope."""
    page, limit, offset = page_args()
    total = db.execute("SELECT COUNT(*) FROM (" + base_sql + where + ")", params).fetchone()[0]
    rows = db.execute(f"{base_sql}{where} ORDER BY {order_by} LIMIT ? OFFSET ?",
                      [*params, limit, offset]).fetchall()
    return {"items": [row_fn(r) for r in rows], "total": total, "page": page, "limit": limit}


def csv_response(rows, headers, filename):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        # Neutralise formula-like cells (CSV injection) when opened in a spreadsheet
        writer.writerow([("'" + c) if isinstance(c, str) and c[:1] in ("=", "+", "-", "@") else c for c in r])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})
