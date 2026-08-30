import os
import json
import uuid
import hashlib
import tempfile
from datetime import datetime, timezone

import requests

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS


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

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


DATA_FILE = os.environ.get(
    "DATA_FILE",
    os.path.join(
        BASE_DIR,
        "data.json"
    )
)


OPENWEATHER_API_KEY = os.environ.get(
    "OPENWEATHER_API_KEY",
    ""
)


# 天草市
AMAKUSA_LAT = 32.4547
AMAKUSA_LON = 130.1978


OPENWEATHER_URL = (
    "https://api.openweathermap.org/data/2.5/weather"
)


# =========================================================
# JSON保存
# =========================================================

DEFAULT_DATA = {
    "groups": {}
}


def ensure_data_directory():
    directory = os.path.dirname(
        os.path.abspath(DATA_FILE)
    )

    if directory:
        os.makedirs(
            directory,
            exist_ok=True
        )


def load_data():
    ensure_data_directory()

    if not os.path.exists(DATA_FILE):
        return {
            "groups": {}
        }

    try:

        with open(
            DATA_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if not isinstance(data, dict):
            return {
                "groups": {}
            }

        if not isinstance(
            data.get("groups"),
            dict
        ):

            data["groups"] = {}

        return data

    except (
        json.JSONDecodeError,
        OSError,
        ValueError
    ):

        app.logger.exception(
            "data.jsonの読み込みに失敗しました"
        )

        return {
            "groups": {}
        }


def save_data(data):
    ensure_data_directory()

    directory = os.path.dirname(
        os.path.abspath(DATA_FILE)
    )

    fd = None
    temp_path = None

    try:

        fd, temp_path = tempfile.mkstemp(
            prefix="otenki_",
            suffix=".json",
            dir=directory,
            text=True
        )

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as f:

            fd = None

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

            f.flush()
            os.fsync(
                f.fileno()
            )

        os.replace(
            temp_path,
            DATA_FILE
        )

        temp_path = None

    except Exception:

        app.logger.exception(
            "data.jsonの保存に失敗しました"
        )

        raise

    finally:

        if fd is not None:

            try:
                os.close(fd)
            except OSError:
                pass

        if temp_path and os.path.exists(
            temp_path
        ):

            try:
                os.remove(
                    temp_path
                )
            except OSError:
                pass


# =========================================================
# 共通
# =========================================================

def now_iso():
    return (
        datetime.now(timezone.utc)
        .isoformat()
    )


def clean_string(
    value,
    max_length=200
):

    if value is None:
        return ""

    return str(value).strip()[:max_length]


def normalize_group_code(
    value
):

    return clean_string(
        value,
        100
    ).lower()


def hash_password(
    password
):

    salt = os.urandom(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(
            "utf-8"
        ),
        salt,
        200_000
    )

    return (
        salt.hex()
        + ":"
        + digest.hex()
    )


def verify_password(
    password,
    stored
):

    try:

        salt_hex, digest_hex = (
            stored.split(":")
        )

        salt = bytes.fromhex(salt_hex)

        expected = bytes.fromhex(digest_hex)

        actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(
                    "utf-8"
                ),
                salt,
                200_000
            )

        return (
            hashlib.compare_digest(
                actual,
                expected
            )
        )

    except Exception:

        return False


def make_group():

    return {
        "password_hash": "",
        "members": [],
        "safety": [],
        "hazards": [],
        "created_at": now_iso()
    }


def get_group(
    group_code
):

    data = load_data()

    return data["groups"].get(
        normalize_group_code(
            group_code
        )
    )


# =========================================================
# ヘルスチェック
# =========================================================

@app.route(
    "/api/health",
    methods=["GET"]
)
def health():

    return jsonify({
        "ok": True,
        "service": "otenki-app",
        "storage": "data.json",
        "weather": (
            "openweathermap"
        ),
        "open_meteo": False
    })


# =========================================================
# グループ登録
# =========================================================

