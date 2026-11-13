from flask import Blueprint, g, jsonify, request

from .db import get_db, transaction
from .inventory import apply_movement
from .security import auth_required
from .utils import ApiError, paged, validate

bp = Blueprint("orders", __name__, url_prefix="/api/orders")

LIST_SQL = ("SELECT o.id, o.customer_id, c.name AS customer_name, o.status, o.total, o.notes, "
            "u.name AS created_by_name, o.created_at, "
            "(SELECT COALESCE(SUM(quantity), 0) FROM order_items i WHERE i.order_id = o.id) AS item_count "
            "FROM orders o JOIN customers c ON c.id = o.customer_id JOIN users u ON u.id = o.created_by")

ITEM_RULES = {"product_id": {"type": int, "required": True, "min": 1},
              "quantity": {"type": int, "required": True, "min": 1, "max": 100_000}}


def order_detail(db, order_id):
    row = db.execute(LIST_SQL + " WHERE o.id = ?", (order_id,)).fetchone()
    if not row:
        raise ApiError(404, "not_found", "Order not found")
    order = dict(row)
    order["items"] = [dict(r) for r in db.execute(
        "SELECT i.product_id, p.name, p.sku, i.quantity, i.unit_price, ROUND(i.quantity * i.unit_price, 2) AS line_total "
        "FROM order_items i JOIN products p ON p.id = i.product_id WHERE i.order_id = ? ORDER BY i.id", (order_id,))]
    return order


def create_order(db, user_id, payload):
    """Create an order and deduct stock. Call inside transaction(): any failure rolls everything back."""
    head = validate(payload, {"customer_id": {"type": int, "required": True, "min": 1},
                                     "notes": {"max_len": 300}})
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ApiError(422, "validation_error", "Some fields are invalid", {"items": "Add at least one item"})
    if len(raw_items) > 100:
        raise ApiError(422, "validation_error", "Some fields are invalid", {"items": "At most 100 items per order"})
    merged = {}
    for raw in raw_items:
        item = validate(raw, ITEM_RULES)
        merged[item["product_id"]] = merged.get(item["product_id"], 0) + item["quantity"]

    if not db.execute("SELECT 1 FROM customers WHERE id = ?", (head["customer_id"],)).fetchone():
        raise ApiError(422, "validation_error", "Customer not found", {"customer_id": "Customer does not exist"})

    cur = db.execute("INSERT INTO orders (customer_id, total, notes, created_by) VALUES (?, 0, ?, ?)",
                     (head["customer_id"], head["notes"], user_id))
    order_id, total = cur.lastrowid, 0.0
    for product_id in sorted(merged):
        qty = merged[product_id]
        product = db.execute("SELECT price FROM products WHERE id = ? AND active = 1", (product_id,)).fetchone()
        if not product:
            raise ApiError(422, "validation_error", f"Product {product_id} not found", {"items": f"Product {product_id} does not exist"})
        apply_movement(db, product_id, "OUT", qty, f"Order #{order_id}", user_id, order_id)
        db.execute("INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                   (order_id, product_id, qty, product["price"]))
        total += qty * product["price"]
    db.execute("UPDATE orders SET total = ? WHERE id = ?", (round(total, 2), order_id))
    return order_id


@bp.post("")
@auth_required()
def new_order():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError(400, "bad_request", "Request body must be a JSON object")
    with transaction() as db:
        order_id = create_order(db, g.user["id"], payload)
        return jsonify(order_detail(db, order_id)), 201


@bp.get("")
@auth_required()
def list_orders():
    where, params = " WHERE 1=1", []
    if request.args.get("status") in ("completed", "cancelled"):
        where += " AND o.status = ?"
        params.append(request.args["status"])
    if request.args.get("customer_id"):
        where += " AND o.customer_id = ?"
        params.append(request.args["customer_id"])
    if request.args.get("from"):
        where += " AND date(o.created_at) >= date(?)"
        params.append(request.args["from"])
    if request.args.get("to"):
        where += " AND date(o.created_at) <= date(?)"
        params.append(request.args["to"])
    return jsonify(paged(get_db(), LIST_SQL, where, params, "o.id DESC"))


@bp.get("/<int:order_id>")
@auth_required()
def read_order(order_id):
    return jsonify(order_detail(get_db(), order_id))


@bp.post("/<int:order_id>/cancel")
@auth_required("manager")
def cancel_order(order_id):
    with transaction() as db:
        order = order_detail(db, order_id)
        if order["status"] == "cancelled":
            raise ApiError(409, "conflict", "Order is already cancelled")
        for item in order["items"]:
            db.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?", (item["quantity"], item["product_id"]))
            db.execute("INSERT INTO stock_movements (product_id, type, quantity, reason, order_id, user_id) "
                       "VALUES (?, 'IN', ?, ?, ?, ?)",
                       (item["product_id"], item["quantity"], f"Order #{order_id} cancelled", order_id, g.user["id"]))
        db.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
        return jsonify(order_detail(db, order_id))
