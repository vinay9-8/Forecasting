from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from backend.database.db import create_database_engine, create_schema
from backend.routes.api import api

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE_URL=None,
        DATA_OUTPUT_DIR=REPOSITORY_ROOT / "data" / "generated",
        JSON_SORT_KEYS=False,
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    app.config["DATA_OUTPUT_DIR"] = Path(app.config["DATA_OUTPUT_DIR"])

    engine = create_database_engine(app.config.get("DATABASE_URL"))
    create_schema(engine)
    app.extensions["database_engine"] = engine
    CORS(app, resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}})
    app.register_blueprint(api)

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        if error.code == 404 and not request.path.startswith("/api/"):
            return error
        return (
            jsonify(
                {
                    "error": {
                        "code": f"HTTP_{error.code}",
                        "message": error.description,
                    }
                }
            ),
            error.code,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.exception("Unhandled API error.", exc_info=error)
        return (
            jsonify(
                {
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected server error occurred.",
                    }
                }
            ),
            500,
        )

    return app


def main() -> None:
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()