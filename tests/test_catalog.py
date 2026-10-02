import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from db import connect  # noqa: E402
from seed import seed  # noqa: E402

ADMIN = {"Authorization": "Bearer admin-test-token"}
STUDENT = {"Authorization": "Bearer student-test-token"}
BASE = "/api/v1/admin"


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app({"DATABASE": self.path, "ADMIN_TOKEN": "admin-test-token",
                               "STUDENT_TOKEN": "student-test-token", "TESTING": True})
        self.c = self.app.test_client()

    def tearDown(self):
        os.remove(self.path)

    def post(self, url, json=None, headers=ADMIN):
        return self.c.post(BASE + url, json=json, headers=headers)

    def patch(self, url, json=None, headers=ADMIN):
        return self.c.patch(BASE + url, json=json, headers=headers)

    def make_category(self, slug="laptops", parent=None):
        return self.post("/categories", {"name": slug.title(), "slug": slug, "parent_id": parent}).get_json()

    def make_product(self, slug="probook", cat=None):
        cat = cat or self.make_category()["id"]
        return self.post("/products", {"name": "ProBook", "slug": slug, "category_id": cat}).get_json()


class TestCreation(Base):
    def test_create_category_product_variant_sku(self):
        p = self.make_product()
        self.assertEqual(p["status"], "draft")
        v = self.post(f"/products/{p['id']}/variants", {"option_values": {"ram": "8GB"}})
        self.assertEqual(v.status_code, 201)
        s = self.post(f"/products/{p['id']}/skus", {"sku_code": "A-1", "price_minor": 100, "stock_qty": 2,
                                                    "variant_id": v.get_json()["id"]})
        self.assertEqual(s.status_code, 201)
        self.assertTrue(s.get_json()["in_stock"])
        listing = self.c.get(BASE + "/products", headers=ADMIN).get_json()["data"]
        self.assertEqual(len(listing[0]["skus"]), 1)

    def test_required_fields_rejected(self):
        self.assertEqual(self.post("/categories", {"slug": "x"}).status_code, 422)
        self.assertEqual(self.post("/products", {"name": "x", "slug": "x"}).status_code, 422)
        p = self.make_product()
        self.assertEqual(self.post(f"/products/{p['id']}/skus", {"sku_code": "A"}).status_code, 422)

    def test_money_must_be_integer(self):
        p = self.make_product()
        r = self.post(f"/products/{p['id']}/skus", {"sku_code": "A", "price_minor": 10.5})
        self.assertEqual(r.status_code, 422)

    def test_new_product_must_be_draft(self):
        cat = self.make_category()["id"]
        r = self.post("/products", {"name": "x", "slug": "x", "category_id": cat, "status": "published"})
        self.assertEqual(r.status_code, 422)


class TestDuplicates(Base):
    def test_duplicate_product_slug_409(self):
        p = self.make_product("same")
        r = self.post("/products", {"name": "Other", "slug": "same", "category_id": p["category_id"]})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["error"]["code"], "DUPLICATE_SLUG")

    def test_duplicate_category_slug_409(self):
        self.make_category("dup")
        self.assertEqual(self.post("/categories", {"name": "Dup2", "slug": "dup"}).status_code, 409)

    def test_duplicate_sku_code_409(self):
        p = self.make_product()
        self.post(f"/products/{p['id']}/skus", {"sku_code": "X-1", "price_minor": 1})
        r = self.post(f"/products/{p['id']}/skus", {"sku_code": "X-1", "price_minor": 2})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["error"]["code"], "DUPLICATE_SKU")

    def test_duplicate_variant_409(self):
        p = self.make_product()
        self.post(f"/products/{p['id']}/variants", {"option_values": {"ram": "8GB", "color": "black"}})
        r = self.post(f"/products/{p['id']}/variants", {"option_values": {"color": "black", "ram": "8GB"}})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["error"]["code"], "DUPLICATE_VARIANT")


class TestCategoryHierarchy(Base):
    def test_self_parent_rejected(self):
        a = self.make_category("a")
        self.assertEqual(self.patch(f"/categories/{a['id']}", {"parent_id": a["id"]}).status_code, 422)

    def test_cycle_rejected(self):
        a = self.make_category("a")
        b = self.make_category("b", a["id"])
        c = self.make_category("c", b["id"])
        r = self.patch(f"/categories/{a['id']}", {"parent_id": c["id"]})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.get_json()["error"]["code"], "CATEGORY_CYCLE")

    def test_tree_is_nested(self):
        a = self.make_category("a")
        self.make_category("b", a["id"])
        tree = self.c.get(BASE + "/categories", headers=ADMIN).get_json()["data"]
        self.assertEqual(tree[0]["children"][0]["slug"], "b")

    def test_deactivating_parent_deactivates_children(self):
        a = self.make_category("a")
        b = self.make_category("b", a["id"])
        self.patch(f"/categories/{a['id']}", {"is_active": False})
        tree = self.c.get(BASE + "/categories", headers=ADMIN).get_json()["data"]
        self.assertFalse(tree[0]["children"][0]["is_active"])
        r = self.patch(f"/categories/{b['id']}", {"is_active": True})
        self.assertEqual(r.status_code, 409)

    def test_cannot_put_product_in_inactive_category(self):
        a = self.make_category("a")
        self.patch(f"/categories/{a['id']}", {"is_active": False})
        r = self.post("/products", {"name": "x", "slug": "x", "category_id": a["id"]})
        self.assertEqual(r.status_code, 422)


