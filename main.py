import os
import json
import uuid
import hashlib
import secrets
import threading
import time
import xml.etree.ElementTree as ET

from datetime import datetime, timezone, timedelta
from functools import wraps

import requests

from flask import Flask, request, jsonify
from flask_cors import CORS

try:
    from pywebpush import webpush, WebPushException
except ImportError:
    webpush = None
    WebPushException = Exception


# =========================================================
# Flask
# =========================================================

app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*"
        }
    }
)


# =========================================================
# 設定
# =========================================================

DATA_FILE = os.environ.get(
    "OTENKI_DATA_FILE",
    "otenki_data.json"
)

OPENWEATHER_API_KEY = os.environ.get(
    "OPENWEATHER_API_KEY",
    ""
)

OPENWEATHER_LAT = 32.4547
OPENWEATHER_LON = 130.1978

DATA_LOCK = threading.RLock()

FRIEND_REQUEST_BLOCK_DAYS = 7

MAX_IMAGE_LENGTH = 8 * 1024 * 1024
MAX_NAME_LENGTH = 100
MAX_SECURITY_KEY_LENGTH = 256


# =========================================================
# Web Push設定
# =========================================================

VAPID_PRIVATE_KEY = os.environ.get(
    "VAPID_PRIVATE_KEY",
    ""
)

VAPID_PUBLIC_KEY = os.environ.get(
    "VAPID_PUBLIC_KEY",
    ""
)

VAPID_CLAIMS_EMAIL = os.environ.get(
    "VAPID_CLAIMS_EMAIL",
    "mailto:admin@example.com"
)


# =========================================================
# 地震情報設定
# =========================================================

JMA_EQVOL_FEED = (
    "https://www.data.jma.go.jp/"
    "developer/xml/feed/eqvol.xml"
)

EARTHQUAKE_CHECK_INTERVAL = 30
EARTHQUAKE_MIN_INTENSITY = 3
MAX_EARTHQUAKE_HISTORY = 500


# =========================================================
# 天気予報監視設定
# =========================================================

# 10分ごとに天気をチェック
WEATHER_CHECK_INTERVAL = 600


# =========================================================
# XML名前空間
# =========================================================

ATOM_NS = {
    "atom":
        "http://www.w3.org/2005/Atom"
}

JMA_NS = {
    "jmx_ib":
        "http://xml.kishou.go.jp/jmaxml1/informationBasis1/",

    "jmx_eb":
        "http://xml.kishou.go.jp/jmaxml1/elementBasis1/",

    "jmx_seis":
        "http://xml.kishou.go.jp/jmaxml1/body/seismology1/"
}


# =========================================================
# データ初期値
# =========================================================

DEFAULT_DATA = {
    "users": {},
    "friend_requests": {},
    "friendships": {},
    "safety_statuses": {},
    "hazard_posts": {},
    "push_subscriptions": {},
    "earthquake_notifications": [],
    "last_weather_state": {}
}


# =========================================================
# 時刻
# =========================================================

def now_utc_iso():

    return datetime.now(
        timezone.utc
    ).isoformat()


def parse_datetime(value):

    if not value:
        return None

    try:

        return datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00"
            )
        )

    except Exception:

        return None


# =========================================================
# JSONデータベース
# =========================================================

def ensure_data_file():

    directory = os.path.dirname(
        os.path.abspath(
            DATA_FILE
        )
    )

    if directory:

        os.makedirs(
            directory,
            exist_ok=True
        )

    if not os.path.exists(
        DATA_FILE
    ):

        save_data(
            DEFAULT_DATA
        )


