import functools
import json
import os
from datetime import datetime
from typing import Optional, Any

from flask import Flask, request
import redis
from redis.commands.json.path import Path

schema = {
    'format': 'shield.io dict',
    'meta': 'dict'
}


class DbManagerDummy:
    store: dict[str, Any]
    def __init__(self, *args, **kwargs):
        self.store = {}

    def store_value(self, key: str, value: dict) -> None:
        print(f"Storing {key}: {value}")
        self.store[key] = value

    def get_value(self, key: str) -> Optional[dict]:
        print(f"Getting {key}")
        return self.store.get(key, None)

    def set_message(self, key: str, message: str) -> None:
        print(f"Setting a message of {key}: {message}")
        self.store[key]['message'] = message

    def __contains__(self, key: str) -> bool:
        print(f"Checking if badge named {key} is in store")
        return key in self.store

    def list(self):
        return list(self.store.keys())

class DbManager(DbManagerDummy):
    db: redis.Redis

    def __init__(self, host: str, port: str):
        super().__init__()
        self.db = redis.Redis(host, port, db=0, decode_responses=True)

    def store_value(self, key: str, value: dict) -> None:
        self.db.json().set(key, Path.root_path(), value)

    def get_value(self, key: str) -> Optional[dict]:
        return self.db.json().get(key)

    def set_message(self, key: str, message: str) -> None:
        self.db.json().set(key, "$.format.message", message)
        self.db.json().set(key, "$.meta.last_seen", datetime.timestamp(datetime.now()))

    def __contains__(self, key: str) -> bool:
        return self.db.exists(key)

    def list(self):
        return [self.db.json().get(x) for x in self.db.keys()]

    def delete(self, key: str) -> None:
        self.db.json().delete(key)

    def close(self, e=None) -> None:
        self.db.close()

def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY="dev",
    )
    app.config.from_prefixed_env()
    db = DbManager(
        os.environ.get("DB_HOST", "localhost"),
        os.environ.get("DB_PORT", 6379))
    app.teardown_appcontext(db.close)

    def api_required(func):
        @functools.wraps(func)
        def decorator(*args, **kwargs):
            api_key = request.args.get("api_key", None)
            if api_key is None:
                return "Please provide an API key", 400
            # Check if API key is correct and valid
            print(os.environ.get("API_KEY"), api_key)
            if api_key == os.environ.get("API_KEY"):
                return func(*args, **kwargs)
            else:
                return "The provided API key is not valid", 403
        return decorator

    @app.route("/garbage_out/")
    @api_required
    def garbage_out():
        name = request.args.get("badge_name", None)

        if name is None:
            return {'schemaVersion': 1, 'label': 'Err', 'message': "no name provided", 'color': 'red' }

        badge = db.get_value(name)

        if badge is None:
            return {'schemaVersion': 1, 'label': 'Err', 'message': "no badge data", 'color': 'red' }

        if float(badge['meta']['last_seen']) + float(badge['meta']['expires']) < datetime.timestamp(datetime.now()):
            badge['format']['message'] = 'AWOL'

        return badge['format']

    @app.route("/garbage_in/")
    @api_required
    def garbage_in():
        message = request.args.get("message", None)
        badge_data = request.args.get("badge_data", None)
        badge_name = request.args.get("badge_name", None)
        expire = request.args.get("expire", 60)

        if badge_name is None:
            return "Please provide badge name", 422

        if badge_data is not None:
            db.store_value(badge_name, {
                'meta': {
                    'last_seen': datetime.timestamp(datetime.now()),
                    'expires': expire
                },
                'format': json.loads(badge_data.replace("'", "\""))
            })
            return "ok", 200

        if message is None:
            return "Please provide message or badge data", 422
        if badge_name not in db:
            return "Badge name not found", 422
        db.set_message(badge_name, message)
        return "ok", 200

    @app.route("/list/")
    @api_required
    def badge_list():
        return db.list()

    @app.route("/delete")
    @api_required
    def delete_badge(key: str):
        db.delete(key)

    return app