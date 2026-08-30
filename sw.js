/* =====================================================
   Service Worker (sw.js)
===================================================== */

self.addEventListener("install", event => {
    self.skipWaiting();
});

self.addEventListener("activate", event => {
    event.waitUntil(clients.claim());
});

/* -----------------------------------------------------
   Push通知受信時の処理（天気・地震などのプッシュを表示）
----------------------------------------------------- */
self.addEventListener("push", event => {
    let data = {};
    
    try {
        if (event.data) {
            data = event.data.json();
        }
    } catch (e) {
        data = {
            title: "防災・天気通知",
            body: event.data ? event.data.text() : "新しい情報が更新されました。"
        };
    }

    const title = data.title || "防災・天気通知";
    const options = {
        body: data.body || "新しい情報が更新されました。",
        icon: data.icon || "/icon.png",
        badge: data.badge || "/badge.png",
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
                    if (targetUrl) {
                        client.navigate(targetUrl);
                    }
                    return;
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});