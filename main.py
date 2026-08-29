import os
import json
import uuid
import datetime
import threading

import requests

from flask import Flask, request, jsonify
from flask_cors import CORS


# =========================================================
# Flask
# =========================================================

app = Flask(__name__)


# =========================================================
# 環境変数
# =========================================================

# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------
#
# RenderのEnvironment Variablesに
#
# CORS_ORIGINS=https://kuggie-programing.github.io
#
# のように設定してください。
#
# 複数指定:
#
# CORS_ORIGINS=https://example.com,https://example2.com
#
# 未設定時は *（開発用）
# ---------------------------------------------------------

CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "*"
).strip()


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


# ---------------------------------------------------------
# OpenWeatherMap
# ---------------------------------------------------------
#
# RenderのEnvironment Variablesに
#
# OPENWEATHER_API_KEY
#
# を設定する。
#
# APIキーをindex.htmlには書かない。
# ---------------------------------------------------------

OPENWEATHER_API_KEY = os.environ.get(
    "OPENWEATHER_API_KEY",
    ""
).strip()


# =========================================================
# 天草
# =========================================================

AMAKUSA_LAT = 32.4547
AMAKUSA_LON = 130.1978


# =========================================================
# JSONデータ保存
# =========================================================
#
# SQL / SQLiteは使用しない。
#
# このmain.pyと同じ場所に
#
# data.json
#
# を作って保存する。
#
# Renderで再起動すると消えて困る場合は、
# Render Diskなどの永続ストレージを使って
# DATA_FILEを変更してください。
#
# 例:
#
# DATA_FILE=/var/data/data.json
#
# =========================================================

DATA_FILE = os.environ.get(
    "DATA_FILE",
    os.path.join(
        os.path.dirname(
            os.path.abspath(__file__)
        ),
        "data.json"
    )
)


# JSONファイルへの同時アクセス対策
data_lock = threading.RLock()


# =========================================================
# 初期データ
# =========================================================

DEFAULT_DATA = {
    "groups": {}
}


# =========================================================
# データ読み込み
# =========================================================

def load_data():

    with data_lock:

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
            TypeError
        ) as e:

            app.logger.exception(
                "data.jsonの読み込みに失敗しました: %s",
                e
            )

            # 壊れたデータを勝手に上書きせず、
            # 空データとして起動する。
            return {
                "groups": {}
            }


# =========================================================
# データ保存
# =========================================================

def save_data(data):

    with data_lock:

        directory = os.path.dirname(
            os.path.abspath(DATA_FILE)
        )


        os.makedirs(
            directory,
            exist_ok=True
        )


        # 直接書き込まず一時ファイルへ書き、
        # 完了後に置き換える。
        temp_file = (
            DATA_FILE
            + ".tmp"
            + uuid.uuid4().hex
        )


        try:

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


                f.flush()


            os.replace(
                temp_file,
                DATA_FILE
            )


        finally:

            if os.path.exists(
                temp_file
            ):

                try:

                    os.remove(
                        temp_file
                    )

                except OSError:

                    pass


# =========================================================
# データ取得
# =========================================================

def get_data():

    return load_data()


# =========================================================
# 共通関数
# =========================================================

def now_iso():

    return datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()


def bad_request(
    msg,
    code=400
):

    return jsonify({
        "ok": False,
        "error": msg
    }), code


def group_exists(
    data,
    group_code
):

    return group_code in data["groups"]


def get_group(
    data,
    group_code
):

    return data["groups"].get(
        group_code
    )


def ensure_group_structure(
    group
):

    if not isinstance(
        group.get("members"),
        list
    ):

        group["members"] = []


    if not isinstance(
        group.get("safety_status"),
        list
    ):

        group["safety_status"] = []


    if not isinstance(
        group.get("hazard_posts"),
        list
    ):

        group["hazard_posts"] = []


# =========================================================
# ヘルスチェック
# =========================================================

@app.route(
    "/api/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "ok":
            True,

        "status":
            "ok",

        "weather_api_configured":
            bool(OPENWEATHER_API_KEY)

    })


# =========================================================
# 天気取得
# =========================================================
#
# GET /api/weather
#
# ブラウザ
#     ↓
# Render /api/weather
#     ↓
# OpenWeatherMap
#
# APIキーはサーバー側だけに置く。
# =========================================================

