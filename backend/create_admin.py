"""Create the first admin user:  ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='...' python create_admin.py"""
import os
import sys

from app import create_app
from app.db import get_db
from app.security import hash_password

email, password = os.environ.get("ADMIN_EMAIL", "").strip().lower(), os.environ.get("ADMIN_PASSWORD", "")
if not email or len(password) < 8:
    sys.exit("Set ADMIN_EMAIL and ADMIN_PASSWORD (8+ characters).")
with create_app().app_context():
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        sys.exit("A user with that email already exists.")
    db.execute("INSERT INTO users (name, email, password_hash, role) VALUES ('Administrator', ?, ?, 'admin')",
               (email, hash_password(password)))
    print("Admin created:", email)
