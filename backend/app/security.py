import datetime as dt
import time
import uuid
from functools import wraps

import jwt
from flask import current_app, g, request
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .utils import ApiError

ROLE_LEVEL = {"staff": 1, "manager": 2, "admin": 3}
_failed = {}  # email -> [timestamps]; simple in-memory brute-force guard
MAX_ATTEMPTS, WINDOW = 5, 15 * 60


def hash_password(password):
    return generate_password_hash(password)


def verify_password(pw_hash, password):
    return check_password_hash(pw_hash, password)


def check_login_allowed(email):
    now = time.time()
    attempts = [t for t in _failed.get(email, []) if now - t < WINDOW]
    _failed[email] = attempts
    if len(attempts) >= MAX_ATTEMPTS:
        raise ApiError(429, "too_many_attempts", "Too many failed sign-in attempts. Try again in 15 minutes.")


def record_failed_login(email):
    _failed.setdefault(email, []).append(time.time())


def clear_failed_logins(email):
    _failed.pop(email, None)


def create_token(user):
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user["id"]), "role": user["role"], "jti": uuid.uuid4().hex,
        "iat": now, "exp": now + dt.timedelta(hours=current_app.config["TOKEN_HOURS"]),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def _decode(token):
    try:
        return jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "token_expired", "Session expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise ApiError(401, "invalid_token", "Invalid authentication token")


def auth_required(min_role="staff"):
    """Require a valid bearer token whose user has at least `min_role`."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                raise ApiError(401, "unauthorized", "Authentication required")
            claims = _decode(header[7:].strip())
            db = get_db()
            if db.execute("SELECT 1 FROM revoked_tokens WHERE jti = ?", (claims["jti"],)).fetchone():
                raise ApiError(401, "token_revoked", "You have been signed out. Please sign in again.")
            user = db.execute("SELECT id, name, email, role, active FROM users WHERE id = ?",
                              (claims["sub"],)).fetchone()
            if not user or not user["active"]:
                raise ApiError(401, "unauthorized", "Account not found or disabled")
            if ROLE_LEVEL[user["role"]] < ROLE_LEVEL[min_role]:
                raise ApiError(403, "forbidden", f"This action requires the {min_role} role or higher")
            g.user, g.claims = dict(user), claims
            return fn(*args, **kwargs)
        return wrapper
    return decorator
