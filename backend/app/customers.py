import sqlite3

from flask import Blueprint, jsonify, request

from .db import get_db
from .security import auth_required
from .utils import ApiError, paged, validate

bp = Blueprint("customers", __name__, url_prefix="/api/customers")

RULES = {
    "name": {"required": True, "max_len": 100},
    "email": {"max_len": 120, "email": True},
    "phone": {"max_len": 30},
    "address": {"max_len": 250},
}


def _get(customer_id):
    row = get_db().execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not row:
        raise ApiError(404, "not_found", "Customer not found")
    return dict(row)


@bp.get("")
@auth_required()
def list_customers():
    where, params = " WHERE 1=1", []
    q = request.args.get("q", "").strip()
    if q:
        where += " AND (name LIKE ? OR email LIKE ? OR phone LIKE ?)"
        params += [f"%{q}%"] * 3
    return jsonify(paged(get_db(), "SELECT * FROM customers", where, params, "name COLLATE NOCASE"))


@bp.get("/<int:customer_id>")
@auth_required()
def read_customer(customer_id):
    return jsonify(_get(customer_id))


@bp.post("")
@auth_required()
def create_customer():
    d = validate(request.get_json(silent=True), RULES)
    cur = get_db().execute("INSERT INTO customers (name, email, phone, address) VALUES (?, ?, ?, ?)",
                           (d["name"], d["email"], d["phone"], d["address"]))
    return jsonify(_get(cur.lastrowid)), 201


@bp.put("/<int:customer_id>")
@auth_required()
def update_customer(customer_id):
    _get(customer_id)
    d = validate(request.get_json(silent=True), RULES)
    get_db().execute("UPDATE customers SET name=?, email=?, phone=?, address=? WHERE id=?",
                     (d["name"], d["email"], d["phone"], d["address"], customer_id))
    return jsonify(_get(customer_id))


@bp.delete("/<int:customer_id>")
@auth_required("manager")
def delete_customer(customer_id):
    _get(customer_id)
    try:
        get_db().execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    except sqlite3.IntegrityError:
        raise ApiError(409, "conflict", "This customer has orders and cannot be deleted")
    return "", 204
