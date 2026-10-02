"""Reproducible sample data. Safe to run repeatedly:  python seed.py"""
import json
import os
import sys

from db import connect, migrate


def _id(conn, sql, args):
    return conn.execute(sql, args).fetchone()[0]


def seed(path):
    migrate(path)
    conn = connect(path)
    cat = lambda name, slug, parent: (conn.execute(
        "INSERT OR IGNORE INTO categories (parent_id, name, slug) VALUES (?,?,?)", (parent, name, slug)),
        _id(conn, "SELECT id FROM categories WHERE slug=?", (slug,)))[1]
    prod = lambda c, name, slug, desc, status: (conn.execute(
        "INSERT OR IGNORE INTO products (category_id, name, slug, description, status) VALUES (?,?,?,?,?)",
        (c, name, slug, desc, "draft")), _id(conn, "SELECT id FROM products WHERE slug=?", (slug,)))[1]
    var = lambda p, opts: (conn.execute(
        "INSERT OR IGNORE INTO variants (product_id, option_values) VALUES (?,?)", (p, json.dumps(opts, sort_keys=True))),
        _id(conn, "SELECT id FROM variants WHERE product_id=? AND option_values=?", (p, json.dumps(opts, sort_keys=True))))[1]
    sku = lambda p, v, code, price, stock: conn.execute(
        "INSERT OR IGNORE INTO skus (product_id, variant_id, sku_code, price_minor, stock_qty) VALUES (?,?,?,?,?)",
        (p, v, code, price, stock))

    # two-level category tree
    electronics = cat("Electronics", "electronics", None)
    laptops = cat("Laptops", "laptops", electronics)
    books = cat("Books", "books", None)
    textbooks = cat("Textbooks", "textbooks", books)

    # Product 1: variants (ram x color). 8GB/black is intentionally NOT created = unavailable combination.
    laptop = prod(laptops, "HP ProBook (Used)", "hp-probook-used", "Refurbished student laptop.", "published")
    v1 = var(laptop, {"ram": "8GB", "color": "silver"})
    v2 = var(laptop, {"ram": "16GB", "color": "silver"})
    v3 = var(laptop, {"ram": "16GB", "color": "black"})
    sku(laptop, v1, "HP-PB-8-SIL", 4500000, 3)
    sku(laptop, v2, "HP-PB-16-SIL", 5500000, 2)
    sku(laptop, v3, "HP-PB-16-BLK", 5600000, 1)

    # Product 2: no variants, one SKU
    book = prod(textbooks, "Data Structures Textbook", "data-structures-textbook", "Second-hand, good condition.", "published")
    sku(book, None, "BOOK-DS-001", 150000, 5)

    # Product 3: no variants, out of stock (stock 0)
    lamp = prod(electronics, "Study Desk Lamp", "study-desk-lamp", "LED lamp for dorm desks.", "published")
    sku(lamp, None, "LAMP-001", 90000, 0)

    for pid in (laptop, book, lamp):  # publish only because each now has an active SKU
        conn.execute("UPDATE products SET status='published' WHERE id=?", (pid,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    target = os.environ.get("DATABASE_PATH", "unimart.db")
    seed(target)
    print(f"Seeded {target}")
