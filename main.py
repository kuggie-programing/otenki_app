import os
import sqlite3
import datetime

from flask import Flask, request, jsonify, g
from flask_cors import CORS

app = Flask(__name__)

# GitHub Pagesなど別オリジンのフロントエンドから /api/* を利用できるようにする。
# 本番運用で公開範囲を限定する場合は、GitHub PagesのURLに変更してください。
CORS(app, resources={r"/api/*": {"origins": "*"}})

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "app.db",
)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)

    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS groups (
            group_code TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_code TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(group_code, name)
        );

        CREATE TABLE IF NOT EXISTS safety_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_code TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS hazard_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_code TEXT NOT NULL,
            author TEXT NOT NULL,
            image TEXT NOT NULL,
            text TEXT NOT NULL,
            lat REAL,
            lon REAL,
            created_at TEXT NOT NULL
        );
        """
    )

    db.commit()
    db.close()


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def bad_request(msg, code=400):
    return jsonify({"error": msg}), code


def group_exists(db, group_code):
    return (
        db.execute(
            "SELECT 1 FROM groups WHERE group_code = ?",
            (group_code,),
        ).fetchone()
        is not None
    )


# ---------- ヘルスチェック ----------
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ---------- グループ登録 / ログイン ----------
@app.route("/api/group/register", methods=["POST"])
def register_group():
    try:
        data = request.get_json(silent=True) or {}

        group_code = str(data.get("group_code", "")).strip()
        password = str(data.get("password", "")).strip()
        name = str(data.get("name", "")).strip()

        if not group_code or not password or not name:
            return bad_request(
                "グループコード・パスワード・名前は必須です。"
            )

        db = get_db()

        existing = db.execute(
            "SELECT 1 FROM groups WHERE group_code = ?",
            (group_code,),
        ).fetchone()

        if existing:
            return bad_request(
                "そのグループコードは既に使われています。"
                "ログインを使ってください。",
                409,
            )

        created_at = now_iso()

        db.execute(
            """
            INSERT INTO groups (group_code, password, created_at)
            VALUES (?, ?, ?)
            """,
            (group_code, password, created_at),
        )

        db.execute(
            """
            INSERT INTO members (group_code, name, created_at)
            VALUES (?, ?, ?)
            """,
            (group_code, name, created_at),
        )

        db.commit()

        members = [
            row["name"]
            for row in db.execute(
                """
                SELECT name
                FROM members
                WHERE group_code = ?
                ORDER BY id
                """,
                (group_code,),
            ).fetchall()
        ]

        return jsonify(
            {
                "group_code": group_code,
                "members": members,
            }
        )

    except sqlite3.IntegrityError as e:
        return bad_request(f"データベースエラー: {str(e)}", 409)

    except Exception as e:
        return bad_request(f"サーバーエラー: {str(e)}", 500)


@app.route("/api/group/login", methods=["POST"])
def login_group():
    try:
        data = request.get_json(silent=True) or {}

        group_code = str(data.get("group_code", "")).strip()
        password = str(data.get("password", "")).strip()
        name = str(data.get("name", "")).strip()

        if not group_code or not password or not name:
            return bad_request(
                "グループコード・パスワード・名前は必須です。"
            )

        db = get_db()

        row = db.execute(
            "SELECT * FROM groups WHERE group_code = ?",
            (group_code,),
        ).fetchone()

        if not row:
            return bad_request(
                "そのグループコードは存在しません。"
                "新規登録してください。",
                404,
            )

        if row["password"] != password:
            return bad_request(
                "パスワードが違います。",
                401,
            )

        db.execute(
            """
            INSERT OR IGNORE INTO members
                (group_code, name, created_at)
            VALUES (?, ?, ?)
            """,
            (group_code, name, now_iso()),
        )

        db.commit()

        members = [
            r["name"]
            for r in db.execute(
                """
                SELECT name
                FROM members
                WHERE group_code = ?
                ORDER BY id
                """,
                (group_code,),
            ).fetchall()
        ]

        return jsonify(
            {
                "group_code": group_code,
                "members": members,
            }
        )

    except Exception as e:
        return bad_request(f"サーバーエラー: {str(e)}", 500)


# ---------- メンバー管理 ----------
@app.route("/api/members/<group_code>", methods=["GET"])
def get_members(group_code):
    try:
        db = get_db()

        if not group_exists(db, group_code):
            return bad_request("グループが存在しません。", 404)

        members = [
            r["name"]
            for r in db.execute(
                """
                SELECT name
                FROM members
                WHERE group_code = ?
                ORDER BY id
                """,
                (group_code,),
            ).fetchall()
        ]

        return jsonify({"members": members})

    except Exception as e:
        return bad_request(f"サーバーエラー: {str(e)}", 500)


@app.route("/api/members/<group_code>", methods=["POST"])
def add_member(group_code):
    try:
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "")).strip()

        if not name:
            return bad_request("名前は必須です。")

        db = get_db()

        if not group_exists(db, group_code):
            return bad_request("グループが存在しません。", 404)

        db.execute(
            """
            INSERT OR IGNORE INTO members
                (group_code, name, created_at)
            VALUES (?, ?, ?)
            """,
            (group_code, name, now_iso()),
        )

        db.commit()

        members = [
            r["name"]
            for r in db.execute(
                """
                SELECT name
                FROM members
                WHERE group_code = ?
                ORDER BY id
                """,
                (group_code,),
            ).fetchall()
        ]

        return jsonify({"members": members})

    except Exception as e:
        return bad_request(f"サーバーエラー: {str(e)}", 500)


@app.route("/api/members/<group_code>/<name>", methods=["DELETE"])
def remove_member(group_code, name):
    try:
        db = get_db()

        if not group_exists(db, group_code):
            return bad_request("グループが存在しません。", 404)

        db.execute(
            """
            DELETE FROM members
            WHERE group_code = ? AND name = ?
            """,
            (group_code, name),
        )

        db.commit()

        members = [
            r["name"]
            for r in db.execute(
                """
                SELECT name
                FROM members
                WHERE group_code = ?
                ORDER BY id
                """,
                (group_code,),
            ).fetchall()
        ]

        return jsonify({"members": members})

    except Exception as e:
        return bad_request(f"サーバーエラー: {str(e)}", 500)


# ---------- 安否確認 ----------
@app.route("/api/safety/<group_code>", methods=["GET"])
def get_safety(group_code):
    try:
        db = get_db()

        if not group_exists(db, group_code):
            return bad_request("グループが存在しません。", 404)

        rows = db.execute(
            """
            SELECT
                s1.name,
                s1.status,
                s1.created_at
            FROM safety_status AS s1
            INNER JOIN (
                SELECT
                    name,
                    MAX(id) AS max_id
                FROM safety_status
                WHERE group_code = ?
                GROUP BY name
            ) AS s2
                ON s1.name = s2.name
                AND s1.id = s2.max_id
            WHERE s1.group_code = ?
            ORDER BY s1.created_at DESC
            """,
            (group_code, group_code),
        ).fetchall()

        result = [
            {
                "name": r["name"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

        return jsonify({"statuses": result})

    except Exception as e:
        return bad_request(f"サーバーエラー: {str(e)}", 500)


@app.route("/api/safety/<group_code>", methods=["POST"])
def post_safety(group_code):
    try:
        data = request.get_json(silent=True) or {}

        name = str(data.get("name", "")).strip()
        status = str(data.get("status", "")).strip()

        if not name or status not in ("safe", "messy", "sos"):
            return bad_request(
                "名前とステータス(safe/messy/sos)は必須です。"
            )

        db = get_db()

        if not group_exists(db, group_code):
            return bad_request("グループが存在しません。", 404)

        db.execute(
            """
            INSERT INTO safety_status
                (group_code, name, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (group_code, name, status, now_iso()),
        )

        db.commit()

        return jsonify({"ok": True})

    except Exception as e:
        return bad_request(f"サーバーエラー: {str(e)}", 500)


