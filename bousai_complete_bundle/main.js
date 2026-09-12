/* =====================================================
   Web Push / 通知
===================================================== */

const VAPID_PUBLIC_KEY =
    window.VAPID_PUBLIC_KEY || "";


/* =====================================================
   Base64URL → Uint8Array
===================================================== */

function urlBase64ToUint8Array(base64String) {

    const padding =
        "=".repeat(
            (4 - base64String.length % 4) % 4
        );

    const base64 =
        (
            base64String +
            padding
        )
            .replace(/-/g, "+")
            .replace(/_/g, "/");

    const rawData =
        window.atob(base64);

    const outputArray =
        new Uint8Array(
            rawData.length
        );

    for (
        let i = 0;
        i < rawData.length;
        i++
    ) {

        outputArray[i] =
            rawData.charCodeAt(i);

    }

    return outputArray;
}


/* =====================================================
   Service Worker登録
===================================================== */

let pushServiceWorkerRegistration =
    null;


async function registerPushServiceWorker() {

    if (
        !("serviceWorker" in navigator)
    ) {

        console.warn(
            "このブラウザはService Workerに対応していません。"
        );

        return null;

    }

    try {

        pushServiceWorkerRegistration =
            await navigator.serviceWorker.register(
                "/sw.js",
                {
                    scope: "/"
                }
            );

        await navigator.serviceWorker.ready;

        console.log(
            "Service Worker登録完了"
        );

        return pushServiceWorkerRegistration;

    } catch (error) {

        console.error(
            "Service Worker登録失敗:",
            error
        );

        return null;

    }

}


/* =====================================================
   通知権限
===================================================== */

async function requestNotificationPermission() {

    if (
        !("Notification" in window)
    ) {

        alert(
            "このブラウザは通知に対応していません。"
        );

        return false;

    }

    const permission =
        await Notification.requestPermission();

    if (
        permission !== "granted"
    ) {

        console.warn(
            "通知が許可されませんでした。"
        );

        return false;

    }

    return true;

}


/* =====================================================
   Web Push購読
===================================================== */

async function subscribeToRealPush() {

    if (
        !("PushManager" in window)
    ) {

        console.warn(
            "このブラウザはWeb Pushに対応していません。"
        );

        return false;

    }

    if (
        !VAPID_PUBLIC_KEY
    ) {

        console.error(
            "VAPID_PUBLIC_KEYが設定されていません。"
        );

        return false;

    }

    try {

        const registration =
            await registerPushServiceWorker();

        if (!registration) {
            return false;
        }

        const permitted =
            await requestNotificationPermission();

        if (!permitted) {
            return false;
        }

        let subscription =
            await registration.pushManager.getSubscription();

        if (!subscription) {

            subscription =
                await registration.pushManager.subscribe(
                    {
                        userVisibleOnly:
                            true,

                        applicationServerKey:
                            urlBase64ToUint8Array(
                                VAPID_PUBLIC_KEY
                            )
                    }
                );

        }

        const result =
            await apiRequest(
                "/api/push/subscribe",
                {
                    method:
                        "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            subscription:
                                subscription.toJSON()
                        })
                },
                15000
            );


        if (!result.ok) {

            console.error(
                "Push購読登録失敗:",
                result.error
            );

            return false;

        }

        console.log(
            "本物のWeb Push購読登録完了"
        );

        return true;

    } catch (error) {

        console.error(
            "Web Push購読エラー:",
            error
        );

        return false;

    }

}


/* =====================================================
   Web Push購読解除
===================================================== */

async function unsubscribeFromRealPush() {

    try {

        const registration =
            await navigator.serviceWorker.ready;

        const subscription =
            await registration.pushManager.getSubscription();

        if (!subscription) {
            return true;
        }

        const endpoint =
            subscription.endpoint;

        await apiRequest(
            "/api/push/unsubscribe",
            {
                method:
                    "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify({
                        endpoint:
                            endpoint
                    })
            },
            10000
        );

        await subscription.unsubscribe();

        console.log(
            "Web Push購読を解除しました。"
        );

        return true;

    } catch (error) {

        console.error(
            "Push購読解除エラー:",
            error
        );

        return false;

    }

}


