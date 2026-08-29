import os
import sqlite3
import datetime
from contextlib import closing

from flask import Flask, request, jsonify, g
from flask_cors import CORS


# =========================================================
# Flask
# =========================================================

app = Flask(__name__)

# ---------------------------------------------------------
# 環境変数
# ---------------------------------------------------------

# 例:
# CORS_ORIGINS=https://kuggie-programing.github.io
#
# 複数指定する場合:
# CORS_ORIGINS=https://example.com,https://example2.com
#
# 未設定時は *（開発用）
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").strip()

if CORS_ORIGINS == "*":
    cors_origins = "*"
else:
    cors_origins = [
        origin.strip()
        for origin in CORS_ORIGINS.split(",")
        if origin.strip()
    ]

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": cors_origins
        }
    }
)


# =========================================================
# DB
# =========================================================

# Renderで永続化する場合は、Render Diskなどを使って
# DB_DIRを指定する。
#
# 例:
# DB_DIR=/var/data
#
# 未設定の場合は、このmain.pyと同じフォルダ。
DB_DIR = os.environ.get(
    "DB_DIR",
    os.path.dirname(os.path.abspath(__file__))
)

os.makedirs(DB_DIR, exist_ok=True)

DB_PATH = os.path.join(
    DB_DIR,
    "app.db"
)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            DB_PATH,
            timeout=30
        )

        g.db.row_factory = sqlite3.Row

        # SQLiteの同時アクセスを少し安定させる
        g.db.execute("PRAGMA busy_timeout = 30000")
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    try:
        db.execute("PRAGMA busy_timeout = 30000")
        db.execute("PRAGMA foreign_keys = ON")

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

                UNIQUE(group_code, name),

                FOREIGN KEY(group_code)
                    REFERENCES groups(group_code)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS safety_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_code TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,

                FOREIGN KEY(group_code)
                    REFERENCES groups(group_code)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS hazard_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_code TEXT NOT NULL,
                author TEXT NOT NULL,
                image TEXT NOT NULL,
                text TEXT NOT NULL,

                latitude REAL,
                longitude REAL,

                -- GPSの精度（メートル）
                accuracy REAL,

                created_at TEXT NOT NULL,

                FOREIGN KEY(group_code)
                    REFERENCES groups(group_code)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_members_group
                ON members(group_code);

            CREATE INDEX IF NOT EXISTS idx_safety_group
                ON safety_status(group_code);

            CREATE INDEX IF NOT EXISTS idx_hazard_group
                ON hazard_posts(group_code);

            CREATE INDEX IF NOT EXISTS idx_hazard_created
                ON hazard_posts(created_at);
            """
        )

        # -------------------------------------------------
        # 既存DBへの簡易マイグレーション
        # -------------------------------------------------
        #
        # 以前のDBではlat / lonだったため、
        # latitude / longitude / accuracyを追加する。
        #

        columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(hazard_posts)"
            ).fetchall()
        }

        if "latitude" not in columns:
            db.execute(
                """
                ALTER TABLE hazard_posts
                ADD COLUMN latitude REAL
                """
            )

        if "longitude" not in columns:
            db.execute(
                """
                ALTER TABLE hazard_posts
                ADD COLUMN longitude REAL
                """
            )

        if "accuracy" not in columns:
            db.execute(
                """
                ALTER TABLE hazard_posts
                ADD COLUMN accuracy REAL
                """
            )

        # 旧lat/lonから新しい列へ移行
        if "lat" in columns:
            db.execute(
                """
                UPDATE hazard_posts
                SET latitude = lat
                WHERE latitude IS NULL
                """
            )

        if "lon" in columns:
            db.execute(
                """
                UPDATE hazard_posts
                SET longitude = lon
                WHERE longitude IS NULL
                """
            )

        db.commit()

    finally:
        db.close()


# =========================================================
# 共通関数
# =========================================================

def now_iso():
    return datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()


def bad_request(msg, code=400):
    return jsonify({
        "ok": False,
        "error": msg
    }), code


def group_exists(db, group_code):
    return (
        db.execute(
            """
            SELECT 1
            FROM groups
            WHERE group_code = ?
            """,
            (group_code,)
        ).fetchone()
        is not None
    )


def get_members_from_db(db, group_code):
    rows = db.execute(
        """
        SELECT name
        FROM members
        WHERE group_code = ?
        ORDER BY id
        """,
        (group_code,)
    ).fetchall()

    return [
        row["name"]
        for row in rows
    ]


# =========================================================
# ヘルスチェック
# =========================================================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "status": "ok"
    })


# =========================================================
# グループ登録
# =========================================================

@app.route(
    "/api/group/register",
    methods=["POST"]
)
def register_group():

    try:
        data = request.get_json(
            silent=True
        ) or {}

        group_code = str(
            data.get("group_code", "")
        ).strip()

        password = str(
            data.get("password", "")
        ).strip()

        name = str(
            data.get("name", "")
        ).strip()

        if not group_code or not password or not name:
            return bad_request(
                "グループコード・パスワード・名前は必須です。"
            )

        db = get_db()

        existing = db.execute(
            """
            SELECT 1
            FROM groups
            WHERE group_code = ?
            """,
            (group_code,)
        ).fetchone()

        if existing:
            return bad_request(
                "そのグループコードは既に使われています。"
                "ログインを使ってください。",
                409
            )

        created_at = now_iso()

        db.execute(
            """
            INSERT INTO groups
                (group_code, password, created_at)
            VALUES (?, ?, ?)
            """,
            (
                group_code,
                password,
                created_at
            )
        )

        db.execute(
            """
            INSERT INTO members
                (group_code, name, created_at)
            VALUES (?, ?, ?)
            """,
            (
                group_code,
                name,
                created_at
            )
        )

        db.commit()

        members = get_members_from_db(
            db,
            group_code
        )

        return jsonify({
            "ok": True,
            "group_code": group_code,
            "members": members
        })

    except sqlite3.IntegrityError as e:

        return bad_request(
            f"データベースエラー: {str(e)}",
            409
        )

    except Exception as e:

        app.logger.exception(
            "グループ登録エラー"
        )

        return bad_request(
            f"サーバーエラー: {str(e)}",
            500
        )


# =========================================================
# グループログイン
# =========================================================

@app.route(
    "/api/group/login",
    methods=["POST"]
)
def login_group():

    try:
        data = request.get_json(
            silent=True
        ) or {}

        group_code = str(
            data.get("group_code", "")
        ).strip()

        password = str(
            data.get("password", "")
        ).strip()

        name = str(
            data.get("name", "")
        ).strip()

        if not group_code or not password or not name:
            return bad_request(
                "グループコード・パスワード・名前は必須です。"
            )

        db = get_db()

        row = db.execute(
            """
            SELECT *
            FROM groups
            WHERE group_code = ?
            """,
            (group_code,)
        ).fetchone()

        if not row:
            return bad_request(
                "そのグループコードは存在しません。"
                "新規登録してください。",
                404
            )

        if row["password"] != password:
            return bad_request(
                "パスワードが違います。",
                401
            )

        db.execute(
            """
            INSERT OR IGNORE INTO members
                (group_code, name, created_at)
            VALUES (?, ?, ?)
            """,
            (
                group_code,
                name,
                now_iso()
            )
        )

        db.commit()

        members = get_members_from_db(
            db,
            group_code
        )

        return jsonify({
            "ok": True,
            "group_code": group_code,
            "members": members
        })

    except Exception as e:

        app.logger.exception(
            "ログインエラー"
        )

        return bad_request(
            f"サーバーエラー: {str(e)}",
            500
        )


# =========================================================
# メンバー取得
# =========================================================

@app.route(
    "/api/members/<group_code>",
    methods=["GET"]
)
def get_members(group_code):

    try:
        db = get_db()

        if not group_exists(
            db,
            group_code
        ):
            return bad_request(
                "グループが存在しません。",
                404
            )

        members = get_members_from_db(
            db,
            group_code
        )

        return jsonify({
            "ok": True,
            "members": members
        })

    except Exception as e:

        app.logger.exception(
            "メンバー取得エラー"
        )

        return bad_request(
            f"サーバーエラー: {str(e)}",
            500
        )


# =========================================================
# メンバー追加
# =========================================================

@app.route(
    "/api/members/<group_code>",
    methods=["POST"]
)
def add_member(group_code):

    try:
        data = request.get_json(
            silent=True
        ) or {}

        name = str(
            data.get("name", "")
        ).strip()

        if not name:
            return bad_request(
                "名前は必須です。"
            )

        db = get_db()

        if not group_exists(
            db,
            group_code
        ):
            return bad_request(
                "グループが存在しません。",
                404
            )

        db.execute(
            """
            INSERT OR IGNORE INTO members
                (group_code, name, created_at)
            VALUES (?, ?, ?)
            """,
            (
                group_code,
                name,
                now_iso()
            )
        )

        db.commit()

        members = get_members_from_db(
            db,
            group_code
        )

        return jsonify({
            "ok": True,
            "members": members
        })

    except Exception as e:

        app.logger.exception(
            "メンバー追加エラー"
        )

        return bad_request(
            f"サーバーエラー: {str(e)}",
            500
        )


# =========================================================
# メンバー削除
# =========================================================

@app.route(
    "/api/members/<group_code>/<name>",
    methods=["DELETE"]
)
def remove_member(
    group_code,
    name
):

    try:
        db = get_db()

        if not group_exists(
            db,
            group_code
        ):
            return bad_request(
                "グループが存在しません。",
                404
            )

        members = get_members_from_db(
            db,
            group_code
        )

        if len(members) <= 1:
            return bad_request(
                "最低1人は残してください。"
            )

        db.execute(
            """
            DELETE FROM members
            WHERE group_code = ?
              AND name = ?
            """,
            (
                group_code,
                name
            )
        )

        db.commit()

        members = get_members_from_db(
            db,
            group_code
        )

        return jsonify({
            "ok": True,
            "members": members
        })

    except Exception as e:

        app.logger.exception(
            "メンバー削除エラー"
        )

        return bad_request(
            f"サーバーエラー: {str(e)}",
            500
        )


# =========================================================
# 安否確認取得
# =========================================================

@app.route(
    "/api/safety/<group_code>",
    methods=["GET"]
)
def get_safety(group_code):

    try:
        db = get_db()

        if not group_exists(
            db,
            group_code
        ):
            return bad_request(
                "グループが存在しません。",
                404
            )

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
            (
                group_code,
                group_code
            )
        ).fetchall()

        statuses = [
            {
                "name": row["name"],
                "status": row["status"],
                "created_at": row["created_at"]
            }
            for row in rows
        ]

        return jsonify({
            "ok": True,
            "statuses": statuses
        })

    except Exception as e:

        app.logger.exception(
            "安否取得エラー"
        )

        return bad_request(
            f"サーバーエラー: {str(e)}",
            500
        )


# =========================================================
# 安否確認送信
# =========================================================

@app.route(
    "/api/safety/<group_code>",
    methods=["POST"]
)
def post_safety(group_code):

    try:
        data = request.get_json(
            silent=True
        ) or {}

        name = str(
            data.get("name", "")
        ).strip()

        status = str(
            data.get("status", "")
        ).strip()

        if (
            not name
            or status not in (
                "safe",
                "messy",
                "sos"
            )
        ):
            return bad_request(
                "名前とステータス"
                "(safe/messy/sos)は必須です。"
            )

        db = get_db()

        if not group_exists(
            db,
            group_code
        ):
            return bad_request(
                "グループが存在しません。",
                404
            )

        db.execute(
            """
            INSERT INTO safety_status
                (
                    group_code,
                    name,
                    status,
                    created_at
                )
            VALUES (?, ?, ?, ?)
            """,
            (
                group_code,
                name,
                status,
                now_iso()
            )
        )

        db.commit()

        return jsonify({
            "ok": True
        })

    except Exception as e:

        app.logger.exception(
            "安否送信エラー"
        )

        return bad_request(
            f"サーバーエラー: {str(e)}",
            500
        )


# =========================================================
# 危険情報取得
# =========================================================

@app.route(
    "/api/hazard/<group_code>",
    methods=["GET"]
)
def get_hazard(group_code):

    try:
        db = get_db()

        if not group_exists(
            db,
            group_code
        ):
            return bad_request(
                "グループが存在しません。",
                404
            )

        rows = db.execute(
            """
            SELECT
                author,
                image,
                text,
                latitude,
                longitude,
                accuracy,
                created_at

            FROM hazard_posts

            WHERE group_code = ?

            ORDER BY id DESC

            LIMIT 50
            """,
            (group_code,)
        ).fetchall()

        posts = [
            {
                "author": row["author"],
                "image": row["image"],
                "text": row["text"],
                "lat": row["latitude"],
                "lon": row["longitude"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "accuracy": row["accuracy"],
                "created_at": row["created_at"]
            }
            for row in rows
        ]

        return jsonify({
            "ok": True,
            "posts": posts
        })

    except Exception as e:

        app.logger.exception(
            "危険情報取得エラー"
        )

        return bad_request(
            f"サーバーエラー: {str(e)}",
            500
        )


# =========================================================
# 危険情報投稿
# =========================================================

@app.route(
    "/api/hazard/<group_code>",
    methods=["POST"]
)
def post_hazard(group_code):

    try:
        data = request.get_json(
            silent=True
        ) or {}

        author = str(
            data.get("author", "")
        ).strip()

        image = str(
            data.get("image", "")
        ).strip()

        text = str(
            data.get("text", "")
        ).strip()

        # 新形式
        latitude = data.get(
            "latitude",
            data.get("lat")
        )

        longitude = data.get(
            "longitude",
            data.get("lon")
        )

        accuracy = data.get(
            "accuracy"
        )

        if (
            not author
            or not image
            or not text
        ):
            return bad_request(
                "投稿者・画像・内容は必須です。"
            )

        # ---------------------------------------------
        # 緯度経度を数値として検証
        # ---------------------------------------------

        if latitude is not None:
            try:
                latitude = float(latitude)
            except (
                TypeError,
                ValueError
            ):
                return bad_request(
                    "緯度の値が正しくありません。"
                )

            if not -90 <= latitude <= 90:
                return bad_request(
                    "緯度の範囲が正しくありません。"
                )

        if longitude is not None:
            try:
                longitude = float(longitude)
            except (
                TypeError,
                ValueError
            ):
                return bad_request(
                    "経度の値が正しくありません。"
                )

            if not -180 <= longitude <= 180:
                return bad_request(
                    "経度の範囲が正しくありません。"
                )

        # ---------------------------------------------
        # GPS精度
        # ---------------------------------------------

        if accuracy is not None:
            try:
                accuracy = float(accuracy)
            except (
                TypeError,
                ValueError
            ):
                return bad_request(
                    "位置情報の精度が正しくありません。"
                )

            if accuracy < 0:
                return bad_request(
                    "位置情報の精度が正しくありません。"
                )

        db = get_db()

        if not group_exists(
            db,
            group_code
        ):
            return bad_request(
                "グループが存在しません。",
                404
            )

        db.execute(
            """
            INSERT INTO hazard_posts
                (
                    group_code,
                    author,
                    image,
                    text,
                    latitude,
                    longitude,
                    accuracy,
                    created_at
                )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                group_code,
                author,
                image,
                text,
                latitude,
                longitude,
                accuracy,
                now_iso()
            )
        )

        db.commit()

        return jsonify({
            "ok": True,
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy
        })

    except Exception as e:

        app.logger.exception(
            "危険情報投稿エラー"
        )

        return bad_request(
            f"サーバーエラー: {str(e)}",
            500
        )


# =========================================================
# DB初期化
# =========================================================

init_db()


# =========================================================
# Render / ローカル起動
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )