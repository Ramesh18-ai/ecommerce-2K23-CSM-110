import json
import re

from flask import Blueprint, jsonify, request

from auth import admin_required
from db import get_db
from errors import ApiError

admin_bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STATUSES = ("draft", "published", "archived")


# ---------- helpers ----------
def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "INVALID_JSON", "Request body must be a JSON object.")
    return data


def invalid(message):
    return ApiError(422, "VALIDATION_ERROR", message)


def req_text(data, field, required=True):
    val = data.get(field)
    if val is None:
        if required:
            raise invalid(f"'{field}' is required.")
        return None
    if not isinstance(val, str) or not val.strip():
        raise invalid(f"'{field}' must be a non-empty string.")
    return val.strip()


def req_slug(data, required=True):
    slug = req_text(data, "slug", required)
    if slug is not None and not SLUG_RE.match(slug):
        raise invalid("'slug' must be lowercase letters, digits and hyphens (e.g. 'used-laptop').")
    return slug


def req_int(data, field, default=None, minimum=0):
    if field not in data:
        if default is None:
            raise invalid(f"'{field}' is required.")
        return default
    val = data[field]
    if isinstance(val, bool) or not isinstance(val, int):
        raise invalid(f"'{field}' must be an integer (money is in minor units, e.g. paisa).")
    if val < minimum:
        raise invalid(f"'{field}' must be >= {minimum}.")
    return val


def req_bool(data, field, default=None):
    if field not in data:
        return default
    if not isinstance(data[field], bool):
        raise invalid(f"'{field}' must be true or false.")
    return data[field]


def one(db, sql, args=()):
    return db.execute(sql, args).fetchone()


