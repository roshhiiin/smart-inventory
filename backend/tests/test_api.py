import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app
from app.db import get_db
from app.security import hash_password


class ApiTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app({"DATABASE": self.path, "TESTING": True})
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        with self.app.app_context():
            db = get_db()
            for n, e, r in [("A", "admin@t.io", "admin"), ("M", "manager@t.io", "manager"), ("S", "staff@t.io", "staff")]:
                db.execute("INSERT INTO users (name,email,password_hash,role) VALUES (?,?,?,?)", (n, e, hash_password("Passw0rd!"), r))
            db.execute("INSERT INTO categories (name) VALUES ('General')")
        self.c = self.app.test_client()
        self.tokens = {r: self.login(f"{r}@t.io") for r in ("admin", "manager", "staff")}

    def tearDown(self):
        os.unlink(self.path)

    def login(self, email, password="Passw0rd!"):
        r = self.c.post("/api/auth/login", json={"email": email, "password": password})
        return r.get_json().get("token")

    def call(self, method, url, role="manager", **kw):
        headers = {"Authorization": f"Bearer {self.tokens[role]}"} if role else {}
        return getattr(self.c, method)(url, headers=headers, **kw)

    def product(self, sku="P1", stock=10, price=5.0, reorder=3):
        r = self.call("post", "/api/products", json={"sku": sku, "name": "Item " + sku, "category_id": 1,
                                                      "price": price, "stock_qty": stock, "reorder_level": reorder})
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def customer(self):
        return self.call("post", "/api/customers", json={"name": "Cust"}).get_json()

    # --- auth & roles
    def test_login_failures_and_me(self):
        self.assertEqual(self.c.post("/api/auth/login", json={"email": "admin@t.io", "password": "bad"}).status_code, 401)
        self.assertEqual(self.c.post("/api/auth/login", json={"email": "x"}).status_code, 422)
        self.assertEqual(self.call("get", "/api/auth/me", "staff").get_json()["role"], "staff")
        self.assertEqual(self.call("get", "/api/auth/me", None).status_code, 401)

    def test_logout_revokes_token(self):
        self.assertEqual(self.call("post", "/api/auth/logout", "staff").status_code, 200)
        self.assertEqual(self.call("get", "/api/auth/me", "staff").status_code, 401)

    def test_role_permissions(self):
        body = {"sku": "X", "name": "X", "price": 1}
        self.assertEqual(self.call("post", "/api/products", "staff", json=body).status_code, 403)
        self.assertEqual(self.call("get", "/api/users", "manager").status_code, 403)
        self.assertEqual(self.call("get", "/api/users", "admin").status_code, 200)
        self.assertEqual(self.call("get", "/api/reports/sales", "staff").status_code, 403)

    # --- products
    def test_product_crud_search_validation(self):
        p = self.product("SKU-9", stock=4, reorder=5)
        self.assertTrue(p["low_stock"])
        self.assertEqual(self.call("post", "/api/products", json={"sku": "SKU-9", "name": "d", "price": 1}).status_code, 409)
        bad = self.call("post", "/api/products", json={"sku": "", "name": "n", "price": -1})
        self.assertEqual(bad.status_code, 422)
        self.assertIn("price", bad.get_json()["error"]["details"])
        self.assertEqual(self.call("get", "/api/products?q=sku-9").get_json()["total"], 1)
        r = self.call("put", f"/api/products/{p['id']}", json={"sku": "SKU-9", "name": "Renamed", "price": 9, "reorder_level": 1})
        self.assertEqual(r.get_json()["name"], "Renamed")
        self.assertEqual(self.call("delete", f"/api/products/{p['id']}").status_code, 204)
        self.assertEqual(self.call("get", f"/api/products/{p['id']}").status_code, 404)

    # --- inventory
    def test_stock_in_out_and_low_stock(self):
        p = self.product(stock=5, reorder=3)
        r = self.call("post", "/api/inventory/stock-in", json={"product_id": p["id"], "quantity": 5})
        self.assertEqual(r.get_json()["stock_qty"], 10)
        r = self.call("post", "/api/inventory/stock-out", json={"product_id": p["id"], "quantity": 8})
        self.assertEqual(r.get_json()["stock_qty"], 2)
        self.assertEqual(self.call("get", "/api/inventory/low-stock").get_json()["total"], 1)
        r = self.call("post", "/api/inventory/stock-out", json={"product_id": p["id"], "quantity": 3})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["error"]["code"], "insufficient_stock")
        self.assertEqual(self.call("post", "/api/inventory/stock-in", json={"product_id": p["id"], "quantity": 0}).status_code, 422)
        self.assertEqual(self.call("get", "/api/inventory/movements").get_json()["total"], 3)

    # --- orders
    def test_order_updates_stock_and_cancel_restores(self):
        p1, p2, cust = self.product("A", 10, 2.5), self.product("B", 4, 10.0), self.customer()
        r = self.call("post", "/api/orders", "staff", json={"customer_id": cust["id"], "items": [
            {"product_id": p1["id"], "quantity": 4}, {"product_id": p1["id"], "quantity": 2}, {"product_id": p2["id"], "quantity": 1}]})
        self.assertEqual(r.status_code, 201, r.get_json())
        order = r.get_json()
        self.assertEqual(order["total"], 25.0)
        self.assertEqual(len(order["items"]), 2)
        self.assertEqual(self.call("get", f"/api/products/{p1['id']}").get_json()["stock_qty"], 4)
        self.assertEqual(self.call("post", f"/api/orders/{order['id']}/cancel", "staff").status_code, 403)
        self.assertEqual(self.call("post", f"/api/orders/{order['id']}/cancel").get_json()["status"], "cancelled")
        self.assertEqual(self.call("get", f"/api/products/{p1['id']}").get_json()["stock_qty"], 10)
        self.assertEqual(self.call("post", f"/api/orders/{order['id']}/cancel").status_code, 409)

    def test_order_rolls_back_when_any_line_fails(self):
        p1, p2, cust = self.product("A", 10), self.product("B", 1), self.customer()
        r = self.call("post", "/api/orders", json={"customer_id": cust["id"], "items": [
            {"product_id": p1["id"], "quantity": 3}, {"product_id": p2["id"], "quantity": 5}]})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.call("get", f"/api/products/{p1['id']}").get_json()["stock_qty"], 10)
        self.assertEqual(self.call("get", "/api/orders").get_json()["total"], 0)

    def test_order_validation(self):
        cust = self.customer()
        self.assertEqual(self.call("post", "/api/orders", json={"customer_id": cust["id"], "items": []}).status_code, 422)
        self.assertEqual(self.call("post", "/api/orders", json={"customer_id": 999, "items": [{"product_id": 1, "quantity": 1}]}).status_code, 422)
        self.assertEqual(self.call("post", "/api/orders", data="nope", content_type="text/plain").status_code, 400)

    # --- customers, dashboard, reports
    def test_customer_delete_blocked_with_orders(self):
        p, cust = self.product(), self.customer()
        self.call("post", "/api/orders", json={"customer_id": cust["id"], "items": [{"product_id": p["id"], "quantity": 1}]})
        self.assertEqual(self.call("delete", f"/api/customers/{cust['id']}").status_code, 409)

    def test_dashboard_and_reports(self):
        p, cust = self.product("D", 20, 4.0, 5), self.customer()
        self.call("post", "/api/orders", json={"customer_id": cust["id"], "items": [{"product_id": p["id"], "quantity": 5}]})
        d = self.call("get", "/api/dashboard", "staff").get_json()
        self.assertEqual((d["products"], d["orders_total"], d["sales_total"], d["units_in_stock"]), (1, 1, 20.0, 15))
        self.assertEqual(len(d["sales_last_7_days"]), 7)
        s = self.call("get", "/api/reports/sales").get_json()
        self.assertEqual(s["totals"], {"orders": 1, "revenue": 20.0, "average_order": 20.0})
        self.assertEqual(self.call("get", "/api/reports/top-products").get_json()["items"][0]["units_sold"], 5)
        self.assertEqual(self.call("get", "/api/reports/inventory").get_json()["totals"]["units"], 15)
        csv = self.call("get", "/api/reports/inventory?format=csv")
        self.assertTrue(csv.data.decode().startswith("sku,name"))
        self.assertEqual(self.call("get", "/api/reports/sales?from=nope").status_code, 400)

    def test_static_and_docs(self):
        self.assertEqual(self.c.get("/api/health").status_code, 200)
        self.assertEqual(self.c.get("/api/docs").status_code, 200)
        self.assertEqual(self.c.get("/api/nothing").status_code, 404)


if __name__ == "__main__":
    unittest.main()