class TestVariantsSkusStock(Base):
    def test_sku_requires_variant_when_product_has_variants(self):
        p = self.make_product()
        self.post(f"/products/{p['id']}/variants", {"option_values": {"ram": "8GB"}})
        r = self.post(f"/products/{p['id']}/skus", {"sku_code": "Z", "price_minor": 1})
        self.assertEqual(r.status_code, 422)

    def test_variant_of_another_product_rejected(self):
        p1, p2 = self.make_product("p1"), self.make_product("p2", self.make_category("other")["id"])
        v = self.post(f"/products/{p1['id']}/variants", {"option_values": {"ram": "8GB"}}).get_json()
        r = self.post(f"/products/{p2['id']}/skus", {"sku_code": "Z", "price_minor": 1, "variant_id": v["id"]})
        self.assertEqual(r.status_code, 422)

    def test_variants_must_share_option_names(self):
        p = self.make_product()
        self.post(f"/products/{p['id']}/variants", {"option_values": {"ram": "8GB"}})
        r = self.post(f"/products/{p['id']}/variants", {"option_values": {"color": "red"}})
        self.assertEqual(r.status_code, 422)

    def test_missing_combination_has_no_sku_row(self):
        seed(self.path)
        conn = connect(self.path)
        n = conn.execute("SELECT COUNT(*) FROM variants WHERE option_values LIKE '%8GB%' AND option_values LIKE '%black%'").fetchone()[0]
        self.assertEqual(n, 0)

    def test_negative_stock_rejected_by_api(self):
        p = self.make_product()
        s = self.post(f"/products/{p['id']}/skus", {"sku_code": "S", "price_minor": 1, "stock_qty": 1}).get_json()
        self.assertEqual(self.patch(f"/skus/{s['id']}", {"stock_qty": -1}).status_code, 422)
        self.assertEqual(self.patch(f"/skus/{s['id']}", {"price_minor": -5}).status_code, 422)

    def test_negative_stock_rejected_by_database(self):
        p = self.make_product()
        conn = connect(self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO skus (product_id, sku_code, price_minor, stock_qty) VALUES (?, 'N', 1, -1)", (p["id"],))

    def test_out_of_stock_flag(self):
        p = self.make_product()
        s = self.post(f"/products/{p['id']}/skus", {"sku_code": "S", "price_minor": 1, "stock_qty": 1}).get_json()
        r = self.patch(f"/skus/{s['id']}", {"stock_qty": 0}).get_json()
        self.assertFalse(r["in_stock"])

    def test_publish_requires_active_sku(self):
        p = self.make_product()
        r = self.patch(f"/products/{p['id']}", {"status": "published"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.get_json()["error"]["code"], "NO_ACTIVE_SKU")
        self.post(f"/products/{p['id']}/skus", {"sku_code": "S", "price_minor": 1})
        self.assertEqual(self.patch(f"/products/{p['id']}", {"status": "published"}).status_code, 200)

    def test_two_skus_may_share_a_price(self):
        p = self.make_product()
        self.assertEqual(self.post(f"/products/{p['id']}/skus", {"sku_code": "A", "price_minor": 5}).status_code, 201)
        self.assertEqual(self.post(f"/products/{p['id']}/skus", {"sku_code": "B", "price_minor": 5}).status_code, 201)


class TestDatabaseIntegrity(Base):
    def test_foreign_keys_enforced(self):
        conn = connect(self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO products (category_id, name, slug) VALUES (999, 'x', 'x')")

    def test_cannot_delete_category_with_products(self):
        p = self.make_product()
        conn = connect(self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM categories WHERE id = ?", (p["category_id"],))


class TestAuthorization(Base):
    ROUTES = [("post", "/categories"), ("get", "/categories"), ("patch", "/categories/1"),
              ("post", "/products"), ("get", "/products"), ("patch", "/products/1"),
              ("post", "/products/1/variants"), ("post", "/products/1/skus"), ("patch", "/skus/1")]

    def call(self, method, url, headers):
        return getattr(self.c, method)(BASE + url, json={}, headers=headers)

    def test_no_token_401(self):
        for m, u in self.ROUTES:
            self.assertEqual(self.call(m, u, {}).status_code, 401, f"{m} {u}")

    def test_bad_token_401(self):
        for m, u in self.ROUTES:
            self.assertEqual(self.call(m, u, {"Authorization": "Bearer nope"}).status_code, 401, f"{m} {u}")

    def test_non_admin_403(self):
        for m, u in self.ROUTES:
            self.assertEqual(self.call(m, u, STUDENT).status_code, 403, f"{m} {u}")


class TestSeed(Base):
    def test_seed_is_reproducible_and_meets_minimums(self):
        seed(self.path)
        seed(self.path)  # running twice must not duplicate anything
        conn = connect(self.path)
        count = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        self.assertEqual((count("categories"), count("products"), count("variants"), count("skus")), (4, 3, 3, 5))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM categories WHERE parent_id IS NOT NULL").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
