天草 お天気防災アプリ - 公開用完成版

【このフォルダをそのまま公開用プロジェクトとして使えます】

必須ファイル
- index.html
- main.py
- app.css
- main.js
- sw.js
- manifest.webmanifest
- quiz.txt
- requirements.txt
- icon.png / icon-192.png / icon-512.png
- badge.png / badge-96.png
- otenki_data.json

【ローカル起動】
1. python -m pip install -r requirements.txt
2. 環境変数を設定
3. python main.py
4. http://127.0.0.1:5000 を開く

【公開サーバー】
起動コマンド:
gunicorn --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT main:app

環境変数:
OPENWEATHER_API_KEY
VAPID_PUBLIC_KEY
VAPID_PRIVATE_KEY
VAPID_CLAIMS_EMAIL
OTENKI_DATA_FILE（任意）

※ private_key.pem のような秘密鍵ファイルは公開フォルダやGitHubへ入れないでください。
※ Web Push と PWA は HTTPS 公開で使用してください。
※ データを永続化する公開環境では、otenki_data.json の保存先に永続ディスクを指定してください。
