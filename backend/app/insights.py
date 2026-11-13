import datetime as dt

from flask import Blueprint, jsonify, request

from .db import get_db
from .orders import LIST_SQL
from .products import BASE, product_dict
from .security import auth_required
from .utils import ApiError, csv_response

bp = Blueprint("insights", __name__, url_prefix="/api")


def _date_arg(name, default):
    value = request.args.get(name)
    if not value:
        return default
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ApiError(400, "bad_request", f"{name} must be a date in YYYY-MM-DD format")


def _range():
    today = dt.date.today()
    start, end = _date_arg("from", today - dt.timedelta(days=29)), _date_arg("to", today)
    if start > end:
        raise ApiError(400, "bad_request", "'from' must be on or before 'to'")
    return start.isoformat(), end.isoformat()


@bp.get("/dashboard")
@auth_required()
def dashboard():
    db = get_db()
    one = lambda sql, *p: db.execute(sql, p).fetchone()[0]
    today = dt.date.today()
    completed = "status = 'completed'"
    daily = {r["d"]: r["revenue"] for r in db.execute(
        f"SELECT date(created_at) d, ROUND(SUM(total), 2) revenue FROM orders WHERE {completed} "
        "AND date(created_at) >= ? GROUP BY d", ((today - dt.timedelta(days=6)).isoformat(),))}
    low = db.execute(BASE + " WHERE p.active = 1 AND p.stock_qty <= p.reorder_level "
                            "ORDER BY (p.stock_qty * 1.0 / MAX(p.reorder_level, 1)) LIMIT 5").fetchall()
    return jsonify({
        "products": one("SELECT COUNT(*) FROM products WHERE active = 1"),
        "units_in_stock": one("SELECT COALESCE(SUM(stock_qty), 0) FROM products WHERE active = 1"),
        "stock_value": round(one("SELECT COALESCE(SUM(stock_qty * price), 0) FROM products WHERE active = 1"), 2),
        "low_stock_count": one("SELECT COUNT(*) FROM products WHERE active = 1 AND stock_qty <= reorder_level"),
        "customers": one("SELECT COUNT(*) FROM customers"),
        "orders_total": one(f"SELECT COUNT(*) FROM orders WHERE {completed}"),
        "orders_today": one(f"SELECT COUNT(*) FROM orders WHERE {completed} AND date(created_at) = ?", today.isoformat()),
        "sales_today": round(one(f"SELECT COALESCE(SUM(total), 0) FROM orders WHERE {completed} AND date(created_at) = ?", today.isoformat()), 2),
        "sales_month": round(one(f"SELECT COALESCE(SUM(total), 0) FROM orders WHERE {completed} AND strftime('%Y-%m', created_at) = ?", today.strftime("%Y-%m")), 2),
        "sales_total": round(one(f"SELECT COALESCE(SUM(total), 0) FROM orders WHERE {completed}"), 2),
        "sales_last_7_days": [{"date": (d := (today - dt.timedelta(days=i)).isoformat()), "revenue": daily.get(d, 0)}
                              for i in range(6, -1, -1)],
        "recent_orders": [dict(r) for r in db.execute(LIST_SQL + " ORDER BY o.id DESC LIMIT 5")],
        "low_stock": [product_dict(r) for r in low],
    })


@bp.get("/reports/sales")
@auth_required("manager")
def sales_report():
    start, end = _range()
    fmt = {"day": "%Y-%m-%d", "month": "%Y-%m"}.get(request.args.get("group", "day"))
    if not fmt:
        raise ApiError(400, "bad_request", "group must be 'day' or 'month'")
    rows = get_db().execute(
        f"SELECT strftime('{fmt}', created_at) AS period, COUNT(*) AS orders, ROUND(SUM(total), 2) AS revenue "
        "FROM orders WHERE status = 'completed' AND date(created_at) BETWEEN ? AND ? GROUP BY period ORDER BY period",
        (start, end)).fetchall()
    if request.args.get("format") == "csv":
        return csv_response([(r["period"], r["orders"], r["revenue"]) for r in rows],
                            ["period", "orders", "revenue"], "sales-report.csv")
    orders = sum(r["orders"] for r in rows)
    revenue = round(sum(r["revenue"] for r in rows), 2)
    return jsonify({"from": start, "to": end, "rows": [dict(r) for r in rows],
                    "totals": {"orders": orders, "revenue": revenue,
                               "average_order": round(revenue / orders, 2) if orders else 0}})


@bp.get("/reports/top-products")
@auth_required("manager")
def top_products():
    start, end = _range()
    rows = get_db().execute(
        "SELECT p.id, p.sku, p.name, SUM(i.quantity) AS units_sold, ROUND(SUM(i.quantity * i.unit_price), 2) AS revenue "
        "FROM order_items i JOIN orders o ON o.id = i.order_id JOIN products p ON p.id = i.product_id "
        "WHERE o.status = 'completed' AND date(o.created_at) BETWEEN ? AND ? "
        "GROUP BY p.id ORDER BY units_sold DESC LIMIT 10", (start, end)).fetchall()
    return jsonify({"from": start, "to": end, "items": [dict(r) for r in rows]})


@bp.get("/reports/inventory")
@auth_required("manager")
def inventory_report():
    rows = get_db().execute(BASE + " WHERE p.active = 1 ORDER BY p.name COLLATE NOCASE").fetchall()
    items = [dict(product_dict(r), stock_value=round(r["stock_qty"] * r["price"], 2)) for r in rows]
    if request.args.get("format") == "csv":
        return csv_response([(i["sku"], i["name"], i["category"] or "", i["stock_qty"], i["reorder_level"],
                              i["price"], i["stock_value"], "LOW" if i["low_stock"] else "OK") for i in items],
                            ["sku", "name", "category", "stock", "reorder_level", "price", "stock_value", "status"],
                            "inventory-report.csv")
    return jsonify({"items": items, "totals": {
        "products": len(items), "units": sum(i["stock_qty"] for i in items),
        "stock_value": round(sum(i["stock_value"] for i in items), 2),
        "low_stock": sum(1 for i in items if i["low_stock"])}})
