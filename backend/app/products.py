import sqlite3

from flask import Blueprint, g, jsonify, request

from .db import get_db, transaction
from .security import auth_required
from .utils import ApiError, paged, validate

bp = Blueprint("products", __name__, url_prefix="/api")

BASE = ("SELECT p.id, p.sku, p.name, p.category_id, c.name AS category, p.price, p.stock_qty, "
        "p.reorder_level, p.active FROM products p LEFT JOIN categories c ON c.id = p.category_id")

RULES = {
    "sku": {"required": True, "max_len": 40},
    "name": {"required": True, "max_len": 120},
    "category_id": {"type": int, "min": 1},
    "price": {"type": float, "required": True, "min": 0, "max": 10_000_000},
    "reorder_level": {"type": int, "min": 0, "max": 1_000_000, "default": 10},
}


def product_dict(row):
    d = dict(row)
    d["low_stock"] = d["stock_qty"] <= d["reorder_level"]
    return d


def get_product(db, product_id):
    row = db.execute(BASE + " WHERE p.id = ? AND p.active = 1", (product_id,)).fetchone()
    if not row:
        raise ApiError(404, "not_found", "Product not found")
    return product_dict(row)


@bp.get("/categories")
@auth_required()
def list_categories():
    rows = get_db().execute("SELECT id, name FROM categories ORDER BY name").fetchall()
    return jsonify({"items": [dict(r) for r in rows]})


@bp.post("/categories")
@auth_required("manager")
def create_category():
    data = validate(request.get_json(silent=True), {"name": {"required": True, "max_len": 60}})
    try:
        cur = get_db().execute("INSERT INTO categories (name) VALUES (?)", (data["name"],))
    except sqlite3.IntegrityError:
        raise ApiError(409, "duplicate", "Category already exists", {"name": "Already exists"})
    return jsonify({"id": cur.lastrowid, "name": data["name"]}), 201


@bp.get("/products")
@auth_required()
def list_products():
    where, params = " WHERE p.active = 1", []
    q = request.args.get("q", "").strip()
    if q:
        where += " AND (p.name LIKE ? OR p.sku LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if request.args.get("category_id"):
        where += " AND p.category_id = ?"
        params.append(request.args["category_id"])
    if request.args.get("low_stock") in ("1", "true"):
        where += " AND p.stock_qty <= p.reorder_level"
    return jsonify(paged(get_db(), BASE, where, params, "p.name COLLATE NOCASE", product_dict))


@bp.get("/products/<int:product_id>")
@auth_required()
def read_product(product_id):
    return jsonify(get_product(get_db(), product_id))


def _save(db, sql, params):
    try:
        return db.execute(sql, params)
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc):
            raise ApiError(409, "duplicate", "A product with this SKU already exists", {"sku": "Already in use"})
        raise ApiError(422, "validation_error", "Invalid category", {"category_id": "Category does not exist"})


@bp.post("/products")
@auth_required("manager")
def create_product():
    body = request.get_json(silent=True)
    data = validate(body, {**RULES, "stock_qty": {"type": int, "min": 0, "max": 10_000_000, "default": 0}})
    with transaction() as db:
        cur = _save(db, "INSERT INTO products (sku, name, category_id, price, stock_qty, reorder_level) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                    (data["sku"], data["name"], data["category_id"], data["price"],
                     data["stock_qty"], data["reorder_level"]))
        if data["stock_qty"] > 0:
            db.execute("INSERT INTO stock_movements (product_id, type, quantity, reason, user_id) "
                       "VALUES (?, 'IN', ?, 'Opening stock', ?)", (cur.lastrowid, data["stock_qty"], g.user["id"]))
        return jsonify(get_product(db, cur.lastrowid)), 201


@bp.put("/products/<int:product_id>")
@auth_required("manager")
def update_product(product_id):
    data = validate(request.get_json(silent=True), RULES)  # stock changes go through /inventory
    db = get_db()
    get_product(db, product_id)
    _save(db, "UPDATE products SET sku=?, name=?, category_id=?, price=?, reorder_level=? WHERE id=?",
          (data["sku"], data["name"], data["category_id"], data["price"], data["reorder_level"], product_id))
    return jsonify(get_product(db, product_id))


@bp.delete("/products/<int:product_id>")
@auth_required("manager")
def delete_product(product_id):
    db = get_db()
    get_product(db, product_id)
    # Soft delete keeps historical orders and stock movements intact
    db.execute("UPDATE products SET active = 0, sku = sku || '#deleted-' || id WHERE id = ?", (product_id,))
    return "", 204
