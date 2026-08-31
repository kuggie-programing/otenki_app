/* =====================================================
   Service Worker (sw.js)
   - Web Push通知
   - アプリ画面のオフライン表示
===================================================== */

const CACHE_VERSION = "otenki-phase-free-v1";
const RUNTIME_CACHE = "otenki-phase-free-runtime-v1";
const APP_SHELL = [
    "/",
    "/index.html",
    "/app.css",
    "/main.js",
    "/quiz.txt",
    "/manifest.webmanifest",
    "/icon-192.png",
    "/icon-512.png",
    "/badge-96.png",
    "/icon.png",
    "/badge.png"
];

self.addEventListener("install", event => {
    event.waitUntil(
        caches.open(CACHE_VERSION)
            .then(cache => cache.addAll(APP_SHELL))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", event => {
    event.waitUntil(
        caches.keys()
            .then(keys => Promise.all(
                keys
                    .filter(key => key !== CACHE_VERSION && key !== RUNTIME_CACHE)
                    .map(key => caches.delete(key))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("message", event => {
    if (event.data && event.data.type === "SKIP_WAITING") {
        self.skipWaiting();
    }
});

/* -----------------------------------------------------
   オフライン用フェッチ
----------------------------------------------------- */
self.addEventListener("fetch", event => {
    const request = event.request;
    if (request.method !== "GET") return;

    const url = new URL(request.url);

    // APIは古い応答を誤って表示しないよう、Service Workerには保存しません。
    // APIが別ドメインにある場合も含め、/api/ の通信はそのままネットへ送ります。
    if (url.pathname.startsWith("/api/")) {
        return;
    }

    // このアプリ以外の外部通信はキャッシュしません。
    if (url.origin !== self.location.origin) {
        return;
    }

    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request)
                .then(response => {
                    if (response && response.ok) {
                        const copy = response.clone();
                        caches.open(RUNTIME_CACHE).then(cache => cache.put("/index.html", copy));
                    }
                    return response;
                })
                .catch(async () => {
                    return (await caches.match("/index.html")) ||
                        (await caches.match("/")) ||
                        new Response(
                            "オフラインです。通信できる時に一度アプリを開いてください。",
                            { headers: { "Content-Type": "text/plain; charset=utf-8" } }
                        );
                })
        );
        return;
    }

    if (url.origin === self.location.origin) {
        event.respondWith(
            caches.match(request).then(cached => {
                if (cached) return cached;
                return fetch(request).then(response => {
                    if (response && response.ok) {
                        const copy = response.clone();
                        caches.open(RUNTIME_CACHE).then(cache => cache.put(request, copy));
                    }
                    return response;
                });
            })
        );
        return;
    }
});

/* -----------------------------------------------------
   Push通知受信時の処理（天気・地震などの通知を表示）
----------------------------------------------------- */
self.addEventListener("push", event => {
    let data = {};

    try {
        if (event.data) {
            data = event.data.json();
        }
    } catch (error) {
        data = {
            title: "防災・天気通知",
            body: event.data ? event.data.text() : "新しい情報が更新されました。"
        };
    }

    const title = data.title || "防災・天気通知";
    const options = {
        body: data.body || "新しい情報が更新されました。",
        icon: data.icon || "/icon-192.png",
        badge: data.badge || "/badge-96.png",
        data: data.url || data.link || "/",
        tag: data.tag || "weather-earthquake-notification",
        renotify: true
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

/* -----------------------------------------------------
   通知をクリックしたときの処理
----------------------------------------------------- */
self.addEventListener("notificationclick", event => {
    event.notification.close();

    const targetUrl = event.notification.data || "/";

    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then(clientList => {
            for (const client of clientList) {
                if (client.url.includes(self.location.origin) && "focus" in client) {
                    client.focus();
                    if (targetUrl && "navigate" in client) {
                        client.navigate(targetUrl);
                    }
                    return;
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
            return undefined;
        })
    );
});
