import os

from flask import Flask

try:  # optional: load .env if python-dotenv is installed
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db import close_db, migrate
from errors import register_error_handlers
from routes import admin_bp


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        DATABASE=os.environ.get("DATABASE_PATH", "unimart.db"),
        ADMIN_TOKEN=os.environ.get("ADMIN_TOKEN"),
        STUDENT_TOKEN=os.environ.get("STUDENT_TOKEN"),
    )
    if config:
        app.config.update(config)
    migrate(app.config["DATABASE"])
    app.teardown_appcontext(close_db)
    register_error_handlers(app)
    app.register_blueprint(admin_bp)
    return app


if __name__ == "__main__":
    create_app().run(debug=True)
