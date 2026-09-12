<!DOCTYPE html>

<html lang="ja">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>天草 お天気防災アプリ</title>
<meta content="#0284c7" name="theme-color"/>
<meta content="yes" name="mobile-web-app-capable"/>
<meta content="yes" name="apple-mobile-web-app-capable"/>
<meta content="default" name="apple-mobile-web-app-status-bar-style"/>
<meta content="毎日の天気から、家族の防災ルールと地域の安全を考えるフェーズフリー防災アプリ" name="description"/>
<link href="/manifest.webmanifest" rel="manifest"/>
<link href="/icon-192.png" rel="icon"/>
<link href="/icon-192.png" rel="apple-touch-icon"/>
<link href="/app.css?v=20260911-auth5" rel="stylesheet"/>

<style>
        html, body {
            margin: 0;
            padding: 0;
            min-height: 100%;
        }
        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: linear-gradient(180deg, #eff6ff 0%, #f8fafc 50%, #ecfeff 100%);
            color: #0f172a;
        }
        .glass-header {
            background: linear-gradient(135deg, rgba(14, 165, 233, .95), rgba(37, 99, 235, .95));
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
        }
        .screen {
            min-height: calc(100vh - 72px);
        }
        .hidden {
            display: none !important;
        }
        button:disabled {
            cursor: not-allowed;
            opacity: .55;
        }
        img {
            max-width: 100%;
        }
        input, button, textarea, select {
            font: inherit;
        }
        button, .tap-card {
            touch-action: manipulation;
        }
        .choice-selected {
            border-color: #0284c7 !important;
            background: #e0f2fe !important;
            box-shadow: 0 0 0 3px rgba(14, 165, 233, .18);
        }
        .rule-choice-selected {
            border-color: #7c3aed !important;
            background: #f5f3ff !important;
            box-shadow: 0 0 0 3px rgba(124, 58, 237, .14);
        }
        .safe-area-bottom {
            padding-bottom: max(1rem, env(safe-area-inset-bottom));
        }
        .offline-soft-pattern {
            background-image: radial-gradient(circle at 20% 20%, rgba(14,165,233,.08) 0, rgba(14,165,233,.08) 2px, transparent 2px);
            background-size: 18px 18px;
        }
        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after {
                scroll-behavior: auto !important;
                transition-duration: .01ms !important;
                animation-duration: .01ms !important;
            }
        }
        .weather-card {
            background: linear-gradient(135deg, rgba(255,255,255,.96), rgba(239,246,255,.96));
        }
        .safe-card {
            background: linear-gradient(135deg, rgba(255,255,255,.97), rgba(240,253,250,.96));
        }
        .danger-card {
            background: linear-gradient(135deg, rgba(255,255,255,.97), rgba(255,247,237,.96));
        }
        .friend-card {
            background: linear-gradient(135deg, rgba(255,255,255,.98), rgba(245,243,255,.96));
        }
        .request-card {
            background: linear-gradient(135deg, rgba(255,255,255,.98), rgba(239,246,255,.98));
        }
        .modal-backdrop {
            background: rgba(15, 23, 42, .55);
            backdrop-filter: blur(5px);
            -webkit-backdrop-filter: blur(5px);
        }
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 9999px;
            display: inline-block;
        }

        body.emergency-active {
            background: linear-gradient(180deg, #fff7ed 0%, #fff1f2 48%, #f8fafc 100%);
        }

        body.emergency-active .glass-header {
            background: linear-gradient(135deg, rgba(225, 29, 72, .98), rgba(234, 88, 12, .98));
        }

        .emergency-pulse {
            animation: emergencyPulse 1.8s ease-in-out infinite;
        }

        @keyframes emergencyPulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(244, 63, 94, .18); }
            50% { box-shadow: 0 0 0 8px rgba(244, 63, 94, 0); }
        }

        @media (prefers-reduced-motion: reduce) {
            .emergency-pulse { animation: none !important; }
        }
    
        /* カンプに合わせたホーム背景 */
        #screen-dashboard {
            background-image: radial-gradient(circle, rgba(14,165,233,.10) 1.2px, transparent 1.2px);
            background-size: 24px 24px;
        }
    </style>
