import sqlite3

from flask import jsonify


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def error_response(status, code, message):
    return jsonify({"error": {"code": code, "message": message}}), status


UNIQUE_CODES = {
    "categories.slug": ("DUPLICATE_SLUG", "A category with this slug already exists."),
    "products.slug": ("DUPLICATE_SLUG", "A product with this slug already exists."),
    "skus.sku_code": ("DUPLICATE_SKU", "A SKU with this code already exists."),
    "variants.product_id": ("DUPLICATE_VARIANT", "This option combination already exists for the product."),
}


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def _api(e):
        return error_response(e.status, e.code, e.message)

    @app.errorhandler(sqlite3.IntegrityError)
    def _integrity(e):
        msg = str(e)
        if msg.startswith("UNIQUE constraint failed"):
            col = msg.split(":", 1)[1].split(",")[0].strip()
            code, text = UNIQUE_CODES.get(col, ("DUPLICATE_VALUE", "Duplicate value."))
            return error_response(409, code, text)
        if msg.startswith("CHECK constraint failed"):
            return error_response(422, "CONSTRAINT_VIOLATION", "A value is outside the allowed range.")
        if msg.startswith("FOREIGN KEY constraint failed"):
            return error_response(409, "FOREIGN_KEY_VIOLATION", "Referenced record is missing or still in use.")
        return error_response(409, "INTEGRITY_ERROR", "Database constraint violated.")

    @app.errorhandler(404)
    def _404(_e):
        return error_response(404, "NOT_FOUND", "Resource not found.")

    @app.errorhandler(405)
    def _405(_e):
        return error_response(405, "METHOD_NOT_ALLOWED", "Method not allowed.")

    @app.errorhandler(Exception)
    def _500(_e):  # never leak a traceback to the client
        app.logger.exception("Unhandled error")
        return error_response(500, "SERVER_ERROR", "Unexpected server error.")
