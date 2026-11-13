"""Load demo data:  python seed.py   (safe to run once on an empty database)"""
from app import create_app
from app.db import get_db, transaction
from app.orders import create_order
from app.security import hash_password

USERS = [("Ada Admin", "admin@example.com", "Admin@123", "admin"),
         ("Mia Manager", "manager@example.com", "Manager@123", "manager"),
         ("Sam Staff", "staff@example.com", "Staff@123", "staff")]
CATEGORIES = ["Beverages", "Snacks", "Stationery", "Household"]
PRODUCTS = [  # sku, name, category, price, stock, reorder
    ("BEV-001", "Mineral Water 1L", "Beverages", 0.80, 240, 60), ("BEV-002", "Orange Juice 1L", "Beverages", 2.50, 45, 30),
    ("BEV-003", "Ground Coffee 500g", "Beverages", 7.90, 18, 20), ("SNK-001", "Salted Peanuts 200g", "Snacks", 1.90, 90, 40),
    ("SNK-002", "Dark Chocolate Bar", "Snacks", 2.20, 12, 25), ("SNK-003", "Oat Biscuits", "Snacks", 1.60, 130, 50),
    ("STA-001", "A4 Notebook", "Stationery", 2.80, 75, 30), ("STA-002", "Ballpoint Pens (10)", "Stationery", 3.40, 8, 20),
    ("STA-003", "Sticky Notes", "Stationery", 1.50, 160, 40), ("HOU-001", "Dish Soap 500ml", "Household", 2.10, 55, 25),
    ("HOU-002", "Paper Towels (4)", "Household", 4.60, 33, 20), ("HOU-003", "LED Bulb 9W", "Household", 3.20, 5, 15)]
CUSTOMERS = [("Northside Cafe", "orders@northside.example", "555-0101", "12 Mill Road"),
             ("Brightway School", "office@brightway.example", "555-0102", "4 Park Lane"),
             ("Corner Mart", "hello@cornermart.example", "555-0103", "88 High Street"),
             ("Harbor Offices", "admin@harbor.example", "555-0104", "1 Dock Square")]

app = create_app()
with app.app_context():
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        raise SystemExit("Database already has data; delete backend/instance/inventory.db to re-seed.")
    with transaction() as db:
        for name, email, pw, role in USERS:
            db.execute("INSERT INTO users (name, email, password_hash, role) VALUES (?,?,?,?)",
                       (name, email, hash_password(pw), role))
        for c in CATEGORIES:
            db.execute("INSERT INTO categories (name) VALUES (?)", (c,))
        for sku, name, cat, price, stock, reorder in PRODUCTS:
            cur = db.execute("INSERT INTO products (sku, name, category_id, price, stock_qty, reorder_level) "
                             "VALUES (?,?,(SELECT id FROM categories WHERE name=?),?,?,?)",
                             (sku, name, cat, price, stock, reorder))
            db.execute("INSERT INTO stock_movements (product_id, type, quantity, reason, user_id) "
                       "VALUES (?, 'IN', ?, 'Opening stock', 1)", (cur.lastrowid, stock))
        for c in CUSTOMERS:
            db.execute("INSERT INTO customers (name, email, phone, address) VALUES (?,?,?,?)", c)
        for cust, items in [(1, [(1, 24), (3, 2)]), (2, [(7, 10), (9, 12)]), (3, [(4, 10), (6, 20), (10, 6)]),
                            (1, [(2, 6)]), (4, [(11, 4), (7, 5)])]:
            create_order(db, 3, {"customer_id": cust, "items": [{"product_id": p, "quantity": q} for p, q in items]})
    print("Seeded. Sign in with admin@example.com / Admin@123 (see README for other roles).")
