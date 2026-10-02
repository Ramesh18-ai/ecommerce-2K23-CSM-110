-- Sprint 2: catalog foundation. Money = integer minor units (paisa). Foreign keys need PRAGMA foreign_keys=ON (done in db.py).
CREATE TABLE categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id  INTEGER REFERENCES categories(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    name       TEXT NOT NULL CHECK (length(trim(name)) > 0),
    slug       TEXT NOT NULL UNIQUE CHECK (length(slug) > 0),
    is_active  INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (parent_id IS NULL OR parent_id <> id)
);

CREATE TABLE products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    name        TEXT NOT NULL CHECK (length(trim(name)) > 0),
    slug        TEXT NOT NULL UNIQUE CHECK (length(slug) > 0),
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE variants (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE ON UPDATE CASCADE,
    option_values TEXT NOT NULL CHECK (json_valid(option_values)), -- canonical JSON, e.g. {"color":"black","ram":"16GB"}
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (product_id, option_values)
);

CREATE TABLE skus (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    variant_id  INTEGER REFERENCES variants(id) ON DELETE RESTRICT ON UPDATE CASCADE, -- NULL = product has no variants
    sku_code    TEXT NOT NULL UNIQUE CHECK (length(trim(sku_code)) > 0),
    price_minor INTEGER NOT NULL CHECK (price_minor >= 0),
    currency    TEXT NOT NULL DEFAULT 'PKR',
    stock_qty   INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Schema only in Sprint 2 (upload/serving is Sprint 3).
CREATE TABLE assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER REFERENCES products(id) ON DELETE CASCADE,
    variant_id  INTEGER REFERENCES variants(id) ON DELETE CASCADE,
    storage_key TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'gallery' CHECK (role IN ('primary', 'gallery', 'thumbnail')),
    alt_text    TEXT NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    CHECK (product_id IS NOT NULL OR variant_id IS NOT NULL)
);

CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_skus_product ON skus(product_id);
CREATE INDEX idx_categories_parent ON categories(parent_id);