<script defer="" src="/api-config.js?v=20260911-auth5"></script><script defer="" src="/main.js?v=20260911-auth5"></script></head>
<body class="app-version-auth5">
<header class="glass-header text-white border-b border-slate-700/20 sticky top-0 z-50 shadow-lg">
<div class="max-w-4xl mx-auto px-5 py-4 flex justify-between items-center app-header-row">
<div class="flex items-center space-x-3">
<img alt="防災アプリ" class="w-10 h-10 rounded-xl object-contain bg-white/15 p-1" src="/icon-192.png"/>
<div>
<h1 class="font-extrabold text-lg">防災アプリ</h1>
<p class="text-[10px] text-white/80">天草の天気・防災・家族・友達</p>
</div>
</div>
<div class="hidden flex items-center gap-2 app-header-actions" id="headerUserArea">
<span class="text-xs font-bold app-header-user" id="currentUserLabel"></span>
<button class="text-[11px] bg-rose-500/90 hover:bg-rose-600 border border-white/30 px-3 py-1.5 rounded-xl font-black shadow-sm" id="headerEmergencyButton" onclick="enterEmergencyMode()">🚨 緊急</button>
<button class="text-[11px] bg-white/20 hover:bg-white/30 px-3 py-1.5 rounded-xl font-bold" onclick="handleLogout()">ログアウト</button>
</div>
</div>
</header>
<!-- ログイン / アカウント作成 -->
<section class="screen flex items-center justify-center px-5 py-7" id="screen-login">
<div class="w-full max-w-md bg-white rounded-3xl shadow-xl border border-sky-100 p-6">
<div class="text-center mb-5">
<img alt="防災アプリ" class="w-20 h-20 mx-auto mb-3 object-contain" src="/icon-192.png"/>
<h2 class="text-2xl font-black text-slate-800">防災アプリ</h2>
<p class="text-sm text-slate-500 mt-2">登録したセキュリティキーでログイン</p></div>
<form id="loginForm" novalidate="">
<label class="block text-sm font-bold text-slate-700" for="loginName">表示名 <span class="text-xs text-slate-500">（新規登録のときだけ必須）</span></label>
<input autocomplete="username" class="mt-2 w-full border border-slate-200 rounded-2xl px-4 py-3" id="loginName" maxlength="100" name="username" placeholder="新規登録する人の名前" type="text"/>
<label class="block text-sm font-bold text-slate-700 mt-4" for="loginSecurityKey">セキュリティキー</label>
<div class="auth-key-row">
<input aria-describedby="securityKeyHelp capsLockHint" autocapitalize="none" autocomplete="current-password" autocorrect="off" class="w-full border border-slate-200 rounded-2xl px-4 py-3" id="loginSecurityKey" maxlength="512" name="password" placeholder="登録したときと同じキー" spellcheck="false" type="password"/>
<button aria-pressed="false" class="auth-key-toggle" id="showSecurityKey" onclick="toggleSecurityKeyVisibility()" type="button">表示</button>
</div>
<p class="text-xs text-slate-500 mt-2" id="securityKeyHelp">大文字・小文字・全角・半角は区別されます。ログインでは表示名を入力しなくても大丈夫です。</p>
<p class="text-xs text-amber-800 mt-2" hidden="" id="capsLockHint">Caps Lockがオンです。大文字・小文字を確認してください。</p>
<label class="flex gap-2 items-center mt-4 text-sm text-slate-700"><input id="rememberLogin" type="checkbox"/>この端末にログイン状態を保存する</label>
<p class="text-xs text-slate-500 mt-1">共有の端末ではチェックせずに使ってください。</p>
<div aria-live="polite" class="hidden mt-4 text-sm font-bold p-3 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900" id="loginErrorMsg" role="status"></div>
<button class="mt-5 w-full bg-sky-600 text-white rounded-2xl py-3 font-black" id="loginLoginBtn" type="submit">ログイン</button>
<button class="mt-3 w-full border border-slate-200 rounded-2xl py-3" hidden="" id="cancelLoginButton" onclick="cancelLogin()" type="button">接続を取り消す</button>
<div class="mt-5 border-t border-slate-200 pt-4">
<p class="text-sm font-black">初めて使う人</p>
<p class="text-xs text-slate-500 mt-1">表示名と、自分で控えたキーを入力して登録します。キーを忘れても表示名だけで再発行はできません。</p>
<button class="mt-3 w-full bg-slate-100 text-slate-800 rounded-2xl py-3 font-black" id="loginRegisterBtn" onclick="handleAuth('register')" type="button">新しくアカウントを作る</button>
<button class="mt-3 text-sm text-sky-700 underline" onclick="makeSecurityKey()" type="button">新規登録用のキーを作る</button>
</div></form>
<button class="mt-5 w-full bg-rose-50 border border-rose-200 text-rose-800 rounded-2xl py-3 font-black" onclick="enterEmergencyMode()" type="button">緊急モードを開く</button>
<button class="hidden mt-3 w-full bg-cyan-50 border border-cyan-200 text-cyan-900 rounded-2xl py-3 font-black" id="openSavedOfflineBtn" onclick="openLastSavedOfflineInfo()" type="button">保存した安心メモを見る</button>
<p class="hidden mt-2 text-xs text-center text-cyan-700" id="offlineLoginHint">この端末に保存した情報を開きます。別の人の保存情報の場合もあります。</p>
<details class="mt-5 border-t border-slate-200 pt-4 text-xs text-slate-500">
<summary class="font-bold cursor-pointer">接続先・ログインできないとき</summary>
<p class="mt-2">接続先：<span class="break-all" id="loginApiTarget"></span></p>
<p class="mt-2">更新前の登録データと同じサーバーに接続してください。接続先を別サーバーにする場合は api-config.js を設定します。</p>
<button class="mt-3 border border-slate-200 rounded-xl px-3 py-2" onclick="checkConnection()" type="button">接続を確認する</button>
<p class="mt-2" id="loginConnectionStatus" role="status"></p>
</details>
<p class="text-xs text-slate-400 mt-5 text-center">更新版 2026.09.11-auth5</p>
</div></section>
<!-- ダッシュボード -->
<section class="screen hidden px-4 sm:px-5 py-6" id="screen-dashboard">
<div class="max-w-4xl mx-auto space-y-5">
<!-- 災害時：最上段に常時見える入口 -->
<button class="emergency-pulse w-full text-left bg-gradient-to-r from-rose-50 to-orange-50 hover:from-rose-100 hover:to-orange-100 border-2 border-rose-200 rounded-3xl p-4 sm:p-5 shadow-sm" onclick="enterEmergencyMode()">
<div class="flex items-center gap-4">
<div class="w-14 h-14 shrink-0 rounded-2xl bg-rose-500 text-white flex items-center justify-center text-3xl shadow-sm">🚨</div>
<div class="flex-1 min-w-0">
<p class="text-[11px] text-rose-600 font-black">災害が起きたら</p>
<h2 class="text-xl sm:text-2xl font-black text-slate-900">緊急モード</h2>
<p class="text-xs text-slate-600 mt-1">まず安全 → 安否 → 家族の約束 → 集合場所の順で確認</p>
</div>
<span class="text-2xl text-rose-500 font-black">›</span>
</div>
</button>
<!-- ふだんから準備しておく2つ -->
<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
<button class="bg-white hover:bg-orange-50 border border-slate-200 rounded-3xl p-5 sm:p-6 text-left shadow-sm" onclick="switchScreen('offline-kit')">
<div class="flex items-start gap-4">
<div class="w-12 h-12 rounded-2xl bg-orange-50 border border-orange-100 flex items-center justify-center text-2xl">📴</div>
<div>
<h3 class="font-black text-slate-800 text-lg">オフライン安心メモ</h3>
<p class="text-xs text-slate-500 mt-1">集合場所・連絡先・家族ルールを保存</p>
</div>
</div>
</button>
<button class="bg-white hover:bg-violet-50 border border-slate-200 rounded-3xl p-5 sm:p-6 text-left shadow-sm" onclick="switchScreen('family-rules')">
<div class="flex items-start gap-4">
<div class="w-12 h-12 rounded-2xl bg-violet-50 border border-violet-100 flex items-center justify-center text-2xl">🏠</div>
<div>
<h3 class="font-black text-slate-800 text-lg">わたしの行動ルール</h3>
<p class="text-xs text-slate-500 mt-1">場面を選んで、家族のルールを作る</p>
</div>
</div>
</button>
</div>
<!-- 安否確認：独立して目立たせる -->
<div class="flex justify-center">
<button class="w-full sm:w-[58%] bg-white hover:bg-sky-50 border border-slate-200 rounded-3xl p-5 text-left shadow-sm" onclick="switchScreen('safety')">
<div class="flex items-center gap-4 justify-center sm:justify-start">
<div class="w-12 h-12 rounded-2xl bg-sky-50 border border-sky-100 flex items-center justify-center text-2xl">🛡️</div>
<div>
<h3 class="font-black text-slate-800 text-lg">安否確認</h3>
<p class="text-xs text-slate-500 mt-1">自分の安否を大切な人へ共有</p>
</div>
</div>
</button>
</div>
<!-- このアプリの主役：あした、どうする？ -->
<div class="bg-white/95 rounded-3xl border border-sky-100 shadow-xl overflow-hidden relative">
<div class="absolute -right-8 -top-10 w-40 h-40 rounded-full bg-yellow-100/70"></div>
<div class="absolute right-10 top-5 w-20 h-20 rounded-full bg-sky-100/70"></div>
<div class="relative p-5 sm:p-7 grid grid-cols-1 lg:grid-cols-[120px_1fr_150px] gap-5 items-center">
<div class="flex lg:block items-center gap-4">
<img alt="防災アプリの案内マーク" class="w-20 h-20 sm:w-24 sm:h-24 object-contain drop-shadow-md" src="/icon-192.png"/>
<div class="lg:mt-3 bg-sky-50 border border-sky-200 rounded-2xl px-3 py-2 text-xs font-black text-sky-800">
<span id="tomorrowMascotMessage">明日の天気を見て、どうそなえるか考えよう。</span>
</div>
</div>
<div class="min-w-0">
<p class="text-[11px] text-sky-600 font-black tracking-wide">明日の自分を先に考える</p>
<h2 class="text-3xl sm:text-4xl font-black text-slate-900 mt-1">あした、どうする？</h2>
<p class="text-xs sm:text-sm text-slate-500 mt-2">天気を見て、自分で考えて、わからなければ家族と相談しよう。</p>
<div class="mt-4 bg-gradient-to-r from-sky-50 to-cyan-50 border border-sky-200 rounded-2xl p-4">
<div class="flex flex-wrap items-center justify-between gap-3">
<div>
<p class="text-[10px] text-sky-600 font-black">あしたの天気</p>
<p class="text-lg sm:text-xl font-black text-slate-900 mt-1" id="dashboardTomorrowWeather">天気を確認中...</p>
</div>
<div class="text-right">
<p class="text-sm font-black text-slate-700" id="dashboardTomorrowTemp">--℃ / --℃</p>
<p class="text-xs text-slate-500 mt-1" id="dashboardTomorrowRain">降水確率 --%</p>
</div>
</div>
</div>
</div>
<button aria-label="知恵貯金を見る" class="relative bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-3xl p-3 text-center shadow-sm transition" onclick="openWisdomBank()">
<img alt="知恵貯金" class="w-16 h-16 mx-auto object-contain drop-shadow-sm" src="/tyokin.png"/>
<p class="text-[11px] font-black text-amber-800 mt-1">知恵貯金</p>
<p class="text-2xl font-black text-amber-700 mt-0.5" id="wisdomBankCount">0</p>
<p class="text-[9px] text-amber-700 mt-1">タップして見返す</p>
</button>
</div>
<div class="relative border-t border-sky-100 bg-sky-50/40 p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
<button class="bg-sky-600 hover:bg-sky-700 text-white border border-sky-600 rounded-2xl p-4 text-left shadow-sm" onclick="openTomorrowPlan()">
<div class="text-2xl">🌤️</div><p class="text-sm font-black mt-2">明日のそなえを始める</p><p class="text-[10px] text-white/80 mt-1">天気 → 持ち物 → 時間 → 注意 → 家族相談</p>
</button>
<button class="bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-2xl p-4 text-left shadow-sm" onclick="openWisdomBank()">
<div class="text-2xl">💡</div><p class="text-sm font-black mt-2 text-amber-900">知恵貯金を見る</p><p class="text-[10px] text-amber-700 mt-1">前に考えたことを次に活かす</p>
</button>
<button class="bg-violet-50 hover:bg-violet-100 border border-violet-200 rounded-2xl p-4 text-left shadow-sm" onclick="switchScreen('family-rules')">
<div class="text-2xl">🏠</div><p class="text-sm font-black mt-2 text-violet-900">家族との約束</p><p class="text-[10px] text-violet-700 mt-1">連絡・集合・待つ場所を決める</p>
</button>
<button class="bg-cyan-50 hover:bg-cyan-100 border border-cyan-200 rounded-2xl p-4 text-left shadow-sm" onclick="switchScreen('offline-kit')">
<div class="text-2xl">📴</div><p class="text-sm font-black mt-2 text-cyan-900">安心メモ</p><p class="text-[10px] text-cyan-700 mt-1">通信がない時も確認する</p>
</button>
</div>
</div>
<!-- 家族・友達 -->
<div class="friend-card border border-white rounded-3xl p-5 shadow-lg">
<div class="flex justify-between items-center gap-3">
<div>
<p class="text-[10px] text-slate-400 font-bold">家族・友達</p>
<h3 class="font-black text-slate-800">つながっている人</h3>
</div>
<div class="flex items-center gap-2">
<span class="hidden bg-rose-500 text-white text-[10px] font-black rounded-full px-2 py-1" id="requestCountBadge">0</span>
<button class="bg-purple-500 hover:bg-purple-600 text-white rounded-xl px-3 py-2 text-xs font-black" onclick="openFriendModal()">＋追加</button>
</div>
</div>
<div class="space-y-2 mt-4" id="friendsList"></div>
<div class="mt-4 pt-4 border-t border-slate-100">
<p class="text-[10px] text-slate-400 font-bold mb-2">家族・友達リクエスト</p>
<div class="space-y-3" id="friendRequestsList"></div>
</div>
</div>
<!-- 地域・学び・天気の補助機能 -->
<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
<button class="bg-white hover:bg-orange-50 border border-slate-200 rounded-3xl p-5 text-left shadow-sm" onclick="switchScreen('hazard')">
<div class="text-3xl mb-2">🗺️</div>
<h3 class="font-black text-slate-800">まちの安全情報</h3>
<p class="text-xs text-slate-500 mt-1">危ない場所と、助けを求められる場所</p>
</button>
<button class="bg-white hover:bg-yellow-50 border border-slate-200 rounded-3xl p-5 text-left shadow-sm" onclick="openQuizScreen()">
<div class="text-3xl mb-2">🧠</div>
<h3 class="font-black text-slate-800">考えるクイズ</h3>
<p class="text-xs text-slate-500 mt-1">状況に合わせて考える練習</p>
</button>
<button class="bg-white hover:bg-sky-50 border border-slate-200 rounded-3xl p-5 text-left shadow-sm" onclick="switchScreen('weather')">
<div class="text-3xl mb-2">🌤️</div>
<h3 class="font-black text-slate-800">天気・準備</h3>
<p class="text-xs text-slate-500 mt-1">今日と明日の天気を詳しく見る</p>
</button>
</div>
<!-- 接続・通知：最下部に控えめに -->
<div class="bg-white/85 border border-slate-200 rounded-3xl p-4 shadow-sm">
<div class="flex flex-wrap justify-between items-center gap-3">
<div>
<p class="text-[10px] text-slate-400 font-bold">接続・通知</p>
<p class="text-[10px] text-slate-500 mt-1" id="networkStatusText">ネットワークを確認中...</p>
<p class="text-[10px] text-slate-400 mt-1" id="pushPermissionStatus">プッシュ通知を確認中...</p>
<span class="text-[10px] text-slate-400" id="globalConnectionStatus">確認中...</span>
</div>
<div class="flex flex-wrap gap-2">
<button class="bg-sky-500 hover:bg-sky-600 text-white rounded-xl px-3 py-2 text-[10px] font-bold" id="enablePushButton">🔔 通知ON</button>
<button class="bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl px-3 py-2 text-[10px] font-bold" id="disablePushButton">🔕 通知OFF</button>
<button class="hidden bg-cyan-500 hover:bg-cyan-600 text-white rounded-xl px-3 py-2 text-[10px] font-bold" id="installAppButton" onclick="installPwaApp()">📲 ホーム画面に追加</button>
</div>
</div>
<p class="text-[10px] text-slate-400 font-bold mt-2" id="welcomeUserName"></p>
</div>
</div>
</section>
<!-- 明日のそなえ -->
<section class="screen hidden px-4 sm:px-5 py-6" id="screen-tomorrow-plan">
<div class="max-w-3xl mx-auto">
<button class="mb-4 text-xs font-bold text-sky-700" onclick="backToHome()">← 戻る</button>
<div class="bg-white/95 rounded-3xl border border-sky-100 shadow-xl overflow-hidden">
<div class="bg-gradient-to-r from-sky-500 to-cyan-500 text-white p-5 sm:p-7">
<p class="text-xs font-black text-white/80">明日の自分を先に考える</p><h2 class="text-3xl font-black mt-1">あした、どうする？</h2>
<p class="text-sm text-white/90 mt-2">正解を当てる画面ではありません。自分で考えて、分からなければ家族と相談しよう。</p>
<div class="mt-5 grid grid-cols-5 gap-2"><div class="h-2 rounded-full bg-white" data-tomorrow-step-dot="1"></div><div class="h-2 rounded-full bg-white/30" data-tomorrow-step-dot="2"></div><div class="h-2 rounded-full bg-white/30" data-tomorrow-step-dot="3"></div><div class="h-2 rounded-full bg-white/30" data-tomorrow-step-dot="4"></div><div class="h-2 rounded-full bg-white/30" data-tomorrow-step-dot="5"></div></div>
</div>
<div class="p-5 sm:p-7">
<div data-tomorrow-step="1"><p class="text-xs text-sky-600 font-black">STEP 1 / 5</p><h3 class="text-xl font-black mt-1">明日の天気を確認</h3><div class="mt-4 bg-sky-50 border border-sky-200 rounded-3xl p-5"><p class="text-2xl font-black" id="tomorrowPlanWeather">確認中...</p><div class="flex flex-wrap gap-3 mt-2 text-sm font-bold text-slate-600"><span id="tomorrowPlanTemp">--℃ / --℃</span><span id="tomorrowPlanRain">降水確率 --%</span><span id="tomorrowPlanWind">風 --m/s</span></div><p class="text-xs text-sky-800 mt-4" id="tomorrowPlanWeatherAdvice">天気を見て、明日の行動を考えよう。</p></div><button class="mt-5 w-full bg-sky-600 text-white rounded-2xl py-3 font-black" onclick="goTomorrowPlanStep(2)">次へ：何を持つ？ →</button></div>
<div class="hidden" data-tomorrow-step="2"><p class="text-xs text-sky-600 font-black">STEP 2 / 5</p><h3 class="text-xl font-black mt-1">何を持っていく？</h3><p class="text-xs text-slate-500 mt-2">必要だと思うものをいくつでも選んでね。</p><div class="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-5" id="tomorrowPlanItemChoices"></div><div class="grid grid-cols-2 gap-3 mt-5"><button class="bg-slate-100 rounded-2xl py-3 font-bold" onclick="goTomorrowPlanStep(1)">← 戻る</button><button class="bg-sky-600 text-white rounded-2xl py-3 font-black" onclick="goTomorrowPlanStep(3)">次へ →</button></div></div>
<div class="hidden" data-tomorrow-step="3"><p class="text-xs text-sky-600 font-black">STEP 3 / 5</p><h3 class="text-xl font-black mt-1">何時ごろ出る？</h3><p class="text-xs text-slate-500 mt-2">学校や家族の決まりを優先して考えよう。</p><div class="grid gap-3 mt-5" id="tomorrowPlanTimeChoices"></div><input class="mt-4 w-full border border-slate-200 rounded-2xl px-4 py-3 text-sm" id="tomorrowPlanTimeNote" maxlength="80" placeholder="例：7時35分に家を出る"/><div class="grid grid-cols-2 gap-3 mt-5"><button class="bg-slate-100 rounded-2xl py-3 font-bold" onclick="goTomorrowPlanStep(2)">← 戻る</button><button class="bg-sky-600 text-white rounded-2xl py-3 font-black" onclick="goTomorrowPlanStep(4)">次へ →</button></div></div>
<div class="hidden" data-tomorrow-step="4"><p class="text-xs text-sky-600 font-black">STEP 4 / 5</p><h3 class="text-xl font-black mt-1">何に気をつける？</h3><p class="text-xs text-slate-500 mt-2">危険がある時は、自分だけで通学路を変えず家族や学校と相談しよう。</p><div class="grid gap-3 mt-5" id="tomorrowPlanCautionChoices"></div><textarea class="mt-4 w-full border border-slate-200 rounded-2xl px-4 py-3 text-sm" id="tomorrowPlanCautionNote" maxlength="200" placeholder="ほかに気をつけたいこと" rows="2"></textarea><div class="grid grid-cols-2 gap-3 mt-5"><button class="bg-slate-100 rounded-2xl py-3 font-bold" onclick="goTomorrowPlanStep(3)">← 戻る</button><button class="bg-sky-600 text-white rounded-2xl py-3 font-black" onclick="goTomorrowPlanStep(5)">次へ →</button></div></div>
<div class="hidden" data-tomorrow-step="5"><p class="text-xs text-sky-600 font-black">STEP 5 / 5</p><h3 class="text-xl font-black mt-1">家族と相談する？</h3><p class="text-xs text-slate-500 mt-2">分からないことを無理に決めなくて大丈夫。</p><div class="grid gap-3 mt-5" id="tomorrowPlanConsultChoices"></div><div class="hidden mt-4 bg-violet-50 border border-violet-200 rounded-2xl p-4" id="tomorrowPlanConsultBox"><label class="text-xs font-black text-violet-900">家族と相談して決めたこと</label><textarea class="mt-2 w-full border border-violet-200 rounded-xl px-3 py-2 text-sm bg-white" id="tomorrowPlanFamilyDecision" maxlength="240" placeholder="例：雨が強そうなので5分早く出る" rows="3"></textarea></div><div class="mt-5 bg-slate-50 border border-slate-200 rounded-3xl p-5" id="tomorrowPlanSummary"></div><div class="hidden mt-3 rounded-2xl p-3 text-xs font-bold" id="tomorrowPlanSaveMessage"></div><div class="grid grid-cols-2 gap-3 mt-5"><button class="bg-slate-100 rounded-2xl py-3 font-bold" onclick="goTomorrowPlanStep(4)">← 戻る</button><button class="bg-amber-500 text-white rounded-2xl py-3 font-black" onclick="saveTomorrowPlan()">知恵貯金に保存</button></div></div>
</div>
</div>
<button class="mt-5 w-full bg-slate-100 border border-slate-200 text-slate-700 rounded-2xl py-3 font-black" onclick="backToHome()">← 戻る</button>
<p aria-live="polite" class="text-xs text-slate-500 mt-3" id="tomorrowDraftStatus">入力すると下書きをこの端末に保存します。</p><details class="mt-3 text-xs text-slate-500"><summary>旧版の下書きを読み込む</summary><button class="mt-2 border border-slate-200 rounded-xl px-3 py-2" onclick="loadLegacyTomorrowDraft()" type="button">以前の端末共通の下書きから読み込む</button></details></div>
</section>
<!-- 知恵貯金 -->
<section class="screen hidden px-4 sm:px-5 py-6" id="screen-wisdom-bank"><div class="max-w-3xl mx-auto"><button class="mb-4 text-xs font-bold text-amber-700" onclick="backToHome()">← 戻る</button><div class="bg-white/95 rounded-3xl border border-amber-100 shadow-xl p-5 sm:p-7"><div class="flex flex-col sm:flex-row sm:items-center gap-4 justify-between"><div class="flex items-center gap-4"><img alt="知恵貯金" class="w-20 h-20 object-contain" src="/tyokin.png"/><div><p class="text-xs font-black text-amber-600">考えたことを、次の判断に</p><h2 class="text-3xl font-black">わたしの知恵貯金</h2></div></div><div class="bg-amber-50 border border-amber-200 rounded-2xl px-5 py-3 text-center"><p class="text-[10px] text-amber-700 font-black">たまった知恵</p><p class="text-3xl font-black text-amber-800" id="wisdomBankTotal">0</p></div></div><p class="text-sm text-slate-500 mt-4">前に決めたことは次に考えるためのヒント。状況が違えば、また考え直そう。</p><div class="mt-5 flex flex-wrap gap-2" id="wisdomBankFilters"></div><div class="space-y-4 mt-5" id="wisdomBankList"></div></div><button class="mt-5 w-full bg-slate-100 border border-slate-200 text-slate-700 rounded-2xl py-3 font-black" onclick="backToHome()">← 戻る</button></div></section>
<!-- 緊急モード -->
<section class="screen hidden px-4 sm:px-5 py-5 sm:py-7" id="screen-emergency">
<div class="max-w-3xl mx-auto">
<div class="bg-gradient-to-br from-rose-600 to-orange-500 text-white rounded-3xl shadow-xl p-5 sm:p-7">
<div class="flex items-start justify-between gap-4">
<div>
<p class="text-xs font-black text-white/80">緊急モード</p>
<h2 class="text-3xl sm:text-4xl font-black mt-1">あわてず、この順番で</h2>
<p class="text-sm text-white/90 mt-2 leading-relaxed">揺れている最中はスマホの操作より、自分の身を守ることを優先してね。</p>
</div>
<div class="text-5xl sm:text-6xl shrink-0">🛡️</div>
</div>
<div class="mt-4 flex flex-wrap items-center gap-2">
<span class="bg-white/20 border border-white/25 rounded-full px-3 py-1 text-[11px] font-black" id="emergencyNetworkBadge">通信を確認中</span>
<span class="bg-white/20 border border-white/25 rounded-full px-3 py-1 text-[11px] font-black">必要な情報を大きく表示</span>
</div>
</div>
<div class="mt-4 bg-white rounded-3xl border-2 border-rose-200 shadow-lg p-5 sm:p-6">
<div class="flex gap-4 items-start">
<div class="w-12 h-12 shrink-0 rounded-2xl bg-rose-100 text-rose-700 flex items-center justify-center text-2xl font-black">1</div>
<div class="flex-1">
<h3 class="text-xl font-black text-slate-900">まず、自分の安全</h3>
<p class="text-xs text-slate-500 mt-1">連絡や移動より先に、自分の身を守る。</p>
<div class="grid sm:grid-cols-3 gap-2 mt-4 text-xs font-bold text-slate-700">
<div class="bg-rose-50 border border-rose-100 rounded-2xl p-3">🙆 頭を守る</div>
<div class="bg-rose-50 border border-rose-100 rounded-2xl p-3">🪑 丈夫な机の下などへ</div>
<div class="bg-rose-50 border border-rose-100 rounded-2xl p-3">⚠️ 倒れる物・割れる物から離れる</div>
</div>
</div>
</div>
</div>
<div class="mt-4 bg-white rounded-3xl border border-slate-200 shadow-sm p-5 sm:p-6">
<div class="flex gap-4 items-start">
<div class="w-12 h-12 shrink-0 rounded-2xl bg-amber-100 text-amber-800 flex items-center justify-center text-2xl font-black">2</div>
<div class="flex-1 min-w-0">
<h3 class="text-xl font-black text-slate-900">安否を知らせる</h3>
<p class="text-xs text-slate-500 mt-1">通信できる時だけ送信。つながらない時は何度も無理に操作しなくて大丈夫。</p>
<div class="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-4">
<button class="bg-amber-50 hover:bg-amber-100 border border-amber-200 text-amber-900 rounded-2xl py-4 px-3 font-black" onclick="sendEmergencySafety('safe')">😊 元気です</button>
<button class="bg-orange-50 hover:bg-orange-100 border border-orange-200 text-orange-900 rounded-2xl py-4 px-3 font-black" onclick="sendEmergencySafety('messy')">🏠 被害あり</button>
<button class="bg-rose-100 hover:bg-rose-200 border border-rose-300 text-rose-900 rounded-2xl py-4 px-3 font-black" onclick="sendEmergencySafety('sos')">🆘 緊急SOS</button>
</div>
<div class="hidden mt-3 rounded-2xl border p-3 text-xs font-bold" id="emergencySafetyResult"></div><p class="text-xs text-slate-600 mt-2">SOSも登録した家族・友達への共有です。救助機関への通報ではありません。</p>
<button class="mt-3 text-xs font-black text-sky-700" onclick="switchScreen('safety')">家族・友達の安否も見る →</button>
</div>
</div>
</div>
<div class="mt-4 bg-white rounded-3xl border border-slate-200 shadow-sm p-5 sm:p-6">
<div class="flex gap-4 items-start">
<div class="w-12 h-12 shrink-0 rounded-2xl bg-violet-100 text-violet-800 flex items-center justify-center text-2xl font-black">3</div>
<div class="flex-1 min-w-0">
<h3 class="text-xl font-black text-slate-900">家族との約束を確認</h3>
<p class="text-xs text-slate-500 mt-1">連絡できない時こそ、前もって家族で決めたルールを手がかりにする。</p>
<div class="mt-4" id="emergencyFamilyRuleSummary"></div>
<button class="mt-3 w-full bg-violet-600 hover:bg-violet-700 text-white rounded-2xl py-3 font-black" onclick="switchScreen('family-rules')">保存した行動ルールを見る</button>
</div>
</div>
</div>
<div class="mt-4 bg-white rounded-3xl border border-slate-200 shadow-sm p-5 sm:p-6">
<div class="flex gap-4 items-start">
<div class="w-12 h-12 shrink-0 rounded-2xl bg-cyan-100 text-cyan-800 flex items-center justify-center text-2xl font-black">4</div>
<div class="flex-1 min-w-0">
<h3 class="text-xl font-black text-slate-900">集合場所・安心メモ</h3>
<p class="text-xs text-slate-500 mt-1">端末に保存した情報は、通信がない時でも確認できます。</p>
<div class="mt-4 grid gap-2" id="emergencyMeetingSummary"></div>
<button class="mt-3 w-full bg-cyan-600 hover:bg-cyan-700 text-white rounded-2xl py-3 font-black" onclick="switchScreen('offline-kit')">オフライン安心メモを開く</button>
</div>
</div>
</div>
<div class="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
<button class="bg-white hover:bg-emerald-50 border border-emerald-200 rounded-2xl p-4 text-left shadow-sm" onclick="switchScreen('hazard')">
<div class="text-2xl">🗺️</div>
<p class="font-black text-slate-800 mt-1">まちの安全情報</p>
<p class="text-[11px] text-slate-500 mt-1">危ない場所・助けを求められる場所を確認</p>
</button>
<button class="bg-white hover:bg-cyan-50 border border-cyan-200 rounded-2xl p-4 text-left shadow-sm" onclick="switchScreen('offline-kit')">
<div class="text-2xl">☎️</div>
<p class="font-black text-slate-800 mt-1">連絡先・家族メモ</p>
<p class="text-[11px] text-slate-500 mt-1">保存した連絡先や「つながらない時のルール」を確認</p>
</button>
</div>
<button class="mt-5 w-full bg-slate-800 hover:bg-slate-900 text-white rounded-2xl py-3 font-black" onclick="exitEmergencyMode()">普段の画面に戻る</button>
</div>
</section>
<!-- 天気 -->
<section class="screen hidden px-5 py-7" id="screen-weather">
<div class="max-w-4xl mx-auto">
<button class="mb-4 text-xs font-bold text-sky-600" onclick="backToHome()">← 戻る</button>
<div class="weather-card rounded-3xl border border-white shadow-lg p-6">
<div class="flex justify-between items-start gap-4">
<div>
<p class="text-xs text-slate-500 font-bold">天草市</p>
<h2 class="text-2xl font-black text-slate-800">最新の気象情報</h2>
</div>
<span class="text-4xl">🌤️</span>
</div>
<div class="mt-5 text-sm font-bold text-slate-700" id="liveWeatherDesc">JST基準で気象データを取得中...</div>
<div class="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-3">
<div class="bg-white/80 rounded-2xl p-4">
<p class="text-[10px] text-slate-400">気温</p>
<p class="text-xl font-black" id="weatherTemperature">--</p>
</div>
<div class="bg-white/80 rounded-2xl p-4">
<p class="text-[10px] text-slate-400">体感温度</p>
<p class="text-xl font-black" id="weatherFeelsLike">--</p>
</div>
<div class="bg-white/80 rounded-2xl p-4">
<p class="text-[10px] text-slate-400">湿度</p>
<p class="text-xl font-black" id="weatherHumidity">--</p>
</div>
<div class="bg-white/80 rounded-2xl p-4">
<p class="text-[10px] text-slate-400">風速</p>
<p class="text-xl font-black" id="weatherWind">--</p>
</div>
</div>
<div class="mt-5">
<h3 class="font-black text-slate-800" id="jstReportTitle">🌤️ 天草市 JST気象情報</h3>
<div class="mt-3 bg-emerald-50 border border-emerald-200 rounded-2xl p-4 text-xs text-emerald-900" id="lifestyleRecommendation">天気情報を取得しています...</div>
</div>
<button class="mt-5 w-full bg-sky-500 hover:bg-sky-600 text-white rounded-2xl py-3 font-black" onclick="fetchRealWeatherWithJST()">🔄 天気を更新</button>
</div>
<div class="mt-5 bg-white/95 rounded-3xl border border-white shadow-lg p-6">
<div class="flex justify-between items-start gap-3">
<div>
<p class="text-xs text-sky-500 font-black">自分で考えてみよう</p>
<h2 class="text-xl font-black text-slate-800 mt-1">🎒 天気から、何を準備する？</h2>
</div>
<span class="text-[10px] bg-cyan-50 border border-cyan-200 text-cyan-700 rounded-full px-3 py-1 font-bold">端末に保存</span>
</div>
<p class="mt-4 text-sm font-black text-slate-800" id="preparationSituation">天気から場面を考えています...</p>
<p class="mt-1 text-[10px] text-slate-400" id="preparationSourceNote">最新の天気が取れない時は、下の場面を自分で選べます。</p>
<div class="mt-4 flex gap-2 overflow-x-auto pb-2">
<button class="shrink-0 bg-sky-600 text-white border border-sky-600 rounded-xl px-3 py-2 text-xs font-black" data-prep-scenario="auto" onclick="setPreparationScenario('auto')">🌤️ 今の天気</button>
<button class="shrink-0 bg-white border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold" data-prep-scenario="rain" onclick="setPreparationScenario('rain')">☔ 雨</button>
<button class="shrink-0 bg-white border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold" data-prep-scenario="rainWind" onclick="setPreparationScenario('rainWind')">🌧️ 雨＋強風</button>
<button class="shrink-0 bg-white border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold" data-prep-scenario="veryHot" onclick="setPreparationScenario('veryHot')">🥵 とても暑い</button>
<button class="shrink-0 bg-white border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold" data-prep-scenario="thunder" onclick="setPreparationScenario('thunder')">⛈️ 雷</button>
<button class="shrink-0 bg-white border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold" data-prep-scenario="heavyRain" onclick="setPreparationScenario('heavyRain')">🌊 大雨</button>
<button class="shrink-0 bg-white border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold" data-prep-scenario="snow" onclick="setPreparationScenario('snow')">❄️ 雪</button>
</div>
<p class="mt-3 text-xs font-black text-slate-700">持っていく物・することを、いくつでも選んでね。</p>
<div class="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3" id="preparationChoices"></div>
<button class="mt-5 w-full bg-sky-500 hover:bg-sky-600 text-white rounded-2xl py-3 font-black" id="checkPreparationBtn" onclick="checkPreparationChoices()">選んだ理由を確かめる</button>
<div class="hidden mt-4 rounded-2xl border p-4 text-sm leading-relaxed" id="preparationFeedback"></div>
<p class="mt-3 text-[10px] text-slate-400" id="preparationSavedAt"></p>
</div>
</div>
<div class="mt-6">
<button class="w-full bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 rounded-2xl py-3 font-black" data-bottom-back="true" onclick="backToHome()">← 戻る</button>
</div>
</section>
<!-- 安否 -->
<section class="screen hidden px-5 py-7" id="screen-safety">
<div class="max-w-4xl mx-auto">
<button class="mb-4 text-xs font-bold text-sky-600" onclick="backToHome()">← 戻る</button>
<div class="safe-card rounded-3xl border border-white shadow-lg p-6">
<h2 class="text-2xl font-black">🛡️ 安否確認</h2>
<p class="text-xs text-slate-500 mt-1">現在の自分の状態を、許可した家族・友達へ送信します。</p>
<div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-5">
<button class="bg-amber-50 border border-amber-200 text-amber-900 rounded-2xl py-4 font-black" onclick="sendSafety('safe')">😊 元気です</button>
<button class="bg-orange-50 border border-orange-200 text-orange-900 rounded-2xl py-4 font-black" onclick="sendSafety('messy')">🏠 被害あり</button>
<button class="bg-rose-100 border border-rose-300 text-rose-900 rounded-2xl py-4 font-black" onclick="sendSafety('sos')">🆘 緊急SOS</button>
</div>
<div class="hidden mt-4 text-xs text-center font-medium p-3.5 rounded-xl" id="safetyResultMsg"></div>
<div class="mt-6">
<div class="flex justify-between items-center">
<h3 class="font-black text-slate-800">家族・友達の安否</h3>
<span class="text-[10px] text-slate-400" id="safetyConnStatus">同期中...</span>
</div>
<div class="space-y-2 mt-3" id="groupSafetyStatusList"></div>
</div>
</div>
</div>
<div class="mt-6">
<button class="w-full bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 rounded-2xl py-3 font-black" data-bottom-back="true" onclick="backToHome()">← 戻る</button>
</div>
</section>
<!-- 家族の行動ルール -->
<section class="screen hidden px-5 py-7" id="screen-family-rules">
<div class="max-w-4xl mx-auto">
<button class="mb-4 text-xs font-bold text-violet-600" onclick="backToHome()">← 戻る</button>
<div class="bg-white/95 rounded-3xl border border-white shadow-lg p-6">
<div class="flex justify-between items-start gap-3">
<div>
<p class="text-xs text-violet-500 font-black">家族で話して決めよう</p>
<h2 class="text-2xl font-black text-slate-800 mt-1">🏠 わたしの行動ルール</h2>
</div>
<span class="text-[10px] bg-cyan-50 border border-cyan-200 text-cyan-700 rounded-full px-3 py-1 font-bold">📴 オフライン対応</span>
</div>
<div class="mt-4 bg-violet-50 border border-violet-200 rounded-2xl p-4 text-xs text-violet-900 leading-relaxed">
                ひとりで正解を決める画面ではありません。まず自分で考えて、そのあと家族と確認しよう。実際の災害では、学校・施設・自治体など、その場の案内を優先してください。
            </div>