@app.route(
    "/api/weather",
    methods=["GET"]
)
def get_weather():

    # -----------------------------------------------------
    # APIキー確認
    # -----------------------------------------------------

    if not OPENWEATHER_API_KEY:

        app.logger.error(
            "OPENWEATHER_API_KEYが設定されていません。"
        )

        return bad_request(
            "OpenWeatherMap APIキーがサーバーに設定されていません。",
            500
        )


    try:

        # -------------------------------------------------
        # OpenWeatherMap Current Weather API
        # -------------------------------------------------

        url = (
            "https://api.openweathermap.org/data/2.5/weather"
        )


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


        response = requests.get(
            url,
            params=params,
            timeout=10
        )


        # -------------------------------------------------
        # OpenWeatherMapエラー
        # -------------------------------------------------

        if not response.ok:

            app.logger.error(
                "OpenWeatherMap HTTP %s: %s",
                response.status_code,
                response.text
            )


            if response.status_code == 401:

                return bad_request(
                    "OpenWeatherMap APIキーが無効です。",
                    502
                )


            if response.status_code == 429:

                return bad_request(
                    "OpenWeatherMapのAPI利用制限に達しました。",
                    502
                )


            return bad_request(
                "OpenWeatherMapから天気情報を取得できませんでした。",
                502
            )


        data = response.json()


        # -------------------------------------------------
        # データ
        # -------------------------------------------------

        weather_list = (
            data.get("weather")
            or []
        )


        weather = (
            weather_list[0]
            if weather_list
            else {}
        )


        main = (
            data.get("main")
            or {}
        )


        wind = (
            data.get("wind")
            or {}
        )


        clouds = (
            data.get("clouds")
            or {}
        )


        rain = (
            data.get("rain")
            or {}
        )


        sys_data = (
            data.get("sys")
            or {}
        )


        # -------------------------------------------------
        # 天気
        # -------------------------------------------------

        description = str(
            weather.get(
                "description",
                "天候不明"
            )
        )


        weather_main = str(
            weather.get(
                "main",
                ""
            )
        )


        weather_id = weather.get(
            "id"
        )


        icon = str(
            weather.get(
                "icon",
                ""
            )
        )


        # -------------------------------------------------
        # 気温
        # -------------------------------------------------

        temperature = main.get(
            "temp"
        )


        feels_like = main.get(
            "feels_like"
        )


        temp_min = main.get(
            "temp_min"
        )


        temp_max = main.get(
            "temp_max"
        )


        humidity = main.get(
            "humidity"
        )


        pressure = main.get(
            "pressure"
        )


        # -------------------------------------------------
        # 風
        # -------------------------------------------------

        wind_speed = wind.get(
            "speed",
            0
        )


        wind_deg = wind.get(
            "deg"
        )


        wind_gust = wind.get(
            "gust"
        )


        # -------------------------------------------------
        # 雲
        # -------------------------------------------------

        cloud_percent = clouds.get(
            "all"
        )


        # -------------------------------------------------
        # 降水
        # -------------------------------------------------

        rain_1h = rain.get(
            "1h",
            0
        )


        rain_3h = rain.get(
            "3h",
            0
        )


        # -------------------------------------------------
        # 時刻
        # -------------------------------------------------

        timestamp = data.get(
            "dt"
        )


        timezone_offset = data.get(
            "timezone",
            0
        )


        # -------------------------------------------------
        # 返却
        # -------------------------------------------------

        return jsonify({

            "ok":
                True,

            "source":
                "OpenWeatherMap",

            "city":
                data.get(
                    "name",
                    "天草"
                ),

            "country":
                sys_data.get(
                    "country",
                    "JP"
                ),

            "latitude":
                AMAKUSA_LAT,

            "longitude":
                AMAKUSA_LON,

            "weather":
                description,

            "description":
                description,

            "weather_main":
                weather_main,

            "weather_id":
                weather_id,

            "icon":
                icon,

            "temperature":
                temperature,

            "feels_like":
                feels_like,

            "temp_min":
                temp_min,

            "temp_max":
                temp_max,

            "humidity":
                humidity,

            "pressure":
                pressure,

            "wind_speed":
                wind_speed,

            "wind_deg":
                wind_deg,

            "wind_gust":
                wind_gust,

            "cloud_percent":
                cloud_percent,

            "rain_1h":
                rain_1h,

            "rain_3h":
                rain_3h,

            "timestamp":
                timestamp,

            "timezone_offset":
                timezone_offset

        })


    except requests.Timeout:

        app.logger.exception(
            "OpenWeatherMap接続タイムアウト"
        )

        return bad_request(
            "天気サーバーへの接続がタイムアウトしました。",
            504
        )


    except requests.RequestException:

        app.logger.exception(
            "OpenWeatherMap通信エラー"
        )

        return bad_request(
            "OpenWeatherMapとの通信に失敗しました。",
            502
        )


    except ValueError:

        app.logger.exception(
            "OpenWeatherMap JSON解析エラー"
        )

        return bad_request(
            "天気サーバーから正しいデータを取得できませんでした。",
            502
        )


    except Exception as e:

        app.logger.exception(
            "天気取得エラー"
        )

        return bad_request(
            f"サーバーエラー: {str(e)}",
            500
        )


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
            data.get(
                "group_code",
                ""
            )
        ).strip()


        password = str(
            data.get(
                "password",
                ""
            )
        ).strip()


        name = str(
            data.get(
                "name",
                ""
            )
        ).strip()


        if (
            not group_code
            or not password
            or not name
        ):

            return bad_request(
                "グループコード・パスワード・名前は必須です。"
            )


        with data_lock:

            db = load_data()


            if group_exists(
                db,
                group_code
            ):

                return bad_request(
                    "そのグループコードは既に使われています。"
                    "ログインを使ってください。",
                    409
                )


            created_at = now_iso()


            db["groups"][group_code] = {

                "password":
                    password,

                "created_at":
                    created_at,

                "members": [

                    name

                ],

                "safety_status": [],

                "hazard_posts": []

            }


            save_data(
                db
            )


            members = list(
                db["groups"][group_code]["members"]
            )


        return jsonify({

            "ok":
                True,

            "group_code":
                group_code,

            "members":
                members

        })


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
            data.get(
                "group_code",
                ""
            )
        ).strip()


        password = str(
            data.get(
                "password",
                ""
            )
        ).strip()


        name = str(
            data.get(
                "name",
                ""
            )
        ).strip()


        if (
            not group_code
            or not password
            or not name
        ):

            return bad_request(
                "グループコード・パスワード・名前は必須です。"
            )


        with data_lock:

            db = load_data()


            group = get_group(
                db,
                group_code
            )


            if group is None:

                return bad_request(
                    "そのグループコードは存在しません。"
                    "新規登録してください。",
                    404
                )


            ensure_group_structure(
                group
            )


            if group.get(
                "password"
            ) != password:

                return bad_request(
                    "パスワードが違います。",
                    401
                )


            if name not in group["members"]:

                group["members"].append(
                    name
                )


                save_data(
                    db
                )


            members = list(
                group["members"]
            )


        return jsonify({

            "ok":
                True,

            "group_code":
                group_code,

            "members":
                members

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

        with data_lock:

            db = load_data()


            group = get_group(
                db,
                group_code
            )


            if group is None:

                return bad_request(
                    "グループが存在しません。",
                    404
                )


            ensure_group_structure(
                group
            )


            members = list(
                group["members"]
            )


        return jsonify({

            "ok":
                True,

            "members":
                members

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
            data.get(
                "name",
                ""
            )
        ).strip()


        if not name:

            return bad_request(
                "名前は必須です。"
            )


        with data_lock:

            db = load_data()


            group = get_group(
                db,
                group_code
            )


            if group is None:

                return bad_request(
                    "グループが存在しません。",
                    404
                )


            ensure_group_structure(
                group
            )


            if name not in group["members"]:

                group["members"].append(
                    name
                )


                save_data(
                    db
                )


            members = list(
                group["members"]
            )


        return jsonify({

            "ok":
                True,

            "members":
                members

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

        with data_lock:

            db = load_data()


            group = get_group(
                db,
                group_code
            )


            if group is None:

                return bad_request(
                    "グループが存在しません。",
                    404
                )


            ensure_group_structure(
                group
            )


            members = group["members"]


            if len(members) <= 1:

                return bad_request(
                    "最低1人は残してください。"
                )


            if name in members:

                members.remove(
                    name
                )


                save_data(
                    db
                )


            members = list(
                members
            )


        return jsonify({

            "ok":
                True,

            "members":
                members

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

        with data_lock:

            db = load_data()


            group = get_group(
                db,
                group_code
            )


            if group is None:

                return bad_request(
                    "グループが存在しません。",
                    404
                )


            ensure_group_structure(
                group
            )


            records = group[
                "safety_status"
            ]


            # 名前ごとに最新の安否だけを残す
            latest = {}


            for record in records:

                record_name = record.get(
                    "name"
                )


                if not record_name:
                    continue


                latest[
                    record_name
                ] = record


            statuses = list(
                latest.values()
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
            data.get(
                "name",
                ""
            )
        ).strip()


        status = str(
            data.get(
                "status",
                ""
            )
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


        with data_lock:

            db = load_data()


            group = get_group(
                db,
                group_code
            )


            if group is None:

                return bad_request(
                    "グループが存在しません。",
                    404
                )


            ensure_group_structure(
                group
            )


            # 安否情報を追加
            group[
                "safety_status"
            ].append({

                "name":
                    name,

                "status":
                    status,

                "created_at":
                    now_iso()

            })


            # データが無限に増えないように
            # 最新200件まで保持
            group[
                "safety_status"
            ] = group[
                "safety_status"
            ][-200:]


            save_data(
                db
            )


        return jsonify({

            "ok":
                True

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

        with data_lock:

            db = load_data()


            group = get_group(
                db,
                group_code
            )


            if group is None:

                return bad_request(
                    "グループが存在しません。",
                    404
                )


            ensure_group_structure(
                group
            )


            posts = list(
                group[
                    "hazard_posts"
                ]
            )


            # 新しい順
            posts.sort(
                key=lambda x:
                    x.get(
                        "created_at",
                        ""
                    ),
                reverse=True
            )


            # 最大50件
            posts = posts[:50]


        return jsonify({

            "ok":
                True,

            "posts":
                posts

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
            data.get(
                "author",
                ""
            )
        ).strip()


        image = str(
            data.get(
                "image",
                ""
            )
        ).strip()


        text = str(
            data.get(
                "text",
                ""
            )
        ).strip()


        # -------------------------------------------------
        # 新形式
        # -------------------------------------------------

        latitude = data.get(
            "latitude",
            data.get(
                "lat"
            )
        )


        longitude = data.get(
            "longitude",
            data.get(
                "lon"
            )
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


        # -------------------------------------------------
        # 画像形式確認
        # -------------------------------------------------

        if not image.startswith(
            "data:image/"
        ):

            return bad_request(
                "画像データの形式が正しくありません。"
            )


        # -------------------------------------------------
        # 緯度
        # -------------------------------------------------

        if latitude is not None:

            try:

                latitude = float(
                    latitude
                )

            except (
                TypeError,
                ValueError
            ):

                return bad_request(
                    "緯度の値が正しくありません。"
                )


            if not (
                -90
                <= latitude
                <= 90
            ):

                return bad_request(
                    "緯度の範囲が正しくありません。"
                )


        # -------------------------------------------------
        # 経度
        # -------------------------------------------------

        if longitude is not None:

            try:

                longitude = float(
                    longitude
                )

            except (
                TypeError,
                ValueError
            ):

                return bad_request(
                    "経度の値が正しくありません。"
                )


            if not (
                -180
                <= longitude
                <= 180
            ):

                return bad_request(
                    "経度の範囲が正しくありません。"
                )


        # -------------------------------------------------
        # GPS精度
        # -------------------------------------------------

        if accuracy is not None:

            try:

                accuracy = float(
                    accuracy
                )

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


        # -------------------------------------------------
        # グループ確認
        # -------------------------------------------------

        with data_lock:

            db = load_data()


            group = get_group(
                db,
                group_code
            )


            if group is None:

                return bad_request(
                    "グループが存在しません。",
                    404
                )


            ensure_group_structure(
                group
            )


            post = {

                "id":
                    uuid.uuid4().hex,

                "author":
                    author,

                "image":
                    image,

                "text":
                    text,

                "lat":
                    latitude,

                "lon":
                    longitude,

                "latitude":
                    latitude,

                "longitude":
                    longitude,

                "accuracy":
                    accuracy,

                "created_at":
                    now_iso()

            }


            group[
                "hazard_posts"
            ].append(
                post
            )


            # 最大100件保存
            group[
                "hazard_posts"
            ] = group[
                "hazard_posts"
            ][-100:]


            save_data(
                db
            )


        return jsonify({

            "ok":
                True,

            "latitude":
                latitude,

            "longitude":
                longitude,

            "accuracy":
                accuracy

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
# エラーハンドラー
# =========================================================

@app.errorhandler(404)
def handle_404(error):

    return jsonify({

        "ok":
            False,

        "error":
            "指定されたAPIは存在しません。"

    }), 404


@app.errorhandler(405)
def handle_405(error):

    return jsonify({

        "ok":
            False,

        "error":
            "このHTTPメソッドには対応していません。"

    }), 405


@app.errorhandler(500)
def handle_500(error):

    app.logger.exception(
        "内部サーバーエラー"
    )

    return jsonify({

        "ok":
            False,

        "error":
            "サーバー内部でエラーが発生しました。"

    }), 500


# =========================================================
# 起動時データ確認
# =========================================================

def ensure_data_file():

    with data_lock:

        if not os.path.exists(
            DATA_FILE
        ):

            save_data(
                {
                    "groups": {}
                }
            )

            app.logger.info(
                "新しいdata.jsonを作成しました: %s",
                DATA_FILE
            )


# =========================================================
# Render / ローカル起動
# =========================================================

ensure_data_file()


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