def load_data():

    with DATA_LOCK:

        ensure_data_file()

        try:

            with open(
                DATA_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

        except Exception:

            data = {}

        if not isinstance(
            data,
            dict
        ):

            data = {}

        for key, default in DEFAULT_DATA.items():

            if key not in data:

                if isinstance(
                    default,
                    dict
                ):

                    data[key] = {}

                elif isinstance(
                    default,
                    list
                ):

                    data[key] = []

                else:

                    data[key] = default

        return data


def save_data(data):

    with DATA_LOCK:

        directory = os.path.dirname(
            os.path.abspath(
                DATA_FILE
            )
        )

        if directory:

            os.makedirs(
                directory,
                exist_ok=True
            )

        temp_file = (
            DATA_FILE +
            ".tmp"
        )

        with open(
            temp_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            temp_file,
            DATA_FILE
        )


# =========================================================
# セキュリティキー
# =========================================================

def hash_security_key(
    security_key
):

    return hashlib.sha256(
        security_key.encode(
            "utf-8"
        )
    ).hexdigest()


def generate_user_id():

    return uuid.uuid4().hex


def generate_security_key():

    return secrets.token_urlsafe(
        32
    )


# =========================================================
# ユーザー認証
# =========================================================

def get_request_security_key():

    value = (
        request.headers.get(
            "X-Security-Key"
        )
        or
        request.headers.get(
            "Authorization"
        )
        or
        ""
    )

    if value.startswith(
        "Bearer "
    ):

        value = value[
            7:
        ]

    return value.strip()


def find_user_by_security_key(
    security_key
):

    if not security_key:

        return None

    hashed = hash_security_key(
        security_key
    )

    data = load_data()

    for user_id, user in data[
        "users"
    ].items():

        if (
            user.get(
                "security_key_hash"
            )
            ==
            hashed
        ):

            result = dict(
                user
            )

            result["id"] = (
                user_id
            )

            return result

    return None


def require_user(
    function
):

    @wraps(function)
    def wrapper(
        *args,
        **kwargs
    ):

        security_key = (
            get_request_security_key()
        )

        user = (
            find_user_by_security_key(
                security_key
            )
        )

        if not user:

            return jsonify({
                "error":
                    "認証に失敗しました。セキュリティキーを確認してください。"
            }), 401

        return function(
            user,
            *args,
            **kwargs
        )

    return wrapper


# =========================================================
# ユーザー情報
# =========================================================

def public_user(user):

    if not user:

        return None

    return {
        "id":
            user.get("id"),

        "name":
            user.get("name"),

        "created_at":
            user.get("created_at")
    }


def get_user(
    data,
    user_id
):

    return data[
        "users"
    ].get(
        user_id
    )


def user_exists(
    data,
    user_id
):

    return user_id in data[
        "users"
    ]


# =========================================================
# フレンドシップ
# =========================================================

def friendship_key(
    user_a,
    user_b
):

    return ":".join(
        sorted(
            [
                str(user_a),
                str(user_b)
            ]
        )
    )


def are_friends(
    data,
    user_a,
    user_b
):

    key = friendship_key(
        user_a,
        user_b
    )

    friendship = data[
        "friendships"
    ].get(
        key
    )

    return bool(
        friendship
        and
        friendship.get(
            "status"
        )
        ==
        "accepted"
    )


def get_friend_ids(
    data,
    user_id
):

    result = []

    for friendship in data[
        "friendships"
    ].values():

        if (
            friendship.get(
                "status"
            )
            !=
            "accepted"
        ):

            continue

        a = friendship.get(
            "user_a"
        )

        b = friendship.get(
            "user_b"
        )

        if a == user_id:

            result.append(
                b
            )

        elif b == user_id:

            result.append(
                a
            )

    return result


# =========================================================
# 家族・友達リクエスト
# =========================================================

def request_is_blocked(
    request_record
):

    blocked_until = parse_datetime(
        request_record.get(
            "blocked_until"
        )
    )

    if not blocked_until:

        return False

    return (
        datetime.now(
            timezone.utc
        )
        <
        blocked_until
    )


def cleanup_expired_requests(
    data
):

    changed = False

    for record in data[
        "friend_requests"
    ].values():

        blocked_until = parse_datetime(
            record.get(
                "blocked_until"
            )
        )

        if (
            blocked_until
            and
            datetime.now(
                timezone.utc
            )
            >=
            blocked_until
        ):

            record[
                "blocked_until"
            ] = None

            if record.get(
                "status"
            ) == "cancelled":

                record[
                    "status"
                ] = "expired"

            changed = True

    return changed


# =========================================================
# ヘルスチェック
# =========================================================

@app.get("/")
def index():

    return jsonify({
        "ok": True,
        "service":
            "otenki-app",
        "message":
            "おてんきアプリAPIは動作しています。"
    })


@app.get("/api/health")
def health():

    return jsonify({
        "ok": True
    })


# =========================================================
# アカウント登録
# =========================================================

@app.post(
    "/api/account/register"
)
def register_account():

    body = request.get_json(
        silent=True
    ) or {}

    name = str(
        body.get(
            "name",
            ""
        )
    ).strip()

    supplied_key = str(
        body.get(
            "security_key",
            ""
        )
    ).strip()

    if not name:

        return jsonify({
            "error":
                "表示名を入力してください。"
        }), 400

    if len(name) > MAX_NAME_LENGTH:

        return jsonify({
            "error":
                "表示名が長すぎます。"
        }), 400

    if supplied_key:

        security_key = supplied_key

    else:

        security_key = (
            generate_security_key()
        )

    if (
        len(security_key)
        >
        MAX_SECURITY_KEY_LENGTH
    ):

        return jsonify({
            "error":
                "セキュリティキーが長すぎます。"
        }), 400

    data = load_data()

    security_hash = (
        hash_security_key(
            security_key
        )
    )

    for existing_user in data[
        "users"
    ].values():

        if (
            existing_user.get(
                "security_key_hash"
            )
            ==
            security_hash
        ):

            return jsonify({
                "error":
                    "そのセキュリティキーは既に使用されています。"
            }), 409

    user_id = generate_user_id()

    user = {
        "name":
            name,

        "security_key_hash":
            security_hash,

        "created_at":
            now_utc_iso()
    }

    data[
        "users"
    ][user_id] = user

    save_data(
        data
    )

    return jsonify({
        "ok":
            True,

        "user": {
            "id":
                user_id,

            "name":
                name
        },

        "security_key":
            security_key
    })


# =========================================================
# ログイン
# =========================================================

@app.post(
    "/api/account/login"
)
def login_account():

    body = request.get_json(
        silent=True
    ) or {}

    security_key = str(
        body.get(
            "security_key",
            ""
        )
    ).strip()

    if not security_key:

        return jsonify({
            "error":
                "セキュリティキーを入力してください。"
        }), 400

    user = (
        find_user_by_security_key(
            security_key
        )
    )

    if not user:

        return jsonify({
            "error":
                "セキュリティキーが正しくありません。"
        }), 401

    data = load_data()

    friends = []

    for friend_id in get_friend_ids(
        data,
        user["id"]
    ):

        friend = get_user(
            data,
            friend_id
        )

        if friend:

            friends.append(
                public_user({
                    **friend,
                    "id":
                        friend_id
                })
            )

    return jsonify({
        "ok":
            True,

        "user":
            public_user(user),

        "friends":
            friends
    })


# =========================================================
# 自分の情報
# =========================================================

@app.get(
    "/api/account/me"
)
@require_user
def account_me(
    user
):

    data = load_data()

    friends = []

    for friend_id in get_friend_ids(
        data,
        user["id"]
    ):

        friend = get_user(
            data,
            friend_id
        )

        if friend:

            friends.append(
                public_user({
                    **friend,
                    "id":
                        friend_id
                })
            )

    return jsonify({
        "ok":
            True,

        "user":
            public_user(user),

        "friends":
            friends
    })


# =========================================================
# 家族・友達リクエスト公開情報
# =========================================================

def public_request(
    data,
    record
):

    from_user = get_user(
        data,
        record.get(
            "from_user_id"
        )
    )

    to_user = get_user(
        data,
        record.get(
            "to_user_id"
        )
    )

    return {
        "id":
            record.get("id"),

        "status":
            record.get("status"),

        "created_at":
            record.get("created_at"),

        "updated_at":
            record.get("updated_at"),

        "blocked_until":
            record.get(
                "blocked_until"
            ),

        "from":
            public_user({
                **from_user,
                "id":
                    record.get(
                        "from_user_id"
                    )
            })
            if from_user
            else None,

        "to":
            public_user({
                **to_user,
                "id":
                    record.get(
                        "to_user_id"
                    )
            })
            if to_user
            else None
    }


# =========================================================
# 家族・友達リクエスト送信
# =========================================================

@app.post(
    "/api/friends/request"
)
@require_user
def send_friend_request(
    user
):

    body = request.get_json(
        silent=True
    ) or {}

    target_name = str(
        body.get(
            "name",
            ""
        )
    ).strip()

    if not target_name:

        return jsonify({
            "error":
                "追加する人の表示名を入力してください。"
        }), 400

    if len(target_name) > MAX_NAME_LENGTH:

        return jsonify({
            "error":
                "表示名が長すぎます。"
        }), 400

    data = load_data()

    cleanup_expired_requests(
        data
    )

    target_id = None

    for candidate_id, candidate in data[
        "users"
    ].items():

        if candidate_id == user[
            "id"
        ]:

            continue

        if (
            candidate.get("name")
            ==
            target_name
        ):

            target_id = candidate_id
            break

    if not target_id:

        return jsonify({
            "error":
                "その表示名のアカウントが見つかりません。"
        }), 404

    if are_friends(
        data,
        user["id"],
        target_id
    ):

        return jsonify({
            "error":
                "すでに家族・友達として接続されています。"
        }), 409

    existing = None

    for record_id, record in data[
        "friend_requests"
    ].items():

        if (
            record.get(
                "from_user_id"
            )
            ==
            user["id"]
            and
            record.get(
                "to_user_id"
            )
            ==
            target_id
        ) or (
            record.get(
                "from_user_id"
            )
            ==
            target_id
            and
            record.get(
                "to_user_id"
            )
            ==
            user["id"]
        ):

            existing = (
                record_id,
                record
            )

            break

    if existing:

        request_id, record = existing

        if request_is_blocked(
            record
        ):

            return jsonify({
                "error":
                    "この相手からのリクエストは現在無効化されています。"
            }), 403

        if record.get(
            "status"
        ) in (
            "pending",
            "accepted"
        ):

            return jsonify({
                "error":
                    "すでにリクエストまたは接続状態があります。"
            }), 409

    request_id = uuid.uuid4().hex

    record = {
        "id":
            request_id,

        "from_user_id":
            user["id"],

        "to_user_id":
            target_id,

        "status":
            "pending",

        "created_at":
            now_utc_iso(),

        "updated_at":
            now_utc_iso(),

        "blocked_until":
            None
    }

    data[
        "friend_requests"
    ][request_id] = record

    save_data(
        data
    )

    notify_user(
        data,
        target_id,
        "家族・友達リクエスト",
        f'{user["name"]}さんから家族・友達リクエストが届きました。'
    )

    return jsonify({
        "ok":
            True,

        "request":
            public_request(
                data,
                record
            )
    })


# =========================================================
# 受信・送信リクエスト一覧
# =========================================================

@app.get(
    "/api/friends/requests"
)
@require_user
def get_friend_requests(
    user
):

    data = load_data()

    changed = cleanup_expired_requests(
        data
    )

    if changed:

        save_data(
            data
        )

    received = []
    sent = []

    for record in data[
        "friend_requests"
    ].values():

        if record.get(
            "to_user_id"
        ) == user["id"]:

            if record.get(
                "status"
            ) in (
                "pending",
                "expired",
                "cancelled",
                "rejected"
            ):

                received.append(
                    public_request(
                        data,
                        record
                    )
                )

        elif record.get(
            "from_user_id"
        ) == user["id"]:

            sent.append(
                public_request(
                    data,
                    record
                )
            )

    return jsonify({
        "ok":
            True,

        "received":
            received,

        "sent":
            sent
    })


# =========================================================
# リクエスト承認
# =========================================================

@app.post(
    "/api/friends/requests/<request_id>/accept"
)
@require_user
def accept_friend_request(
    user,
    request_id
):

    data = load_data()

    record = data[
        "friend_requests"
    ].get(
        request_id
    )

    if not record:

        return jsonify({
            "error":
                "リクエストが見つかりません。"
        }), 404

    if record.get(
        "to_user_id"
    ) != user["id"]:

        return jsonify({
            "error":
                "このリクエストを操作する権限がありません。"
        }), 403

    if record.get(
        "status"
    ) != "pending":

        return jsonify({
            "error":
                "このリクエストはすでに処理されています。"
        }), 409

    from_user_id = record.get(
        "from_user_id"
    )

    if not user_exists(
        data,
        from_user_id
    ):

        return jsonify({
            "error":
                "相手のアカウントが存在しません。"
        }), 404

    key = friendship_key(
        user["id"],
        from_user_id
    )

    data[
        "friendships"
    ][key] = {
        "user_a":
            user["id"],

        "user_b":
            from_user_id,

        "status":
            "accepted",

        "created_at":
            now_utc_iso()
    }

    record[
        "status"
    ] = "accepted"

    record[
        "updated_at"
    ] = now_utc_iso()

    record[
        "blocked_until"
    ] = None

    save_data(
        data
    )

    other = get_user(
        data,
        from_user_id
    )

    if other:

        notify_user(
            data,
            from_user_id,
            "家族・友達リクエスト承認",
            f'{user["name"]}さんがリクエストを承認しました。'
        )

    return jsonify({
        "ok":
            True,

        "message":
            "家族・友達として接続しました。",

        "friend":
            public_user({
                **other,
                "id":
                    from_user_id
            })
            if other
            else None
    })


# =========================================================
# リクエスト拒否
# =========================================================

@app.post(
    "/api/friends/requests/<request_id>/reject"
)
@require_user
def reject_friend_request(
    user,
    request_id
):

    data = load_data()

    record = data[
        "friend_requests"
    ].get(
        request_id
    )

    if not record:

        return jsonify({
            "error":
                "リクエストが見つかりません。"
        }), 404

    if record.get(
        "to_user_id"
    ) != user["id"]:

        return jsonify({
            "error":
                "このリクエストを操作する権限がありません。"
        }), 403

    if record.get(
        "status"
    ) != "pending":

        return jsonify({
            "error":
                "このリクエストはすでに処理されています。"
        }), 409

    record[
        "status"
    ] = "rejected"

    record[
        "updated_at"
    ] = now_utc_iso()

    save_data(
        data
    )

    sender_id = record.get(
        "from_user_id"
    )

    notify_user(
        data,
        sender_id,
        "家族・友達リクエスト",
        f'{user["name"]}さんがリクエストを拒否しました。'
    )

    return jsonify({
        "ok":
            True
    })


# =========================================================
# 送信者によるキャンセル
# =========================================================

@app.post(
    "/api/friends/requests/<request_id>/cancel"
)
@require_user
def cancel_friend_request(
    user,
    request_id
):

    data = load_data()

    record = data[
        "friend_requests"
    ].get(
        request_id
    )

    if not record:

        return jsonify({
            "error":
                "リクエストが見つかりません。"
        }), 404

    if record.get(
        "from_user_id"
    ) != user["id"]:

        return jsonify({
            "error":
                "このリクエストをキャンセルする権限がありません。"
        }), 403

    if record.get(
        "status"
    ) != "pending":

        return jsonify({
            "error":
                "このリクエストはすでに処理されています。"
        }), 409

    blocked_until = (
        datetime.now(
            timezone.utc
        )
        +
        timedelta(
            days=
                FRIEND_REQUEST_BLOCK_DAYS
        )
    )

    record[
        "status"
    ] = "cancelled"

    record[
        "updated_at"
    ] = now_utc_iso()

    record[
        "blocked_until"
    ] = blocked_until.isoformat()

    save_data(
        data
    )

    target_id = record.get(
        "to_user_id"
    )

    notify_user(
        data,
        target_id,
        "家族・友達リクエスト取消",
        f'{user["name"]}さんがリクエストをキャンセルしました。7日間、この相手からの新しいリクエストは無効です。'
    )

    return jsonify({
        "ok":
            True,

        "blocked_until":
            blocked_until.isoformat()
    })


# =========================================================
# フレンド一覧
# =========================================================

@app.get(
    "/api/friends"
)
@require_user
def get_friends(
    user
):

    data = load_data()

    result = []

    for friend_id in get_friend_ids(
        data,
        user["id"]
    ):

        friend = get_user(
            data,
            friend_id
        )

        if friend:

            result.append(
                public_user({
                    **friend,
                    "id":
                        friend_id
                })
            )

    return jsonify({
        "ok":
            True,

        "friends":
            result
    })


# =========================================================
# フレンド解除
# =========================================================

@app.delete(
    "/api/friends/<friend_id>"
)
@require_user
def remove_friend(
    user,
    friend_id
):

    data = load_data()

    if not are_friends(
        data,
        user["id"],
        friend_id
    ):

        return jsonify({
            "error":
                "その相手とは接続されていません。"
        }), 404

    key = friendship_key(
        user["id"],
        friend_id
    )

    data[
        "friendships"
    ].pop(
        key,
        None
    )

    save_data(
        data
    )

    friend = get_user(
        data,
        friend_id
    )

    if friend:

        notify_user(
            data,
            friend_id,
            "家族・友達接続解除",
            f'{user["name"]}さんとの家族・友達接続が解除されました。'
        )

    return jsonify({
        "ok":
            True
    })


# =========================================================
# 安否確認
# =========================================================

VALID_SAFETY_STATUSES = {
    "safe",
    "messy",
    "sos"
}


@app.post(
    "/api/safety"
)
@require_user
def send_safety(
    user
):

    body = request.get_json(
        silent=True
    ) or {}

    status = str(
        body.get(
            "status",
            ""
        )
    ).strip()

    if status not in VALID_SAFETY_STATUSES:

        return jsonify({
            "error":
                "不正な安否状態です。"
        }), 400

    data = load_data()

    record_id = uuid.uuid4().hex

    record = {
        "id":
            record_id,

        "user_id":
            user["id"],

        "name":
            user["name"],

        "status":
            status,

        "created_at":
            now_utc_iso()
    }

    data[
        "safety_statuses"
    ][record_id] = record

    save_data(
        data
    )

    label = {
        "safe":
            "元気です",

        "messy":
            "被害あり",

        "sos":
            "緊急SOS"
    }[
        status
    ]

    for friend_id in get_friend_ids(
        data,
        user["id"]
    ):

        notify_user(
            data,
            friend_id,
            "安否確認",
            f'{user["name"]}さんは「{label}」です！'
        )

    return jsonify({
        "ok":
            True,

        "status":
            record
    })


# =========================================================
# 安否確認取得
# =========================================================

@app.get(
    "/api/safety"
)
@require_user
def get_safety(
    user
):

    data = load_data()

    friend_ids = set(
        get_friend_ids(
            data,
            user["id"]
        )
    )

    friend_ids.add(
        user["id"]
    )

    statuses = []

    for record in data[
        "safety_statuses"
    ].values():

        if record.get(
            "user_id"
        ) not in friend_ids:

            continue

        statuses.append(
            dict(record)
        )

    statuses.sort(
        key=lambda x:
            x.get(
                "created_at",
                ""
            ),
        reverse=True
    )

    return jsonify({
        "ok":
            True,

        "statuses":
            statuses
    })


# =========================================================
# 危険情報投稿
# =========================================================

@app.post(
    "/api/hazards"
)
@require_user
def create_hazard(
    user
):

    body = request.get_json(
        silent=True
    ) or {}

    text = str(
        body.get(
            "text",
            ""
        )
    ).strip()

    image = str(
        body.get(
            "image",
            ""
        )
    ).strip()

    if not text:

        return jsonify({
            "error":
                "危険情報の内容を入力してください。"
        }), 400

    if len(text) > 2000:

        return jsonify({
            "error":
                "危険情報の文章が長すぎます。"
        }), 400

    if image:

        if not image.startswith(
            "data:image/"
        ):

            return jsonify({
                "error":
                    "画像データの形式が正しくありません。"
            }), 400

        if len(image) > MAX_IMAGE_LENGTH:

            return jsonify({
                "error":
                    "画像サイズが大きすぎます。"
            }), 400

    latitude = body.get(
        "latitude"
    )

    longitude = body.get(
        "longitude"
    )

    accuracy = body.get(
        "accuracy"
    )

    try:

        if latitude is not None:

            latitude = float(
                latitude
            )

        if longitude is not None:

            longitude = float(
                longitude
            )

        if accuracy is not None:

            accuracy = float(
                accuracy
            )

    except Exception:

        return jsonify({
            "error":
                "危険箇所の位置情報が正しくありません。"
        }), 400

    if (
        latitude is not None
        and
        not (
            -90
            <=
            latitude
            <=
            90
        )
    ):

        return jsonify({
            "error":
                "緯度が不正です。"
        }), 400

    if (
        longitude is not None
        and
        not (
            -180
            <=
            longitude
            <=
            180
        )
    ):

        return jsonify({
            "error":
                "経度が不正です。"
        }), 400

    data = load_data()

    post_id = uuid.uuid4().hex

    record = {
        "id":
            post_id,

        "author_id":
            user["id"],

        "author":
            user["name"],

        "image":
            image,

        "text":
            text,

        "latitude":
            latitude,

        "longitude":
            longitude,

        "accuracy":
            accuracy,

        "created_at":
            now_utc_iso()
    }

    data[
        "hazard_posts"
    ][post_id] = record

    save_data(
        data
    )

    for friend_id in get_friend_ids(
        data,
        user["id"]
    ):

        notify_user(
            data,
            friend_id,
            "危険情報",
            f'{user["name"]}さんが危険情報を共有しました。'
        )

    return jsonify({
        "ok":
            True,

        "post":
            record
    })


# =========================================================
# 危険情報取得
# =========================================================

@app.get(
    "/api/hazards"
)
@require_user
def get_hazards(
    user
):

    data = load_data()

    friend_ids = set(
        get_friend_ids(
            data,
            user["id"]
        )
    )

    friend_ids.add(
        user["id"]
    )

    posts = []

    for post in data[
        "hazard_posts"
    ].values():

        if post.get(
            "author_id"
        ) not in friend_ids:

            continue

        posts.append(
            dict(post)
        )

    posts.sort(
        key=lambda x:
            x.get(
                "created_at",
                ""
            ),
        reverse=True
    )

    return jsonify({
        "ok":
            True,

        "posts":
            posts
    })


# =========================================================
# Web Push購読情報
# =========================================================

def normalize_push_subscription(
    subscription
):

    if not isinstance(
        subscription,
        dict
    ):

        return None

    endpoint = str(
        subscription.get(
            "endpoint",
            ""
        )
    ).strip()

    keys = subscription.get(
        "keys"
    )

    if not endpoint:

        return None

    if not isinstance(
        keys,
        dict
    ):

        return None

    p256dh = str(
        keys.get(
            "p256dh",
            ""
        )
    ).strip()

    auth = str(
        keys.get(
            "auth",
            ""
        )
    ).strip()

    if not p256dh or not auth:

        return None

    return {
        "endpoint":
            endpoint,

        "keys": {
            "p256dh":
                p256dh,

            "auth":
                auth
        }
    }


# =========================================================
# Web Push購読登録
# =========================================================

@app.post(
    "/api/push/subscribe"
)
@require_user
def push_subscribe(
    user
):

    body = request.get_json(
        silent=True
    ) or {}

    subscription = (
        normalize_push_subscription(
            body.get(
                "subscription"
            )
        )
    )

    if not subscription:

        return jsonify({
            "error":
                "Push購読情報が正しくありません。"
        }), 400

    data = load_data()

    user_id = user[
        "id"
    ]

    if user_id not in data[
        "push_subscriptions"
    ]:

        data[
            "push_subscriptions"
        ][user_id] = []

    subscriptions = data[
        "push_subscriptions"
    ][user_id]

    endpoint = subscription[
        "endpoint"
    ]

    subscriptions = [
        x
        for x in subscriptions
        if x.get(
            "endpoint"
        )
        !=
        endpoint
    ]

    subscriptions.append(
        subscription
    )

    data[
        "push_subscriptions"
    ][user_id] = subscriptions

    save_data(
        data
    )

    return jsonify({
        "ok":
            True
    })


# =========================================================
# Web Push購読解除
# =========================================================

@app.post(
    "/api/push/unsubscribe"
)
@require_user
def push_unsubscribe(
    user
):

    body = request.get_json(
        silent=True
    ) or {}

    endpoint = str(
        body.get(
            "endpoint",
            ""
        )
    ).strip()

    if not endpoint:

        return jsonify({
            "error":
                "endpointがありません。"
        }), 400

    data = load_data()

    subscriptions = data[
        "push_subscriptions"
    ].get(
        user["id"],
        []
    )

    subscriptions = [
        x
        for x in subscriptions
        if x.get(
            "endpoint"
        )
        !=
        endpoint
    ]

    data[
        "push_subscriptions"
    ][user["id"]] = subscriptions

    save_data(
        data
    )

    return jsonify({
        "ok":
            True
    })


# =========================================================
# Web Push送信
# =========================================================

def notify_user(
    data,
    user_id,
    title,
    message,
    extra_data=None
):

    if not webpush:

        print(
            "pywebpushがインストールされていないためPushを送信できません。",
            flush=True
        )

        return

    if not VAPID_PRIVATE_KEY:

        print(
            "VAPID_PRIVATE_KEYが設定されていないためPushを送信できません。",
            flush=True
        )

        return

    subscriptions = data[
        "push_subscriptions"
    ].get(
        user_id,
        []
    )

    if not subscriptions:

        return

    payload_data = {
        "title":
            title,

        "body":
            message,

        "timestamp":
            now_utc_iso()
    }

    if isinstance(
        extra_data,
        dict
    ):

        payload_data.update(
            extra_data
        )

    payload = json.dumps(
        payload_data,
        ensure_ascii=False
    )

    valid_subscriptions = []

    for subscription in subscriptions:

        try:

            webpush(
                subscription_info=
                    subscription,

                data=
                    payload,

                vapid_private_key=
                    VAPID_PRIVATE_KEY,

                vapid_claims={
                    "sub":
                        VAPID_CLAIMS_EMAIL
                }
            )

            valid_subscriptions.append(
                subscription
            )

        except WebPushException as error:

            print(
                "Web Push送信エラー:",
                error,
                flush=True
            )

            response = getattr(
                error,
                "response",
                None
            )

            status_code = getattr(
                response,
                "status_code",
                None
            )

            if status_code in (
                404,
                410
            ):

                continue

            valid_subscriptions.append(
                subscription
            )

        except Exception as error:

            print(
                "Web Push送信エラー:",
                error,
                flush=True
            )

            valid_subscriptions.append(
                subscription
            )

    data[
        "push_subscriptions"
    ][user_id] = (
        valid_subscriptions
    )

    save_data(
        data
    )


def notify_all_users(
    data,
    title,
    message,
    extra_data=None
):

    user_ids = list(
        data[
            "users"
        ].keys()
    )

    for user_id in user_ids:

        notify_user(
            data,
            user_id,
            title,
            message,
            extra_data
        )


# =========================================================
# 地震情報XML
# =========================================================

def get_xml_text(
    element,
    path,
    namespaces=None
):

    if element is None:

        return ""

    value = element.findtext(
        path,
        default="",
        namespaces=namespaces
    )

    return (
        value or ""
    ).strip()


def parse_intensity(
    value
):

    if value is None:

        return None

    value = str(
        value
    ).strip()

    intensity_map = {
        "1": 1,
        "2": 2,
        "3": 3,
        "4": 4,
        "5-": 5,
        "5弱": 5,
        "5+": 5,
        "5強": 5,
        "6-": 6,
        "6弱": 6,
        "6+": 6,
        "6強": 6,
        "7": 7
    }

    if value in intensity_map:

        return intensity_map[
            value
        ]

    try:

        return int(
            value
        )

    except Exception:

        return None


def parse_jma_earthquake_xml(
    url
):

    response = requests.get(
        url,
        timeout=15
    )

    response.raise_for_status()

    root = ET.fromstring(
        response.content
    )

    head = root.find(
        ".//jmx_ib:Head",
        JMA_NS
    )

    if head is None:

        return None

    title = get_xml_text(
        head,
        "jmx_ib:Title",
        JMA_NS
    )

    report_datetime = get_xml_text(
        head,
        "jmx_ib:ReportDateTime",
        JMA_NS
    )

    info_kind = get_xml_text(
        head,
        "jmx_ib:InfoKind",
        JMA_NS
    )

    info_type = get_xml_text(
        head,
        "jmx_ib:InfoType",
        JMA_NS
    )

    headline = get_xml_text(
        head,
        "jmx_ib:Headline/jmx_eb:Text",
        JMA_NS
    )

    body = root.find(
        ".//jmx_eb:Body",
        JMA_NS
    )

    if body is None:

        return None

    earthquake = body.find(
        ".//jmx_seis:Earthquake",
        JMA_NS
    )

    if earthquake is None:

        earthquake = body.find(
            ".//Earthquake"
        )

    if earthquake is None:

        return None

    origin_time = get_xml_text(
        earthquake,
        "jmx_seis:OriginTime",
        JMA_NS
    )

    hypocenter = earthquake.find(
        ".//jmx_seis:Hypocenter",
        JMA_NS
    )

    if hypocenter is None:

        hypocenter = earthquake.find(
            ".//Hypocenter"
        )

    place_name = ""

    latitude = None
    longitude = None
    depth = None

    if hypocenter is not None:

        place_name = get_xml_text(
            hypocenter,
            ".//jmx_seis:Area/jmx_eb:Name",
            JMA_NS
        )

        if not place_name:

            place_name = get_xml_text(
                hypocenter,
                ".//jmx_eb:Name",
                JMA_NS
            )

        coordinate = get_xml_text(
            hypocenter,
            ".//jmx_seis:Area/jmx_eb:Coordinate",
            JMA_NS
        )

        if coordinate:

            parts = coordinate.split()

            try:

                if len(parts) >= 2:

                    latitude = parts[0]
                    longitude = parts[1]

            except Exception:

                pass

        depth_text = get_xml_text(
            hypocenter,
            ".//jmx_seis:Area/jmx_eb:Depth",
            JMA_NS
        )

        if depth_text:

            depth = depth_text

    magnitude = None

    magnitude_text = get_xml_text(
        earthquake,
        ".//jmx_seis:Magnitude",
        JMA_NS
    )

    if magnitude_text:

        try:

            magnitude = float(
                magnitude_text
            )

        except Exception:

            magnitude = magnitude_text

    max_intensity = None

    for intensity in root.findall(
        ".//jmx_seis:Intensity",
        JMA_NS
    ):

        for child in intensity.iter():

            tag = child.tag.split(
                "}"
            )[-1]

            if tag.lower() in (
                "maxintensity",
                "maxint"
            ):

                parsed = parse_intensity(
                    child.text
                )

                if parsed is not None:

                    if (
                        max_intensity is None
                        or
                        parsed > max_intensity
                    ):

                        max_intensity = parsed

    text_pool = " ".join([
        title,
        headline,
        info_kind,
        info_type
    ])

    for value in (
        "7",
        "6強",
        "6弱",
        "5強",
        "5弱",
        "4",
        "3",
        "2",
        "1"
    ):

        if (
            f"震度{value}"
            in
            text_pool
        ):

            parsed = parse_intensity(
                value
            )

            if parsed is not None:

                if (
                    max_intensity is None
                    or
                    parsed > max_intensity
                ):

                    max_intensity = parsed

    event_id = ""

    event_id_element = root.find(
        ".//jmx_ib:EventID",
        JMA_NS
    )

    if event_id_element is not None:

        event_id = (
            event_id_element.text
            or
            ""
        ).strip()

    if not event_id:

        event_id = url

    return {
        "event_id":
            event_id,

        "title":
            title,

        "report_datetime":
            report_datetime,

        "info_kind":
            info_kind,

        "info_type":
            info_type,

        "headline":
            headline,

        "origin_time":
            origin_time,

        "place_name":
            place_name,

        "latitude":
            latitude,

        "longitude":
            longitude,

        "depth":
            depth,

        "magnitude":
            magnitude,

        "max_intensity":
            max_intensity,

        "url":
            url
    }


def fetch_jma_earthquake_feed():

    response = requests.get(
        JMA_EQVOL_FEED,
        timeout=15,
        headers={
            "User-Agent":
                "OtenkiApp/1.0 earthquake-monitor"
        }
    )

    response.raise_for_status()

    return ET.fromstring(
        response.content
    )


def get_jma_feed_entries():

    root = fetch_jma_earthquake_feed()

    entries = []

    for entry in root.findall(
        "atom:entry",
        ATOM_NS
    ):

        title = get_xml_text(
            entry,
            "atom:title",
            ATOM_NS
        )

        entry_id = get_xml_text(
            entry,
            "atom:id",
            ATOM_NS
        )

        link_element = entry.find(
            "atom:link",
            ATOM_NS
        )

        link = ""

        if link_element is not None:

            link = (
                link_element.get(
                    "href",
                    ""
                )
                or
                ""
            ).strip()

        updated = get_xml_text(
            entry,
            "atom:updated",
            ATOM_NS
        )

        if not entry_id:

            entry_id = link

        if not link:

            continue

        entries.append({
            "id":
                entry_id,

            "title":
                title,

            "link":
                link,

            "updated":
                updated
        })

    return entries


def earthquake_should_notify(
    earthquake
):

    if not earthquake:

        return False

    intensity = (
        earthquake.get(
            "max_intensity"
        )
    )

    if intensity is not None:

        return (
            intensity
            >=
            EARTHQUAKE_MIN_INTENSITY
        )

    title = (
        earthquake.get(
            "title",
            ""
        )
    )

    if title == "震度速報":

        return True

    return False


def earthquake_message(
    earthquake
):

    place = (
        earthquake.get(
            "place_name"
        )
        or
        "震源地不明"
    )

    magnitude = (
        earthquake.get(
            "magnitude"
        )
    )

    intensity = (
        earthquake.get(
            "max_intensity"
        )
    )

    parts = [
        f"{place}で地震が発生しました。"
    ]

    if magnitude is not None:

        parts.append(
            f"M{magnitude}"
        )

    if intensity is not None:

        parts.append(
            f"最大震度{intensity}"
        )

    parts.append(
        "安全を確認してください。"
    )

    return " ".join(
        parts
    )


def process_earthquake_entry(
    entry
):

    data = load_data()

    event_id = (
        entry.get(
            "id"
        )
        or
        entry.get(
            "link"
        )
    )

    if not event_id:

        return False

    history = data[
        "earthquake_notifications"
    ]

    if event_id in history:

        return False

    try:

        earthquake = (
            parse_jma_earthquake_xml(
                entry["link"]
            )
        )

    except Exception as error:

        print(
            "地震XML解析エラー:",
            error,
            flush=True
        )

        return False

    if not earthquake:

        return False

    history.append(
        event_id
    )

    if len(history) > MAX_EARTHQUAKE_HISTORY:

        del history[
            :-
            MAX_EARTHQUAKE_HISTORY
        ]

    save_data(
        data
    )

    if not earthquake_should_notify(
        earthquake
    ):

        return False

    message = earthquake_message(
        earthquake
    )

    notify_all_users(
        data,
        "地震情報",
        message,
        {
            "type":
                "earthquake",

            "event_id":
                earthquake.get(
                    "event_id"
                ),

            "place_name":
                earthquake.get(
                    "place_name"
                ),

            "magnitude":
                earthquake.get(
                    "magnitude"
                ),

            "max_intensity":
                earthquake.get(
                    "max_intensity"
                )
        }
    )

    return True


def earthquake_monitor_loop():

    print(
        "地震情報監視を開始します。",
        flush=True
    )

    while True:

        try:

            entries = (
                get_jma_feed_entries()
            )

            for entry in entries[
                :10
            ]:

                try:

                    process_earthquake_entry(
                        entry
                    )

                except Exception as error:

                    print(
                        "地震エントリー処理エラー:",
                        error,
                        flush=True
                    )

        except Exception as error:

            print(
                "地震情報取得エラー:",
                error,
                flush=True
            )

        time.sleep(
            EARTHQUAKE_CHECK_INTERVAL
        )


def start_earthquake_monitor():

    thread = threading.Thread(
        target=
            earthquake_monitor_loop,

        name=
            "earthquake-monitor",

        daemon=True
    )

    thread.start()

    return thread


# =========================================================
# 天気予報監視・自動通知ループ（新機能）
# =========================================================

def check_weather_and_notify():

    if not OPENWEATHER_API_KEY:
        return

    params = {
        "lat": OPENWEATHER_LAT,
        "lon": OPENWEATHER_LON,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "ja"
    }

    try:
        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params=params,
            timeout=10
        )
        if not response.ok:
            return
        
        weather_data = response.json()
    except Exception as error:
        print("天気監視取得エラー:", error, flush=True)
        return

    weather_list = weather_data.get("weather", [])
    if not weather_list:
        return

    current_weather = weather_list[0].get("description", "不明")
    main_info = weather_data.get("main", {})
    temp = main_info.get("temp")
    city = weather_data.get("name", "天草市")

    data = load_data()
    last_state = data.get("last_weather_state", {})

    last_weather = last_state.get("description", "")
    
    # 初回または天候に変化があった場合
    if last_weather and last_weather != current_weather:
        message = f"{city}の天気予報が「{current_weather}」に変わりました。（気温: {temp}°C）"
        
        # もし雨や雪などの荒天に変わった場合は特別メッセージ
        if "雨" in current_weather or "雪" in current_weather or "雷" in current_weather:
            message = f"【お天気警報】{city}で「{current_weather}」が確認されました。傘の準備をしてください！"

        print("天気変更Push通知送信:", message, flush=True)
        notify_all_users(
            data,
            "天気予報の更新",
            message,
            {
                "type": "weather_update",
                "weather": current_weather,
                "temperature": temp
            }
        )

    # 状態を保存
    data["last_weather_state"] = {
        "description": current_weather,
        "temperature": temp,
        "updated_at": now_utc_iso()
    }
    save_data(data)