<div class="mt-6" id="familyRuleScenarioArea">
<h3 class="font-black text-slate-800">どこにいる時のルールを作る？</h3>
<div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3" id="familyRuleScenarioGrid"></div>
</div>
<div class="hidden mt-6 border border-violet-200 rounded-3xl p-5 bg-violet-50/60" id="familyRuleWizard">
<div class="flex justify-between items-center gap-3">
<h3 class="font-black text-violet-900" id="familyRuleScenarioTitle"></h3>
<span class="text-xs font-bold text-violet-500" id="familyRuleProgress"></span>
</div>
<p class="mt-5 text-lg font-black text-slate-800" id="familyRuleQuestion"></p>
<div class="grid gap-3 mt-4" id="familyRuleChoices"></div>
<div class="mt-4 bg-white rounded-2xl border border-slate-200 p-3">
<label class="text-[11px] font-black text-slate-600" for="familyRuleCustomInput">家族で決めた別の答えがある時</label>
<div class="flex flex-col sm:flex-row gap-2 mt-2">
<input class="flex-1 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-violet-300" id="familyRuleCustomInput" maxlength="160" placeholder="短い言葉で入力"/>
<button class="bg-violet-100 hover:bg-violet-200 text-violet-800 rounded-xl px-4 py-2 text-xs font-black" onclick="saveFamilyRuleCustomAnswer()">この答えを選ぶ</button>
</div>
</div>
<div class="hidden mt-4 rounded-2xl border p-4 text-sm leading-relaxed" id="familyRuleFeedback"></div>
<div class="grid grid-cols-2 gap-3 mt-4">
<button class="bg-white border border-slate-200 text-slate-600 rounded-2xl py-3 font-bold" onclick="cancelFamilyRuleWizard()">いったん戻る</button>
<button class="bg-violet-600 hover:bg-violet-700 text-white rounded-2xl py-3 font-black" disabled="" id="familyRuleNextBtn" onclick="nextFamilyRuleStep()">次へ →</button>
</div>
</div>
<div class="hidden mt-6 border border-emerald-200 rounded-3xl p-5 bg-emerald-50/70" id="familyRuleSummary">
<p class="text-xs text-emerald-600 font-black">できあがり</p>
<h3 class="text-xl font-black text-emerald-900 mt-1">✨ わたしの行動ルール</h3>
<div class="mt-4 space-y-3" id="familyRuleSummaryContent"></div>
<div class="mt-4 bg-white/80 rounded-2xl p-4 text-xs text-slate-600 leading-relaxed">
                    この内容は「下書き」です。家族と話して、集合場所や連絡方法を確かめたら保存しよう。
                </div>