def get_or_404(db, table, row_id, label):
    row = one(db, f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    if row is None:
        raise ApiError(404, "NOT_FOUND", f"{label} {row_id} not found.")
    return row


def category_json(r):
    return {"id": r["id"], "parent_id": r["parent_id"], "name": r["name"], "slug": r["slug"],
            "is_active": bool(r["is_active"]), "created_at": r["created_at"], "updated_at": r["updated_at"]}


def sku_json(r):
    return {"id": r["id"], "product_id": r["product_id"], "variant_id": r["variant_id"],
            "sku_code": r["sku_code"], "price_minor": r["price_minor"], "currency": r["currency"],
            "stock_qty": r["stock_qty"], "in_stock": r["stock_qty"] > 0, "is_active": bool(r["is_active"])}


def product_json(db, r, with_children=True):
    out = {"id": r["id"], "category_id": r["category_id"], "name": r["name"], "slug": r["slug"],
           "description": r["description"], "status": r["status"],
           "created_at": r["created_at"], "updated_at": r["updated_at"]}
    if with_children:
        out["variants"] = [{"id": v["id"], "option_values": json.loads(v["option_values"])}
                           for v in db.execute("SELECT * FROM variants WHERE product_id = ? ORDER BY id", (r["id"],))]
        out["skus"] = [sku_json(s) for s in db.execute("SELECT * FROM skus WHERE product_id = ? ORDER BY id", (r["id"],))]
    return out


# ---------- categories ----------
@admin_bp.post("/categories")
@admin_required
def create_category():
    data, db = body(), get_db()
    name, slug = req_text(data, "name"), req_slug(data)
    parent_id = data.get("parent_id")
    if parent_id is not None:
        parent = one(db, "SELECT id FROM categories WHERE id = ?", (parent_id,)) if isinstance(parent_id, int) else None
        if parent is None:
            raise invalid("'parent_id' does not match an existing category.")
    cur = db.execute("INSERT INTO categories (parent_id, name, slug) VALUES (?, ?, ?)", (parent_id, name, slug))
    db.commit()
    return jsonify(category_json(get_or_404(db, "categories", cur.lastrowid, "Category"))), 201


@admin_bp.get("/categories")
@admin_required
def list_categories():
    rows = [category_json(r) for r in get_db().execute("SELECT * FROM categories ORDER BY name")]
    nodes = {c["id"]: {**c, "children": []} for c in rows}
    roots = []
    for n in nodes.values():
        (nodes[n["parent_id"]]["children"] if n["parent_id"] in nodes else roots).append(n)
    return jsonify({"data": roots})


@admin_bp.patch("/categories/<int:cat_id>")
@admin_required
def update_category(cat_id):
    data, db = body(), get_db()
    cat = get_or_404(db, "categories", cat_id, "Category")
    name = req_text(data, "name", False) or cat["name"]
    slug = req_slug(data, False) or cat["slug"]
    parent_id = data.get("parent_id", cat["parent_id"])
    if "parent_id" in data and parent_id is not None:
        if not isinstance(parent_id, int) or one(db, "SELECT id FROM categories WHERE id = ?", (parent_id,)) is None:
            raise invalid("'parent_id' does not match an existing category.")
        # cycle prevention: walk up from the new parent; hitting cat_id means a loop
        node = parent_id
        while node is not None:
            if node == cat_id:
                raise ApiError(422, "CATEGORY_CYCLE", "A category cannot be its own ancestor.")
            node = one(db, "SELECT parent_id FROM categories WHERE id = ?", (node,))["parent_id"]
    active = req_bool(data, "is_active", bool(cat["is_active"]))
    if active and not cat["is_active"] and parent_id is not None:
        if not one(db, "SELECT is_active FROM categories WHERE id = ?", (parent_id,))["is_active"]:
            raise ApiError(409, "PARENT_INACTIVE", "Activate the parent category first.")
    db.execute("UPDATE categories SET name=?, slug=?, parent_id=?, is_active=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
               (name, slug, parent_id, int(active), cat_id))
    if not active:  # deactivating a parent deactivates all descendants
        db.execute("""WITH RECURSIVE sub(id) AS (SELECT id FROM categories WHERE parent_id = ?
                      UNION SELECT c.id FROM categories c JOIN sub ON c.parent_id = sub.id)
                      UPDATE categories SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id IN (SELECT id FROM sub)""",
                   (cat_id,))
    db.commit()
    return jsonify(category_json(get_or_404(db, "categories", cat_id, "Category")))


# ---------- products ----------
@admin_bp.post("/products")
@admin_required
def create_product():
    data, db = body(), get_db()
    name, slug = req_text(data, "name"), req_slug(data)
    if data.get("status", "draft") != "draft":
        raise invalid("New products are always created as 'draft'.")
    cat_id = data.get("category_id")
    cat = one(db, "SELECT * FROM categories WHERE id = ?", (cat_id,)) if isinstance(cat_id, int) else None
    if cat is None or not cat["is_active"]:
        raise invalid("'category_id' must reference an active category.")
    cur = db.execute("INSERT INTO products (category_id, name, slug, description) VALUES (?, ?, ?, ?)",
                     (cat_id, name, slug, str(data.get("description", ""))))
    db.commit()
    return jsonify(product_json(db, get_or_404(db, "products", cur.lastrowid, "Product"))), 201


@admin_bp.get("/products")
@admin_required
def list_products():
    db = get_db()
    return jsonify({"data": [product_json(db, r) for r in db.execute("SELECT * FROM products ORDER BY id")]})


@admin_bp.patch("/products/<int:product_id>")
@admin_required
def update_product(product_id):
    data, db = body(), get_db()
    p = get_or_404(db, "products", product_id, "Product")
    name = req_text(data, "name", False) or p["name"]
    slug = req_slug(data, False) or p["slug"]
    description = str(data["description"]) if "description" in data else p["description"]
    status = data.get("status", p["status"])
    if status not in STATUSES:
        raise invalid(f"'status' must be one of {', '.join(STATUSES)}.")
    cat_id = data.get("category_id", p["category_id"])
    if "category_id" in data and (not isinstance(cat_id, int) or one(db, "SELECT id FROM categories WHERE id = ?", (cat_id,)) is None):
        raise invalid("'category_id' must reference an existing category.")
    if status == "published":
        n = one(db, "SELECT COUNT(*) AS n FROM skus WHERE product_id = ? AND is_active = 1", (product_id,))["n"]
        if n == 0:
            raise ApiError(422, "NO_ACTIVE_SKU", "A product needs at least one active SKU before it can be published.")
    db.execute("UPDATE products SET name=?, slug=?, description=?, status=?, category_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
               (name, slug, description, status, cat_id, product_id))
    db.commit()
    return jsonify(product_json(db, get_or_404(db, "products", product_id, "Product")))


# ---------- variants & SKUs ----------
@admin_bp.post("/products/<int:product_id>/variants")
@admin_required
def create_variant(product_id):
    data, db = body(), get_db()
    get_or_404(db, "products", product_id, "Product")
    opts = data.get("option_values")
    if not isinstance(opts, dict) or not opts or not all(
            isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip() for k, v in opts.items()):
        raise invalid("'option_values' must be a non-empty object of text values, e.g. {\"color\": \"black\"}.")
    existing = one(db, "SELECT option_values FROM variants WHERE product_id = ? LIMIT 1", (product_id,))
    if existing and set(json.loads(existing["option_values"])) != set(opts):
        raise invalid("All variants of a product must use the same option names.")
    cur = db.execute("INSERT INTO variants (product_id, option_values) VALUES (?, ?)",
                     (product_id, json.dumps(opts, sort_keys=True)))
    db.commit()
    v = get_or_404(db, "variants", cur.lastrowid, "Variant")
    return jsonify({"id": v["id"], "product_id": product_id, "option_values": json.loads(v["option_values"])}), 201


@admin_bp.post("/products/<int:product_id>/skus")
@admin_required
def create_sku(product_id):
    data, db = body(), get_db()
    get_or_404(db, "products", product_id, "Product")
    code = req_text(data, "sku_code")
    price = req_int(data, "price_minor")
    stock = req_int(data, "stock_qty", default=0)
    active = req_bool(data, "is_active", True)
    variant_id = data.get("variant_id")
    has_variants = one(db, "SELECT id FROM variants WHERE product_id = ? LIMIT 1", (product_id,)) is not None
    if variant_id is None and has_variants:
        raise invalid("This product has variants; 'variant_id' is required.")
    if variant_id is not None:
        v = one(db, "SELECT product_id FROM variants WHERE id = ?", (variant_id,)) if isinstance(variant_id, int) else None
        if v is None or v["product_id"] != product_id:
            raise invalid("'variant_id' must be a variant of this product.")
    cur = db.execute("INSERT INTO skus (product_id, variant_id, sku_code, price_minor, stock_qty, is_active) VALUES (?,?,?,?,?,?)",
                     (product_id, variant_id, code, price, stock, int(active)))
    db.commit()
    return jsonify(sku_json(get_or_404(db, "skus", cur.lastrowid, "SKU"))), 201


@admin_bp.patch("/skus/<int:sku_id>")
@admin_required
def update_sku(sku_id):
    data, db = body(), get_db()
    s = get_or_404(db, "skus", sku_id, "SKU")
    price = req_int(data, "price_minor", default=s["price_minor"]) if "price_minor" in data else s["price_minor"]
    stock = req_int(data, "stock_qty", default=s["stock_qty"]) if "stock_qty" in data else s["stock_qty"]
    active = req_bool(data, "is_active", bool(s["is_active"]))
    db.execute("UPDATE skus SET price_minor=?, stock_qty=?, is_active=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
               (price, stock, int(active), sku_id))
    db.commit()
    return jsonify(sku_json(get_or_404(db, "skus", sku_id, "SKU")))
