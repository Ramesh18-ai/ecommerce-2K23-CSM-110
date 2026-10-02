## Catalog (Sprint 2) – local setup

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then edit the tokens
python seed.py                                         # creates unimart.db with sample catalog
python app.py                                          # http://127.0.0.1:5000
python -m unittest discover -s tests -v                # run the tests
```

| Variable | Purpose |
|---|---|
| `DATABASE_PATH` | SQLite file (default `unimart.db`) |
| `ADMIN_TOKEN` | Bearer token that grants administrator access |
| `STUDENT_TOKEN` | Optional bearer token for a non-admin user (gets 403 on admin routes) |

Call the API with `Authorization: Bearer <ADMIN_TOKEN>`. Full route list: `docs/SPRINT_2.md`.