<div class="grid grid-cols-2 gap-3 mt-4">
<button class="bg-white border border-emerald-200 text-emerald-800 rounded-2xl py-3 font-bold" onclick="restartCurrentFamilyRule()">考え直す</button>
<button class="bg-emerald-600 hover:bg-emerald-700 text-white rounded-2xl py-3 font-black" onclick="saveCurrentFamilyRule()">端末に保存</button>
</div>
</div>
</div>
<div class="mt-5 bg-white/95 rounded-3xl border border-white shadow-lg p-6">
<div class="flex justify-between items-center gap-3">
<div>
<h3 class="font-black text-slate-800">保存した家族ルール</h3>
<p class="text-[10px] text-slate-400 mt-1">この端末に保存され、通信がない時も見られます。</p>
</div>
<span class="bg-violet-100 text-violet-700 rounded-full px-3 py-1 text-xs font-black" id="familyRuleSavedCount">0</span>
</div>
<div class="space-y-3 mt-4" id="savedFamilyRulesList"></div>
</div>
</div>
<div class="mt-6">
<button class="w-full bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 rounded-2xl py-3 font-black" data-bottom-back="true" onclick="backToHome()">← 戻る</button>
</div>
</section>
<!-- オフライン安心メモ -->
<section class="screen hidden px-5 py-7 offline-soft-pattern" id="screen-offline-kit">
<div class="max-w-4xl mx-auto">
<button class="mb-4 text-xs font-bold text-cyan-700" onclick="backFromOfflineKit()">← 戻る</button>
<div class="bg-white/95 rounded-3xl border border-white shadow-lg p-6">
<div class="flex justify-between items-start gap-3">
<div>
<p class="text-xs text-cyan-600 font-black">通信がなくても確認できる</p>
<h2 class="text-2xl font-black text-slate-800 mt-1">📴 オフライン安心メモ</h2>
<p class="text-xs text-slate-500 mt-2" id="offlineOwnerLabel"></p>
</div>
<span class="text-[10px] rounded-full px-3 py-1 font-black bg-slate-100 text-slate-600" id="offlineKitNetworkBadge">確認中</span>
</div>
<div class="mt-4 bg-cyan-50 border border-cyan-200 rounded-2xl p-4 text-xs text-cyan-900 leading-relaxed">
                この情報はこの端末の中に保存します。共有の端末を使う場合は、名前や電話番号の扱いに注意してください。天気・警報などの最新情報には通信が必要です。
            </div>