@app.route(
    "/api/group/register",
    methods=["POST"]
)
def register_group():

    payload = request.get_json(
            silent=True
        ) or {}

    group_code = normalize_group_code(
            payload.get(
                "group_code"
            )
        )

    password = clean_string(
            payload.get(
                "password"
            ),
            200
        )

    name = clean_string(
            payload.get(
                "name"
            ),
            100
        )

    if not group_code:
        return jsonify({
            "error":
                "グループコードを入力してください。"
        }), 400

    if not password:
        return jsonify({
            "error":
                "パスワードを入力してください。"
        }), 400

    if not name:
        return jsonify({
            "error":
                "表示名を入力してください。"
        }), 400

    data = load_data()

    if group_code in data["groups"]:

        return jsonify({
            "error":
                "そのグループコードはすでに使用されています。"
        }), 409

    group = make_group()

    group["password_hash"] = hash_password(
            password
        )

    group["members"] = [
        name
    ]

    data["groups"][
        group_code
    ] = group

    save_data(
        data
    )

    return jsonify({
        "ok": True,
        "members":
            group["members"]
    })


# =========================================================
# グループログイン
# =========================================================

@app.route(
    "/api/group/login",
    methods=["POST"]
)
def login_group():

    payload = request.get_json(
            silent=True
        ) or {}

    group_code = normalize_group_code(
            payload.get(
                "group_code"
            )
        )

    password = clean_string(
            payload.get(
                "password"
            ),
            200
        )

    name = clean_string(
            payload.get(
                "name"
            ),
            100
        )

    if not group_code:
        return jsonify({
            "error":
                "グループコードを入力してください。"
        }), 400

    if not password:
        return jsonify({
            "error":
                "パスワードを入力してください。"
        }), 400

    if not name:
        return jsonify({
            "error":
                "表示名を入力してください。"
        }), 400

    data = load_data()

    group = data["groups"].get(
            group_code
        )

    if not group:

        return jsonify({
            "error":
                "グループコードまたはパスワードが正しくありません。"
        }), 401

    if not verify_password(
        password,
        group.get(
            "password_hash",
            ""
        )
    ):

        return jsonify({
            "error":
                "グループコードまたはパスワードが正しくありません。"
        }), 401

    members = group.get(
            "members",
            []
        )

    if name not in members:

        members.append(
            name
        )

        group["members"] = members

        save_data(
            data
        )

    return jsonify({
        "ok": True,
        "members":
            members
    })


# =========================================================
# メンバー取得
# =========================================================

@app.route(
    "/api/members/<group_code>",
    methods=["GET"]
)
def get_members(
    group_code
):

    group = get_group(
            group_code
        )

    if not group:

        return jsonify({
            "error":
                "グループが見つかりません。"
        }), 404

    return jsonify({
        "members":
            group.get(
                "members",
                []
            )
    })


# =========================================================
# メンバー追加
# =========================================================

@app.route(
    "/api/members/<group_code>",
    methods=["POST"]
)
def add_member(
    group_code
):

    payload = request.get_json(
            silent=True
        ) or {}

    name = clean_string(
            payload.get(
                "name"
            ),
            100
        )

    if not name:

        return jsonify({
            "error":
                "表示名を入力してください。"
        }), 400

    data = load_data()

    normalized = normalize_group_code(
            group_code
        )

    group = data["groups"].get(
            normalized
        )

    if not group:

        return jsonify({
            "error":
                "グループが見つかりません。"
        }), 404

    members = group.setdefault(
            "members",
            []
        )

    if name not in members:

        members.append(
            name
        )

    save_data(
        data
    )

    return jsonify({
        "ok": True,
        "members":
            members
    })


# =========================================================
# メンバー削除
# =========================================================

@app.route(
    "/api/members/<group_code>/<name>",
    methods=["DELETE"]
)
def delete_member(
    group_code,
    name
):

    data = load_data()

    normalized = normalize_group_code(
            group_code
        )

    group = data["groups"].get(
            normalized
        )

    if not group:

        return jsonify({
            "error":
                "グループが見つかりません。"
        }), 404

    member_name = clean_string(
            name,
            100
        )

    members = group.setdefault(
            "members",
            []
        )

    if len(members) <= 1:

        return jsonify({
            "error":
                "最低1人は残してください。"
        }), 400

    if member_name in members:

        members.remove(
            member_name
        )

    save_data(
        data
    )

    return jsonify({
        "ok": True,
        "members":
            members
    })


# =========================================================
# 安否取得
# =========================================================

@app.route(
    "/api/safety/<group_code>",
    methods=["GET"]
)
def get_safety(
    group_code
):

    group = get_group(
            group_code
        )

    if not group:

        return jsonify({
            "error":
                "グループが見つかりません。"
        }), 404

    return jsonify({
        "statuses":
            group.get(
                "safety",
                []
            )
    })


# =========================================================
# 安否送信
# =========================================================

