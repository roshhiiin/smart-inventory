from flask import Blueprint, g, jsonify, request

from .db import get_db, transaction
from .products import BASE, get_product, product_dict
from .security import auth_required
from .utils import ApiError, paged, validate

bp = Blueprint("inventory", __name__, url_prefix="/api/inventory")

MOVE_RULES = {
    "product_id": {"type": int, "required": True, "min": 1},
    "quantity": {"type": int, "required": True, "min": 1, "max": 1_000_000},
    "reason": {"max_len": 200},
}


def apply_movement(db, product_id, kind, qty, reason, user_id, order_id=None):
    """Change stock and log it. Must run inside a transaction. Raises 409 if stock would go negative."""
    if kind == "OUT":
        cur = db.execute("UPDATE products SET stock_qty = stock_qty - ? "
                         "WHERE id = ? AND active = 1 AND stock_qty >= ?", (qty, product_id, qty))
    else:
        cur = db.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ? AND active = 1",
                         (qty, product_id))
    if cur.rowcount == 0:
        row = db.execute("SELECT name, stock_qty FROM products WHERE id = ? AND active = 1", (product_id,)).fetchone()
        if not row:
            raise ApiError(404, "not_found", "Product not found")
        raise ApiError(409, "insufficient_stock", f"Only {row['stock_qty']} of {row['name']} in stock",
                       {"product_id": product_id, "available": row["stock_qty"], "requested": qty})
    db.execute("INSERT INTO stock_movements (product_id, type, quantity, reason, order_id, user_id) "
               "VALUES (?, ?, ?, ?, ?, ?)", (product_id, kind, qty, reason, order_id, user_id))


def _movement(kind, default_reason):
    data = validate(request.get_json(silent=True), MOVE_RULES)
    with transaction() as db:
        apply_movement(db, data["product_id"], kind, data["quantity"],
                       data["reason"] or default_reason, g.user["id"])
        return jsonify(get_product(db, data["product_id"]))


@bp.post("/stock-in")
@auth_required("manager")
def stock_in():
    return _movement("IN", "Stock received")


@bp.post("/stock-out")
@auth_required("manager")
def stock_out():
    return _movement("OUT", "Stock removed")


@bp.get("/movements")
@auth_required()
def movements():
    base = ("SELECT m.id, m.product_id, p.name AS product, p.sku, m.type, m.quantity, m.reason, m.order_id, "
            "u.name AS user, m.created_at FROM stock_movements m JOIN products p ON p.id = m.product_id "
            "LEFT JOIN users u ON u.id = m.user_id")
    where, params = " WHERE 1=1", []
    if request.args.get("product_id"):
        where += " AND m.product_id = ?"
        params.append(request.args["product_id"])
    if request.args.get("type") in ("IN", "OUT"):
        where += " AND m.type = ?"
        params.append(request.args["type"])
    return jsonify(paged(get_db(), base, where, params, "m.id DESC"))


@bp.get("/low-stock")
@auth_required()
def low_stock():
    rows = get_db().execute(BASE + " WHERE p.active = 1 AND p.stock_qty <= p.reorder_level "
                                   "ORDER BY (p.stock_qty * 1.0 / MAX(p.reorder_level, 1)), p.name").fetchall()
    return jsonify({"items": [product_dict(r) for r in rows], "total": len(rows)})