/* =====================================================
   通知設定を有効化 / 無効化 / 状態確認
===================================================== */

async function enableRealPushNotifications() {

    const success =
        await subscribeToRealPush();

    const statusEl =
        document.getElementById(
            "pushPermissionStatus"
        );

    if (success) {

        if (statusEl) {
            statusEl.innerText = "通知：許可済み";
        }

        triggerPushNotification(
            "通知を有効にしました",
            "地震や天気などの重要なお知らせを受け取れるようになりました。"
        );

        return true;

    }

    if (statusEl) {
        statusEl.innerText = "通知：未許可";
    }

    return false;

}

async function disableRealPushNotifications() {

    const success =
        await unsubscribeFromRealPush();

    const statusEl =
        document.getElementById(
            "pushPermissionStatus"
        );

    if (success && statusEl) {
        statusEl.innerText = "通知：無効";
    }

}

async function updatePushPermissionStatus() {

    const statusEl =
        document.getElementById(
            "pushPermissionStatus"
        );

    if (!statusEl) {
        return;
    }

    if (!("Notification" in window)) {
        statusEl.innerText = "通知：非対応";
        return;
    }

    if (Notification.permission === "granted") {

        try {
            const registration =
                await navigator.serviceWorker.ready;

            const subscription =
                await registration.pushManager.getSubscription();

            statusEl.innerText =
                subscription
                    ? "通知：許可済み"
                    : "通知：未登録";

        } catch {
            statusEl.innerText = "通知：許可済み";
        }

        return;

    }

    if (Notification.permission === "denied") {
        statusEl.innerText = "通知：ブロック中";
        return;
    }

    statusEl.innerText = "通知：未設定";

}


/* =====================================================
   画面内通知バナー
===================================================== */

function triggerPushNotification(
    title,
    msg
) {

    const banner =
        document.getElementById(
            "pushNotificationBanner"
        );

    if (!banner) {
        return;
    }

    const titleEl =
        document.getElementById(
            "pushNotificationTitle"
        );

    const textEl =
        document.getElementById(
            "pushNotificationText"
        );

    if (titleEl) {
        titleEl.innerText = title;
    }

    if (textEl) {
        textEl.innerText = msg;
    }

    banner.classList.remove(
        "translate-x-full"
    );

    setTimeout(
        () => {
            banner.classList.add(
                "translate-x-full"
            );
        },
        6000
    );

}

function closePushBanner() {
    document
        .getElementById(
            "pushNotificationBanner"
        )
        ?.classList.add(
            "translate-x-full"
        );
}


/* =====================================================
   初期化とイベントリスナー
===================================================== */

document.addEventListener(
    "DOMContentLoaded",
    async () => {

        loadAppState();

        await registerPushServiceWorker();

        await updatePushPermissionStatus();

        if (appState.userName) {

            const welcome =
                document.getElementById(
                    "welcomeUserName"
                );

            if (welcome) {
                welcome.innerText = appState.userName;
            }

            const label =
                document.getElementById(
                    "currentUserLabel"
                );

            if (label) {
                label.innerText = `ログイン中: ${appState.userName}`;
            }

            document
                .getElementById(
                    "headerUserArea"
                )
                ?.classList.remove(
                    "hidden"
                );

            switchScreen("dashboard");

        } else {
            switchScreen("login");
        }

    }
);

document.addEventListener(
    "click",
    event => {

        const enableButton =
            event.target.closest(
                "#enablePushButton"
            );

        if (enableButton) {
            enableRealPushNotifications();
        }

        const disableButton =
            event.target.closest(
                "#disablePushButton"
            );

        if (disableButton) {
            disableRealPushNotifications();
        }

    }
);