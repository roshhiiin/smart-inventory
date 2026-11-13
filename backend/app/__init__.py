import os
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from . import auth, customers, insights, inventory, orders, products
from .db import close_db, init_db
from .utils import ApiError

ROOT = Path(__file__).resolve().parents[2]


def create_app(config=None):
    app = Flask(__name__, static_folder=str(ROOT / "web"), static_url_path="")
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me-please-0123456789abcdef"),
        DATABASE=os.environ.get("DATABASE", str(ROOT / "backend" / "instance" / "inventory.db")),
        TOKEN_HOURS=int(os.environ.get("TOKEN_HOURS", "8")),
        CORS_ORIGINS=os.environ.get("CORS_ORIGINS", "*"),
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if config:
        app.config.update(config)
    if os.environ.get("APP_ENV") == "production" and "SECRET_KEY" not in os.environ and not (config and "SECRET_KEY" in config):
        raise RuntimeError("Set the SECRET_KEY environment variable before running in production")
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()

    for module in (auth, products, inventory, customers, orders, insights):
        app.register_blueprint(module.bp)

    @app.errorhandler(ApiError)
    def handle_api_error(e):
        body = {"error": {"code": e.code, "message": e.message}}
        if e.details:
            body["error"]["details"] = e.details
        return jsonify(body), e.status

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": {"code": "not_found", "message": "Resource not found"}}), 404

    @app.errorhandler(405)
    def bad_method(_e):
        return jsonify({"error": {"code": "method_not_allowed", "message": "Method not allowed"}}), 405

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify({"error": {"code": "too_large", "message": "Request body too large"}}), 413

    @app.errorhandler(sqlite3.Error)
    def db_error(e):
        app.logger.exception("Database error")
        return jsonify({"error": {"code": "database_error", "message": "A database error occurred"}}), 500

    @app.errorhandler(Exception)
    def unexpected(e):
        app.logger.exception("Unhandled error")
        return jsonify({"error": {"code": "server_error", "message": "Something went wrong on our side"}}), 500

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Access-Control-Allow-Origin"] = app.config["CORS_ORIGINS"]
        resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return resp

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/docs")
    def docs():
        return ("<!doctype html><title>API docs</title>"
                '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.17.14/swagger-ui.min.css">'
                '<div id="ui"></div>'
                '<script src="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.17.14/swagger-ui-bundle.min.js"></script>'
                "<script>SwaggerUIBundle({url:'/api/openapi.yaml',dom_id:'#ui'})</script>")

    @app.get("/api/openapi.yaml")
    def openapi():
        return send_from_directory(ROOT / "docs", "openapi.yaml", mimetype="text/yaml")

    return app