@app.route(
    "/api/safety/<group_code>",
    methods=["POST"]
)
def post_safety(
    group_code
):

    payload = request.get_json(
            silent=True
        ) or {}

    name = clean_string(
            payload.get(
                "name"
            ),
            100
        )

    status = clean_string(
            payload.get(
                "status"
            ),
            50
        )

    if not name:

        return jsonify({
            "error":
                "表示名がありません。"
        }), 400

    if status not in {
        "safe",
        "messy",
        "sos"
    }:

        return jsonify({
            "error":
                "不正な安否ステータスです。"
        }), 400

    data = load_data()

    normalized = normalize_group_code(
            group_code
        )

    group = data["groups"].get(
            normalized
        )

    if not group:

        return jsonify({
            "error":
                "グループが見つかりません。"
        }), 404

    statuses = group.setdefault(
            "safety",
            []
        )

    new_status = {
        "id":
            uuid.uuid4().hex,

        "name":
            name,

        "status":
            status,

        "created_at":
            now_iso()
    }

    # 同じ人の最新状態を優先
    statuses = [
            item
            for item in statuses
            if item.get("name") != name
        ]

    statuses.insert(
        0,
        new_status
    )

    # 古すぎる履歴を無限に増やさない
    group["safety"] = statuses[:100]

    save_data(
        data
    )

    return jsonify({
        "ok": True,
        "status":
            new_status
    })


# =========================================================
# 危険情報取得
# =========================================================

@app.route(
    "/api/hazard/<group_code>",
    methods=["GET"]
)
def get_hazards(
    group_code
):

    group = get_group(
            group_code
        )

    if not group:

        return jsonify({
            "error":
                "グループが見つかりません。"
        }), 404

    return jsonify({
        "posts":
            group.get(
                "hazards",
                []
            )
    })


# =========================================================
# 危険情報投稿
# =========================================================

@app.route(
    "/api/hazard/<group_code>",
    methods=["POST"]
)
def post_hazard(
    group_code
):

    payload = request.get_json(
            silent=True
        ) or {}

    author = clean_string(
            payload.get(
                "author"
            ),
            100
        )

    text = clean_string(
            payload.get(
                "text"
            ),
            1000
        )

    image = payload.get(
            "image",
            ""
        )

    latitude = payload.get(
            "latitude"
        )

    longitude = payload.get(
            "longitude"
        )

    accuracy = payload.get(
            "accuracy"
        )

    if not author:

        return jsonify({
            "error":
                "投稿者名がありません。"
        }), 400

    if not text:

        return jsonify({
            "error":
                "危険内容を入力してください。"
        }), 400

    # -----------------------------------------------------
    # 緯度経度
    # -----------------------------------------------------

    try:

        latitude = float(latitude)

        longitude = float(longitude)

    except (
        TypeError,
        ValueError
    ):

        return jsonify({
            "error":
                "位置情報が正しくありません。"
        }), 400

    if not (
        -90 <= latitude <= 90
    ):

        return jsonify({
            "error":
                "緯度が不正です。"
        }), 400

    if not (
        -180 <= longitude <= 180
    ):

        return jsonify({
            "error":
                "経度が不正です。"
        }), 400

    if accuracy is not None:

        try:

            accuracy = float(accuracy)

        except (
            TypeError,
            ValueError
        ):

            accuracy = None

    # -----------------------------------------------------
    # 画像
    # -----------------------------------------------------

    if image:

        image = str(image)

        # Data URL以外は保存しない
        if not image.startswith(
            "data:image/"
        ):

            image = ""

        # 極端に大きい画像を拒否
        if len(image) > 8_000_000:

            return jsonify({
                "error":
                    "画像が大きすぎます。もう少し小さい画像で投稿してください。"
            }), 413

    data = load_data()

    normalized = normalize_group_code(
            group_code
        )

    group = data["groups"].get(
            normalized
        )

    if not group:

        return jsonify({
            "error":
                "グループが見つかりません。"
        }), 404

    post = {

        "id":
            uuid.uuid4().hex,

        "author":
            author,

        "text":
            text,

        "image":
            image,

        # ここは投稿時のGPS座標を
        # そのまま保存する。
        "latitude":
            latitude,

        "longitude":
            longitude,

        "accuracy":
            accuracy,

        "created_at":
            now_iso()
    }

    hazards = group.setdefault(
            "hazards",
            []
        )

    hazards.insert(
        0,
        post
    )

    # 無限に増え続けないようにする
    group["hazards"] = hazards[:100]

    save_data(
        data
    )

    return jsonify({
        "ok": True,
        "post":
            post
    })


