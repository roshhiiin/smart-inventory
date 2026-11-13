# Stockroom: Smart Inventory & Order Management System

A web app, an Android app and a REST API sharing one database.

| Part | Folder | Tech |
|---|---|---|
| REST API + business logic | `backend/` | Python 3.12, Flask, JWT auth, SQLite (schema is portable SQL) |
| Responsive web app | `web/` | Vanilla JS, no build step; served by the API at `/` |
| Android app | `mobile/` | Kotlin, Jetpack Compose, Retrofit |
| API docs | `docs/openapi.yaml` | OpenAPI 3, Swagger UI at `/api/docs` |

## Run it locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed.py          # optional demo data and demo accounts
python run.py           # http://localhost:5000  (web app)  ·  /api/docs (API docs)
```

Demo accounts (from `seed.py`, for local use only):

| Role | Email | Password |
|---|---|---|
| Admin | admin@example.com | Admin@123 |
| Manager | manager@example.com | Manager@123 |
| Staff | staff@example.com | Staff@123 |

Run the tests: `cd backend && python -m unittest discover -s tests -v`

## What each role can do

| | Staff | Manager | Admin |
|---|---|---|---|
| Dashboard, view products/stock/orders/customers | ✔ | ✔ | ✔ |
| Create orders, add/edit customers | ✔ | ✔ | ✔ |
| Add/edit/delete products, stock in/out, cancel orders, delete customers, reports | | ✔ | ✔ |
| Manage users and roles | | | ✔ |

Permissions are enforced on the server (`auth_required(role)`); the UIs only hide what you can't use.

## Modules

1. **Authentication**: login, logout (the token is revoked server-side), roles, brute-force lockout (5 failures / 15 min per email).
2. **Dashboard**: product count, units, stock value, low-stock count, sales today/month, 7-day chart, recent orders.
3. **Products**: add, edit, soft-delete, search by name/SKU, filter by category or low stock, pagination.
4. **Inventory**: stock-in/out with a full movement history, low-stock alerts (`stock_qty <= reorder_level`).
5. **Customers**: add, edit, search, delete (blocked if the customer has orders).
6. **Orders**: one database transaction per order. It checks stock, deducts it, records movements and totals. If any line lacks stock, nothing changes. Cancelling returns the stock.
7. **Reports**: sales by day/month, best sellers, inventory valuation, CSV export.

## Database design

`users`, `categories`, `products`, `customers`, `orders`, `order_items`, `stock_movements`, `revoked_tokens` (see `backend/app/schema.sql`). Foreign keys, `CHECK` constraints (no negative stock or prices) and indexes are in the schema. `order_items.unit_price` stores the price at the time of sale, so later price edits don't change history. `stock_movements` is an audit trail of every stock change.

## Android app

Open `mobile/` in Android Studio (Koala or newer) and run on an emulator. The app reaches your local API at `http://10.0.2.2:5000/` (set in `app/build.gradle.kts`). Features: sign in, dashboard, product search and low-stock filter, stock in/out (manager+), order list, create order. For a physical device or production, change `API_BASE` to your HTTPS URL. If Android Studio asks for a Gradle wrapper jar, accept its prompt to generate it (or run `gradle wrapper`).

## Deploy

**Docker** (any host):
```bash
docker build -t stockroom .
docker run -p 8000:8000 -v stockroom-data:/data \
  -e SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')" \
  -e ADMIN_EMAIL=you@example.com -e ADMIN_PASSWORD='choose-a-strong-one' stockroom
```
**Render**: push to GitHub, create a Blueprint from `render.yaml`, and set `ADMIN_EMAIL` / `ADMIN_PASSWORD`. The disk keeps the SQLite file between deploys.

Production notes: set `SECRET_KEY` (the app refuses to start without it when `APP_ENV=production`), serve over HTTPS, and set `CORS_ORIGINS` to your web origin if the API is hosted separately. To use PostgreSQL instead of SQLite, replace `db.py` with a `psycopg` connection and adapt the few SQLite date functions (`strftime`, `date`) in `insights.py` and `schema.sql`.

## Security and validation

Passwords are hashed (Werkzeug scrypt/PBKDF2). JWTs expire after 8 hours. Every request body is validated (types, ranges, lengths, email format) and failures return `422` with per-field messages. SQL is fully parameterised. The web UI escapes all rendered data. CSV exports neutralise formula injection. Errors use one JSON shape: `{"error": {"code", "message", "details"}}`.

## Git workflow

```bash
git init && git add . && git commit -m "Initial commit"
git branch -M main && git remote add origin <your-repo-url> && git push -u origin main
```
GitHub Actions (`.github/workflows/ci.yml`) runs the backend tests on every push.
