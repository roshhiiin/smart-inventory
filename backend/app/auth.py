import sqlite3
import time

from flask import Blueprint, g, jsonify, request

from .db import get_db
from .security import (auth_required, check_login_allowed, clear_failed_logins, create_token,
                       hash_password, record_failed_login, verify_password)
from .utils import ApiError, paged, validate

bp = Blueprint("auth", __name__, url_prefix="/api")


def public_user(u):
    return {k: u[k] for k in ("id", "name", "email", "role")}


@bp.post("/auth/login")
def login():
    data = validate(request.get_json(silent=True), {
        "email": {"required": True, "max_len": 120},
        "password": {"required": True, "max_len": 200},
    })
    email = data["email"].lower()
    check_login_allowed(email)
    user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not user["active"] or not verify_password(user["password_hash"], data["password"]):
        record_failed_login(email)
        raise ApiError(401, "invalid_credentials", "Incorrect email or password")
    clear_failed_logins(email)
    return jsonify({"token": create_token(user), "user": public_user(user)})


@bp.post("/auth/logout")
@auth_required()
def logout():
    db = get_db()
    db.execute("INSERT OR IGNORE INTO revoked_tokens (jti, expires_at) VALUES (?, ?)",
               (g.claims["jti"], g.claims["exp"]))
    db.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (int(time.time()),))
    return jsonify({"message": "Signed out"})


@bp.get("/auth/me")
@auth_required()
def me():
    return jsonify(public_user(g.user))


USER_RULES = {
    "name": {"required": True, "max_len": 80},
    "email": {"required": True, "max_len": 120, "email": True},
    "password": {"required": True, "min_len": 8, "max_len": 128},
    "role": {"required": True, "choices": ["admin", "manager", "staff"]},
}


@bp.get("/users")
@auth_required("admin")
def list_users():
    return jsonify(paged(get_db(), "SELECT id, name, email, role, active, created_at FROM users", "", [], "id"))


@bp.post("/users")
@auth_required("admin")
def create_user():
    data = validate(request.get_json(silent=True), USER_RULES)
    try:
        cur = get_db().execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (data["name"], data["email"].lower(), hash_password(data["password"]), data["role"]))
    except sqlite3.IntegrityError:
        raise ApiError(409, "duplicate", "A user with this email already exists", {"email": "Already in use"})
    return jsonify({"id": cur.lastrowid, "name": data["name"], "email": data["email"].lower(), "role": data["role"]}), 201


@bp.patch("/users/<int:user_id>")
@auth_required("admin")
def update_user(user_id):
    data = validate(request.get_json(silent=True), {
        "role": {"choices": ["admin", "manager", "staff"]}, "active": {"type": bool}})
    if user_id == g.user["id"] and (data.get("active") is False or (data.get("role") and data["role"] != "admin")):
        raise ApiError(409, "conflict", "You cannot demote or disable your own account")
    db = get_db()
    if not db.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone():
        raise ApiError(404, "not_found", "User not found")
    if data.get("role"):
        db.execute("UPDATE users SET role = ? WHERE id = ?", (data["role"], user_id))
    if data.get("active") is not None:
        db.execute("UPDATE users SET active = ? WHERE id = ?", (int(data["active"]), user_id))
    return jsonify({"message": "User updated"})