# =========================================================
# OpenWeatherMap
# =========================================================

@app.route(
    "/api/weather",
    methods=["GET"]
)
def get_weather():

    if not OPENWEATHER_API_KEY:

        app.logger.error(
            "OPENWEATHER_API_KEYが設定されていません。"
        )

        return jsonify({
            "error":
                "OPENWEATHER_API_KEYがRenderの環境変数に設定されていません。"
        }), 500

    params = {

        "lat":
            AMAKUSA_LAT,

        "lon":
            AMAKUSA_LON,

        "appid":
            OPENWEATHER_API_KEY,

        "units":
            "metric",

        "lang":
            "ja"
    }

    try:

        response = requests.get(
                OPENWEATHER_URL,
                params=params,
                timeout=15
            )

    except requests.RequestException:

        app.logger.exception(
            "OpenWeatherMapへの接続に失敗しました。"
        )

        return jsonify({
            "error":
                "OpenWeatherMapへ接続できませんでした。"
        }), 502

    if response.status_code != 200:

        app.logger.error(
            "OpenWeatherMap HTTP %s: %s",
            response.status_code,
            response.text[:500]
        )

        if response.status_code in {
            401,
            403
        }:

            return jsonify({
                "error":
                    "OpenWeatherMap APIキーが無効または利用できません。"
            }), 502

        return jsonify({
            "error":
                "OpenWeatherMapから天気情報を取得できませんでした。"
        }), 502

    try:

        weather = response.json()

    except ValueError:

        return jsonify({
            "error":
                "OpenWeatherMapの応答を読み取れませんでした。"
        }), 502

    weather_list = weather.get(
            "weather",
            []
        )

    first_weather = (
            weather_list[0]
            if weather_list
            else {}
        )

    main = weather.get(
            "main",
            {}
        )

    wind = weather.get(
            "wind",
            {}
        )

    # OpenWeatherMapのUNIX timestampを
    # JSTのISO形式にも変換
    timestamp = weather.get(
            "dt"
        )

    jst_time = None

    if timestamp is not None:

        try:

            from datetime import timedelta

            jst = datetime.fromtimestamp(
                    float(timestamp),
                    timezone.utc
                ).astimezone(
                    timezone(
                        timedelta(hours=9)
                    )
                )

            jst_time = jst.isoformat()

        except Exception:

            jst_time = None

    return jsonify({

        "ok":
            True,

        "source":
            "OpenWeatherMap",

        "city":
            weather.get(
                "name",
                "天草市"
            ),

        "description":
            first_weather.get(
                "description",
                "天候不明"
            ),

        "weather":
            first_weather.get(
                "description",
                "天候不明"
            ),

        "weather_main":
            first_weather.get(
                "main",
                ""
            ),

        "weather_icon":
            first_weather.get(
                "icon",
                ""
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

        "pressure":
            main.get(
                "pressure"
            ),

        "wind_speed":
            wind.get(
                "speed"
            ),

        "wind_deg":
            wind.get(
                "deg"
            ),

        "visibility":
            weather.get(
                "visibility"
            ),

        "latitude":
            AMAKUSA_LAT,

        "longitude":
            AMAKUSA_LON,

        "observed_at":
            jst_time

    })


# =========================================================
# フロントエンド配信
# =========================================================

@app.route(
    "/",
    methods=["GET"]
)
def index():

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


@app.route(
    "/index.html",
    methods=["GET"]
)
def index_html():

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


# =========================================================
# エラーハンドリング
# =========================================================

@app.errorhandler(404)
def not_found(error):

    if request.path.startswith(
        "/api/"
    ):

        return jsonify({
            "error":
                "APIが見つかりません。"
        }), 404

    return (
        "Not Found",
        404
    )


@app.errorhandler(413)
def request_too_large(error):

    return jsonify({
        "error":
            "送信データが大きすぎます。"
    }), 413


@app.errorhandler(500)
def internal_error(error):

    app.logger.exception(
        "Internal Server Error"
    )

    if request.path.startswith(
        "/api/"
    ):

        return jsonify({
            "error":
                "サーバー内部でエラーが発生しました。"
        }), 500

    return (
        "Internal Server Error",
        500
    )


# =========================================================
# 起動
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