<div class="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
<div>
<label class="text-xs font-black text-slate-700" for="offlinePrimaryMeeting">📍 第一集合場所</label>
<input class="mt-2 w-full border border-slate-200 rounded-2xl px-4 py-3 outline-none focus:ring-2 focus:ring-cyan-300" id="offlinePrimaryMeeting" maxlength="160" placeholder="例：○○小学校 体育館前"/>
</div>
<div>
<label class="text-xs font-black text-slate-700" for="offlineSecondaryMeeting">📍 第二集合場所</label>
<input class="mt-2 w-full border border-slate-200 rounded-2xl px-4 py-3 outline-none focus:ring-2 focus:ring-cyan-300" id="offlineSecondaryMeeting" maxlength="160" placeholder="例：△△公民館"/>
</div>
<div>
<label class="text-xs font-black text-slate-700" for="offlineContactName1">☎️ 連絡する人 1</label>
<input class="mt-2 w-full border border-slate-200 rounded-2xl px-4 py-3 outline-none focus:ring-2 focus:ring-cyan-300" id="offlineContactName1" maxlength="80" placeholder="名前"/>
<input class="mt-2 w-full border border-slate-200 rounded-2xl px-4 py-3 outline-none focus:ring-2 focus:ring-cyan-300" id="offlineContactPhone1" maxlength="40" placeholder="電話番号" type="tel"/>
</div>
<div>
<label class="text-xs font-black text-slate-700" for="offlineContactName2">☎️ 連絡する人 2</label>
<input class="mt-2 w-full border border-slate-200 rounded-2xl px-4 py-3 outline-none focus:ring-2 focus:ring-cyan-300" id="offlineContactName2" maxlength="80" placeholder="名前"/>
<input class="mt-2 w-full border border-slate-200 rounded-2xl px-4 py-3 outline-none focus:ring-2 focus:ring-cyan-300" id="offlineContactPhone2" maxlength="40" placeholder="電話番号" type="tel"/>
</div>
</div>
<label class="block text-xs font-black text-slate-700 mt-5" for="offlineNoContactRule">📵 電話やネットがつながらない時のルール</label>
<textarea class="mt-2 w-full border border-slate-200 rounded-2xl px-4 py-3 outline-none focus:ring-2 focus:ring-cyan-300" id="offlineNoContactRule" maxlength="500" placeholder="例：学校にいる時は先生の指示を聞いて、迎えが来るまで学校で待つ" rows="3"></textarea>
<label class="block text-xs font-black text-slate-700 mt-4" for="offlineNotes">📝 家族で決めたこと・大切なメモ</label>
<textarea class="mt-2 w-full border border-slate-200 rounded-2xl px-4 py-3 outline-none focus:ring-2 focus:ring-cyan-300" id="offlineNotes" maxlength="1000" placeholder="例：無理に家へ戻らず、その場の安全と案内を優先する" rows="4"></textarea>
<button class="mt-5 w-full bg-cyan-600 hover:bg-cyan-700 text-white rounded-2xl py-3 font-black" onclick="saveOfflinePlan()">この端末に保存する</button>
<div class="hidden mt-3 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-800 p-3 text-xs font-bold" id="offlineSaveMessage"></div>
<p class="mt-3 text-[10px] text-slate-400" id="offlineLastSavedAt"></p>
</div>
<div class="mt-5 grid grid-cols-1 lg:grid-cols-2 gap-5">
<div class="bg-white/95 rounded-3xl border border-white shadow-lg p-5">
<h3 class="font-black text-slate-800">🏠 保存した家族ルール</h3>
<div class="space-y-3 mt-4" id="offlineRulesList"></div>
</div>
<div class="bg-white/95 rounded-3xl border border-white shadow-lg p-5">
<h3 class="font-black text-slate-800">🆘 助けを求められる場所</h3>
<p class="text-[10px] text-slate-400 mt-1">最後に通信できた時の保存情報です。</p>
<div class="space-y-3 mt-4" id="offlineHelpPlacesList"></div>
</div>
<div class="bg-white/95 rounded-3xl border border-white shadow-lg p-5">
<h3 class="font-black text-slate-800">⚠️ 危ない場所</h3>
<p class="text-[10px] text-slate-400 mt-1">状況が変わることがあります。周りを見て判断してください。</p>
<div class="space-y-3 mt-4" id="offlineDangerPlacesList"></div>
</div>
<div class="bg-white/95 rounded-3xl border border-white shadow-lg p-5">
<h3 class="font-black text-slate-800">🧭 困った時に思い出すこと</h3>
<div class="space-y-3 mt-4 text-xs text-slate-700 leading-relaxed">
<div class="bg-sky-50 border border-sky-200 rounded-2xl p-3"><b>1. まず自分の身を守る</b><br/>頭を守り、倒れそうな物・割れた物などから離れる。</div>
<div class="bg-violet-50 border border-violet-200 rounded-2xl p-3"><b>2. ひとりで無理に決めない</b><br/>先生・施設の人・信頼できる大人や、助けを求められる場所を頼る。</div>
<div class="bg-emerald-50 border border-emerald-200 rounded-2xl p-3"><b>3. 家族と決めたルールを確認</b><br/>電話がつながらない時も、集合場所と行動ルールを手がかりにする。</div>
</div>
</div>
</div>
</div>
<div class="mt-6">
<button class="w-full bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 rounded-2xl py-3 font-black" data-bottom-back="true" onclick="backFromOfflineKit()">← 戻る</button>
</div>
<button class="screen-bottom-back" onclick="backToHome()" type="button">← 戻る</button></section>
<!-- クイズ -->
<section class="screen hidden px-5 py-7" id="screen-quiz">
<div class="max-w-2xl mx-auto">
<button class="mb-4 text-xs font-bold text-sky-600" onclick="backToHome()">← 戻る</button>
<div class="bg-white/95 rounded-3xl border border-white shadow-lg p-6">
<div class="flex justify-between items-start gap-3">
<div>
<p class="text-xs text-amber-500 font-black">防災・天気</p>
<h2 class="text-2xl font-black text-slate-800">🧠 考えるクイズ</h2>
</div>
<div class="text-right">
<span class="block text-xs font-bold text-slate-400" id="quizProgress">-- / --</span>
<span class="block text-[10px] font-bold text-emerald-600 mt-1" id="quizScore">0問チャレンジ</span>
</div>
</div>
<div class="grid grid-cols-3 gap-2 mt-5">
<button class="bg-amber-500 text-white border border-amber-500 rounded-xl py-2 text-[11px] font-black" id="quizModeScenario" onclick="setQuizMode('scenario')">考える</button>
<button class="bg-white text-slate-600 border border-slate-200 rounded-xl py-2 text-[11px] font-black" id="quizModeKnowledge" onclick="setQuizMode('knowledge')">知識</button>
<button class="bg-white text-slate-600 border border-slate-200 rounded-xl py-2 text-[11px] font-black" id="quizModeMixed" onclick="setQuizMode('mixed')">まぜる</button>
</div>
<p class="mt-3 text-xs text-slate-500" id="quizModeDescription">場所や天気を見て、「今ならどうする？」を考えます。</p>
<div class="mt-6 text-sm text-slate-500" id="quizLoading">問題を読み込んでいます...</div>
<div class="hidden mt-6" id="quizArea">
<span class="inline-block text-[10px] bg-amber-50 border border-amber-200 text-amber-700 rounded-full px-3 py-1 font-black" id="quizTopic"></span>
<p class="text-base font-black text-slate-800 whitespace-pre-line leading-relaxed mt-3" id="quizQuestion"></p>
<div class="grid gap-3 mt-5" id="quizChoices"></div>
<div class="hidden mt-5 rounded-2xl p-4 text-sm whitespace-pre-line leading-relaxed" id="quizAnswerBox"></div>
<button class="hidden mt-4 w-full bg-amber-500 hover:bg-amber-600 text-white rounded-2xl py-3 font-black" id="quizNextBtn" onclick="nextQuizQuestion()">次の問題へ →</button>
</div>
</div>
</div>
<div class="mt-6">
<button class="w-full bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 rounded-2xl py-3 font-black" data-bottom-back="true" onclick="backToHome()">← 戻る</button>
</div>
</section>
<!-- まちの安全情報 -->
<section class="screen hidden px-5 py-7" id="screen-hazard">
<div class="max-w-4xl mx-auto">
<button class="mb-4 text-xs font-bold text-sky-600" onclick="backToHome()">← 戻る</button>
<div class="danger-card rounded-3xl border border-white shadow-lg p-6">
<div class="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
<div>
<h2 class="text-2xl font-black">🗺️ まちの安全情報</h2>
<p class="text-xs text-slate-500 mt-1">危ない場所と、困った時に助けを求められる場所を家族・友達と共有します。</p>
</div>
<div class="grid grid-cols-2 gap-2">
<button class="bg-orange-500 hover:bg-orange-600 text-white px-3 py-3 rounded-2xl font-black text-xs" onclick="openHazardPostModal('danger')">＋ ⚠️ 危ない場所</button>
<button class="bg-emerald-500 hover:bg-emerald-600 text-white px-3 py-3 rounded-2xl font-black text-xs" onclick="openHazardPostModal('help')">＋ 🆘 助けの場所</button>
</div>
</div>
<div class="mt-4 bg-amber-50 border border-amber-200 rounded-2xl p-3">
<p class="text-[10px] text-amber-900 leading-relaxed">
                    写真なしでも登録できます。GPSは登録する場所を示す時だけ使い、現在位置や移動履歴を追跡しません。個人宅などの情報は、家族・友達の間でも必要な範囲だけ共有してください。
                </p>