def weather_monitor_loop():

    print(
        "天気予報監視を開始します。",
        flush=True
    )

    while True:

        try:

            check_weather_and_notify()

        except Exception as error:

            print(
                "天気監視ループエラー:",
                error,
                flush=True
            )

        time.sleep(
            WEATHER_CHECK_INTERVAL
        )


def start_weather_monitor():

    thread = threading.Thread(
        target=
            weather_monitor_loop,

        name=
            "weather-monitor",

        daemon=True
    )

    thread.start()

    return thread


# =========================================================
# 手動地震Pushテスト
# =========================================================

@app.post(
    "/api/admin/test-earthquake"
)
@require_user
def test_earthquake_push(
    user
):

    data = load_data()

    notify_user(
        data,
        user["id"],
        "地震情報テスト",
        "これはWeb Pushのテスト通知です。",
        {
            "type":
                "earthquake_test"
        }
    )

    return jsonify({
        "ok":
            True,

        "message":
            "テストPush送信処理を実行しました。"
    })


# =========================================================
# OpenWeatherMap
# =========================================================

@app.get(
    "/api/weather"
)
def get_weather():

    if not OPENWEATHER_API_KEY:

        return jsonify({
            "error":
                "OPENWEATHER_API_KEYが設定されていません。"
        }), 500

    params = {
        "lat":
            OPENWEATHER_LAT,

        "lon":
            OPENWEATHER_LON,

        "appid":
            OPENWEATHER_API_KEY,

        "units":
            "metric",

        "lang":
            "ja"
    }

    try:

        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params=params,
            timeout=10
        )

    except requests.RequestException as error:

        return jsonify({
            "error":
                f"OpenWeatherMapへの接続に失敗しました: {error}"
        }), 502

    try:

        weather_data = (
            response.json()
        )

    except Exception:

        return jsonify({
            "error":
                "OpenWeatherMapから正しいデータを取得できませんでした。"
        }), 502

    if not response.ok:

        return jsonify({
            "error":
                weather_data.get(
                    "message",
                    f"OpenWeatherMap HTTP {response.status_code}"
                )
        }), response.status_code

    weather_list = (
        weather_data.get(
            "weather",
            []
        )
    )

    weather = (
        weather_list[0]
        if weather_list
        else {}
    )

    main = (
        weather_data.get(
            "main",
            {}
        )
    )

    wind = (
        weather_data.get(
            "wind",
            {}
        )
    )

    return jsonify({
        "ok":
            True,

        "city":
            weather_data.get(
                "name",
                "天草市"
            ),

        "description":
            weather.get(
                "description",
                "天候不明"
            ),

        "temperature":
            main.get(
                "temp"
            ),

        "feels_like":
            main.get(
                "feels_like"
            ),

        "humidity":
            main.get(
                "humidity"
            ),

        "wind_speed":
            wind.get(
                "speed"
            ),

        "weather":
            weather.get(
                "description"
            ),

        "timezone":
            weather_data.get(
                "timezone"
            ),

        "fetched_at":
            now_utc_iso()
    })