# ---------- 危険みーつけた ----------
@app.route("/api/hazard/<group_code>", methods=["GET"])
def get_hazard(group_code):
    try:
        db = get_db()

        if not group_exists(db, group_code):
            return bad_request("グループが存在しません。", 404)

        rows = db.execute(
            """
            SELECT
                author,
                image,
                text,
                lat,
                lon,
                created_at
            FROM hazard_posts
            WHERE group_code = ?
            ORDER BY id DESC
            LIMIT 50
            """,
            (group_code,),
        ).fetchall()

        posts = [dict(row) for row in rows]

        return jsonify({"posts": posts})

    except Exception as e:
        return bad_request(f"サーバーエラー: {str(e)}", 500)


@app.route("/api/hazard/<group_code>", methods=["POST"])
def post_hazard(group_code):
    try:
        data = request.get_json(silent=True) or {}

        author = str(data.get("author", "")).strip()
        image = str(data.get("image", "")).strip()
        text = str(data.get("text", "")).strip()
        lat = data.get("lat")
        lon = data.get("lon")

        if not author or not image or not text:
            return bad_request(
                "投稿者・画像・内容は必須です。"
            )

        db = get_db()

        if not group_exists(db, group_code):
            return bad_request("グループが存在しません。", 404)

        db.execute(
            """
            INSERT INTO hazard_posts
                (group_code, author, image, text, lat, lon, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                group_code,
                author,
                image,
                text,
                lat,
                lon,
                now_iso(),
            ),
        )

        db.commit()

        return jsonify({"ok": True})

    except Exception as e:
        return bad_request(f"サーバーエラー: {str(e)}", 500)


init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