</div>
<div class="grid grid-cols-3 gap-2 mt-4">
<button class="bg-slate-800 text-white border border-slate-800 rounded-xl py-2 text-xs font-black" id="hazardFilterAll" onclick="setHazardFilter('all')">すべて <span id="hazardCountAll">0</span></button>
<button class="bg-white text-orange-700 border border-orange-200 rounded-xl py-2 text-xs font-black" id="hazardFilterDanger" onclick="setHazardFilter('danger')">⚠️ 危険 <span id="hazardCountDanger">0</span></button>
<button class="bg-white text-emerald-700 border border-emerald-200 rounded-xl py-2 text-xs font-black" id="hazardFilterHelp" onclick="setHazardFilter('help')">🆘 助け <span id="hazardCountHelp">0</span></button>
</div>
<input accept="image/*" capture="environment" class="hidden" id="hazardImageInput" onchange="previewHazardImage(event)" type="file"/>
<div class="mt-4 text-[10px] text-slate-400" id="hazardSyncStatus">同期中...</div>
<div class="space-y-4 mt-4" id="hazardPostList"></div>
</div>
</div>
<div class="mt-6">
<button class="w-full bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 rounded-2xl py-3 font-black" data-bottom-back="true" onclick="backToHome()">← 戻る</button>
</div>
</section>
<!-- まちの安全情報 投稿モーダル -->
<div class="hidden fixed inset-0 z-[105] modal-backdrop flex items-center justify-center px-5" id="hazardPostModal">
<div class="w-full max-w-md bg-white rounded-3xl shadow-2xl p-6 max-h-[90vh] overflow-y-auto safe-area-bottom">
<h2 class="text-xl font-black text-slate-800" id="hazardModalTitle">⚠️ 危ない場所を登録</h2>
<p class="text-xs text-slate-500 mt-1" id="hazardModalSubtitle">写真なしでも登録できます。</p>
<input id="hazardPlaceKindValue" type="hidden" value="danger"/>
<label class="block text-xs font-black text-slate-700 mt-5">どちらを登録する？</label>
<div class="grid grid-cols-2 gap-2 mt-2">
<button class="bg-orange-500 text-white border border-orange-500 rounded-2xl py-3 text-xs font-black" id="hazardKindDanger" onclick="setPlaceKind('danger')">⚠️ 危ない場所</button>
<button class="bg-white text-emerald-700 border border-emerald-200 rounded-2xl py-3 text-xs font-black" id="hazardKindHelp" onclick="setPlaceKind('help')">🆘 助けの場所</button>
</div>
<label class="block text-xs font-black text-slate-700 mt-4">場所の種類</label>
<select class="w-full mt-2 border border-slate-200 rounded-2xl px-4 py-3 bg-white" id="hazardCategory"></select>
<label class="block text-xs font-black text-slate-700 mt-4" for="hazardPlaceName" id="hazardPlaceNameLabel">場所の名前（任意）</label>
<input class="w-full mt-2 border border-slate-200 rounded-2xl px-4 py-3 outline-none focus:ring-2 focus:ring-orange-300" id="hazardPlaceName" maxlength="120" placeholder="例：○○交差点"/>
<label class="block text-xs font-black text-slate-700 mt-4" for="hazardTextInput" id="hazardTextLabel">どんなところ？</label>
<textarea class="w-full mt-2 border border-slate-200 rounded-2xl px-4 py-3 outline-none focus:ring-2 focus:ring-orange-300" id="hazardTextInput" maxlength="2000" placeholder="例：雨のあとに道路へ水がたまりやすいです" rows="3"></textarea>
<label class="block text-xs font-black text-slate-700 mt-4">写真（任意）</label>
<div class="grid grid-cols-2 gap-2 mt-2">
<button class="bg-orange-50 border border-orange-200 text-orange-800 rounded-xl py-2 text-xs font-bold" id="hazardPhotoChooseBtn" onclick="triggerImageUpload()" type="button">📷 写真を選ぶ</button>
<button class="bg-slate-100 border border-slate-200 text-slate-600 rounded-xl py-2 text-xs font-bold" id="hazardPhotoNoneBtn" onclick="chooseNoHazardImage()" type="button">🚫 写真なし</button>
</div>
<p class="mt-2 text-[10px] text-slate-400" id="hazardPhotoChoiceStatus">写真は任意です。</p>
<div class="hidden mt-3" id="hazardImagePreviewWrap">
<img alt="登録写真のプレビュー" class="w-full max-h-44 object-cover rounded-xl" id="hazardImagePreview"/>
</div>
<label class="block text-xs font-black text-slate-700 mt-4">場所</label>
<select class="w-full mt-2 border border-slate-200 rounded-2xl px-4 py-3 bg-white" id="hazardLocationMode" onchange="updateHazardLocationMode()">
<option value="area">大まかな地域から選ぶ</option>
<option value="gps">今いる登録場所のGPSを使う</option>
<option value="none">場所を付けない</option>
</select>
<div class="mt-3" id="hazardAreaSelectWrap">
<select class="w-full border border-slate-200 rounded-2xl px-4 py-3 bg-white" id="hazardAreaSelect">
<option value="中山口">中山口</option>
<option value="本渡町（本渡）">本渡町（本渡）</option>
<option value="中央新町">中央新町</option>
<option value="栄町">栄町</option>
<option value="古川町">古川町</option>
<option value="川原町">川原町</option>
<option value="船之尾町">船之尾町</option>
<option value="東浜町">東浜町</option>
<option value="諏訪町">諏訪町</option>
<option value="南町">南町</option>
<option value="浄南町">浄南町</option>
<option value="港町">港町</option>
<option value="東町">東町</option>
<option value="南新町">南新町</option>
<option value="太田町">太田町</option>
<option value="大浜町">大浜町</option>
<option value="城下町">城下町</option>
<option value="川原新町">川原新町</option>
<option value="山の手町">山の手町</option>
</select>
</div>
<div class="hidden mt-3 text-[10px] text-slate-500" id="hazardGpsInfo">登録時に位置情報の許可を確認します。</div>
<div class="hidden mt-4 text-xs font-bold p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700" id="hazardPostError"></div>
<div class="grid grid-cols-2 gap-3 mt-5">
<button class="bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-2xl py-3 font-bold" onclick="closeHazardPostModal()">キャンセル</button>
<button class="bg-orange-500 hover:bg-orange-600 text-white rounded-2xl py-3 font-black" id="hazardSubmitBtn" onclick="submitHazardPost()">登録する</button>
</div>
</div>
</div>
<!-- 家族・友達追加モーダル -->
<div class="hidden fixed inset-0 z-[100] modal-backdrop flex items-center justify-center px-5" id="friendModal">
<div class="w-full max-w-sm bg-white rounded-3xl shadow-2xl p-6">
<h2 class="text-xl font-black text-slate-800">家族・友達を検索</h2>
<p class="text-xs text-slate-500 mt-1 leading-relaxed">名前の最初の文字から検索できます。例：R → Rie / Raad / Ran</p>
<div class="relative mt-5">
<input autocomplete="off" class="w-full border border-slate-200 rounded-2xl px-4 py-3 outline-none focus:ring-2 focus:ring-purple-300" id="friendSearchInput" maxlength="100" oninput="handleFriendSearchInput()" placeholder="名前を入力（例：R）" type="text"/>
<div class="hidden absolute right-4 top-3 text-xs text-slate-400" id="friendSearchSpinner">検索中...</div>
</div>
<div class="mt-3 text-[11px] text-slate-400" id="friendSearchHint">1文字以上入力すると候補が表示されます。</div>
<div class="mt-3 max-h-64 overflow-y-auto space-y-2" id="friendSearchResults"></div>
<div class="hidden mt-3 text-xs font-bold p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700" id="friendModalError"></div>
<button class="mt-5 w-full bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-2xl py-3 font-bold" onclick="closeFriendModal()">閉じる</button>
</div>
</div>
<!-- リクエスト詳細モーダル -->
<div class="hidden fixed inset-0 z-[110] modal-backdrop flex items-center justify-center px-5" id="friendRequestModal">
<div class="w-full max-w-sm bg-white rounded-3xl shadow-2xl p-6">
<div class="text-center">
<div class="text-5xl mb-3">👋</div>
<h2 class="text-xl font-black text-slate-800">家族・友達リクエスト</h2>
<p class="text-sm text-slate-600 mt-3 leading-relaxed" id="requestModalText"></p>
</div>
<div class="mt-5 bg-slate-50 rounded-2xl p-4">
<p class="text-[10px] text-slate-400">許可すると共有される情報</p>
<ul class="text-xs text-slate-700 mt-2 space-y-1">
<li>✓ 安否確認の結果</li>
<li>✓ まちの安全情報の画像</li>
<li>✓ 登録した場所の位置</li>
<li>✓ 危険・助けの場所のメッセージ</li>
</ul>
<p class="text-[10px] text-rose-500 mt-3 font-bold">✕ 現在位置の追跡・共有は行いません。</p>
</div>
<div class="grid grid-cols-2 gap-3 mt-5">
<button class="bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-2xl py-3 font-bold" onclick="rejectCurrentFriendRequest()">拒否</button>
<button class="bg-emerald-500 hover:bg-emerald-600 text-white rounded-2xl py-3 font-black" onclick="acceptCurrentFriendRequest()">許可</button>
</div>
</div>
</div>
<!-- オフライン表示 -->
<div class="hidden fixed left-4 right-4 bottom-4 z-[190] max-w-xl mx-auto safe-area-bottom" id="networkBanner">
<div class="bg-slate-900/95 text-white rounded-2xl shadow-2xl px-4 py-3 flex items-center gap-3">
<span class="text-xl">📴</span>
<div class="flex-1">
<p class="text-xs font-black">オフラインです</p>
<p class="text-[10px] text-white/80 mt-0.5" id="networkBannerText">保存した家族ルールや安心メモは見られます。</p>
</div>
<button class="bg-white/15 hover:bg-white/25 rounded-xl px-3 py-2 text-[10px] font-black" onclick="switchScreen('offline-kit')">安心メモ</button>
</div>
</div>
<!-- 通知バナー -->
<div class="fixed top-20 right-4 z-[200] w-[min(380px,calc(100vw-32px))] translate-x-full transition-transform duration-300" hidden="" id="pushNotificationBanner">
<div class="bg-white rounded-2xl shadow-2xl border border-slate-200 p-4">
<div class="flex gap-3">
<div class="text-2xl">🔔</div>
<div class="flex-1">
<p class="font-black text-sm text-slate-800" id="pushNotificationTitle"></p>
<p class="text-xs text-slate-500 mt-1" id="pushNotificationText"></p>
</div>
<button class="text-slate-400 font-black" onclick="closePushBanner()">×</button>
</div>
</div>
</div>

<!-- Copyright -->
<footer class="px-4 py-6 text-center text-[10px] sm:text-xs text-slate-400 bg-white/50 border-t border-slate-200/70">
  <p class="font-bold text-slate-500">© 2026 防災アプリ. All Rights Reserved.</p>
  <p class="mt-1">画像・文章・デザイン・プログラムの無断転載・複製を禁止します。</p>
</footer>

</body>
</html>