# =========================================================
# VAPID公開鍵
# =========================================================

@app.get(
    "/api/push/public-key"
)
def get_push_public_key():

    if not VAPID_PUBLIC_KEY:

        return jsonify({
            "error":
                "VAPID_PUBLIC_KEYが設定されていません。"
        }), 500

    return jsonify({
        "ok":
            True,

        "public_key":
            VAPID_PUBLIC_KEY
    })


# =========================================================
# エラーハンドリング
# =========================================================

@app.errorhandler(
    404
)
def not_found(
    error
):

    return jsonify({
        "error":
            "APIが見つかりません。"
    }), 404


@app.errorhandler(
    405
)
def method_not_allowed(
    error
):

    return jsonify({
        "error":
            "このHTTPメソッドには対応していません。"
    }), 405


@app.errorhandler(
    500
)
def internal_error(
    error
):

    return jsonify({
        "error":
            "サーバー内部でエラーが発生しました。"
    }), 500


# =========================================================
# 起動
# =========================================================

if __name__ == "__main__":

    ensure_data_file()

    print(
        "========================================"
    )

    print(
        "おてんきアプリ API"
    )

    print(
        "========================================"
    )

    print(
        f"データ保存先: {DATA_FILE}"
    )

    print(
        "SQL / SQLite: 使用しません"
    )

    print(
        "OPENWEATHER_API_KEY:",
        "設定済み"
        if OPENWEATHER_API_KEY
        else "未設定"
    )

    print(
        "VAPID_PUBLIC_KEY:",
        "設定済み"
        if VAPID_PUBLIC_KEY
        else "未設定"
    )

    print(
        "VAPID_PRIVATE_KEY:",
        "設定済み"
        if VAPID_PRIVATE_KEY
        else "未設定"
    )

    print(
        "Web Push:",
        "設定済み"
        if (
            webpush
            and
            VAPID_PRIVATE_KEY
        )
        else "未設定"
    )

    print(
        "地震情報:",
        "監視開始"
    )

    print(
        "天気予報監視:",
        "監視開始（10分おき）"
    )

    print(
        "現在位置追跡:",
        "実装なし"
    )

    print(
        "========================================"
    )

    start_earthquake_monitor()
    start_weather_monitor()

    app.run(
        host="0.0.0.0",

        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),

        debug=False,

        use_reloader=False
    )