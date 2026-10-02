"""Prints the admin demo (create category, product, variant, SKU, then read back). Uses a throwaway DB."""
import json
import os
import tempfile

from app import create_app

fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
app = create_app({"DATABASE": path, "ADMIN_TOKEN": "demo-secret", "STUDENT_TOKEN": "demo-student"})
c = app.test_client()
H = {"Authorization": "Bearer demo-secret"}


def call(method, url, body=None, headers=H, note=""):
    r = getattr(c, method)("/api/v1/admin" + url, json=body, headers=headers)
    print(f"### {note}" if note else "")
    shown = "Authorization: Bearer <REDACTED>\n" if headers else ""
    print(f"```http\n{method.upper()} /api/v1/admin{url}\n{shown}{json.dumps(body, indent=2) if body else ''}\n```")
    print(f"Response `{r.status_code}`:\n```json\n{json.dumps(r.get_json(), indent=2)}\n```\n")
    return r.get_json()


cat = call("post", "/categories", {"name": "Laptops", "slug": "laptops"}, note="1. Create a category")
prod = call("post", "/products", {"name": "HP ProBook", "slug": "hp-probook", "description": "Used laptop", "category_id": cat["id"]}, note="2. Create a draft product")
var = call("post", f"/products/{prod['id']}/variants", {"option_values": {"ram": "8GB", "color": "silver"}}, note="3. Create a variant")
call("post", f"/products/{prod['id']}/skus", {"sku_code": "HP-PB-8-SIL", "price_minor": 4500000, "stock_qty": 3, "variant_id": var["id"]}, note="4. Create a SKU (price in minor units: 4500000 = PKR 45,000.00)")
call("get", "/products", note="5. Retrieve products with variants and SKUs")
call("post", f"/products/{prod['id']}/skus", {"sku_code": "HP-PB-8-SIL", "price_minor": 1, "variant_id": var["id"]}, note="6. Duplicate SKU is rejected (clean 409, no traceback)")
call("post", "/categories", {"name": "X", "slug": "x"}, headers={}, note="7. No token is rejected")
os.remove(path)
