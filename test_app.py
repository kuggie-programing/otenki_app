
/* ログイン処理は、通知・天気・オフライン準備の成功に依存しない。 */
let authEpoch = 0;
let authBusy = false;
let rememberLogin = false;
let pushBannerTimer = null;
const activeApiControllers = new Set();
function storageRead(key) { try { return localStorage.getItem(key); } catch { return null; } }
function storageWrite(key,value) { try { localStorage.setItem(key,value); return true; } catch { return false; } }
function storageDelete(key) { try { localStorage.removeItem(key); return true; } catch { return false; } }
function encodeSecurityKey(value) {
    return btoa(Array.from(new TextEncoder().encode(value), x=>String.fromCharCode(x)).join(""));
}
function promiseTimeout(promise, ms) {
    let timer;
    return Promise.race([promise,new Promise((_,reject)=>{ timer=setTimeout(()=>reject(new Error("Timeout")),ms); })])
        .finally(()=>clearTimeout(timer));
}
function invalidateRequests() {
    authEpoch += 1;
    activeApiControllers.forEach(c=>c.abort()); activeApiControllers.clear();
}
function resetAccountViews() {
    stopPolling();
    emergencyModeActive = false; emergencyModeExiting = false;
    document.body.classList.remove("emergency-active");
    ["userName","securityKey","accountId"].forEach(k=>appState[k]="");
    ["friends","friendRequests","safetyStatuses","hazardPosts"].forEach(k=>appState[k]=[]);
    currentOfflineStorageKey = "";
    offlineProfile = createDefaultOfflineProfile();
    currentWeatherSnapshot = null;
    selectedPreparationItems = new Set();
    currentPreparationScenario = "auto"; activePreparationScenario = "mild";
    const prep = document.getElementById("preparationChoices");
    if (prep) delete prep.dataset.restored;
    resetTomorrowPlanState();
    closeFriendModal(); closeHazardPostModal(); closeFriendRequestModal(); closePushBanner();
}
function clearLoginSession() {
    invalidateRequests();
    authBusy = false;
    setLoginButtonsDisabled(false);
    resetAccountViews();
    storageDelete("otenkiAppState");
    try { sessionStorage.removeItem("otenkiAppState"); } catch {}
    document.getElementById("headerUserArea")?.classList.add("hidden");
}
function cancelLogin() {
    invalidateRequests(); authBusy=false;
    setLoginButtonsDisabled(false); showLoginError("接続を取り消しました。キーは入力欄に残っています。");
}
function toggleSecurityKeyVisibility() {
    const input=document.getElementById("loginSecurityKey"), button=document.getElementById("showSecurityKey");
    if (!input) return;
    input.type=input.type==="password"?"text":"password";
    if (button) { button.textContent=input.type==="text"?"隠す":"表示"; button.setAttribute("aria-pressed",String(input.type==="text")); }
}
function makeSecurityKey() {
    const bytes=crypto.getRandomValues(new Uint8Array(24));
    const key=btoa(Array.from(bytes,b=>String.fromCharCode(b)).join("")).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"");
    document.getElementById("loginSecurityKey").value=key;
    document.getElementById("loginSecurityKey").type="text";
    document.getElementById("showSecurityKey").textContent="隠す";
    document.getElementById("showSecurityKey").setAttribute("aria-pressed","true");
    showLoginError("新規登録用のキーを作りました。必ず自分で安全な場所に控えてから登録してください。以前のアカウントのキーは変わりません。");
}
async function checkConnection() {
    const el=document.getElementById("loginConnectionStatus");
    if (el) el.textContent="サーバーを確認しています…";
    const r=await apiRequest("/api/health",{skipAuth:true},6000);
    if (r.stale) return;
    if (el) el.textContent=r.ok && r.data.app==="otenki"
        ? `接続できました（${r.data.version||"バージョン不明"}）`
        : r.error || "防災アプリのサーバーか確認できませんでした。main.py も更新してください。";
}
async function restoreSavedLogin() {
    if (!appState.accountId) return;
    if (!navigator.onLine) { updateUserHeader(); switchScreen("dashboard"); return; }
    const epoch=authEpoch;
    const result=await apiRequest("/api/account/me",{},10000);
    if (epoch!==authEpoch) return;
    if (result.ok && result.data.user?.id===appState.accountId) {
        appState.userName=result.data.user.name;
        saveAppState(); updateUserHeader(); startPolling();
    } else if (result.status===401) {
        clearLoginSession(); switchScreen("login");
        showLoginError("保存したログイン情報を確認できません。元のキーと接続先を確認してください。端末の知恵・安心メモは消していません。");
    }
}
function backToHome() {
    if (emergencyModeActive) switchScreen("emergency");
    else if (appState.accountId) switchScreen("dashboard");
    else switchScreen("login");
}



/* =====================================================
   API設定 & グローバル変数
===================================================== */
const API_BASE_URL = String(window.OTENKI_API_BASE_URL || (location.protocol.startsWith("http") ? location.origin : "")).replace(/\/+$/,"");
const AMAKUSA_LAT = 32.4547;
const AMAKUSA_LON = 130.1978;
const POLL_INTERVAL_MS = 15000;
let VAPID_PUBLIC_KEY = "";

let pollTimers = [];
let jstMonitorStarted = false;
let lastNotifiedKey = "";
let currentFriendRequest = null;
let pushServiceWorkerRegistration = null;
let deferredInstallPrompt = null;

let allQuizQuestions = [];
let quizQuestions = [];
let quizIndex = 0;
let quizAnswered = false;
let quizMode = "scenario";
let quizScore = { answered: 0, correct: 0 };

let selectedHazardImage = "";
let selectedPlaceKind = "danger";
let hazardFilter = "all";

let currentWeatherSnapshot = null;
let currentPreparationScenario = "auto";
let activePreparationScenario = "mild";
let selectedPreparationItems = new Set();
let emergencyModeActive = false;
let emergencyModeExiting = false;

let currentFamilyRuleScenario = "";
let familyRuleStep = 0;
let familyRuleDraft = { answers: [] };

let currentOfflineStorageKey = "";
let offlineProfile = createDefaultOfflineProfile();

const appState = {
    userName: "",
    securityKey: "",
    accountId: "",
    friends: [],
    friendRequests: [],
    safetyStatuses: [],
    hazardPosts: []
};

/* =====================================================
   API通信用ラッパー
===================================================== */
function isApiConfigured() {
    return /^https?:\/\//.test(API_BASE_URL);
}

async function apiRequest(path, options = {}, timeout = 15000) {
    if (!isApiConfigured()) return {ok:false,error:"HTMLを直接開かず、python main.py で起動し http://127.0.0.1:5000 を開いてください。"};
    if (!navigator.onLine) return {ok:false,offline:true,error:"オフラインです。送信はできません。保存した情報は確認できます。"};
    const {skipAuth = /^\/api\/(?:account\/(?:login|register)|health|weather(?:\/|$)|push\/public-key)/.test(path),
           headers: extraHeaders = {}, ...fetchOptions} = options;
    const epoch = authEpoch;
    const controller = new AbortController();
    activeApiControllers.add(controller);
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
        const headers = {"Content-Type":"application/json", ...extraHeaders};
        if (!skipAuth && appState.securityKey) {
            // HTTPヘッダーは日本語を直接載せられないため、UTF-8→Base64で送信する。
            headers["X-Security-Key-Encoded"] = encodeSecurityKey(appState.securityKey);
        }
        const response = await fetch(API_BASE_URL + path, {
            ...fetchOptions, headers, signal:controller.signal, cache:"no-store",
            credentials:"omit", redirect:"error"
        });
        const raw = await response.text();
        let data;
        try { data = JSON.parse(raw); } catch { data = null; }
        if (epoch !== authEpoch) return {ok:false,stale:true,error:"操作が取り消されました。"};
        if (!data || typeof data !== "object" || Array.isArray(data)) {
            return {ok:false,status:response.status,error:"接続先からアプリ用の応答が返りません。Pythonサーバーと api-config.js の接続先を確認してください。"};
        }
        if (!response.ok || data.ok === false) return {ok:false,status:response.status,code:data.code,error:data.error || `通信エラー（${response.status}）`};
        return {ok:true,status:response.status,data};
    } catch (error) {
        if (epoch !== authEpoch) return {ok:false,stale:true,error:"操作が取り消されました。"};
        return {ok:false,error:error?.name === "AbortError"
            ? "接続がタイムアウトしました。サーバーの起動と接続先を確認して、もう一度試してください。"
            : "サーバーに接続できません。通信状態・サーバーの起動・接続先を確認してください。"};
    } finally {
        clearTimeout(timer);
        activeApiControllers.delete(controller);
    }
}

/* =====================================================
   ローカル保存
===================================================== */
function saveAppState() {
    if (!appState.accountId || !appState.securityKey) return false;
    const data = {...appState, apiBase:API_BASE_URL, version:5};
    const value = JSON.stringify(data);
    try {
        sessionStorage.setItem("otenkiAppState", value);
        if (rememberLogin) storageWrite("otenkiAppState", value);
        else storageDelete("otenkiAppState");
        return true;
    } catch {
        if (rememberLogin) return storageWrite("otenkiAppState",value);
        return false;
    }
}

function loadAppState() {
    let raw = null;
    try { raw = sessionStorage.getItem("otenkiAppState"); } catch {}
    if (!raw) raw = storageRead("otenkiAppState");
    if (!raw) return;
    try {
        const data = JSON.parse(raw);
        if (!data || typeof data !== "object" || !data.accountId || !data.securityKey) return;
        if (data.apiBase && data.apiBase !== API_BASE_URL) {
            showLoginError("前回と接続先が違います。元の登録データがあるサーバーを確認してください。");
            return;
        }
        appState.userName = String(data.userName || "");
        appState.accountId = String(data.accountId || "");
        appState.securityKey = String(data.securityKey || "");
        ["friends","friendRequests","safetyStatuses","hazardPosts"].forEach(k => {
            appState[k] = Array.isArray(data[k]) ? data[k] : [];
        });
        rememberLogin = Boolean(storageRead("otenkiAppState"));
    } catch { showLoginError("保存したログイン情報を読み込めません。もう一度ログインしてください。"); }
}

function createDefaultOfflineProfile() {
    return {
        version: 2,
        ownerId: "",
        ownerName: "",
        familyRules: [],
        emergencyPlan: {
            primaryMeeting: "",
            secondaryMeeting: "",
            contactName1: "",
            contactPhone1: "",
            contactName2: "",
            contactPhone2: "",
            noContactRule: "",
            notes: ""
        },
        weatherPreparation: null,
        lastWeather: null,
        cachedPlaces: [],
        lastSavedAt: ""
    };
}

function normalizeOfflineProfile(value) {
    const base = createDefaultOfflineProfile();
    const source = value && typeof value === "object" ? value : {};
    const plan = source.emergencyPlan && typeof source.emergencyPlan === "object"
        ? source.emergencyPlan
        : {};

    return {
        ...base,
        ...source,
        familyRules: Array.isArray(source.familyRules) ? source.familyRules : [],
        emergencyPlan: {
            ...base.emergencyPlan,
            ...plan
        },
        cachedPlaces: Array.isArray(source.cachedPlaces) ? source.cachedPlaces : []
    };
}

function getOfflineStorageKey() {
    if (appState.accountId) {
        return `otenkiOfflineProfile:${appState.accountId}`;
    }
    return storageRead("otenkiLastOfflineProfileKey") || "otenkiOfflineProfile:guest";
}

function loadOfflineProfile(storageKey = "") {
    try {
        const key = storageKey || getOfflineStorageKey();
        const raw = storageRead(key);
        offlineProfile = normalizeOfflineProfile(raw ? JSON.parse(raw) : null);
        currentOfflineStorageKey = key;

        if (appState.accountId) {
            offlineProfile.ownerId = appState.accountId;
            offlineProfile.ownerName = appState.userName;
            currentOfflineStorageKey = `otenkiOfflineProfile:${appState.accountId}`;
            storageWrite("otenkiLastOfflineProfileKey", currentOfflineStorageKey);
        }
    } catch (error) {
        console.error("オフライン情報の読み込みエラー:", error);
        offlineProfile = createDefaultOfflineProfile();
        currentOfflineStorageKey = getOfflineStorageKey();
    }

    updateOfflineEntryAvailability();
    return offlineProfile;
}

function hasOfflineProfileContent(profile = offlineProfile) {
    const plan = profile?.emergencyPlan || {};
    return Boolean(
        (Array.isArray(profile?.familyRules) && profile.familyRules.length > 0) ||
        (Array.isArray(profile?.cachedPlaces) && profile.cachedPlaces.length > 0) ||
        plan.primaryMeeting ||
        plan.secondaryMeeting ||
        plan.contactName1 ||
        plan.contactPhone1 ||
        plan.contactName2 ||
        plan.contactPhone2 ||
        plan.noContactRule ||
        plan.notes
    );
}

function saveOfflineProfile(touchSavedAt = true) {
    try {
        const key = appState.accountId
            ? `otenkiOfflineProfile:${appState.accountId}`
            : (currentOfflineStorageKey || getOfflineStorageKey());

        currentOfflineStorageKey = key;
        if (appState.accountId) {
            offlineProfile.ownerId = appState.accountId;
            offlineProfile.ownerName = appState.userName;
        }
        if (touchSavedAt) {
            offlineProfile.lastSavedAt = new Date().toISOString();
        }

        if (!storageWrite(key, JSON.stringify(offlineProfile))) return false;
        if (hasOfflineProfileContent(offlineProfile) || appState.accountId) {
            storageWrite("otenkiLastOfflineProfileKey", key);
        }
        updateOfflineEntryAvailability();
        updateOfflineSavedLabels();
        return true;
    } catch (error) {
        console.error("オフライン情報の保存エラー:", error);
        return false;
    }
}

function formatSavedTime(value) {
    if (!value) return "まだ保存されていません";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "保存日時不明";
    return date.toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" });
}

function updateOfflineEntryAvailability() {
    const button = document.getElementById("openSavedOfflineBtn");
    const hint = document.getElementById("offlineLoginHint");
    const lastKey = storageRead("otenkiLastOfflineProfileKey");
    let exists = false;

    if (lastKey) {
        try {
            const raw = storageRead(lastKey);
            exists = hasOfflineProfileContent(normalizeOfflineProfile(raw ? JSON.parse(raw) : null));
        } catch {
            exists = false;
        }
    }

    button?.classList.toggle("hidden", !exists);
    hint?.classList.toggle("hidden", !exists);
}

function updateOfflineSavedLabels() {
    const label = document.getElementById("offlineLastSavedAt");
    if (label) {
        label.innerText = `最終保存：${formatSavedTime(offlineProfile.lastSavedAt)}`;
    }

    const prepLabel = document.getElementById("preparationSavedAt");
    if (prepLabel) {
        const savedAt = offlineProfile.weatherPreparation?.checkedAt;
        prepLabel.innerText = savedAt
            ? `前回考えた日時：${formatSavedTime(savedAt)}`
            : "選んだ内容は、この端末の安心メモに保存できます。";
    }
}

function getJSTNow() {
    return new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Tokyo" }));
}

/* =====================================================
   画面切替
===================================================== */
function switchScreen(screenId) {
    if (emergencyModeActive && screenId === "dashboard" && !emergencyModeExiting) {
        screenId = "emergency";
    }

    document.querySelectorAll(".screen").forEach(el => el.classList.add("hidden"));
    const target = document.getElementById(`screen-${screenId}`);
    if (target) {
        target.classList.remove("hidden");
    }
    window.scrollTo(0, 0);

    if (screenId === "quiz") {
        loadQuizIfNeeded();
    }
    if (screenId === "weather") {
        initializePreparationUI();
        fetchRealWeatherWithJST();
    }
    if (screenId === "safety") {
        if (navigator.onLine) {
            pollSafety();
        } else {
            renderSafetyList(appState.safetyStatuses);
        }
    }
    if (screenId === "hazard") {
        if (navigator.onLine) {
            pollHazard();
        } else {
            renderOfflineCachedHazardsInMainScreen();
        }
    }
    if (screenId === "family-rules") {
        renderFamilyRuleScenarioGrid();
        renderSavedFamilyRules();
    }
    if (screenId === "offline-kit") {
        hydrateOfflineForm();
        renderOfflineKit();
    }
    if (screenId === "tomorrow-plan") renderTomorrowPlan();
    if (screenId === "wisdom-bank") renderWisdomBank();
    if (screenId === "dashboard") {
        updateWisdomBankCount();
        fetchTomorrowDashboard();
        if (navigator.onLine) {
            pollFriends();
            pollFriendRequests();
        } else {
            renderFriends();
            renderFriendRequests();
        }
    }
    if (screenId === "emergency") {
        renderEmergencyMode();
    }
}

/* =====================================================
   ログインエラー制御
===================================================== */
function showLoginError(msg) {
    const el = document.getElementById("loginErrorMsg");
    if (!el) return;
    el.innerText = msg;
    el.classList.remove("hidden");
}

function hideLoginError() {
    const el = document.getElementById("loginErrorMsg");
    if (el) el.classList.add("hidden");
}

function setLoginButtonsDisabled(disabled) {
    ["loginRegisterBtn","loginLoginBtn"].forEach(id => {
        const button = document.getElementById(id);
        if (button) button.disabled = disabled;
    });
    document.getElementById("loginForm")?.setAttribute("aria-busy",String(disabled));
    const cancel = document.getElementById("cancelLoginButton");
    if (cancel) cancel.hidden = !disabled;
}

/* =====================================================
   認証・ログイン処理
===================================================== */
async function handleAuth(type) {
    if (authBusy) return;
    hideLoginError();
    const keyInput = document.getElementById("loginSecurityKey");
    const name = document.getElementById("loginName")?.value.trim() || "";
    const securityKey = keyInput?.value.trim() || "";
    const register = type === "register";
    if (!securityKey) { showLoginError("セキュリティキーを入力してください。"); keyInput?.focus(); return; }
    if ([...securityKey].length > 256 || /[\x00-\x1f\x7f]/.test(securityKey)) {
        showLoginError("キーは256文字以内、改行なしで入力してください。"); return;
    }
    if (register && !name) {
        showLoginError("アカウント作成には表示名も必要です。ログインだけなら表示名は不要です。");
        document.getElementById("loginName")?.focus(); return;
    }
    invalidateRequests();
    const epoch = authEpoch;
    authBusy = true;
    setLoginButtonsDisabled(true);
    showLoginError(register ? "アカウントを作成しています…" : "キーを確認しています…");
    try {
        const result = await apiRequest(register ? "/api/account/register" : "/api/account/login", {
            method:"POST", skipAuth:true,
            body:JSON.stringify(register ? {name,security_key:securityKey} : {security_key:securityKey})
        }, 20000);
        if (epoch !== authEpoch) return;
        if (!result.ok) {
            if (!result.stale) showLoginError(result.error);
            return;
        }
        const user = result.data?.user;
        if (!user || typeof user.id !== "string" || !user.id || typeof user.name !== "string") {
            showLoginError("ログイン結果を確認できません。main.py と接続先を確認してください。"); return;
        }
        resetAccountViews();
        appState.userName = user.name;
        appState.accountId = user.id;
        appState.securityKey = securityKey;
        appState.friends = Array.isArray(result.data.friends) ? result.data.friends : [];
        rememberLogin = Boolean(document.getElementById("rememberLogin")?.checked);
        storageWrite("otenkiLastLoginName",user.name);
        saveAppState();
        loadOfflineProfile();
        hideLoginError();
        if (keyInput) { keyInput.value = ""; keyInput.type = "password"; }
        const keyToggle = document.getElementById("showSecurityKey");
        if (keyToggle) { keyToggle.textContent = "表示"; keyToggle.setAttribute("aria-pressed","false"); }
        updateUserHeader();
        renderFriends(); renderFriendRequests();
        switchScreen("dashboard");
        initJSTBackgroundMonitors(); startPolling();
        void updatePushPermissionStatus();
    } catch (error) {
        if (epoch === authEpoch) showLoginError("ログイン後の画面を表示できませんでした。キーは変更せず、もう一度試してください。");
        console.error("ログイン処理:", error?.name || "Error");
    } finally {
        if (epoch === authEpoch) { authBusy = false; setLoginButtonsDisabled(false); }
    }
}

function updateUserHeader() {
    const welcome = document.getElementById("welcomeUserName");
    if (welcome) welcome.innerText = appState.userName;

    const label = document.getElementById("currentUserLabel");
    if (label) label.innerText = `ログイン中: ${appState.userName}`;

    document.getElementById("headerUserArea")?.classList.remove("hidden");
}

function handleLogout() {
    if (!confirm("ログアウトしますか？ 保存した知恵や安心メモは消えません。")) return;
    const previousName = appState.userName;
    clearLoginSession();
    storageWrite("otenkiLastLoginName",previousName);
    const nameInput = document.getElementById("loginName");
    const keyInput = document.getElementById("loginSecurityKey");
    if (nameInput) nameInput.value = previousName;
    if (keyInput) { keyInput.value = ""; keyInput.type = "password"; }
    const keyToggle = document.getElementById("showSecurityKey");
    if (keyToggle) { keyToggle.textContent = "表示"; keyToggle.setAttribute("aria-pressed","false"); }
    hideLoginError();
    switchScreen("login");
    updateOfflineEntryAvailability();
    keyInput?.focus();
}

/* =====================================================
   Web Push / 通知関連処理 (main.js 統合)
===================================================== */
async function ensureVapidPublicKey() {
    if (VAPID_PUBLIC_KEY) {
        return true;
    }

    try {
        const result = await apiRequest("/api/push/public-key", {
            method: "GET"
        }, 15000);

        const publicKey = String(result?.data?.public_key || "").trim();

        if (!result.ok || !publicKey) {
            console.warn(
                "VAPID公開キーを取得できませんでした:",
                result?.error || "公開キーが空です。"
            );
            return false;
        }

        VAPID_PUBLIC_KEY = publicKey;
        return true;
    } catch (error) {
        console.error("VAPID公開キー取得エラー:", error);
        return false;
    }
}

function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

async function registerPushServiceWorker() {
    if (!("serviceWorker" in navigator) || !window.isSecureContext) return null;
    try {
        const registration = await promiseTimeout(navigator.serviceWorker.register("/sw.js", {
            scope:"/", updateViaCache:"none"
        }), 5000);
        pushServiceWorkerRegistration = registration;
        // ready が永久に完了しなくても、ログイン・画面表示は待たせない。
        if (registration.active) return registration;
        return await promiseTimeout(navigator.serviceWorker.ready,5000);
    } catch {
        console.warn("オフライン機能の準備を完了できませんでした。ログインは続けられます。");
        return null;
    }
}

async function requestNotificationPermission() {
    if (!("Notification" in window)) {
        alert("このブラウザは通知に対応していません。");
        return false;
    }
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
        console.warn("通知が許可されませんでした。");
        return false;
    }
    return true;
}

async function subscribeToRealPush() {
    if (!appState.accountId || !navigator.onLine || !("PushManager" in window) || !window.isSecureContext) return false;
    try {
        // ユーザーが通知ONを押した直後に許可を確認。
        const permitted = Notification.permission === "granted" || await requestNotificationPermission();
        if (!permitted) return false;
        if (!(await ensureVapidPublicKey())) return false;
        const reg = await registerPushServiceWorker();
        if (!reg?.active) return false;
        let sub = await promiseTimeout(reg.pushManager.getSubscription(),5000);
        if (sub) {
            const configured = urlBase64ToUint8Array(VAPID_PUBLIC_KEY);
            const existing = sub.options?.applicationServerKey;
            if (existing && Array.from(new Uint8Array(existing)).join(",") !== Array.from(configured).join(",")) {
                await sub.unsubscribe(); sub = null;
            }
        }
        if (!sub) sub = await promiseTimeout(reg.pushManager.subscribe({
            userVisibleOnly:true, applicationServerKey:urlBase64ToUint8Array(VAPID_PUBLIC_KEY)
        }),12000);
        const response = await apiRequest("/api/push/subscribe",{
            method:"POST",body:JSON.stringify({subscription:sub.toJSON()})
        });
        return response.ok;
    } catch { return false; }
}

async function unsubscribeFromRealPush() {
    if (!("serviceWorker" in navigator)) return true;
    try {
        const reg = await promiseTimeout(navigator.serviceWorker.getRegistration("/"),3000);
        const sub = reg?.pushManager ? await promiseTimeout(reg.pushManager.getSubscription(),3000) : null;
        if (!sub) return true;
        if (appState.accountId && navigator.onLine) await apiRequest("/api/push/unsubscribe",{
            method:"POST",body:JSON.stringify({endpoint:sub.endpoint})
        });
        await promiseTimeout(sub.unsubscribe(),5000);
        return true;
    } catch { return false; }
}

async function enableRealPushNotifications() {
    const button = document.getElementById("enablePushButton");
    const status = document.getElementById("pushPermissionStatus");
    if (button?.disabled) return;
    if (button) button.disabled = true;
    if (status) status.textContent = "通知を設定中…";
    try {
        const ok = await subscribeToRealPush();
        if (status) status.textContent = ok ? "通知：登録済み" : "通知：設定できません。HTTPS・通知許可・サーバーのVAPID設定を確認してください。";
        return ok;
    } finally { if (button) button.disabled = false; }
}

async function disableRealPushNotifications() {
    const success = await unsubscribeFromRealPush();
    const statusEl = document.getElementById("pushPermissionStatus");
    if (success && statusEl) statusEl.innerText = "通知：無効";
}

async function updatePushPermissionStatus() {
    const el = document.getElementById("pushPermissionStatus");
    if (!el) return;
    if (!("Notification" in window) || !("serviceWorker" in navigator)) { el.textContent="通知：非対応"; return; }
    if (Notification.permission !== "granted") {
        el.textContent = Notification.permission === "denied" ? "通知：ブラウザでブロック中" : "通知：未設定";
        return;
    }
    try {
        const reg = await promiseTimeout(navigator.serviceWorker.getRegistration("/"),2000);
        const sub = reg?.active && reg.pushManager ? await promiseTimeout(reg.pushManager.getSubscription(),2000) : null;
        el.textContent = sub ? "通知：端末の購読あり" : "通知：未登録（通知ONで設定）";
    } catch { el.textContent="通知：確認できません（アプリは使えます）"; }
}

function triggerPushNotification(title, msg) {
    const banner = document.getElementById("pushNotificationBanner");
    if (!banner) return;
    document.getElementById("pushNotificationTitle").textContent = title;
    document.getElementById("pushNotificationText").textContent = msg;
    banner.hidden = false;
    banner.classList.remove("translate-x-full");
    clearTimeout(pushBannerTimer);
    pushBannerTimer = setTimeout(closePushBanner,6000);
    // 画面内の操作結果をOS通知に重複配信しない。実際のPushはsw.jsが表示する。
}

function closePushBanner() {
    const banner = document.getElementById("pushNotificationBanner");
    if (banner) { banner.classList.add("translate-x-full"); banner.hidden = true; }
}

/* =====================================================
   フレンド・リクエスト関連
===================================================== */
let friendSearchTimer = null;
let friendSearchSerial = 0;

function openFriendModal() {
    const modal = document.getElementById("friendModal");
    if (!modal) return;

    const input = document.getElementById("friendSearchInput");
    if (input) input.value = "";

    document.getElementById("friendSearchResults")?.replaceChildren();
    document.getElementById("friendModalError")?.classList.add("hidden");

    const hint = document.getElementById("friendSearchHint");
    if (hint) {
        hint.innerText = "1文字以上入力すると候補が表示されます。";
        hint.classList.remove("hidden");
    }

    modal.classList.remove("hidden");
    setTimeout(() => input?.focus(), 100);
}

function closeFriendModal() {
    if (friendSearchTimer) {
        clearTimeout(friendSearchTimer);
        friendSearchTimer = null;
    }
    friendSearchSerial += 1;
    document.getElementById("friendModal")?.classList.add("hidden");
}

function handleFriendSearchInput() {
    const input = document.getElementById("friendSearchInput");
    const query = input?.value.trim() || "";
    const resultsEl = document.getElementById("friendSearchResults");
    const errorEl = document.getElementById("friendModalError");
    const hint = document.getElementById("friendSearchHint");

    if (errorEl) errorEl.classList.add("hidden");
    if (friendSearchTimer) clearTimeout(friendSearchTimer);

    if (!query) {
        friendSearchSerial += 1;
        if (resultsEl) resultsEl.innerHTML = "";
        if (hint) {
            hint.innerText = "1文字以上入力すると候補が表示されます。";
            hint.classList.remove("hidden");
        }
        return;
    }

    if (hint) {
        hint.innerText = "入力した文字から始まるユーザーを検索します。";
        hint.classList.remove("hidden");
    }

    friendSearchTimer = setTimeout(() => searchFriendUsers(query), 250);
}

async function searchFriendUsers(query) {
    if (!appState.accountId || !appState.securityKey) {
        showFriendSearchError("ログインしてください。");
        return;
    }

    const serial = ++friendSearchSerial;
    const spinner = document.getElementById("friendSearchSpinner");
    const resultsEl = document.getElementById("friendSearchResults");
    const hint = document.getElementById("friendSearchHint");

    spinner?.classList.remove("hidden");

    const result = await apiRequest(`/api/users/search?q=${encodeURIComponent(query)}`, {
        method: "GET"
    }, 10000);

    if (serial !== friendSearchSerial) return;
    spinner?.classList.add("hidden");

    if (!result.ok) {
        if (resultsEl) resultsEl.innerHTML = "";
        showFriendSearchError(result.error || "ユーザー検索に失敗しました。");
        return;
    }

    const users = Array.isArray(result.data.users) ? result.data.users : [];
    renderFriendSearchResults(users);

    if (hint) {
        hint.innerText = users.length
            ? `${users.length}人見つかりました。追加したい人を選んでください。`
            : "一致するユーザーが見つかりませんでした。";
        hint.classList.remove("hidden");
    }
}

function renderFriendSearchResults(users) {
    const container = document.getElementById("friendSearchResults");
    if (!container) return;
    container.innerHTML = "";

    users.forEach(user => {
        const id = String(user.id || "");
        const name = String(user.name || "");
        if (!id || !name) return;

        const row = document.createElement("button");
        row.type = "button";
        row.className = "w-full text-left bg-slate-50 hover:bg-purple-50 border border-slate-200 hover:border-purple-200 rounded-2xl p-3 flex items-center justify-between gap-3";

        const left = document.createElement("div");
        left.className = "flex items-center gap-3 min-w-0";
        left.innerHTML = `
            <div class="w-10 h-10 shrink-0 rounded-full bg-purple-100 flex items-center justify-center text-xl">👤</div>
            <div class="min-w-0">
                <div class="text-sm font-black text-slate-800 truncate">${escapeHtml(name)}</div>
                <div class="text-[10px] text-slate-400 truncate">ユーザーID: ${escapeHtml(id.slice(0, 12))}</div>
            </div>
        `;

        const action = document.createElement("span");
        action.className = "shrink-0 bg-purple-500 text-white rounded-xl px-3 py-2 text-[11px] font-black";
        action.innerText = "追加";

        row.appendChild(left);
        row.appendChild(action);
        row.addEventListener("click", () => sendFriendRequestToUser(id, name, row));
        container.appendChild(row);
    });
}

function showFriendSearchError(message) {
    const errorEl = document.getElementById("friendModalError");
    if (!errorEl) return;
    errorEl.innerText = message;
    errorEl.classList.remove("hidden");
}

async function sendFriendRequestToUser(targetUserId, targetName, rowButton) {
    if (!targetUserId) return;

    const errorEl = document.getElementById("friendModalError");
    errorEl?.classList.add("hidden");

    const previousHtml = rowButton?.innerHTML;
    if (rowButton) {
        rowButton.disabled = true;
        rowButton.innerHTML = '<div class="w-full text-center text-xs font-bold text-slate-500 py-2">送信中...</div>';
    }

    const result = await apiRequest("/api/friends/request", {
        method: "POST",
        body: JSON.stringify({ user_id: targetUserId })
    }, 20000);

    if (!result.ok) {
        if (rowButton) {
            rowButton.disabled = false;
            rowButton.innerHTML = previousHtml;
        }
        showFriendSearchError(result.error || "リクエストの送信に失敗しました。");
        return;
    }

    closeFriendModal();
    triggerPushNotification("家族・友達リクエスト", `${targetName}さんへリクエストを送信しました。`);
    alert(`${targetName}さんへ家族・友達リクエストを送信しました。`);
    await pollFriendRequests();
}

async function pollFriends() {
    if (!appState.accountId) return;
    const result = await apiRequest("/api/friends", { method: "GET" }, 10000);
    if (!result.ok) return;
    appState.friends = result.data.friends || [];
    saveAppState();
    renderFriends();
}

function renderFriends() {
    const container = document.getElementById("friendsList");
    if (!container) return;
    container.innerHTML = "";

    if (!appState.friends || appState.friends.length === 0) {
        container.innerHTML = `
            <div class="text-center py-8 bg-white/60 rounded-2xl border border-dashed border-slate-300">
                <div class="text-3xl mb-2">👥</div>
                <p class="text-xs text-slate-400">まだ家族・友達が登録されていません。</p>
                <button onclick="openFriendModal()" class="mt-3 bg-purple-500 text-white rounded-xl px-4 py-2 text-xs font-black">家族・友達を追加</button>
            </div>
        `;
        return;
    }

    appState.friends.forEach(friend => {
        const name = typeof friend === "string" ? friend : friend.name || "";
        const friendId = typeof friend === "object" ? friend.id || "" : "";
        const status = typeof friend === "object" ? friend.status || "connected" : "connected";
        const row = document.createElement("div");
        row.className = "bg-white border border-slate-200 rounded-2xl p-3 flex items-center justify-between";
        const statusText = status === "connected" ? "接続中" : status;

        row.innerHTML = `
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center text-xl">👤</div>
                <div>
                    <p class="text-xs font-black text-slate-800">${escapeHtml(name)}</p>
                    <p class="text-[10px] text-emerald-600 mt-1"><span class="status-dot bg-emerald-500"></span>${escapeHtml(statusText)}</p>
                </div>
            </div>
            <button class="text-[10px] text-slate-400 hover:text-rose-500 font-bold" onclick="removeFriend('${escapeJs(friendId)}', '${escapeJs(name)}')">接続解除</button>
        `;
        container.appendChild(row);
    });
}

async function removeFriend(friendId, name) {
    if (!friendId) {
        alert("相手のユーザーIDを取得できませんでした。画面を更新してもう一度お試しください。");
        return;
    }
    if (!confirm(`${name}さんとの家族・友達接続を解除しますか？`)) return;
    const result = await apiRequest(`/api/friends/${encodeURIComponent(friendId)}`, { method: "DELETE" });
    if (!result.ok) {
        alert(`接続解除に失敗しました：${result.error}`);
        return;
    }
    await pollFriends();
}

async function pollFriendRequests() {
    if (!appState.accountId) return;
    const result = await apiRequest("/api/friends/requests", { method: "GET" }, 10000);
    if (!result.ok) return;

    const newRequests = (result.data.received || []).filter(request => request.status === "pending");
    const oldIds = new Set(appState.friendRequests.map(r => String(r.id || "")));

    newRequests.forEach(request => {
        const id = String(request.id || "");
        if (id && !oldIds.has(id)) {
            triggerPushNotification("家族・友達リクエスト", `${request.from?.name || "誰か"}さんからリクエストが届きました。`);
        }
    });

    appState.friendRequests = newRequests;
    saveAppState();
    renderFriendRequests();
}

function renderFriendRequests() {
    const container = document.getElementById("friendRequestsList");
    const badge = document.getElementById("requestCountBadge");
    if (!container) return;
    container.innerHTML = "";

    const requests = appState.friendRequests || [];
    if (badge) {
        if (requests.length > 0) {
            badge.innerText = String(requests.length);
            badge.classList.remove("hidden");
        } else {
            badge.classList.add("hidden");
        }
    }

    if (requests.length === 0) {
        container.innerHTML = `<p class="text-[11px] text-slate-400 text-center py-5">新しいリクエストはありません。</p>`;
        return;
    }

    requests.forEach(request => {
        const fromName = request.from?.name || request.from_name || request.name || "不明なユーザー";
        const row = document.createElement("div");
        row.className = "bg-white border border-slate-200 rounded-2xl p-4";
        row.innerHTML = `
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-full bg-sky-100 flex items-center justify-center text-xl">👋</div>
                <div class="flex-1">
                    <p class="text-sm font-black text-slate-800">${escapeHtml(fromName)}</p>
                    <p class="text-[10px] text-slate-500 mt-1">家族・友達になりたいというリクエストです。</p>
                </div>
            </div>
            <div class="grid grid-cols-2 gap-2 mt-3">
                <button class="bg-slate-100 hover:bg-slate-200 rounded-xl py-2 text-xs font-bold text-slate-700" onclick="rejectFriendRequest('${escapeJs(request.id)}')">拒否</button>
                <button class="bg-emerald-500 hover:bg-emerald-600 rounded-xl py-2 text-xs font-black text-white" onclick="acceptFriendRequest('${escapeJs(request.id)}')">許可</button>
            </div>
        `;
        container.appendChild(row);
    });
}

async function acceptFriendRequest(requestId) {
    const result = await apiRequest(`/api/friends/requests/${encodeURIComponent(requestId)}/accept`, {
        method: "POST",
        body: JSON.stringify({ account_id: appState.accountId })
    });
    if (!result.ok) {
        alert(`リクエストの許可に失敗しました：${result.error}`);
        return;
    }
    appState.friendRequests = appState.friendRequests.filter(req => String(req.id) !== String(requestId));
    saveAppState();
    await pollFriends();
    renderFriendRequests();
    triggerPushNotification("家族・友達接続完了", "家族・友達として接続されました。");
}

async function rejectFriendRequest(requestId) {
    const result = await apiRequest(`/api/friends/requests/${encodeURIComponent(requestId)}/reject`, {
        method: "POST",
        body: JSON.stringify({ account_id: appState.accountId })
    });
    if (!result.ok) {
        alert(`リクエストの拒否に失敗しました：${result.error}`);
        return;
    }
    appState.friendRequests = appState.friendRequests.filter(req => String(req.id) !== String(requestId));
    saveAppState();
    renderFriendRequests();
}

/* =====================================================
   ポーリング & サーバ接続状態
===================================================== */
function startPolling() {
    stopPolling();
    if (!navigator.onLine || !appState.accountId) return;
    pollFriends();
    pollFriendRequests();
    pollSafety();
    pollHazard();

    pollTimers.push(setInterval(pollFriends, POLL_INTERVAL_MS));
    pollTimers.push(setInterval(pollFriendRequests, POLL_INTERVAL_MS));
    pollTimers.push(setInterval(pollSafety, POLL_INTERVAL_MS));
    pollTimers.push(setInterval(pollHazard, POLL_INTERVAL_MS));
}

function stopPolling() {
    pollTimers.forEach(timer => clearInterval(timer));
    pollTimers = [];
}

function setServerConnStatus(ok) {
    const elements = document.querySelectorAll("#safetyConnStatus, #hazardSyncStatus, #globalConnectionStatus");
    const isOffline = !navigator.onLine;
    elements.forEach(el => {
        if (!el.dataset.customStatus) {
            el.innerText = isOffline
                ? "オフライン（保存情報を利用できます）"
                : (ok ? "サーバー接続中" : "サーバー接続エラー");
        }
    });
}

/* =====================================================
   安否確認
===================================================== */
async function pollSafety() {
    if (!appState.accountId) return;
    const statusEl = document.getElementById("safetyConnStatus");
    const result = await apiRequest("/api/safety", { method: "GET" }, 10000);
    setServerConnStatus(result.ok);

    if (!result.ok) {
        if (statusEl) statusEl.innerText = "同期エラー（再試行中）";
        return;
    }
    if (statusEl) statusEl.innerText = `最終同期: ${getJSTNow().toLocaleTimeString("ja-JP")}`;

    appState.safetyStatuses = result.data.statuses || [];
    saveAppState();
    renderSafetyList(appState.safetyStatuses);
}

function safetyStatusLabel(status) {
    if (status === "safe") return { emoji: "😊", text: "元気です", cls: "bg-amber-50 border-amber-200 text-amber-900" };
    if (status === "messy") return { emoji: "🏠", text: "被害あり", cls: "bg-orange-50 border-orange-200 text-orange-900" };
    if (status === "sos") return { emoji: "🆘", text: "緊急SOS", cls: "bg-rose-100 border-rose-300 text-rose-900" };
    return { emoji: "❔", text: status, cls: "bg-slate-50 border-slate-200 text-slate-700" };
}

function renderSafetyList(statuses) {
    const container = document.getElementById("groupSafetyStatusList");
    if (!container) return;
    if (!statuses || statuses.length === 0) {
        container.innerHTML = '<p class="text-[11px] text-slate-400 text-center py-4">まだ安否報告を受信していません。</p>';
        return;
    }
    container.innerHTML = "";
    statuses.forEach(s => {
        const info = safetyStatusLabel(s.status);
        const jstTime = s.created_at ? new Date(s.created_at).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" }) : "";
        const row = document.createElement("div");
        row.className = `flex justify-between items-center text-xs font-bold px-3.5 py-2.5 rounded-xl border ${info.cls}`;
        row.innerHTML = `<span>${info.emoji} ${escapeHtml(s.name || "")}さんは${escapeHtml(info.text)}！</span><span class="text-[10px] font-medium opacity-70">${escapeHtml(jstTime)}</span>`;
        container.appendChild(row);
    });
}

async function sendSafety(type) {
    if (!appState.accountId) {
        alert("ログインしてください。");
        return;
    }
    const msgEl = document.getElementById("safetyResultMsg");
    const result = await apiRequest("/api/safety", {
        method: "POST",
        body: JSON.stringify({ status: type })
    });

    if (!result.ok) {
        if (msgEl) {
            msgEl.innerText = `送信に失敗しました：${result.error}`;
            msgEl.className = "mt-4 text-xs text-center font-medium p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700";
            msgEl.classList.remove("hidden");
        }
        return;
    }

    if (msgEl) {
        const info = safetyStatusLabel(type);
        msgEl.innerText = `${appState.userName}さんは${info.text}！`;
        msgEl.className = "mt-4 text-xs text-center font-medium p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700";
        msgEl.classList.remove("hidden");
    }

    triggerPushNotification("安否確認送信", `${appState.userName}さんの安否情報を家族・友達へ共有しました。`);
    setTimeout(() => msgEl?.classList.add("hidden"), 5000);
    pollSafety();
}

/* =====================================================
   まちの安全情報（危ない場所 / 助けを求められる場所）
===================================================== */
const PLACE_CATEGORY_OPTIONS = {
    danger: [
        ["road", "道路・交差点"],
        ["flood", "水がたまりやすい・冠水"],
        ["river", "川・用水路"],
        ["cliff", "崖・斜面"],
        ["dark", "暗い道・見えにくい場所"],
        ["traffic", "車や自転車が多い場所"],
        ["damage", "壊れた物・倒れそうな物"],
        ["other", "その他の危ない場所"]
    ],
    help: [
        ["child110", "子ども110番の家"],
        ["police", "交番・警察署"],
        ["school", "学校・保育施設"],
        ["shelter", "避難所"],
        ["store", "コンビニ・お店"],
        ["public", "公民館・公共施設"],
        ["trusted", "家族が決めた頼れる場所"],
        ["other", "その他の助けを求められる場所"]
    ]
};

function normalizePlaceKind(post = {}) {
    const explicitKind = String(post.kind || "").trim().toLowerCase();
    if (explicitKind === "help" || explicitKind === "danger") {
        return explicitKind;
    }

    const explicitPlaceType = String(post.place_type || "").trim().toLowerCase();
    if (explicitPlaceType === "help" || explicitPlaceType === "danger") {
        return explicitPlaceType;
    }

    // ここから下は、種類を保存していなかった古い投稿だけの互換処理。
    // 新しい投稿では必ず kind / place_type が保存されるため、
    // カテゴリだけで危険と助けが入れ替わることはありません。
    const category = String(post.category || "").trim();
    const legacyHelpCategories = [
        "child110",
        "police",
        "school",
        "shelter",
        "store",
        "public",
        "trusted"
    ];

    return legacyHelpCategories.includes(category) ? "help" : "danger";
}

function getPlaceCategoryLabel(kind, category) {
    const list = PLACE_CATEGORY_OPTIONS[kind] || PLACE_CATEGORY_OPTIONS.danger;
    const found = list.find(item => item[0] === category);
    return found ? found[1] : (category || (kind === "help" ? "助けを求められる場所" : "危ない場所"));
}

function renderHazardCategoryOptions() {
    const select = document.getElementById("hazardCategory");
    if (!select) return;
    const options = PLACE_CATEGORY_OPTIONS[selectedPlaceKind] || [];
    select.innerHTML = "";
    options.forEach(([value, label]) => {
        const option = document.createElement("option");
        option.value = value;
        option.innerText = label;
        select.appendChild(option);
    });
}

function setPlaceKind(kind) {
    selectedPlaceKind = kind === "help" ? "help" : "danger";

    const kindInput = document.getElementById("hazardPlaceKindValue");
    if (kindInput) {
        kindInput.value = selectedPlaceKind;
    }

    const isHelp = selectedPlaceKind === "help";
    const dangerButton = document.getElementById("hazardKindDanger");
    const helpButton = document.getElementById("hazardKindHelp");
    const submitButton = document.getElementById("hazardSubmitBtn");

    if (dangerButton) {
        dangerButton.className = isHelp
            ? "bg-white text-orange-700 border border-orange-200 rounded-2xl py-3 text-xs font-black"
            : "bg-orange-500 text-white border border-orange-500 rounded-2xl py-3 text-xs font-black";
    }
    if (helpButton) {
        helpButton.className = isHelp
            ? "bg-emerald-500 text-white border border-emerald-500 rounded-2xl py-3 text-xs font-black"
            : "bg-white text-emerald-700 border border-emerald-200 rounded-2xl py-3 text-xs font-black";
    }

    const title = document.getElementById("hazardModalTitle");
    const subtitle = document.getElementById("hazardModalSubtitle");
    const placeNameLabel = document.getElementById("hazardPlaceNameLabel");
    const placeName = document.getElementById("hazardPlaceName");
    const textLabel = document.getElementById("hazardTextLabel");
    const textInput = document.getElementById("hazardTextInput");

    if (title) title.innerText = isHelp ? "🆘 助けを求められる場所を登録" : "⚠️ 危ない場所を登録";
    if (subtitle) subtitle.innerText = isHelp
        ? "困った時に頼れる場所を、家族・友達と共有します。"
        : "気をつけたい場所を、家族・友達と共有します。";
    if (placeNameLabel) placeNameLabel.innerText = isHelp ? "場所の名前（必須）" : "場所の名前（任意）";
    if (placeName) placeName.placeholder = isHelp ? "例：○○交番、△△こども110番の家" : "例：○○交差点";
    if (textLabel) textLabel.innerText = isHelp ? "どんな時に、どう頼れる？" : "どんなところが危ない？";
    if (textInput) textInput.placeholder = isHelp
        ? "例：困った時に店員さんへ助けを求められます"
        : "例：雨のあとに道路へ水がたまりやすいです";
    if (submitButton) {
        submitButton.innerText = "登録する";
        submitButton.className = isHelp
            ? "bg-emerald-500 hover:bg-emerald-600 text-white rounded-2xl py-3 font-black"
            : "bg-orange-500 hover:bg-orange-600 text-white rounded-2xl py-3 font-black";
    }

    renderHazardCategoryOptions();
}

function openHazardPostModal(kind) {
    const selectedKind = kind === "help" ? "help" : "danger";

    document.getElementById("hazardPostError")?.classList.add("hidden");

    const textInput = document.getElementById("hazardTextInput");
    const nameInput = document.getElementById("hazardPlaceName");

    if (textInput) textInput.value = "";
    if (nameInput) nameInput.value = "";

    clearHazardImage();
    updateHazardPhotoChoiceUI("none");

    // 助けの場所を押した場合は、ここで必ず help を保持する
    selectedPlaceKind = selectedKind;
    setPlaceKind(selectedKind);

    document.getElementById("hazardPostModal")?.classList.remove("hidden");
    updateHazardLocationMode();

    setTimeout(() => {
        document.getElementById("hazardPlaceName")?.focus();
    }, 100);
}

function closeHazardPostModal() {
    document.getElementById("hazardPostModal")?.classList.add("hidden");
}

function updateHazardPhotoChoiceUI(mode = "none") {
    const chooseBtn = document.getElementById("hazardPhotoChooseBtn");
    const noneBtn = document.getElementById("hazardPhotoNoneBtn");
    const status = document.getElementById("hazardPhotoChoiceStatus");

    const hasPhoto = mode === "photo";

    if (chooseBtn) {
        chooseBtn.className = hasPhoto
            ? "bg-orange-500 border border-orange-500 text-white rounded-xl py-2 text-xs font-bold"
            : "bg-orange-50 border border-orange-200 text-orange-800 rounded-xl py-2 text-xs font-bold";
    }

    if (noneBtn) {
        noneBtn.className = hasPhoto
            ? "bg-slate-100 border border-slate-200 text-slate-600 rounded-xl py-2 text-xs font-bold"
            : "bg-slate-700 border border-slate-700 text-white rounded-xl py-2 text-xs font-bold";
    }

    if (status) {
        status.innerText = hasPhoto
            ? "写真を使う設定です。"
            : "写真なしで登録します。";
    }
}

function triggerImageUpload() {
    document.getElementById("hazardImageInput")?.click();
}

function chooseNoHazardImage() {
    clearHazardImage();
    updateHazardPhotoChoiceUI("none");
}

function clearHazardImage() {
    selectedHazardImage = "";
    const input = document.getElementById("hazardImageInput");
    if (input) input.value = "";
    document.getElementById("hazardImagePreviewWrap")?.classList.add("hidden");
    updateHazardPhotoChoiceUI("none");
}

async function previewHazardImage(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
        selectedHazardImage = await compressImage(file);
        const preview = document.getElementById("hazardImagePreview");
        if (preview) preview.src = selectedHazardImage;
        document.getElementById("hazardImagePreviewWrap")?.classList.remove("hidden");
        updateHazardPhotoChoiceUI("photo");
    } catch (error) {
        selectedHazardImage = "";
        alert("画像の読み込みに失敗しました。");
    }
}

function updateHazardLocationMode() {
    const mode = document.getElementById("hazardLocationMode")?.value || "area";
    document.getElementById("hazardAreaSelectWrap")?.classList.toggle("hidden", mode !== "area");
    document.getElementById("hazardGpsInfo")?.classList.toggle("hidden", mode !== "gps");
}

function compressImage(file, maxWidth = 1280, quality = 0.78) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = event => {
            const img = new Image();
            img.onload = () => {
                let width = img.width;
                let height = img.height;
                if (width > maxWidth) {
                    height = Math.round(height * maxWidth / width);
                    width = maxWidth;
                }
                const canvas = document.createElement("canvas");
                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext("2d");
                if (!ctx) {
                    reject(new Error("画像処理を開始できませんでした。"));
                    return;
                }
                ctx.drawImage(img, 0, 0, width, height);
                resolve(canvas.toDataURL("image/jpeg", quality));
            };
            img.onerror = reject;
            img.src = event.target.result;
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

function getCurrentPosition() {
    return new Promise(resolve => {
        if (!navigator.geolocation) {
            resolve({ latitude: null, longitude: null, accuracy: null, fallback: true });
            return;
        }
        navigator.geolocation.getCurrentPosition(
            position => resolve({
                latitude: position.coords.latitude,
                longitude: position.coords.longitude,
                accuracy: position.coords.accuracy,
                fallback: false
            }),
            () => resolve({ latitude: null, longitude: null, accuracy: null, fallback: true }),
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
        );
    });
}

async function submitHazardPost() {
    const textValue = document.getElementById("hazardTextInput")?.value.trim() || "";
    const placeName = document.getElementById("hazardPlaceName")?.value.trim() || "";
    const mode = document.getElementById("hazardLocationMode")?.value || "area";
    const errorEl = document.getElementById("hazardPostError");
    const button = document.getElementById("hazardSubmitBtn");

    // 投稿ボタンを押した瞬間に種類を固定する。
    // 以降のGPS取得や通信中に、危険/助けが入れ替わらないようにする。
    const kindInputValue = document.getElementById("hazardPlaceKindValue")?.value;
    const postKind = kindInputValue === "help" ? "help" : "danger";
    const isHelp = postKind === "help";

    // 選ばれているカテゴリが、その種類のカテゴリかも確認する。
    const rawCategory = document.getElementById("hazardCategory")?.value || "other";
    const validCategoryValues = (PLACE_CATEGORY_OPTIONS[postKind] || []).map(item => item[0]);
    const category = validCategoryValues.includes(rawCategory) ? rawCategory : "other";

    if (isHelp && !placeName) {
        if (errorEl) {
            errorEl.innerText = "助けを求められる場所の名前を入力してください。";
            errorEl.classList.remove("hidden");
        }
        return;
    }

    if (!textValue) {
        if (errorEl) {
            errorEl.innerText = isHelp
                ? "どんな時に頼れる場所なのか入力してください。"
                : "どんなところが危ないのか入力してください。";
            errorEl.classList.remove("hidden");
        }
        return;
    }

    if (!navigator.onLine) {
        if (errorEl) {
            errorEl.innerText = "オフラインでは新しい場所を共有できません。保存済みの安心メモは確認できます。";
            errorEl.classList.remove("hidden");
        }
        return;
    }

    let latitude = null;
    let longitude = null;
    let accuracy = null;
    let locationLabel = "";

    if (mode === "area") {
        locationLabel = document.getElementById("hazardAreaSelect")?.value || "天草市内";
    } else if (mode === "gps") {
        if (button) {
            button.disabled = true;
            button.innerText = "位置取得中...";
        }
        const position = await getCurrentPosition();
        if (position.fallback || position.latitude == null || position.longitude == null) {
            if (button) {
                button.disabled = false;
                button.innerText = "登録する";
            }
            if (errorEl) {
                errorEl.innerText = "位置情報を取得できませんでした。大まかな地域を選ぶ方法も使えます。";
                errorEl.classList.remove("hidden");
            }
            return;
        }
        latitude = position.latitude;
        longitude = position.longitude;
        accuracy = position.accuracy;
        locationLabel = "GPSで指定した場所";
    }

    if (button) {
        button.disabled = true;
        button.innerText = "登録中...";
    }
    errorEl?.classList.add("hidden");

    const result = await apiRequest("/api/hazards", {
        method: "POST",
        body: JSON.stringify({
            kind: postKind,
            place_type: postKind,
            category,
            place_name: placeName,
            image: selectedHazardImage || "",
            text: textValue,
            latitude,
            longitude,
            accuracy,
            location_label: locationLabel
        })
    }, 60000);

    if (button) {
        button.disabled = false;
        button.innerText = "登録する";
    }

    if (!result.ok) {
        if (errorEl) {
            errorEl.innerText = result.error || "登録に失敗しました。";
            errorEl.classList.remove("hidden");
        }
        return;
    }

    const input = document.getElementById("hazardTextInput");
    const nameInput = document.getElementById("hazardPlaceName");
    if (input) input.value = "";
    if (nameInput) nameInput.value = "";
    clearHazardImage();
    closeHazardPostModal();
    triggerPushNotification(
        isHelp ? "助けを求められる場所を登録しました" : "危ない場所を登録しました",
        "家族・友達へ、まちの安全情報を共有しました。"
    );
    await pollHazard();
}

function makeOfflinePlaceRecord(post) {
    const lat = Number(post.latitude ?? post.lat);
    const lon = Number(post.longitude ?? post.lon);
    return {
        id: String(post.id || ""),
        kind: normalizePlaceKind(post),
        category: String(post.category || ""),
        place_name: String(post.place_name || ""),
        text: String(post.text || ""),
        author: String(post.author || ""),
        latitude: Number.isFinite(lat) ? lat : null,
        longitude: Number.isFinite(lon) ? lon : null,
        accuracy: Number.isFinite(Number(post.accuracy)) ? Number(post.accuracy) : null,
        location_label: String(post.location_label || ""),
        created_at: String(post.created_at || ""),
        cached_offline: true
    };
}

function cachePlacesForOffline(posts) {
    const nextPlaces = (Array.isArray(posts) ? posts : [])
        .slice(0, 100)
        .map(makeOfflinePlaceRecord);
    const before = JSON.stringify(offlineProfile.cachedPlaces || []);
    const after = JSON.stringify(nextPlaces);
    if (before === after) return;

    offlineProfile.cachedPlaces = nextPlaces;
    offlineProfile.placesCachedAt = new Date().toISOString();
    saveOfflineProfile(false);
}

async function pollHazard() {
    if (!appState.accountId) return;
    const syncEl = document.getElementById("hazardSyncStatus");
    const result = await apiRequest("/api/hazards", { method: "GET" }, 10000);
    setServerConnStatus(result.ok);

    if (!result.ok) {
        if (syncEl) {
            syncEl.innerText = result.offline
                ? `オフライン表示：${formatSavedTime(offlineProfile.placesCachedAt)}`
                : "同期エラー（保存情報があれば表示します）";
        }
        renderOfflineCachedHazardsInMainScreen();
        return;
    }

    if (syncEl) syncEl.innerText = `最終同期: ${getJSTNow().toLocaleTimeString("ja-JP")}`;
    appState.hazardPosts = result.data.posts || [];
    saveAppState();
    cachePlacesForOffline(appState.hazardPosts);
    renderHazardPosts(appState.hazardPosts);
}

function renderOfflineCachedHazardsInMainScreen() {
    const cached = Array.isArray(offlineProfile.cachedPlaces) ? offlineProfile.cachedPlaces : [];
    renderHazardPosts(cached);
    const syncEl = document.getElementById("hazardSyncStatus");
    if (syncEl && !navigator.onLine) {
        syncEl.innerText = cached.length
            ? `オフライン：${formatSavedTime(offlineProfile.placesCachedAt)}の保存情報`
            : "オフライン：保存された場所はありません";
    }
}

function setHazardFilter(filter) {
    hazardFilter = ["all", "danger", "help"].includes(filter) ? filter : "all";
    const definitions = [
        ["hazardFilterAll", "all", "slate"],
        ["hazardFilterDanger", "danger", "orange"],
        ["hazardFilterHelp", "help", "emerald"]
    ];

    definitions.forEach(([id, value, color]) => {
        const button = document.getElementById(id);
        if (!button) return;
        const active = hazardFilter === value;
        if (value === "all") {
            button.className = active
                ? "bg-slate-800 text-white border border-slate-800 rounded-xl py-2 text-xs font-black"
                : "bg-white text-slate-700 border border-slate-200 rounded-xl py-2 text-xs font-black";
        } else if (color === "orange") {
            button.className = active
                ? "bg-orange-500 text-white border border-orange-500 rounded-xl py-2 text-xs font-black"
                : "bg-white text-orange-700 border border-orange-200 rounded-xl py-2 text-xs font-black";
        } else {
            button.className = active
                ? "bg-emerald-500 text-white border border-emerald-500 rounded-xl py-2 text-xs font-black"
                : "bg-white text-emerald-700 border border-emerald-200 rounded-xl py-2 text-xs font-black";
        }
    });

    const source = navigator.onLine && appState.hazardPosts.length
        ? appState.hazardPosts
        : (offlineProfile.cachedPlaces || []);
    renderHazardPosts(source);
}

function renderHazardPosts(posts = appState.hazardPosts) {
    const container = document.getElementById("hazardPostList");
    if (!container) return;

    const normalized = (Array.isArray(posts) ? posts : []).map(post => {
        const normalizedKind = normalizePlaceKind(post);
        return {
            ...post,
            kind: normalizedKind,
            place_type: normalizedKind
        };
    });
    const dangerCount = normalized.filter(post => post.kind === "danger").length;
    const helpCount = normalized.filter(post => post.kind === "help").length;
    const allCount = normalized.length;

    const allCountEl = document.getElementById("hazardCountAll");
    const dangerCountEl = document.getElementById("hazardCountDanger");
    const helpCountEl = document.getElementById("hazardCountHelp");
    if (allCountEl) allCountEl.innerText = String(allCount);
    if (dangerCountEl) dangerCountEl.innerText = String(dangerCount);
    if (helpCountEl) helpCountEl.innerText = String(helpCount);

    const filtered = hazardFilter === "all"
        ? normalized
        : normalized.filter(post => post.kind === hazardFilter);

    if (filtered.length === 0) {
        const message = hazardFilter === "help"
            ? "まだ助けを求められる場所は登録されていません。<br>子ども110番の家、交番、学校などを家族と確認してみよう。"
            : hazardFilter === "danger"
                ? "まだ危ない場所は登録されていません。<br>気になる場所を家族と確認してみよう。"
                : "まだまちの安全情報はありません。<br>危ない場所や助けを求められる場所を登録できます。";
        container.innerHTML = `<div class="text-center py-12 text-xs text-slate-400 bg-white/60 rounded-2xl border border-dashed border-slate-300">${message}</div>`;
        return;
    }

    container.innerHTML = "";
    filtered.forEach(post => {
        const isHelp = post.kind === "help";
        const lat = Number(post.latitude ?? post.lat);
        const lon = Number(post.longitude ?? post.lon);
        const hasLocation = Number.isFinite(lat) && Number.isFinite(lon);
        const mapUrl = hasLocation ? `https://www.google.com/maps?q=${encodeURIComponent(`${lat},${lon}`)}` : "";
        const jstTime = post.created_at
            ? new Date(post.created_at).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" })
            : "";
        const div = document.createElement("div");
        div.className = isHelp
            ? "bg-white/95 border border-emerald-200 rounded-2xl p-4 shadow-sm space-y-3"
            : "bg-white/95 border border-orange-200 rounded-2xl p-4 shadow-sm space-y-3";

        const safeImage = String(post.image || "").startsWith("data:image/") ? post.image : "";
        const imageHtml = safeImage
            ? `<img src="${escapeHtml(safeImage)}" class="w-full h-40 object-cover rounded-xl" alt="登録された場所の写真" loading="lazy">`
            : `<div class="text-[10px] text-slate-400 bg-slate-50 rounded-xl p-3">📷 写真なしの登録</div>`;

        const locationLabel = String(post.location_label || "").trim();
        const mapHtml = mapUrl
            ? `<a href="${mapUrl}" target="_blank" rel="noopener noreferrer" class="text-xs text-sky-600 font-extrabold underline block">📍 登録場所をマップで確認</a>
               <div class="text-[10px] text-slate-400">${escapeHtml(locationLabel || "GPSで指定した場所")}</div>
               ${Number.isFinite(Number(post.accuracy)) ? `<div class="text-[10px] text-slate-400">GPS精度 約${Math.round(Number(post.accuracy))}m</div>` : ""}`
            : locationLabel
                ? `<div class="text-xs text-sky-700 font-bold">📍 ${escapeHtml(locationLabel)}</div>`
                : `<div class="text-[10px] text-slate-400">📍 場所指定なし</div>`;

        const categoryLabel = getPlaceCategoryLabel(post.kind, String(post.category || ""));
        const placeTitle = String(post.place_name || "").trim() || categoryLabel;
        const cachedNotice = post.cached_offline
            ? `<div class="text-[10px] text-cyan-700 bg-cyan-50 border border-cyan-100 rounded-xl p-2">📴 この端末に保存した情報を表示しています。</div>`
            : "";

        div.innerHTML = `
            <div class="flex justify-between items-start gap-3">
                <div>
                    <span class="inline-block text-[10px] font-black rounded-full px-3 py-1 ${isHelp ? "bg-emerald-100 text-emerald-800" : "bg-orange-100 text-orange-800"}">${isHelp ? "🆘 助けを求められる場所" : "⚠️ 危ない場所"}</span>
                    <h3 class="font-black text-slate-800 mt-2">${escapeHtml(placeTitle)}</h3>
                    <p class="text-[10px] text-slate-400 mt-1">${escapeHtml(categoryLabel)}</p>
                </div>
                <div class="text-right text-[10px] text-slate-400">
                    <div>👤 ${escapeHtml(post.author || "")}</div>
                    <div class="mt-1">${escapeHtml(jstTime)}</div>
                </div>
            </div>
            ${imageHtml}
            <p class="text-xs text-slate-800 font-semibold leading-relaxed">${escapeHtml(post.text || "")}</p>
            ${mapHtml}
            ${cachedNotice}
            <div class="text-[10px] text-slate-400 border-t border-slate-100 pt-2">登録した場所の情報です。投稿者の現在位置を示すものではありません。</div>
        `;
        container.appendChild(div);
    });
}

/* =====================================================
   防災・天気クイズ
===================================================== */
async function openQuizScreen() {
    switchScreen("quiz");
}

function updateQuizModeButtons() {
    const definitions = [
        ["quizModeScenario", "scenario"],
        ["quizModeKnowledge", "knowledge"],
        ["quizModeMixed", "mixed"]
    ];
    definitions.forEach(([id, mode]) => {
        const button = document.getElementById(id);
        if (!button) return;
        const active = quizMode === mode;
        button.className = active
            ? "bg-amber-500 text-white border border-amber-500 rounded-xl py-2 text-[11px] font-black"
            : "bg-white text-slate-600 border border-slate-200 rounded-xl py-2 text-[11px] font-black";
    });

    const description = document.getElementById("quizModeDescription");
    if (description) {
        description.innerText = quizMode === "scenario"
            ? "場所や天気を見て、「今ならどうする？」を考えます。"
            : quizMode === "knowledge"
                ? "天気や防災について知っていることを確かめます。"
                : "考える問題と知識問題の両方にチャレンジします。";
    }
}

function shuffleQuizItems(items) {
    const copied = [...items];
    for (let i = copied.length - 1; i > 0; i -= 1) {
        const j = Math.floor(Math.random() * (i + 1));
        [copied[i], copied[j]] = [copied[j], copied[i]];
    }
    return copied;
}

function applyQuizMode() {
    const scenarioItems = allQuizQuestions.filter(item => item.type === "scenario");
    const knowledgeItems = allQuizQuestions.filter(item => item.type !== "scenario");

    if (quizMode === "scenario") {
        quizQuestions = scenarioItems.length ? shuffleQuizItems(scenarioItems) : shuffleQuizItems(allQuizQuestions);
    } else if (quizMode === "knowledge") {
        quizQuestions = knowledgeItems.length ? shuffleQuizItems(knowledgeItems) : shuffleQuizItems(allQuizQuestions);
    } else {
        quizQuestions = shuffleQuizItems(allQuizQuestions);
    }

    quizIndex = 0;
    quizAnswered = false;
    quizScore = { answered: 0, correct: 0 };
    updateQuizModeButtons();
    updateQuizScore();
    renderQuizQuestion();
}

function setQuizMode(mode) {
    quizMode = ["scenario", "knowledge", "mixed"].includes(mode) ? mode : "scenario";
    updateQuizModeButtons();
    if (allQuizQuestions.length > 0) {
        applyQuizMode();
    }
}

async function loadQuizIfNeeded() {
    updateQuizModeButtons();
    if (allQuizQuestions.length > 0) {
        if (!quizQuestions.length) applyQuizMode();
        else renderQuizQuestion();
        return;
    }

    const loading = document.getElementById("quizLoading");
    const area = document.getElementById("quizArea");
    if (loading) {
        loading.innerText = "問題を読み込んでいます...";
        loading.classList.remove("hidden");
    }

    try {
        const response = await fetch("/quiz.json", { cache: "no-cache" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const parsed = await response.json();
        allQuizQuestions = Array.isArray(parsed)
            ? parsed.filter(item => item && item.q && item.a)
            : [];
        if (allQuizQuestions.length === 0) throw new Error("問題がありません");
        if (loading) loading.classList.add("hidden");
        if (area) area.classList.remove("hidden");
        applyQuizMode();
    } catch (error) {
        console.error("クイズ読み込みエラー:", error);
        if (loading) {
            loading.innerText = "クイズを読み込めませんでした。オフライン保存がまだ終わっていない場合は、一度通信できる時に開いてください。";
        }
    }
}

function parseQuizQuestion(item) {
    const lines = String(item.q || "").split("\n").map(line => line.trim()).filter(Boolean);
    const questionLines = [];
    const choices = [];
    for (const line of lines) {
        const match = line.match(/^(\d+)\.\s*(.+)$/);
        if (match) choices.push({ number: match[1], text: match[2] });
        else questionLines.push(line.replace(/^問題：/, ""));
    }
    const answerMatch = String(item.a || "").match(/正解：\s*(\d+)\./);
    return {
        question: questionLines.join("\n"),
        choices,
        correctNumber: answerMatch ? answerMatch[1] : "",
        explanation: String(item.a || ""),
        type: item.type === "scenario" ? "scenario" : "knowledge",
        topic: String(item.topic || (item.type === "scenario" ? "状況を考える" : "知識を確かめる"))
    };
}

function updateQuizScore() {
    const score = document.getElementById("quizScore");
    if (!score) return;
    score.innerText = quizScore.answered > 0
        ? `${quizScore.answered}問チャレンジ・${quizScore.correct}回よく考えられた`
        : "0問チャレンジ";
}

function renderQuizQuestion() {
    if (!quizQuestions.length) return;
    quizAnswered = false;
    const item = quizQuestions[quizIndex % quizQuestions.length];
    const parsed = parseQuizQuestion(item);

    const progress = document.getElementById("quizProgress");
    const question = document.getElementById("quizQuestion");
    const topic = document.getElementById("quizTopic");
    if (progress) progress.innerText = `${quizIndex + 1} / ${quizQuestions.length}`;
    if (question) question.innerText = parsed.question;
    if (topic) topic.innerText = parsed.type === "scenario" ? `💭 ${parsed.topic}` : `📘 ${parsed.topic}`;

    const choicesEl = document.getElementById("quizChoices");
    if (!choicesEl) return;
    choicesEl.innerHTML = "";

    parsed.choices.forEach(choice => {
        const button = document.createElement("button");
        button.className = "w-full text-left bg-slate-50 hover:bg-amber-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold";
        button.innerText = `${choice.number}. ${choice.text}`;
        button.dataset.choiceNumber = choice.number;
        button.onclick = () => answerQuiz(choice.number, parsed.correctNumber, parsed.explanation, button, parsed.type);
        choicesEl.appendChild(button);
    });

    if (parsed.choices.length === 0) {
        choicesEl.innerHTML = '<div class="bg-rose-50 border border-rose-200 text-rose-700 rounded-2xl p-4 text-xs">この問題の選択肢を読み取れませんでした。</div>';
    }

    const answerBox = document.getElementById("quizAnswerBox");
    answerBox?.classList.add("hidden");
    document.getElementById("quizNextBtn")?.classList.add("hidden");
}

function answerQuiz(selected, correct, explanation, clickedButton, type = "knowledge") {
    if (quizAnswered) return;
    quizAnswered = true;
    const isCorrect = String(selected) === String(correct);
    quizScore.answered += 1;
    if (isCorrect) quizScore.correct += 1;
    updateQuizScore();

    const answerBox = document.getElementById("quizAnswerBox");
    const encouragement = isCorrect
        ? (type === "scenario"
            ? "🌟 いい考え方だね。状況を見て、安全につながる選び方ができたよ。"
            : "🎉 よく分かったね！")
        : (type === "scenario"
            ? "💡 その選び方を考えた理由も大事だよ。ここでは、もう一つ安全な見方を確かめよう。"
            : "💡 おしい！理由を知れば、次は自信を持って選べるよ。");

    if (answerBox) {
        answerBox.innerText = `${encouragement}\n\n${explanation}`;
        answerBox.className = `mt-5 rounded-2xl p-4 text-sm whitespace-pre-line leading-relaxed border ${isCorrect ? "bg-emerald-50 border-emerald-200 text-emerald-900" : "bg-amber-50 border-amber-200 text-amber-900"}`;
    }

    document.querySelectorAll("#quizChoices button").forEach(button => {
        button.disabled = true;
        if (String(button.dataset.choiceNumber) === String(correct)) {
            button.className = "w-full text-left bg-emerald-50 border-2 border-emerald-400 rounded-2xl px-4 py-3 text-sm font-bold text-emerald-900";
        }
    });
    if (clickedButton && !isCorrect) {
        clickedButton.className = "w-full text-left bg-amber-50 border-2 border-amber-300 rounded-2xl px-4 py-3 text-sm font-bold text-amber-900";
    }
    document.getElementById("quizNextBtn")?.classList.remove("hidden");
}

function nextQuizQuestion() {
    if (!quizQuestions.length) return;
    quizIndex = (quizIndex + 1) % quizQuestions.length;
    renderQuizQuestion();
}

/* =====================================================
   緊急モード
===================================================== */
function enterEmergencyMode() {
    emergencyModeActive = true;
    emergencyModeExiting = false;
    document.body.classList.add("emergency-active");
    switchScreen("emergency");
}

function exitEmergencyMode() {
    emergencyModeExiting = true;
    emergencyModeActive = false;
    document.body.classList.remove("emergency-active");
    switchScreen(appState.accountId ? "dashboard" : "login");
    emergencyModeExiting = false;
}

function renderEmergencyMode() {
    loadOfflineProfile();

    const networkBadge = document.getElementById("emergencyNetworkBadge");
    if (networkBadge) {
        networkBadge.innerText = navigator.onLine
            ? "🟢 オンライン：安否を送れます"
            : "⚫ オフライン：保存情報を使います";
        networkBadge.className = navigator.onLine
            ? "bg-emerald-500/30 border border-white/30 rounded-full px-3 py-1 text-[11px] font-black"
            : "bg-slate-900/30 border border-white/30 rounded-full px-3 py-1 text-[11px] font-black";
    }

    const familyRuleEl = document.getElementById("emergencyFamilyRuleSummary");
    if (familyRuleEl) {
        const rules = Array.isArray(offlineProfile.familyRules) ? offlineProfile.familyRules : [];
        const confirmed = rules.filter(rule => rule.confirmed);
        const shown = (confirmed.length ? confirmed : rules).slice(0, 3);

        if (!shown.length) {
            familyRuleEl.innerHTML = '<div class="bg-amber-50 border border-amber-200 rounded-2xl p-3 text-xs text-amber-900"><b>まだ家族ルールが保存されていません。</b><br>安全な場所にいて、学校・施設・自治体などその場の案内を優先しよう。</div>';
        } else {
            familyRuleEl.innerHTML = shown.map(rule => {
                const title = escapeHtml(rule.scenarioTitle || "家族ルール");
                const status = rule.confirmed ? "家族と確認済み" : "家族と相談中";
                return `<div class="mt-2 first:mt-0 bg-violet-50 border border-violet-200 rounded-2xl p-3"><div class="flex items-center justify-between gap-2"><b class="text-xs text-violet-900">${title}</b><span class="text-[10px] font-black text-violet-600">${status}</span></div></div>`;
            }).join("");
        }
    }

    const meetingEl = document.getElementById("emergencyMeetingSummary");
    if (meetingEl) {
        const plan = offlineProfile.emergencyPlan || {};
        const rows = [];
        if (plan.primaryMeeting) rows.push(`<div class="bg-cyan-50 border border-cyan-200 rounded-2xl p-3"><p class="text-[10px] text-cyan-600 font-black">第一集合場所</p><p class="text-sm font-black text-slate-800 mt-1">📍 ${escapeHtml(plan.primaryMeeting)}</p></div>`);
        if (plan.secondaryMeeting) rows.push(`<div class="bg-cyan-50 border border-cyan-200 rounded-2xl p-3"><p class="text-[10px] text-cyan-600 font-black">第二集合場所</p><p class="text-sm font-black text-slate-800 mt-1">📍 ${escapeHtml(plan.secondaryMeeting)}</p></div>`);
        if (plan.noContactRule) rows.push(`<div class="bg-slate-50 border border-slate-200 rounded-2xl p-3"><p class="text-[10px] text-slate-500 font-black">連絡できない時のルール</p><p class="text-xs font-bold text-slate-700 mt-1 leading-relaxed">${escapeHtml(plan.noContactRule)}</p></div>`);
        if (plan.contactName1 || plan.contactPhone1) rows.push(`<div class="bg-white border border-slate-200 rounded-2xl p-3"><p class="text-[10px] text-slate-500 font-black">連絡先</p><p class="text-xs font-bold text-slate-700 mt-1">☎️ ${escapeHtml(plan.contactName1 || "連絡先1")} ${escapeHtml(plan.contactPhone1 || "")}</p></div>`);

        meetingEl.innerHTML = rows.length
            ? rows.join("")
            : '<div class="bg-amber-50 border border-amber-200 rounded-2xl p-3 text-xs text-amber-900"><b>集合場所・連絡先がまだ保存されていません。</b><br>今いる場所の安全を優先して、近くの信頼できる大人や施設の案内を聞こう。</div>';
    }
}

async function sendEmergencySafety(type) {
    const resultEl = document.getElementById("emergencySafetyResult");

    if (!navigator.onLine) {
        if (resultEl) {
            resultEl.innerText = "オフラインのため安否は送信できません。保存した家族ルール・集合場所を確認してね。";
            resultEl.className = "mt-3 rounded-2xl border border-amber-200 bg-amber-50 text-amber-900 p-3 text-xs font-bold";
            resultEl.classList.remove("hidden");
        }
        return;
    }

    if (!appState.accountId) {
        if (resultEl) {
            resultEl.innerText = "安否を送るにはログインが必要です。";
            resultEl.className = "mt-3 rounded-2xl border border-rose-200 bg-rose-50 text-rose-800 p-3 text-xs font-bold";
            resultEl.classList.remove("hidden");
        }
        return;
    }

    const result = await apiRequest("/api/safety", {
        method: "POST",
        body: JSON.stringify({ status: type })
    });

    if (!result.ok) {
        if (resultEl) {
            resultEl.innerText = `送信に失敗しました：${result.error}`;
            resultEl.className = "mt-3 rounded-2xl border border-rose-200 bg-rose-50 text-rose-800 p-3 text-xs font-bold";
            resultEl.classList.remove("hidden");
        }
        return;
    }

    const info = safetyStatusLabel(type);
    if (resultEl) {
        resultEl.innerText = `${info.emoji}「${info.text}」を家族・友達へ送りました。`;
        resultEl.className = "mt-3 rounded-2xl border border-emerald-200 bg-emerald-50 text-emerald-800 p-3 text-xs font-bold";
        resultEl.classList.remove("hidden");
    }
    triggerPushNotification("安否確認送信", `${appState.userName}さんの安否情報を家族・友達へ共有しました。`);
    pollSafety();
}

/* =====================================================
   ダッシュボード：明日のそなえ
===================================================== */
function getWisdomBankEntries() {
    const own = readSavedArray(accountStorageKey("wisdom"));
    const legacy = readSavedArray("otenkiWisdomBank").map((e,i)=>({...e,id:`legacy-${i}`,legacy:true}));
    return [...own,...legacy];
}

function updateWisdomBankCount() {
    const el = document.getElementById("wisdomBankCount");
    if (el) { try { el.innerText = String(getWisdomBankEntries().length); } catch { el.innerText = "読込エラー"; } }
}

function saveWisdomBankEntry(entry) {
    try {
        const key = accountStorageKey("wisdom"), list = readSavedArray(key);
        const record = {...entry,id:entry.id || newLocalId(),ownerId:appState.accountId,
            savedAt:entry.savedAt || new Date().toISOString()};
        const found = list.findIndex(e=>e.id===record.id);
        if (found>=0) list[found]=record; else list.push(record);
        if (!storageWrite(key,JSON.stringify(list))) throw new Error("StorageUnavailable");
        updateWisdomBankCount();
        return true;
    } catch {
        planMessage("保存できませんでした。ブラウザの保存容量・保存の許可を確認してください。入力内容はそのまま残しています。",false);
        return false;
    }
}


const TOMORROW_PLAN_DRAFT_KEY = "otenkiTomorrowPlanDraft";
let tomorrowPlanState = { step:1, weather:null, items:[], leaveChoice:"", leaveNote:"", cautions:[], cautionNote:"", consultChoice:"", familyDecision:"" };
const TOMORROW_ITEM_LIBRARY = [
 {id:"umbrella",icon:"☂️",label:"傘"},{id:"raincoat",icon:"🧥",label:"レインコート"},{id:"towel",icon:"🟦",label:"タオル"},{id:"water",icon:"🥤",label:"水筒"},{id:"hat",icon:"🧢",label:"帽子"},{id:"light",icon:"🔦",label:"ライト"},{id:"warm",icon:"🧣",label:"防寒具"},{id:"none",icon:"👌",label:"特になし"},{id:"unknown",icon:"❓",label:"まだ分からない"}
];
const TOMORROW_TIME_OPTIONS = [["usual","いつも通り","学校や家族の決まりどおり"],["early5","5分くらい早く","少し余裕を持つ"],["early10","10分くらい早く","雨や風が強い時に余裕を持つ"],["family","家族と相談して決める","送迎や予定変更も相談"],["unknown","まだ分からない","今は決めず相談する"]];
function resetTomorrowPlanState() {
    tomorrowPlanState = {id:newLocalId(),step:1,weather:null,items:[],leaveChoice:"",leaveNote:"",
        cautions:[],cautionNote:"",consultChoice:"",familyDecision:"",saved:false,forecastDate:tomorrowDate()};
}
function saveTomorrowPlanDraft(capture = true) {
    if (tomorrowPlanState.saved) return true;
    if (capture !== false) {
        [["tomorrowPlanTimeNote","leaveNote"],["tomorrowPlanCautionNote","cautionNote"],["tomorrowPlanFamilyDecision","familyDecision"]].forEach(([id,key])=>{
            const el=document.getElementById(id);
            if (el) tomorrowPlanState[key]=el.value.trim();
        });
    }
    const ok=storageWrite(accountStorageKey("draft"),JSON.stringify({...tomorrowPlanState,ownerId:appState.accountId}));
    const status=document.getElementById("tomorrowDraftStatus");
    if(status)status.textContent=ok?"下書きをこの端末に保存しました":"下書きを保存できません。この画面を閉じずに保存設定を確認してください。";
    return ok;
}
function loadTomorrowPlanDraft() {
    const raw = storageRead(accountStorageKey("draft"));
    if (!raw) return;
    try {
        const p=JSON.parse(raw);
        if (!p || typeof p!=="object" || (p.ownerId && p.ownerId!==appState.accountId)) return;
        tomorrowPlanState={...tomorrowPlanState,...p,
            step:Math.min(5,Math.max(1,Number(p.step)||1)),
            items:Array.isArray(p.items)?p.items:[],cautions:Array.isArray(p.cautions)?p.cautions:[]};
        if (p.forecastDate !== tomorrowDate()) {
            tomorrowPlanState.step=1;
            tomorrowPlanState.weather=null;
            tomorrowPlanState.consultChoice="pending";
            tomorrowPlanState.saved=false;
            tomorrowPlanState.forecastDate=tomorrowDate();
        }
    } catch { planMessage("下書きを読み込めませんでした。元の保存データは消していません。",false); }
}
function openTomorrowPlan() {
    resetTomorrowPlanState(); loadTomorrowPlanDraft();
    document.getElementById("tomorrowPlanSaveMessage")?.classList.add("hidden");
    switchScreen("tomorrow-plan");
    void fetchTomorrowForPlan();
}
function renderTomorrowPlan() {
    const step=+tomorrowPlanState.step||1;
    document.querySelectorAll("[data-tomorrow-step]").forEach(el=>el.classList.toggle("hidden",+el.dataset.tomorrowStep!==step));
    document.querySelectorAll("[data-tomorrow-step-dot]").forEach(el=>el.className=`h-2 rounded-full ${+el.dataset.tomorrowStepDot<=step?"bg-white":"bg-white/30"}`);
    [["tomorrowPlanTimeNote","leaveNote"],["tomorrowPlanCautionNote","cautionNote"],["tomorrowPlanFamilyDecision","familyDecision"]].forEach(([id,key])=>{
        const el=document.getElementById(id); if(el)el.value=tomorrowPlanState[key]||"";
    });
    renderTomorrowWeatherCard(); renderTomorrowItemChoices(); renderTomorrowTimeChoices();
    renderTomorrowCautionChoices(); renderTomorrowConsultChoices(); renderTomorrowPlanSummary();
}
async function fetchTomorrowForPlan() {
    const epoch=authEpoch, draftId=tomorrowPlanState.id;
    const forecast=await getTomorrowForecast();
    if (epoch!==authEpoch || draftId!==tomorrowPlanState.id) return;
    tomorrowPlanState.weather=forecast;
    renderTomorrowWeatherCard(); renderTomorrowItemChoices(); renderTomorrowCautionChoices();
    saveTomorrowPlanDraft(false);
}
function tomorrowWeatherFlags() {
    const w=tomorrowPlanState.weather||{},d=String(w.description||"");
    const p=numberOrNaN(w.pop),v=numberOrNaN(w.wind??w.windSpeed),t=numberOrNaN(w.tempMax??w.temperature);
    return {rain:/雨|降水/.test(d)||(Number.isFinite(p)&&p>=.4),thunder:/雷/.test(d),
        snow:/雪/.test(d),windy:Number.isFinite(v)&&v>=7,hot:Number.isFinite(t)&&t>=30,veryHot:Number.isFinite(t)&&t>=33};
}
function renderTomorrowWeatherCard() {
    const w=tomorrowPlanState.weather, q=id=>document.getElementById(id);
    const show=(id,text)=>{if(q(id))q(id).textContent=text;};
    if(!w) {
        show("tomorrowPlanWeather","明日の予報はまだ確認できていません");
        show("tomorrowPlanTemp","--℃ / --℃");show("tomorrowPlanRain","降水確率 --%");show("tomorrowPlanWind","風 --m/s");
        show("tomorrowPlanWeatherAdvice","通信できる時に更新してください。今の天気を明日の予報の代わりには使いません。");return;
    }
    show("tomorrowPlanWeather",w.description);
    const fmt=(n,round=true)=>Number.isFinite(numberOrNaN(n))?(round?Math.round(n):Number(n).toFixed(1)):"--";
    show("tomorrowPlanTemp",`${fmt(w.tempMax)}℃ / ${fmt(w.tempMin)}℃`);
    show("tomorrowPlanRain",`予報時間帯の最大降水確率 ${Number.isFinite(numberOrNaN(w.pop))?Math.round(w.pop*100):"--"}%`);
    show("tomorrowPlanWind",`風 ${fmt(w.wind,false)}m/s`);
    show("tomorrowPlanWeatherAdvice",`${w.forecastDate} の予報・${w.cached?"保存済み":"取得"} ${formatSavedTime(w.fetchedAt)}。予報は変わるので、出かける前にも家族と確認しよう。`);
}
function recommendedTomorrowItems(){const f=tomorrowWeatherFlags(),x=[];if(f.rain)x.push("umbrella","towel");if(f.rain&&f.windy)x.push("raincoat");if(f.hot)x.push("water","hat");if(f.snow)x.push("warm");return[...new Set(x)]}
function toggleTomorrowItem(id) {
    let set=new Set(tomorrowPlanState.items);
    if(["none","unknown"].includes(id))set=new Set(set.has(id)?[]:[id]);
    else {set.delete("none");set.delete("unknown");set.has(id)?set.delete(id):set.add(id);}
    tomorrowPlanState.items=[...set];saveTomorrowPlanDraft();renderTomorrowItemChoices();
}
function renderTomorrowItemChoices(){const c=document.getElementById("tomorrowPlanItemChoices");if(!c)return;const s=new Set(tomorrowPlanState.items||[]),r=new Set(recommendedTomorrowItems());c.innerHTML=TOMORROW_ITEM_LIBRARY.map(i=>`<button onclick="toggleTomorrowItem('${i.id}')" class="relative rounded-2xl border p-4 text-left ${s.has(i.id)?"border-sky-500 bg-sky-50 ring-2 ring-sky-100":"border-slate-200 bg-white"}">${r.has(i.id)?'<span class="absolute right-2 top-2 text-[9px] bg-amber-100 text-amber-800 rounded-full px-2 py-0.5 font-black">天気から候補</span>':""}<div class="text-2xl">${i.id==="towel"?PREPARATION_ITEMS.towel.iconHtml:i.icon}</div><p class="text-sm font-black mt-2">${i.label}</p></button>`).join("");}
function chooseTomorrowTime(id){tomorrowPlanState.leaveChoice=id;saveTomorrowPlanDraft();renderTomorrowTimeChoices();}
function renderTomorrowTimeChoices(){const c=document.getElementById("tomorrowPlanTimeChoices");if(!c)return;c.innerHTML=TOMORROW_TIME_OPTIONS.map(([id,l,n])=>`<button onclick="chooseTomorrowTime('${id}')" class="rounded-2xl border p-4 text-left ${tomorrowPlanState.leaveChoice===id?"border-sky-500 bg-sky-50 ring-2 ring-sky-100":"border-slate-200 bg-white"}"><p class="font-black">${escapeHtml(l)}</p><p class="text-[11px] text-slate-500 mt-1">${escapeHtml(n)}</p></button>`).join("");}
function cautionLibraryForTomorrow(){const f=tomorrowWeatherFlags(),x=[["unknown","❓","まだ分からないので家族と相談する"],["route","👀","いつもの通学路の注意点を家族と確認"],["traffic","🚗","車・自転車・見通しに気をつける"],["adult","🧑","困ったら家族・先生・頼れる大人に相談"]];if(f.rain)x.unshift(["wet","☔","すべりやすい所・水たまりに注意"]);if(f.windy)x.unshift(["wind","💨","看板・木の枝・飛ばされる物から離れる"]);if(f.thunder)x.unshift(["thunder","⛈️","雷が近づいたら丈夫な建物へ移る"]);if(f.hot)x.unshift(["heat","🥵","水分をとって、無理せず休む"]);return x;}
function toggleTomorrowCaution(id){const s=new Set(tomorrowPlanState.cautions||[]);s.has(id)?s.delete(id):s.add(id);tomorrowPlanState.cautions=[...s];saveTomorrowPlanDraft();renderTomorrowCautionChoices();}
function renderTomorrowCautionChoices(){const c=document.getElementById("tomorrowPlanCautionChoices");if(!c)return;const s=new Set(tomorrowPlanState.cautions||[]);c.innerHTML=cautionLibraryForTomorrow().map(([id,ic,l])=>`<button onclick="toggleTomorrowCaution('${id}')" class="rounded-2xl border p-4 text-left flex gap-3 items-center ${s.has(id)?"border-sky-500 bg-sky-50 ring-2 ring-sky-100":"border-slate-200 bg-white"}"><span class="text-2xl">${ic}</span><span class="text-sm font-black">${escapeHtml(l)}</span></button>`).join("");}
function chooseTomorrowConsult(id){tomorrowPlanState.consultChoice=id;saveTomorrowPlanDraft();renderTomorrowConsultChoices();renderTomorrowPlanSummary();}
function renderTomorrowConsultChoices(){const c=document.getElementById("tomorrowPlanConsultChoices");if(!c)return;const o=[["decided","✅ 自分で考えて、家族とも確認できた"],["consult","👨‍👩‍👧‍👦 家族と相談中（下書き保存）"],["pending","❓ まだ決めない・相談待ち"]];c.innerHTML=o.map(([id,l])=>`<button onclick="chooseTomorrowConsult('${id}')" class="rounded-2xl border p-4 text-left font-black ${tomorrowPlanState.consultChoice===id?"border-violet-500 bg-violet-50 ring-2 ring-violet-100":"border-slate-200 bg-white"}">${l}</button>`).join("");document.getElementById("tomorrowPlanConsultBox")?.classList.toggle("hidden",!["consult","decided"].includes(tomorrowPlanState.consultChoice));}
function tomorrowItemLabels(ids) {
    const map=Object.fromEntries(TOMORROW_ITEM_LIBRARY.map(x=>[x.id,x.label]));
    return(ids||[]).map(id=>map[id]||PREPARATION_ITEMS[id]?.label||id);
}
function tomorrowTimeLabel(id){const m=TOMORROW_TIME_OPTIONS.find(x=>x[0]===id);return m?m[1]:"まだ決めていない"}
function tomorrowCautionLabels(ids) {
    const names={route:"いつもの通学路の注意点を家族と確認",traffic:"車・自転車・見通しに注意",
        adult:"困ったら家族・先生・頼れる大人に相談",wet:"すべりやすい所・水たまりに注意",
        wind:"看板・木の枝・飛ばされる物から離れる",thunder:"雷が近づいたら丈夫な建物へ",
        heat:"水分をとり、無理せず休む",unknown:"まだ分からないので相談する"};
    return (ids||[]).map(id=>names[id]||id);
}
function renderTomorrowPlanSummary() {
    const el=document.getElementById("tomorrowPlanSummary");if(!el)return;
    const p=tomorrowPlanState;
    el.innerHTML=`<p class="text-xs font-black text-slate-500">明日のそなえメモ</p>
        <div class="mt-3 space-y-2 text-sm">
        <p><b>天気：</b>${escapeHtml(p.weather?.description||"未取得")}</p>
        <p><b>持ち物：</b>${escapeHtml(tomorrowItemLabels(p.items).join("・")||"未選択")}</p>
        <p><b>出る時間：</b>${escapeHtml(p.leaveNote||tomorrowTimeLabel(p.leaveChoice))}</p>
        <p><b>気をつけること：</b>${escapeHtml([...tomorrowCautionLabels(p.cautions),p.cautionNote].filter(Boolean).join("・")||"未選択")}</p>
        <p><b>家族と決めたこと：</b>${escapeHtml(p.familyDecision||"まだ相談・確認していない")}</p></div>`;
}
function goTomorrowPlanStep(step) {
    saveTomorrowPlanDraft();
    tomorrowPlanState.step=Math.max(1,Math.min(5,Number(step)||1));
    saveTomorrowPlanDraft(false);renderTomorrowPlan();
    window.scrollTo({top:0,behavior:"auto"});
}
function saveTomorrowPlan() {
    if(tomorrowPlanState.saved) {planMessage("この知恵は保存済みです。知恵貯金で見返せます。",true);return;}
    const draftOK=saveTomorrowPlanDraft();
    const p=tomorrowPlanState;
    if(!draftOK) {planMessage("保存できませんでした。入力内容は消していません。",false);return;}
    if(p.consultChoice!=="decided") {
        planMessage("相談待ちの下書きとして保存しました。次に「明日のそなえ」を開くと続きを確認できます。決まったら「家族とも確認できた」を選んでください。",false);
        return;
    }
    if(!p.familyDecision.trim()) {planMessage("家族と確認して決めたことを、一言書いてから保存しよう。",false);return;}
    const flags=tomorrowWeatherFlags(),category=flags.thunder?"雷":flags.snow?"雪":flags.rain&&flags.windy?"雨と強風":flags.rain?"雨":flags.hot?"暑い日":flags.windy?"強風":"ふだん";
    const ok=saveWisdomBankEntry({id:p.id,type:"tomorrowPlan",category,weather:p.weather,
        selectedItems:[...p.items],leaveChoice:p.leaveChoice,leaveNote:p.leaveNote,
        cautions:[...p.cautions],cautionNote:p.cautionNote,familyDecision:p.familyDecision,
        summary:{items:tomorrowItemLabels(p.items),time:p.leaveNote||tomorrowTimeLabel(p.leaveChoice),
        cautions:[...tomorrowCautionLabels(p.cautions),p.cautionNote].filter(Boolean)}});
    if(!ok)return;
    p.saved=true;storageDelete(accountStorageKey("draft"));
    planMessage("知恵貯金に保存しました。同じボタンをもう一度押しても件数は増えません。",true);
}
let wisdomBankFilter="all";
function openWisdomBank(){wisdomBankFilter="all";switchScreen("wisdom-bank")}
function wisdomEntryCategory(e){if(e.category)return e.category;if(e.type==="weatherPreparation"){const m={rain:"雨",rainWind:"雨と強風",veryHot:"暑い日",thunder:"雷",heavyRain:"大雨",snow:"雪",auto:"天気"};return m[e.scenario]||"天気"}return"その他"}
function setWisdomBankFilter(f){wisdomBankFilter=f;renderWisdomBank()}
function renderWisdomBank() {
    let entries;
    try {entries=getWisdomBankEntries().slice().reverse();}
    catch {document.getElementById("wisdomBankList").textContent="保存データを読み込めません。元のデータは変更していません。";return;}
    const total=document.getElementById("wisdomBankTotal");if(total)total.textContent=String(entries.length);
    const filters=["all",...new Set(entries.map(wisdomEntryCategory))], box=document.getElementById("wisdomBankFilters");
    if(box) {
        box.replaceChildren();
        filters.forEach(filter=>{
            const b=document.createElement("button");b.type="button";
            b.className="rounded-full px-3 py-2 text-xs font-black border "+(wisdomBankFilter===filter?"bg-amber-500 text-white":"bg-white border-amber-200 text-amber-800");
            b.textContent=filter==="all"?"すべて":filter;b.onclick=()=>setWisdomBankFilter(filter);box.append(b);
        });
    }
    const list=document.getElementById("wisdomBankList");if(!list)return;
    const visible=wisdomBankFilter==="all"?entries:entries.filter(e=>wisdomEntryCategory(e)===wisdomBankFilter);
    list.replaceChildren();
    if(!visible.length) {
        list.innerHTML='<p class="p-5">まだ知恵がありません。「明日のそなえ」で考えて保存してみよう。</p>';return;
    }
    visible.forEach(entry=>{
        const summary=entry.summary||{}, items=Array.isArray(summary.items)?summary.items:tomorrowItemLabels(entry.selectedItems||[]);
        const cautions=Array.isArray(summary.cautions)?summary.cautions:tomorrowCautionLabels(entry.cautions||[]);
        const card=document.createElement("article");card.className="rounded-3xl border border-amber-200 bg-white p-5 shadow-sm";
        const title=entry.familyDecision||items.join("・")||"以前に考えたこと";
        card.innerHTML=`<p class="text-xs text-amber-800 font-black">${escapeHtml(wisdomEntryCategory(entry))} / ${escapeHtml(formatSavedTime(entry.savedAt))}</p>
            ${entry.legacy?'<p class="text-xs text-slate-500 mt-1">以前の端末共通の記録（作成者は特定できません）</p>':""}
            <h3 class="font-black mt-3">${escapeHtml(title)}</h3>
            <p class="text-sm mt-2">持ち物：${escapeHtml(items.join("・")||"記録なし")}</p>
            <p class="text-sm mt-1">時間：${escapeHtml(summary.time||entry.leaveNote||tomorrowTimeLabel(entry.leaveChoice))}</p>
            <p class="text-sm mt-1">気をつけること：${escapeHtml(cautions.join("・")||"記録なし")}</p>`;
        const button=document.createElement("button");button.type="button";button.className="mt-4 w-full border border-sky-200 rounded-2xl py-3 text-sky-800 font-black";
        button.textContent="この知恵をヒントに、もう一度考える";button.onclick=()=>reuseWisdomEntry(entry.id||entry.savedAt);
        card.append(button);list.append(card);
    });
}
function reuseWisdomEntry(id) {
    const entry=getWisdomBankEntries().find(e=>e.id===id||e.savedAt===id);
    if(!entry)return;
    resetTomorrowPlanState();
    tomorrowPlanState.items=(entry.selectedItems||[]).map(x=>({flashlight:"light",warmClothes:"warm"}[x]||x));
    tomorrowPlanState.leaveChoice=entry.leaveChoice||"";tomorrowPlanState.leaveNote=entry.leaveNote||"";
    tomorrowPlanState.cautions=Array.isArray(entry.cautions)?[...entry.cautions]:[];
    tomorrowPlanState.cautionNote=entry.cautionNote||"";
    // 過去の家族確認や天気を「今回も確認済み」として引き継がない。
    switchScreen("tomorrow-plan");saveTomorrowPlanDraft(false);void fetchTomorrowForPlan();
}
async function openTomorrowPreparation() {
    openTomorrowPlan();
}

async function fetchTomorrowDashboard() {
    const epoch=authEpoch;
    const data=await getTomorrowForecast();
    if(epoch!==authEpoch)return;
    const set=(id,text)=>{const el=document.getElementById(id);if(el)el.textContent=text;};
    if(!data) {
        set("dashboardTomorrowWeather","明日の予報を取得できません");
        set("dashboardTomorrowTemp","--℃ / --℃");set("dashboardTomorrowRain","未取得");
        set("tomorrowMascotMessage","明日の予定から考えてみよう。天気は通信できる時に確認してね。");return;
    }
    set("dashboardTomorrowWeather",`${data.description}${data.cached?"（保存済み予報）":""}`);
    const fmt=n=>Number.isFinite(numberOrNaN(n))?Math.round(n):"--";
    set("dashboardTomorrowTemp",`${fmt(data.tempMax)}℃ / ${fmt(data.tempMin)}℃`);
    set("dashboardTomorrowRain",`予報の最大降水確率 ${Number.isFinite(numberOrNaN(data.pop))?Math.round(data.pop*100):"--"}%`);
    set("tomorrowMascotMessage",`${data.forecastDate} の天気から、持ち物や気をつけたいことを考えよう。`);
}

/* =====================================================
   天気情報取得
===================================================== */
async function fetchRealWeatherWithJST() {
    const descEl = document.getElementById("liveWeatherDesc");
    if (!descEl) return;

    if (!navigator.onLine) {
        renderCachedWeatherOrUnavailable();
        return;
    }

    descEl.innerText = "JST基準で気象データを取得中...";

    try {
        const result = await apiRequest("/api/weather", { method: "GET" }, 15000);
        if (!result.ok) {
            throw new Error(result.error || "天気情報を取得できませんでした。");
        }

        const data = result.data;
        const snapshot = {
            description: String(data.description || data.weather || "天候不明"),
            temperature: Number(data.temperature),
            feelsLike: Number(data.feels_like),
            humidity: Number(data.humidity),
            windSpeed: Number(data.wind_speed),
            fetchedAt: String(data.fetched_at || new Date().toISOString()),
            cachedAt: new Date().toISOString()
        };

        currentWeatherSnapshot = snapshot;
        offlineProfile.lastWeather = snapshot;
        offlineProfile.weatherCachedAt = snapshot.cachedAt;
        saveOfflineProfile(false);
        renderWeatherSnapshot(snapshot, false);
        evaluateJSTWeatherAndAdvice(
            snapshot.description,
            snapshot.windSpeed,
            [],
            snapshot.temperature,
            snapshot.feelsLike,
            false
        );
        updateAutoPreparationFromWeather(snapshot);
    } catch (error) {
        console.error("天気取得エラー:", error);
        if (offlineProfile.lastWeather) {
            renderWeatherSnapshot(offlineProfile.lastWeather, true);
            evaluateJSTWeatherAndAdvice(
                offlineProfile.lastWeather.description,
                offlineProfile.lastWeather.windSpeed,
                [],
                offlineProfile.lastWeather.temperature,
                offlineProfile.lastWeather.feelsLike,
                true
            );
            updateAutoPreparationFromWeather(offlineProfile.lastWeather);
        } else {
            descEl.innerText = `天気情報の取得に失敗しました。${error.message || ""}`;
            const recommendationEl = document.getElementById("lifestyleRecommendation");
            if (recommendationEl) {
                recommendationEl.innerText = "最新の天気は表示できません。下の『今日、何を準備する？』では、雨・強風・暑さなどの場面を自分で選べます。";
            }
            initializePreparationUI();
        }
    }
}

function renderWeatherSnapshot(snapshot, cached = false) {
    const description = String(snapshot?.description || "天候不明");
    const temperature = numberOrNaN(snapshot?.temperature);
    const feelsLike = numberOrNaN(snapshot?.feelsLike);
    const humidity = numberOrNaN(snapshot?.humidity);
    const windSpeed = numberOrNaN(snapshot?.windSpeed);
    const savedTime = snapshot?.cachedAt || snapshot?.fetchedAt || offlineProfile.weatherCachedAt;

    const descEl = document.getElementById("liveWeatherDesc");
    if (descEl) {
        descEl.innerText = cached
            ? `保存した天気：${description} / ${Number.isFinite(temperature) ? temperature.toFixed(1) : "--"}℃ / 風速 ${Number.isFinite(windSpeed) ? windSpeed.toFixed(1) : "--"} m/s（${formatSavedTime(savedTime)}）`
            : `天草市：${description} / 気温: ${Number.isFinite(temperature) ? temperature.toFixed(1) : "--"}℃ / 風速: ${Number.isFinite(windSpeed) ? windSpeed.toFixed(1) : "--"} m/s (JST)`;
    }

    const temperatureEl = document.getElementById("weatherTemperature");
    const feelsLikeEl = document.getElementById("weatherFeelsLike");
    const humidityEl = document.getElementById("weatherHumidity");
    const windEl = document.getElementById("weatherWind");
    if (temperatureEl) temperatureEl.innerText = Number.isFinite(temperature) ? `${temperature.toFixed(1)}℃` : "--";
    if (feelsLikeEl) feelsLikeEl.innerText = Number.isFinite(feelsLike) ? `${feelsLike.toFixed(1)}℃` : "--";
    if (humidityEl) humidityEl.innerText = Number.isFinite(humidity) ? `${humidity}%` : "--";
    if (windEl) windEl.innerText = Number.isFinite(windSpeed) ? `${windSpeed.toFixed(1)} m/s` : "--";

    const sourceNote = document.getElementById("preparationSourceNote");
    if (sourceNote) {
        sourceNote.innerText = cached
            ? `現在は最新情報を取得できないため、${formatSavedTime(savedTime)}に保存した天気を使っています。状況が変わっていないか周りも確認してね。`
            : `最新の天気を使って場面を選びました。自分で別の場面へ切り替えることもできます。`;
    }
}

function renderCachedWeatherOrUnavailable() {
    if (offlineProfile.lastWeather) {
        currentWeatherSnapshot = offlineProfile.lastWeather;
        renderWeatherSnapshot(offlineProfile.lastWeather, true);
        evaluateJSTWeatherAndAdvice(
            offlineProfile.lastWeather.description,
            offlineProfile.lastWeather.windSpeed,
            [],
            offlineProfile.lastWeather.temperature,
            offlineProfile.lastWeather.feelsLike,
            true
        );
        updateAutoPreparationFromWeather(offlineProfile.lastWeather);
        return;
    }

    const descEl = document.getElementById("liveWeatherDesc");
    if (descEl) descEl.innerText = "オフラインです。まだ保存した天気情報がありません。";
    const recommendationEl = document.getElementById("lifestyleRecommendation");
    if (recommendationEl) {
        recommendationEl.innerText = "天気・警報などの最新情報には通信が必要です。準備物の場面は手動で選べます。";
    }
    initializePreparationUI();
}

function evaluateJSTWeatherAndAdvice(desc, windSpeed, forecastList, temperature = NaN, feelsLike = NaN, cached = false) {
    const jst = getJSTNow();
    const hour = jst.getHours();
    const hourMinuteStr = `${String(hour).padStart(2, "0")}:${String(jst.getMinutes()).padStart(2, "0")}`;
    const recommendations = [];
    const description = String(desc || "");
    const wind = Number(windSpeed);
    const temp = Number(temperature);
    const feel = Number(feelsLike);
    const rainFlag = /雨|降水|雷|雪/.test(description);
    const thunderFlag = /雷/.test(description);
    const heavyRainFlag = /大雨|豪雨|猛烈|激しい雨/.test(description);
    const hotFlag = (Number.isFinite(feel) && feel >= 33) || (Number.isFinite(temp) && temp >= 33);
    let timeGreeting = "";

    if (cached) {
        timeGreeting = "保存した天気情報を表示しています。最新の状況ではない可能性があります。";
    } else if (hour < 12) {
        timeGreeting = `おはようございます。日本標準時 ${hourMinuteStr}、天草市の気象情報をお届けします。`;
    } else {
        timeGreeting = `日本標準時 ${hourMinuteStr}、天草市の気象情報です。`;
    }

    if (thunderFlag) {
        recommendations.push("雷が聞こえたり空が急に暗くなったりしたら、丈夫な建物など安全な場所へ移ることを考えましょう。");
    } else if (heavyRainFlag) {
        recommendations.push("大雨の時は、川・用水路・水がたまった場所へ近づかないようにしましょう。");
    } else if (rainFlag) {
        recommendations.push(Number.isFinite(wind) && wind >= 7
            ? "雨と強い風が予想されます。傘だけに頼らず、レインコートなども考えましょう。"
            : "雨具を準備し、足元や見えにくさにも気をつけましょう。");
    } else {
        recommendations.push("現在の天候を確認しながら、安全にお過ごしください。");
    }

    if (Number.isFinite(wind) && wind >= 10) {
        recommendations.push("風が強いため、飛ばされやすい物、看板、木の枝など周りの様子にも注意してください。");
    }
    if (hotFlag) {
        recommendations.push("暑さが厳しい時は、水分・帽子・休憩を忘れず、無理をしないようにしましょう。");
    }

    const titleEl = document.getElementById("jstReportTitle");
    const recommendationEl = document.getElementById("lifestyleRecommendation");
    if (titleEl) titleEl.innerText = cached
        ? "📴 保存した天草市の気象情報"
        : `🌤️ 天草市 JST気象情報 (${hourMinuteStr})`;
    if (!recommendationEl) return;

    let htmlOutput = `<div class="font-bold text-emerald-900 mb-1">${escapeHtml(timeGreeting)}</div><ul class="list-disc pl-4 space-y-1">`;
    recommendations.forEach(rec => {
        htmlOutput += `<li>${escapeHtml(rec)}</li>`;
    });
    htmlOutput += "</ul>";
    recommendationEl.innerHTML = htmlOutput;
}

/* =====================================================
   天気に合わせて準備物を考える
===================================================== */
const PREPARATION_ITEMS = {
    umbrella: { emoji: "☂️", label: "傘" },
    raincoat: { emoji: "🧥", label: "レインコート" },
    boots: { emoji: "🥾", label: "長靴" },
    towel: {
        emoji: "",
        label: "タオル",
        iconHtml: `<svg viewBox="0 0 48 48" class="w-8 h-8" aria-hidden="true"><rect x="7" y="11" width="34" height="27" rx="6" fill="#7dd3fc"/><path d="M13 18h22M13 24h22" stroke="#e0f2fe" stroke-width="3" stroke-linecap="round"/><path d="M13 32h22" stroke="#0284c7" stroke-width="2.5" stroke-linecap="round"/><path d="M33 30v8" stroke="#0369a1" stroke-width="2" stroke-linecap="round"/></svg>`
    },
    hat: { emoji: "🧢", label: "帽子" },
    water: { emoji: "🥤", label: "水筒・飲み物" },
    coolTowel: { emoji: "🧊", label: "冷たいタオル" },
    warmClothes: { emoji: "🧣", label: "防寒着" },
    gloves: { emoji: "🧤", label: "手袋" },
    nonSlipShoes: { emoji: "👟", label: "滑りにくい靴" },
    flashlight: { emoji: "🔦", label: "ライト" },
    battery: { emoji: "🔋", label: "モバイルバッテリー" },
    delay: { emoji: "⏰", label: "出かける時間をずらす" },
    safeBuilding: { emoji: "🏢", label: "安全な建物へ移る" },
    checkRoute: { emoji: "🗺️", label: "通学路の危ない場所を確認" },
    sandals: { emoji: "🩴", label: "サンダル" }
};

const PREPARATION_SCENARIOS = {
    mild: {
        icon: "🌤️",
        title: "おだやかな天気",
        situation: "大きな雨や風の心配は少なそうです。普段の外出に必要な物を考えよう。",
        choices: ["water", "hat", "towel", "battery", "umbrella", "raincoat", "warmClothes", "sandals"],
        recommended: ["water"],
        reasons: {
            water: "天気が穏やかでも、水分を持っておくと安心だから。"
        },
        cautions: {},
        action: "出かける前に空の様子をもう一度見て、予定に合う持ち物を足してね。"
    },
    rain: {
        icon: "☔",
        title: "雨",
        situation: "雨が降りそうです。ぬれにくく、歩きやすくする物を考えよう。",
        choices: ["umbrella", "raincoat", "boots", "towel", "water", "hat", "sandals", "delay"],
        recommended: ["umbrella", "towel"],
        reasons: {
            umbrella: "風が弱い普通の雨なら、傘で雨をよけやすいから。",
            towel: "服や持ち物がぬれた時にすぐ拭けるから。"
        },
        cautions: {
            sandals: "サンダルは足がぬれやすく、場所によっては滑りやすいよ。道の様子も確かめよう。"
        },
        action: "雨が強くなったり風が出たりしたら、傘だけでなくレインコートや外出時間の変更も考えよう。"
    },
    rainWind: {
        icon: "🌧️",
        title: "雨と強い風",
        situation: "雨に加えて風も強そうです。傘があおられる場合も考えて選ぼう。",
        choices: ["umbrella", "raincoat", "boots", "towel", "delay", "safeBuilding", "checkRoute", "sandals"],
        recommended: ["raincoat", "delay", "checkRoute"],
        reasons: {
            raincoat: "両手を使いやすく、強い風で傘があおられる心配を減らせるから。",
            delay: "雨風が強い時間を避けることも、自分を守る立派な準備だから。",
            checkRoute: "いつもの通学路で、海・川・倒れそうな物など天気で危険が増す場所に気づけるから。危ない時は一人で道を変えず、家族や学校と相談しよう。"
        },
        cautions: {
            umbrella: "傘を選んだ理由も分かるよ。ただ、風が強い時はあおられて危ないことがあるので、傘だけに頼らない方法も考えよう。",
            sandals: "強い雨風の日は、サンダルだと滑ったり脱げたりしやすいことがあるよ。"
        },
        action: "雨風がとても強い時は、準備物より先に『今は出かけない』という選び方も大切です。"
    },
    hot: {
        icon: "☀️",
        title: "暑い日",
        situation: "気温が高くなりそうです。体に熱がたまりすぎない準備を考えよう。",
        choices: ["water", "hat", "coolTowel", "towel", "delay", "umbrella", "warmClothes", "sandals"],
        recommended: ["water", "hat"],
        reasons: {
            water: "のどが渇く前から少しずつ水分をとる準備になるから。",
            hat: "外で頭に強い日差しが当たり続けるのを減らせるから。"
        },
        cautions: {
            warmClothes: "冷房対策に役立つこともあるけれど、外では暑くなりすぎない服装か確かめよう。"
        },
        action: "日陰や涼しい場所で休む時間も、持ち物と同じくらい大切だよ。"
    },
    veryHot: {
        icon: "🥵",
        title: "とても暑い日",
        situation: "かなり暑くなりそうです。持ち物だけでなく、時間や休み方も考えよう。",
        choices: ["water", "hat", "coolTowel", "delay", "safeBuilding", "umbrella", "warmClothes", "sandals"],
        recommended: ["water", "hat", "delay"],
        reasons: {
            water: "体の水分が不足しないように、すぐ飲める物が必要だから。",
            hat: "直射日光を受け続けるのを減らせるから。",
            delay: "特に暑い時間を避けることが、無理をしない行動につながるから。"
        },
        cautions: {
            warmClothes: "室内の冷房対策には使えるけれど、屋外では熱がこもらないようにしよう。"
        },
        action: "具合が悪い時は我慢せず、涼しい場所へ移って近くの大人に伝えよう。"
    },
    thunder: {
        icon: "⛈️",
        title: "雷",
        situation: "雷が起こる可能性があります。外にいる時の安全な動きも選ぼう。",
        choices: ["safeBuilding", "delay", "umbrella", "raincoat", "checkRoute", "water", "hat", "sandals"],
        recommended: ["safeBuilding", "delay"],
        reasons: {
            safeBuilding: "雷の音や急な空の変化に気づいた時、丈夫な建物へ移ることが安全につながるから。",
            delay: "雷が近い時に外へ出ない選び方もできるから。"
        },
        cautions: {
            umbrella: "雨よけにはなるけれど、雷から身を守る道具ではないよ。まず安全な場所を考えよう。"
        },
        action: "雷が鳴っている時は、木のすぐ下や開けた場所にとどまらず、周りの大人や施設の案内も聞こう。"
    },
    heavyRain: {
        icon: "🌊",
        title: "大雨",
        situation: "雨がとても強い場面です。何を持つかより、どこを通るか・出かけるかも考えよう。",
        choices: ["delay", "checkRoute", "raincoat", "boots", "flashlight", "battery", "umbrella", "sandals"],
        recommended: ["delay", "checkRoute", "battery"],
        reasons: {
            delay: "危険が高い時間に無理に移動しないことが、自分を守る準備になるから。",
            checkRoute: "いつもの通学路に川・用水路・低い場所などがないか先に確認できるから。危険がありそうなら家族や学校と相談しよう。",
            battery: "通信できる時に情報や家族の連絡を確認しやすくするから。"
        },
        cautions: {
            umbrella: "傘を持つだけでは、深い水や強い流れからは身を守れないよ。移動しない判断や安全な道の確認を先にしよう。",
            sandals: "足元が見えにくい大雨では、脱げやすい履物は危険が増えることがあるよ。"
        },
        action: "川や用水路、水がたまった道の様子を見に行かないで、早めに安全な場所で情報を確かめよう。"
    },
    snow: {
        icon: "❄️",
        title: "雪・路面の凍結",
        situation: "雪や凍った道を考えた準備が必要です。暖かさと歩きやすさを選ぼう。",
        choices: ["warmClothes", "gloves", "nonSlipShoes", "boots", "water", "delay", "sandals", "umbrella"],
        recommended: ["warmClothes", "gloves", "nonSlipShoes"],
        reasons: {
            warmClothes: "体が冷えすぎないように調整できるから。",
            gloves: "手を冷えから守り、転んだ時にも手を守りやすいから。",
            nonSlipShoes: "雪や凍った場所で滑りにくくするため。"
        },
        cautions: {
            sandals: "雪や凍った道では足が冷えやすく、滑りやすいので別の靴を考えよう。"
        },
        action: "歩幅を小さくして急がず、道路や交通の情報も確かめよう。"
    },
    cold: {
        icon: "🥶",
        title: "寒い日",
        situation: "気温が低くなりそうです。体温を保ちながら動ける準備を考えよう。",
        choices: ["warmClothes", "gloves", "water", "nonSlipShoes", "hat", "umbrella", "sandals", "towel"],
        recommended: ["warmClothes", "gloves"],
        reasons: {
            warmClothes: "暑くなった時は脱ぐなど、体温を調整できるから。",
            gloves: "手先の冷えを防ぎやすいから。"
        },
        cautions: {
            sandals: "寒い日は足が冷えやすいので、天気と道に合う靴を考えよう。"
        },
        action: "雨や雪もある時は、濡れたままにしない準備も足してね。"
    },
    strongWind: {
        icon: "💨",
        title: "強い風",
        situation: "風が強そうです。飛ばされる物や歩きにくさも考えて選ぼう。",
        choices: ["delay", "checkRoute", "raincoat", "umbrella", "hat", "safeBuilding", "water", "battery"],
        recommended: ["delay", "checkRoute"],
        reasons: {
            delay: "風が弱まるまで移動を待つことも安全な選び方だから。",
            checkRoute: "いつもの通学路で、看板・木の枝・海沿いなど強風で危険が増す場所を先に確認できるから。"
        },
        cautions: {
            umbrella: "雨があっても、強風では傘があおられることがあるよ。レインコートや時間変更も考えよう。",
            hat: "帽子は日差し対策になるけれど、風で飛ばされない工夫も必要だよ。"
        },
        action: "外に出る必要があるかを大人と確認し、飛んでくる物や転倒にも注意しよう。"
    }
};

function detectPreparationScenario(snapshot) {
    const description = String(snapshot?.description || "");
    const temperature = numberOrNaN(snapshot?.temperature);
    const feelsLike = numberOrNaN(snapshot?.feelsLike);
    const windSpeed = numberOrNaN(snapshot?.windSpeed);

    if (/雷/.test(description)) return "thunder";
    if (/雪|みぞれ|霰/.test(description)) return "snow";
    if (/大雨|豪雨|猛烈|激しい雨/.test(description)) return "heavyRain";
    if (/雨|降水/.test(description) && Number.isFinite(windSpeed) && windSpeed >= 7) return "rainWind";
    if ((Number.isFinite(feelsLike) && feelsLike >= 35) || (Number.isFinite(temperature) && temperature >= 35)) return "veryHot";
    if ((Number.isFinite(feelsLike) && feelsLike >= 28) || (Number.isFinite(temperature) && temperature >= 28)) return "hot";
    if (/雨|降水/.test(description)) return "rain";
    if (Number.isFinite(windSpeed) && windSpeed >= 10) return "strongWind";
    if (Number.isFinite(temperature) && temperature <= 7) return "cold";
    return "mild";
}

function initializePreparationUI() {
    const saved = offlineProfile.weatherPreparation;
    if (!document.getElementById("preparationChoices")) return;

    if (saved && !document.getElementById("preparationChoices").dataset.restored) {
        currentPreparationScenario = saved.requestedScenario || "auto";
        activePreparationScenario = saved.resolvedScenario || "mild";
        selectedPreparationItems = new Set(Array.isArray(saved.selectedItems) ? saved.selectedItems : []);
        document.getElementById("preparationChoices").dataset.restored = "true";
    }

    setPreparationScenario(currentPreparationScenario, true);
    updateOfflineSavedLabels();
}

function updateAutoPreparationFromWeather(snapshot) {
    currentWeatherSnapshot = snapshot || currentWeatherSnapshot;
    if (currentPreparationScenario === "auto") {
        setPreparationScenario("auto", true);
    }
}

function setPreparationScenario(requestedScenario, preserveSelections = false) {
    const requested = PREPARATION_SCENARIOS[requestedScenario] ? requestedScenario : "auto";
    const resolved = requested === "auto"
        ? detectPreparationScenario(currentWeatherSnapshot || offlineProfile.lastWeather)
        : requested;
    const changed = activePreparationScenario !== resolved || currentPreparationScenario !== requested;

    currentPreparationScenario = requested;
    activePreparationScenario = PREPARATION_SCENARIOS[resolved] ? resolved : "mild";
    if (changed && !preserveSelections) {
        selectedPreparationItems.clear();
    }

    document.querySelectorAll("[data-prep-scenario]").forEach(button => {
        const active = button.dataset.prepScenario === currentPreparationScenario;
        button.className = active
            ? "shrink-0 bg-sky-600 text-white border border-sky-600 rounded-xl px-3 py-2 text-xs font-black"
            : "shrink-0 bg-white text-slate-700 border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold";
    });

    const config = PREPARATION_SCENARIOS[activePreparationScenario];
    const situation = document.getElementById("preparationSituation");
    if (situation) situation.innerText = `${config.icon} ${config.title}：${config.situation}`;

    const sourceNote = document.getElementById("preparationSourceNote");
    if (sourceNote && requested !== "auto") {
        sourceNote.innerText = "自分で選んだ場面です。実際に出かける時は、最新の天気や周りの様子も確かめてね。";
    }

    renderPreparationChoices();
    document.getElementById("preparationFeedback")?.classList.add("hidden");
}

function renderPreparationChoices() {
    const container = document.getElementById("preparationChoices");
    if (!container) return;
    const config = PREPARATION_SCENARIOS[activePreparationScenario] || PREPARATION_SCENARIOS.mild;
    container.innerHTML = "";

    config.choices.forEach(itemId => {
        const item = PREPARATION_ITEMS[itemId];
        if (!item) return;
        const selected = selectedPreparationItems.has(itemId);
        const button = document.createElement("button");
        button.type = "button";
        button.className = `tap-card min-h-24 rounded-2xl border p-3 text-left ${selected ? "choice-selected" : "bg-white border-slate-200 hover:bg-sky-50"}`;
        button.setAttribute("aria-pressed", selected ? "true" : "false");
        const iconMarkup = item.iconHtml
            ? `<span class="block">${item.iconHtml}</span>`
            : `<span class="block text-2xl">${escapeHtml(item.emoji || "")}</span>`;
        button.innerHTML = `${iconMarkup}<span class="block text-xs font-black text-slate-800 mt-2">${escapeHtml(item.label)}</span><span class="block text-[10px] mt-1 ${selected ? "text-sky-700" : "text-slate-400"}">${selected ? "選んだよ ✓" : "タップして選ぶ"}</span>`;
        button.onclick = () => togglePreparationItem(itemId);
        container.appendChild(button);
    });
}

function togglePreparationItem(itemId) {
    if (selectedPreparationItems.has(itemId)) {
        selectedPreparationItems.delete(itemId);
    } else {
        selectedPreparationItems.add(itemId);
    }
    renderPreparationChoices();
    document.getElementById("preparationFeedback")?.classList.add("hidden");
}

function preparationItemNames(ids) {
    return ids
        .map(id => PREPARATION_ITEMS[id]?.label)
        .filter(Boolean)
        .join("・");
}

function checkPreparationChoices() {
    const feedback = document.getElementById("preparationFeedback");
    if (!feedback) return;
    const config = PREPARATION_SCENARIOS[activePreparationScenario] || PREPARATION_SCENARIOS.mild;
    const selected = [...selectedPreparationItems];

    if (selected.length === 0) {
        feedback.className = "mt-4 rounded-2xl border border-amber-200 bg-amber-50 text-amber-900 p-4 text-sm leading-relaxed";
        feedback.innerHTML = "<b>まずは一つ選んでみよう。</b><br>完璧に当てるクイズではないよ。『自分ならこれが必要かも』と思うものから選んで大丈夫。";
        return;
    }

    const matched = config.recommended.filter(id => selectedPreparationItems.has(id));
    const missing = config.recommended.filter(id => !selectedPreparationItems.has(id));
    const cautionMessages = selected
        .map(id => config.cautions?.[id])
        .filter(Boolean);
    const reasonMessages = matched
        .map(id => config.reasons?.[id])
        .filter(Boolean);

    const parts = [];
    if (matched.length > 0) {
        parts.push(`<b>いい考えだね！</b> ${escapeHtml(preparationItemNames(matched))}を選んだことが、安全や過ごしやすさにつながるよ。`);
        reasonMessages.forEach(message => parts.push(`✅ ${escapeHtml(message)}`));
    } else {
        parts.push("<b>自分で考えて選べたね。</b> 選んだ物にも役立つ場面があります。ここから、今の天気に特に合う物も一緒に確かめよう。");
    }

    if (missing.length > 0) {
        const suggestions = missing.slice(0, 2);
        parts.push(`💡 もう一つ考えるなら、<b>${escapeHtml(preparationItemNames(suggestions))}</b>も候補だよ。`);
        suggestions.forEach(id => {
            if (config.reasons?.[id]) parts.push(`・${escapeHtml(config.reasons[id])}`);
        });
    }

    cautionMessages.forEach(message => parts.push(`🔎 ${escapeHtml(message)}`));
    parts.push(`🧭 ${escapeHtml(config.action)}`);

    feedback.className = `mt-4 rounded-2xl border p-4 text-sm leading-relaxed ${matched.length ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-200 bg-amber-50 text-amber-900"}`;
    feedback.innerHTML = parts.map(part => `<p class="mt-2 first:mt-0">${part}</p>`).join("");

    offlineProfile.weatherPreparation = {
        requestedScenario: currentPreparationScenario,
        resolvedScenario: activePreparationScenario,
        selectedItems: selected,
        checkedAt: new Date().toISOString(),
        weatherSnapshot: currentWeatherSnapshot || offlineProfile.lastWeather || null
    };
    saveOfflineProfile(true);
    saveWisdomBankEntry({
        type: "weatherPreparation",
        scenario: activePreparationScenario,
        selectedItems: selected
    });
    updateOfflineSavedLabels();
}

/* =====================================================
   家族の行動ルール
===================================================== */
function makeRuleOption(id, label, feedback, tone = "good") {
    return { id, label, feedback, tone };
}

const FAMILY_RULE_SCENARIOS = {
    school: {
        icon: "🏫",
        title: "学校にいる時",
        subtitle: "先生や学校の決まりを手がかりに考える",
        questions: [
            {
                key: "first",
                icon: "1️⃣",
                question: "揺れなどがおさまったあと、まずどうする？",
                options: [
                    makeRuleOption("listen_teacher", "先生の話を聞く", "いい考えだね。学校では先生や学校の人が周りの安全を確かめています。ひとりで動く前に、近くの先生へ相談すると安心につながるよ。"),
                    makeRuleOption("go_home_fast", "急いで家へ帰る", "家族に会いたくなるよね。でも道の安全が分からなかったり、迎えに来た家族とすれ違ったりすることがあります。まず先生と、家族で決めたルールを確かめよう。", "think"),
                    makeRuleOption("keep_calling", "家族へ何度も電話する", "声を聞きたいと思うのは自然だよ。ただ、電話が混み合う時もあります。短い連絡を試したあと、学校の指示や決めたルールで動けるようにしておくと安心だね。", "think")
                ]
            },
            {
                key: "place",
                icon: "2️⃣",
                question: "どこで待つのがよさそう？",
                options: [
                    makeRuleOption("school_safe_area", "学校が決めた安全な場所", "いいね。校庭や教室など、学校が安全を確認した場所で待つと、先生も家族も見つけやすくなるよ。"),
                    makeRuleOption("walk_route", "ひとりで通学路を歩く", "いつもの道でも、災害のあとはブロック塀や電線、道路などの様子が変わることがあります。ひとりで出る前に先生へ確認しよう。", "think"),
                    makeRuleOption("near_damage", "壊れた物の近くで待つ", "分かりやすい場所にいたいと思ったのかな。けれど、倒れたり落ちたりする物の近くは避けて、先生が案内する場所へ移ろう。", "think")
                ]
            },
            {
                key: "helper",
                icon: "3️⃣",
                question: "困った時、だれに助けを求める？",
                options: [
                    makeRuleOption("teacher_staff", "先生・学校の人", "いい考えだね。学校の中では、まず先生や学校の人へ伝えると、家族への連絡や安全確認につなげてもらえるよ。"),
                    makeRuleOption("friends_only", "友達だけで決める", "友達と助け合うのは大切だね。そのうえで、子どもだけで決めず先生にも伝えると、もっと安全な方法を選びやすいよ。", "think"),
                    makeRuleOption("tell_no_one", "だれにも言わず我慢する", "心配をかけたくないと思うこともあるね。でも困ったことやけがは、早めに先生へ伝えて大丈夫。助けを求めるのも大切な力だよ。", "think")
                ]
            },
            {
                key: "no_contact",
                icon: "4️⃣",
                question: "家族と連絡できなかったら？",
                options: [
                    makeRuleOption("school_handover", "学校と家族で決めた引き渡しルールで待つ", "とても大事な考え方だね。電話が通じなくても、家族と学校が同じルールを知っていれば、別々に探し回る心配を減らせるよ。"),
                    makeRuleOption("leave_alone", "だれにも言わず学校を出る", "自分で動かなきゃと思ったのかもしれないね。でも家族や先生が探せなくなることがあります。移動する時は先生へ伝えよう。", "think"),
                    makeRuleOption("search_far", "家族を探して遠くまで歩く", "家族を心配する気持ちは大切だよ。でも危ない場所を通るかもしれません。まず安全な場所にいて、決めた集合方法を使おう。", "think")
                ]
            },
            {
                key: "meeting",
                icon: "5️⃣",
                question: "最後に、家族とどこで会う？",
                options: [
                    makeRuleOption("primary_meeting", "{primaryMeeting}", "家族で同じ場所を知っておくのはいいね。学校の引き渡し方法と合っているかも、いっしょに確認しよう。"),
                    makeRuleOption("school_pickup", "学校で家族の迎えを待つ", "学校と家族がこの方法を決めているなら、分かりやすいルールになるね。だれが迎えに来るかまで決めると、さらに安心だよ。"),
                    makeRuleOption("not_decided", "まだ決めていないので家族と相談する", "『まだ決めていない』と気づけたのも大切だよ。今日、学校の決まりも確認しながら家族で一つ決めよう。", "think")
                ]
            }
        ]
    },
    home: {
        icon: "🏠",
        title: "家にひとりの時",
        subtitle: "自分の身を守り、頼れる人につなぐ",
        questions: [
            {
                key: "first",
                icon: "1️⃣",
                question: "大きく揺れたら、まずどうする？",
                options: [
                    makeRuleOption("protect_head", "頭を守り、安全な場所で揺れがおさまるのを待つ", "いい考えだね。丈夫な机の下など、その場で頭を守れる場所を使い、あわてて走らないことが最初の安全につながるよ。"),
                    makeRuleOption("rush_out", "すぐ外へ飛び出す", "外へ出たくなるよね。でも、落ちてくる物や割れた物があるかもしれません。まず頭を守り、揺れがおさまってから周りを確かめよう。", "think"),
                    makeRuleOption("find_phone_first", "最初にスマホを探す", "連絡は大事だね。ただ、揺れている間は物が落ちることがあります。まず身を守り、そのあと安全を確かめて連絡しよう。", "think")
                ]
            },
            {
                key: "place",
                icon: "2️⃣",
                question: "揺れがおさまったら、どこにいる？",
                options: [
                    makeRuleOption("safe_room", "窓や倒れそうな家具から離れた安全な場所", "よく周りを見られているね。割れたガラスや倒れそうな物を避け、出口も確かめられる場所が安心だよ。"),
                    makeRuleOption("balcony", "ベランダへ出る", "外の様子を見たい気持ちは分かるよ。でも落下物や転落の危険があります。まず室内の安全な場所で状況を確かめよう。", "think"),
                    makeRuleOption("near_tall_furniture", "背の高い家具のそば", "家具の近くならつかまれると思ったのかな。倒れる可能性がある物からは離れて、安全な場所を選ぼう。", "think")
                ]
            },
            {
                key: "helper",
                icon: "3️⃣",
                question: "ひとりで不安な時、だれを頼る？",
                options: [
                    makeRuleOption("trusted_neighbor", "家族と決めた近所の大人・助けの場所", "いいね。ふだんから顔と場所を知っている、家族が決めた相手なら、ひとりで抱え込まず助けを求められるよ。"),
                    makeRuleOption("any_online_person", "ネットで見つけた知らない人", "だれかに話したいよね。でも知らない人へ住所などを伝えるのは避けよう。家族と決めた大人、交番、店、子ども110番の家などを頼ろう。", "think"),
                    makeRuleOption("stay_silent", "怖くてもだれにも言わない", "怖い時に声が出にくいこともあるよ。短く『助けてください』『家にひとりです』と伝える練習を家族としておくといいね。", "think")
                ]
            },
            {
                key: "no_contact",
                icon: "4️⃣",
                question: "電話がつながらなかったら？",
                options: [
                    makeRuleOption("message_then_rule", "短いメッセージを残し、家族ルールで動く", "とても実用的だね。『無事・今いる場所・これからどうする』を短く残し、つながらなくても決めた行動へ移れると安心だよ。"),
                    makeRuleOption("call_forever", "つながるまでずっと電話する", "声を聞きたいよね。でも電話が混んでいたり電池が減ったりします。何度か試したら、メッセージや決めた連絡方法・行動ルールも使おう。", "think"),
                    makeRuleOption("leave_no_note", "何も知らせず遠くへ行く", "安全な場所へ移る必要がある時もあるね。その場合も、できれば行き先をメモやメッセージで残すと家族が探しやすいよ。", "think")
                ]
            },
            {
                key: "meeting",
                icon: "5️⃣",
                question: "家にいられない時、どこで家族と会う？",
                options: [
                    makeRuleOption("primary_meeting", "{primaryMeeting}", "第一集合場所を家族みんなが覚えていると、連絡できない時の手がかりになるね。そこまでの道も家族と確認しよう。"),
                    makeRuleOption("secondary_meeting", "{secondaryMeeting}", "第二集合場所まで決めておくと、第一集合場所へ行けない時にも別の選び方ができます。順番も決めよう。"),
                    makeRuleOption("not_decided", "まだ決めていないので家族と相談する", "大切な空白に気づけたね。安全な道で行ける場所を、第一・第二の二つ決めてみよう。", "think")
                ]
            }
        ]
    },
    lesson: {
        icon: "🎒",
        title: "習い事・施設にいる時",
        subtitle: "その場所の大人と家族の約束をつなぐ",
        questions: [
            {
                key: "first",
                icon: "1️⃣",
                question: "まずどうする？",
                options: [
                    makeRuleOption("follow_staff", "先生・施設の人の案内を聞く", "いい考えだね。その場所の出口や安全な場所を知っている大人の案内を聞くと、ひとりで判断しなくてよくなるよ。"),
                    makeRuleOption("leave_quietly", "何も言わず外へ出る", "家族のところへ行きたいよね。でも施設の人や家族が見つけられなくなることがあります。移動する前に必ず伝えよう。", "think"),
                    makeRuleOption("hide_unknown", "ひとりで知らない部屋に隠れる", "静かな場所へ行きたい気持ちは分かるよ。ただ、見つけてもらいにくくなります。施設の人が案内する安全な場所へ行こう。", "think")
                ]
            },
            {
                key: "place",
                icon: "2️⃣",
                question: "どこで待つ？",
                options: [
                    makeRuleOption("facility_safe", "施設が決めた安全な場所", "いいね。施設と家族が同じ待ち場所を知っていれば、迎えの時にも分かりやすいよ。"),
                    makeRuleOption("outside_gate", "ひとりで外の門や道路へ出る", "目立つ場所で待ちたいのかな。でも道路や落下物の危険があります。施設の人と安全を確かめてからにしよう。", "think"),
                    makeRuleOption("go_home_route", "いつもの道をひとりで帰る", "いつもの道でも、災害のあとは変わっていることがあります。家族と施設の人が決めた方法を優先しよう。", "think")
                ]
            },
            {
                key: "helper",
                icon: "3️⃣",
                question: "だれに助けを求める？",
                options: [
                    makeRuleOption("lesson_teacher", "習い事の先生・施設の人", "その場所をよく知る大人へ伝えるのはいい考えだね。名前や家族の連絡先も、必要な範囲で伝えられるといいよ。"),
                    makeRuleOption("other_children", "子どもだけで決める", "友達と一緒にいると心強いね。さらに施設の大人へ知らせると、安全確認や家族への連絡につながるよ。", "think"),
                    makeRuleOption("random_car", "知らない人の車に乗る", "早く帰りたい時でも、家族や施設が確認していない人の車には乗らないようにしよう。信頼できる大人へ助けを求めてね。", "think")
                ]
            },
            {
                key: "no_contact",
                icon: "4️⃣",
                question: "家族へ連絡できなかったら？",
                options: [
                    makeRuleOption("facility_rule", "施設で待ち、家族と決めた迎えのルールを使う", "いいね。『だれが迎えに来るか』『何時まで待つか』まで決めておくと、連絡できなくても動きやすいよ。"),
                    makeRuleOption("walk_search", "家族を探して歩く", "家族を心配しているんだね。でもすれ違いや危ない道の心配があります。まず施設の安全な場所にいて、決めたルールを使おう。", "think"),
                    makeRuleOption("phone_only", "電話だけを何度も試す", "電話を試すのは大切だね。つながらない時のために、短いメッセージと待つ場所も決めておくと安心だよ。", "think")
                ]
            },
            {
                key: "meeting",
                icon: "5️⃣",
                question: "最後にどこで会う？",
                options: [
                    makeRuleOption("facility_pickup", "習い事・施設で迎えを待つ", "施設と家族が確認した方法なら分かりやすいね。迎えに来てよい人も決めておこう。"),
                    makeRuleOption("primary_meeting", "{primaryMeeting}", "集合場所を使う場合は、施設の人へ伝えてから移動することと、安全な道を家族で確かめよう。"),
                    makeRuleOption("not_decided", "まだ決めていないので家族と相談する", "今決める必要があることに気づけたね。次の習い事までに、施設の決まりも聞いて家族で決めよう。", "think")
                ]
            }
        ]
    },
    outside: {
        icon: "🚶",
        title: "外出中・通学中",
        subtitle: "周りを見て、安全な場所と頼れる人を探す",
        questions: [
            {
                key: "first",
                icon: "1️⃣",
                question: "外で大きな揺れを感じたら、まずどうする？",
                options: [
                    makeRuleOption("protect_move_away", "頭を守り、塀・看板・ガラスなどから離れる", "よく周りを見ているね。落ちたり倒れたりしそうな物から離れ、揺れがおさまるまで頭を守ろう。"),
                    makeRuleOption("run_without_looking", "周りを見ずに走る", "早く逃げたいよね。でも車や落下物に気づきにくくなります。まず周りを見て、安全な方向へ落ち着いて動こう。", "think"),
                    makeRuleOption("stand_wall", "ブロック塀のそばに立つ", "体を支えたいと思ったのかな。でも塀が倒れることがあります。塀や古い建物から離れよう。", "think")
                ]
            },
            {
                key: "place",
                icon: "2️⃣",
                question: "揺れがおさまったら、どこへ行く？",
                options: [
                    makeRuleOption("near_safe_place", "近くの安全な広い場所・丈夫な建物", "いい考えだね。今いる場所に応じて、落下物が少ない場所や、案内のある丈夫な建物を選ぼう。"),
                    makeRuleOption("river_check", "川や海の様子を見に行く", "どうなったか気になるよね。でも地震や大雨のあとは危険が増えることがあります。水辺へ近づかず、情報を確認しよう。", "think"),
                    makeRuleOption("damaged_shortcut", "壊れた物がある近道を通る", "早く着きたい気持ちは分かるよ。けれど、近道より安全な道を選ぶことが大切。通れない時の別ルートも考えよう。", "think")
                ]
            },
            {
                key: "helper",
                icon: "3️⃣",
                question: "困った時、どこで助けを求める？",
                options: [
                    makeRuleOption("help_place", "交番・店・学校・子ども110番の家など", "いいね。助けを求められる場所を普段から知っておくと、ひとりでも次の行動を相談できます。"),
                    makeRuleOption("unknown_person", "だれでもいいのでついて行く", "助けを求めることは大切。でも知らない人について行かず、人のいる店・交番・学校など場所を選んで相談しよう。", "think"),
                    makeRuleOption("hide_problem", "困っていても隠す", "迷ったり怖かったりしたら、助けを求めて大丈夫。『家族と連絡できません』と短く伝えてみよう。", "think")
                ]
            },
            {
                key: "no_contact",
                icon: "4️⃣",
                question: "家族と連絡できなかったら？",
                options: [
                    makeRuleOption("stay_and_rule", "安全な場所にいて、家族ルールを確認する", "とても大切だね。むやみに動かず、今いる場所を伝えられる時に短く残し、決めた集合方法を使おう。"),
                    makeRuleOption("wander", "家族を探して歩き回る", "会いたい気持ちは自然だよ。でもすれ違いや危ない場所を通る心配があります。安全な場所と決めたルールを手がかりにしよう。", "think"),
                    makeRuleOption("battery_calls", "電池がなくなるまで電話する", "何度か試すのはいいね。そのあとに備え、電池を残しながらメッセージや助けの場所も使おう。", "think")
                ]
            },
            {
                key: "meeting",
                icon: "5️⃣",
                question: "安全を確認できたら、どこで会う？",
                options: [
                    makeRuleOption("primary_meeting", "{primaryMeeting}", "家族で同じ場所と行き方を知っておくのはいいね。道が危ない時は無理に向かわない、という条件も決めよう。"),
                    makeRuleOption("secondary_meeting", "{secondaryMeeting}", "第一集合場所へ行けない時の第二候補があると、状況に合わせて考えられるね。使う順番も確認しよう。"),
                    makeRuleOption("not_decided", "まだ決めていないので家族と相談する", "空白に気づけたのは前進だよ。学校・家・よく行く場所から安全に向かえる所を家族で考えよう。", "think")
                ]
            }
        ]
    },
    separated: {
        icon: "👨‍👩‍👧‍👦",
        title: "家族が別々の場所にいる時",
        subtitle: "連絡できなくても、同じ考え方で動けるようにする",
        questions: [
            {
                key: "first",
                icon: "1️⃣",
                question: "家族と離れている時、最初に大切なのは？",
                options: [
                    makeRuleOption("own_safety_first", "まず自分のいる場所で身を守る", "その通り。家族を心配しても、まず一人ひとりが今いる場所で安全を確かめることが、あとで会うための第一歩になるよ。"),
                    makeRuleOption("go_search", "すぐ家族を探しに行く", "家族のところへ行きたいよね。でも道路や建物が危ないかもしれません。まず自分の安全と、その場所の指示を確かめよう。", "think"),
                    makeRuleOption("panic_calls", "何も考えず電話をかけ続ける", "不安な時に電話したくなるよね。短い連絡を試したら、電池を残して、決めた行動ルールも使おう。", "think")
                ]
            },
            {
                key: "place",
                icon: "2️⃣",
                question: "それぞれ、どこにいる？",
                options: [
                    makeRuleOption("stay_safe_current", "今いる学校・職場・施設などの安全な場所", "いい考えだね。急いで全員が移動するより、それぞれが安全な場所で案内を聞く方が、すれ違いを減らせる場合があります。"),
                    makeRuleOption("all_home", "必ずすぐ家に戻る", "家は安心に感じるよね。でも家までの道や家自体が安全とは限りません。『安全を確認できた時だけ』など条件も決めよう。", "think"),
                    makeRuleOption("unknown_meeting", "その時に思いついた場所", "柔軟に考えることは大切だね。ただ、連絡できない時は家族に伝わりません。前もって第一・第二の場所を決めよう。", "think")
                ]
            },
            {
                key: "helper",
                icon: "3️⃣",
                question: "ひとりになった家族は、だれを頼る？",
                options: [
                    makeRuleOption("trusted_adults_places", "先生・施設の人・家族が決めた頼れる人や場所", "いいね。家族以外にも頼れる相手を決めておくと、電話がつながらない時の安心が増えるよ。"),
                    makeRuleOption("family_only", "家族以外には絶対に頼らない", "家族を待ちたい気持ちは分かるよ。でもけがや危険がある時は、先生・交番・店など信頼できる大人へ助けを求めて大丈夫。", "think"),
                    makeRuleOption("social_post", "住所や居場所を誰でも見られる所へ投稿する", "見つけてもらいたいよね。ただ、住所や細かい居場所を広く公開するのは避け、家族が決めた連絡相手や公的な場所を使おう。", "think")
                ]
            },
            {
                key: "no_contact",
                icon: "4️⃣",
                question: "電話が通じない時、どう連絡する？",
                options: [
                    makeRuleOption("multiple_methods", "短いメッセージ・伝言サービス・決めた連絡先を使う", "いい考えだね。一つにつながらなくても別の方法があるように、家族で使う順番を練習しておこう。"),
                    makeRuleOption("voice_calls_only", "通話だけを何度も続ける", "声を聞ける通話は安心だよ。でも混み合う時があります。短いメッセージや伝言サービスも家族で試しておこう。", "think"),
                    makeRuleOption("no_plan", "連絡できるまで何も決めない", "待つことが安全な場合もあるね。だからこそ『どこで待つ』『何時間後にどうする』を前もって決めると不安を減らせるよ。", "think")
                ]
            },
            {
                key: "meeting",
                icon: "5️⃣",
                question: "連絡できなくても分かる集合場所は？",
                options: [
                    makeRuleOption("primary_meeting", "{primaryMeeting}", "家族みんなが第一集合場所を知っていれば、大きな手がかりになるね。行けない時の条件も一緒に決めよう。"),
                    makeRuleOption("secondary_meeting", "{secondaryMeeting}", "第二集合場所まであると応用がきくね。第一へ行けない時だけ使うなど、順番をそろえよう。"),
                    makeRuleOption("not_decided", "まだ決めていないので家族と相談する", "今ここで気づけたのが大切だよ。家族全員が知っていて、安全な道で行ける場所を二つ考えてみよう。", "think")
                ]
            }
        ]
    }
};

function substituteFamilyRuleLabel(label) {
    const plan = offlineProfile.emergencyPlan || {};
    const primary = plan.primaryMeeting
        ? `第一集合場所：${plan.primaryMeeting}`
        : "家族で決めた第一集合場所";
    const secondary = plan.secondaryMeeting
        ? `第二集合場所：${plan.secondaryMeeting}`
        : "家族で決めた第二集合場所";
    return String(label)
        .replace("{primaryMeeting}", primary)
        .replace("{secondaryMeeting}", secondary);
}

function getFamilyRuleScenario(scenarioId) {
    return FAMILY_RULE_SCENARIOS[scenarioId] || null;
}

function renderFamilyRuleScenarioGrid() {
    const container = document.getElementById("familyRuleScenarioGrid");
    if (!container) return;
    container.innerHTML = "";

    Object.entries(FAMILY_RULE_SCENARIOS).forEach(([id, scenario]) => {
        const saved = (offlineProfile.familyRules || []).find(rule => rule.scenarioId === id);
        const button = document.createElement("button");
        button.type = "button";
        button.className = "tap-card bg-white hover:bg-violet-50 border border-violet-200 rounded-2xl p-4 text-left";
        button.innerHTML = `
            <div class="flex items-start gap-3">
                <span class="text-3xl">${scenario.icon}</span>
                <div class="flex-1">
                    <h4 class="font-black text-slate-800">${escapeHtml(scenario.title)}</h4>
                    <p class="text-[10px] text-slate-500 mt-1">${escapeHtml(scenario.subtitle)}</p>
                    <span class="inline-block mt-2 text-[10px] rounded-full px-2 py-1 font-bold ${saved ? (saved.confirmed ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700") : "bg-slate-100 text-slate-500"}">${saved ? (saved.confirmed ? "家族と確認済み" : "保存済み・家族と相談中") : "まだ作っていない"}</span>
                </div>
            </div>`;
        button.onclick = () => startFamilyRuleScenario(id);
        container.appendChild(button);
    });
}

function startFamilyRuleScenario(scenarioId) {
    const scenario = getFamilyRuleScenario(scenarioId);
    if (!scenario) return;
    currentFamilyRuleScenario = scenarioId;
    familyRuleStep = 0;
    familyRuleDraft = { scenarioId, answers: [] };
    document.getElementById("familyRuleScenarioArea")?.classList.add("hidden");
    document.getElementById("familyRuleSummary")?.classList.add("hidden");
    document.getElementById("familyRuleWizard")?.classList.remove("hidden");
    renderFamilyRuleStep();
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderFamilyRuleStep() {
    const scenario = getFamilyRuleScenario(currentFamilyRuleScenario);
    if (!scenario) return;
    const question = scenario.questions[familyRuleStep];
    if (!question) {
        showFamilyRuleSummary();
        return;
    }

    const title = document.getElementById("familyRuleScenarioTitle");
    const progress = document.getElementById("familyRuleProgress");
    const questionEl = document.getElementById("familyRuleQuestion");
    const choices = document.getElementById("familyRuleChoices");
    const custom = document.getElementById("familyRuleCustomInput");
    const feedback = document.getElementById("familyRuleFeedback");
    const nextButton = document.getElementById("familyRuleNextBtn");

    if (title) title.innerText = `${scenario.icon} ${scenario.title}`;
    if (progress) progress.innerText = `${familyRuleStep + 1} / ${scenario.questions.length}`;
    if (questionEl) questionEl.innerText = `${question.icon} ${question.question}`;
    if (custom) custom.value = "";
    feedback?.classList.add("hidden");
    if (nextButton) {
        nextButton.disabled = true;
        nextButton.innerText = familyRuleStep === scenario.questions.length - 1 ? "ルールを見る →" : "次へ →";
    }

    if (!choices) return;
    choices.innerHTML = "";
    question.options.forEach(option => {
        const displayLabel = substituteFamilyRuleLabel(option.label);
        const button = document.createElement("button");
        button.type = "button";
        button.className = "tap-card bg-white hover:bg-violet-50 border border-violet-200 rounded-2xl px-4 py-4 text-left text-sm font-black text-slate-800";
        button.innerText = displayLabel;
        button.onclick = () => chooseFamilyRuleAnswer(option, displayLabel, button);
        choices.appendChild(button);
    });
}

function chooseFamilyRuleAnswer(option, displayLabel, clickedButton) {
    const scenario = getFamilyRuleScenario(currentFamilyRuleScenario);
    const question = scenario?.questions?.[familyRuleStep];
    if (!scenario || !question) return;

    familyRuleDraft.answers[familyRuleStep] = {
        key: question.key,
        question: question.question,
        answerId: option.id,
        answer: displayLabel,
        feedback: option.feedback,
        tone: option.tone || "good"
    };

    document.querySelectorAll("#familyRuleChoices button").forEach(button => {
        button.disabled = true;
        button.classList.remove("rule-choice-selected");
    });
    clickedButton?.classList.add("rule-choice-selected");
    showFamilyRuleFeedback(option.feedback, option.tone || "good");
    const nextButton = document.getElementById("familyRuleNextBtn");
    if (nextButton) nextButton.disabled = false;
}

function saveFamilyRuleCustomAnswer() {
    const input = document.getElementById("familyRuleCustomInput");
    const value = input?.value.trim() || "";
    if (!value) {
        input?.focus();
        return;
    }

    const scenario = getFamilyRuleScenario(currentFamilyRuleScenario);
    const question = scenario?.questions?.[familyRuleStep];
    if (!scenario || !question) return;

    familyRuleDraft.answers[familyRuleStep] = {
        key: question.key,
        question: question.question,
        answerId: "custom",
        answer: value,
        feedback: "家族で決めた言葉を自分で書けたね。実際にその行動ができるか、場所・道・頼る人まで家族と確かめると、もっと自信を持てるよ。",
        tone: "good"
    };

    document.querySelectorAll("#familyRuleChoices button").forEach(button => {
        button.disabled = true;
        button.classList.remove("rule-choice-selected");
    });
    showFamilyRuleFeedback(familyRuleDraft.answers[familyRuleStep].feedback, "good");
    const nextButton = document.getElementById("familyRuleNextBtn");
    if (nextButton) nextButton.disabled = false;
}

function showFamilyRuleFeedback(message, tone = "good") {
    const feedback = document.getElementById("familyRuleFeedback");
    if (!feedback) return;
    const good = tone !== "think";
    feedback.className = `mt-4 rounded-2xl border p-4 text-sm leading-relaxed ${good ? "bg-emerald-50 border-emerald-200 text-emerald-900" : "bg-amber-50 border-amber-200 text-amber-900"}`;
    feedback.innerHTML = `<b>${good ? "その考えに自信を持っていいね。" : "そう考えた気持ちも大事だよ。"}</b><br><span class="inline-block mt-2">${escapeHtml(message)}</span>`;
}

function nextFamilyRuleStep() {
    const scenario = getFamilyRuleScenario(currentFamilyRuleScenario);
    if (!scenario || !familyRuleDraft.answers[familyRuleStep]) return;
    if (familyRuleStep >= scenario.questions.length - 1) {
        showFamilyRuleSummary();
        return;
    }
    familyRuleStep += 1;
    renderFamilyRuleStep();
}

function showFamilyRuleSummary() {
    const scenario = getFamilyRuleScenario(currentFamilyRuleScenario);
    const summary = document.getElementById("familyRuleSummaryContent");
    if (!scenario || !summary) return;

    document.getElementById("familyRuleWizard")?.classList.add("hidden");
    document.getElementById("familyRuleScenarioArea")?.classList.add("hidden");
    document.getElementById("familyRuleSummary")?.classList.remove("hidden");
    summary.innerHTML = `
        <div class="bg-white rounded-2xl border border-emerald-200 p-4">
            <h4 class="font-black text-slate-800">${scenario.icon} ${escapeHtml(scenario.title)}</h4>
        </div>
        ${familyRuleDraft.answers.map((answer, index) => `
            <div class="bg-white rounded-2xl border border-slate-200 p-4">
                <p class="text-[10px] text-slate-400 font-bold">${index + 1}. ${escapeHtml(answer.question)}</p>
                <p class="text-sm font-black text-slate-800 mt-1">${escapeHtml(answer.answer)}</p>
            </div>
        `).join("")}`;
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function restartCurrentFamilyRule() {
    if (!currentFamilyRuleScenario) return;
    startFamilyRuleScenario(currentFamilyRuleScenario);
}

function cancelFamilyRuleWizard() {
    currentFamilyRuleScenario = "";
    familyRuleStep = 0;
    familyRuleDraft = { answers: [] };
    document.getElementById("familyRuleWizard")?.classList.add("hidden");
    document.getElementById("familyRuleSummary")?.classList.add("hidden");
    document.getElementById("familyRuleScenarioArea")?.classList.remove("hidden");
    renderFamilyRuleScenarioGrid();
}

function saveCurrentFamilyRule() {
    const scenario = getFamilyRuleScenario(currentFamilyRuleScenario);
    if (!scenario || familyRuleDraft.answers.length !== scenario.questions.length) return;

    const now = new Date().toISOString();
    const existingIndex = (offlineProfile.familyRules || []).findIndex(rule => rule.scenarioId === currentFamilyRuleScenario);
    const existing = existingIndex >= 0 ? offlineProfile.familyRules[existingIndex] : null;
    const record = {
        id: existing?.id || `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        scenarioId: currentFamilyRuleScenario,
        scenarioTitle: scenario.title,
        scenarioIcon: scenario.icon,
        answers: familyRuleDraft.answers.map(answer => ({
            key: answer.key,
            question: answer.question,
            answer: answer.answer
        })),
        confirmed: false,
        confirmedAt: "",
        createdAt: existing?.createdAt || now,
        updatedAt: now
    };

    if (!Array.isArray(offlineProfile.familyRules)) offlineProfile.familyRules = [];
    if (existingIndex >= 0) offlineProfile.familyRules.splice(existingIndex, 1, record);
    else offlineProfile.familyRules.push(record);

    if (!saveOfflineProfile(true)) {
        alert("端末への保存に失敗しました。ブラウザの保存容量を確認してください。");
        return;
    }

    triggerPushNotification("家族ルールを保存しました", "家族と確認できたら『確認済み』にしてね。");
    cancelFamilyRuleWizard();
    renderSavedFamilyRules();
    renderFamilyRuleScenarioGrid();
}

function toggleFamilyRuleConfirmed(ruleId) {
    const rule = (offlineProfile.familyRules || []).find(item => item.id === ruleId);
    if (!rule) return;
    rule.confirmed = !rule.confirmed;
    rule.confirmedAt = rule.confirmed ? new Date().toISOString() : "";
    rule.updatedAt = new Date().toISOString();
    saveOfflineProfile(true);
    renderSavedFamilyRules();
    renderFamilyRuleScenarioGrid();
    renderOfflineKit();
}

function rebuildFamilyRule(scenarioId) {
    startFamilyRuleScenario(scenarioId);
}

function deleteFamilyRule(ruleId) {
    const rule = (offlineProfile.familyRules || []).find(item => item.id === ruleId);
    if (!rule) return;
    if (!confirm(`「${rule.scenarioTitle}」のルールを削除しますか？`)) return;
    offlineProfile.familyRules = offlineProfile.familyRules.filter(item => item.id !== ruleId);
    saveOfflineProfile(true);
    renderSavedFamilyRules();
    renderFamilyRuleScenarioGrid();
    renderOfflineKit();
}

function familyRuleCardHtml(rule, compact = false) {
    const answers = Array.isArray(rule.answers) ? rule.answers : [];
    const statusClass = rule.confirmed
        ? "bg-emerald-100 text-emerald-700"
        : "bg-amber-100 text-amber-700";
    const statusText = rule.confirmed ? "家族と確認済み" : "家族と相談中";
    const answerHtml = answers.map((answer, index) => `
        <div class="${compact ? "py-1" : "bg-slate-50 rounded-xl p-3"}">
            <p class="text-[10px] text-slate-400">${index + 1}. ${escapeHtml(answer.question || "")}</p>
            <p class="text-xs font-black text-slate-700 mt-1">${escapeHtml(answer.answer || "")}</p>
        </div>`).join("");

    return `
        <div class="bg-white border border-violet-200 rounded-2xl p-4">
            <div class="flex justify-between items-start gap-3">
                <div>
                    <h4 class="font-black text-slate-800">${escapeHtml(rule.scenarioIcon || "🏠")} ${escapeHtml(rule.scenarioTitle || "家族ルール")}</h4>
                    <span class="inline-block mt-2 text-[10px] rounded-full px-2 py-1 font-black ${statusClass}">${statusText}</span>
                </div>
                <span class="text-[10px] text-slate-400">更新 ${escapeHtml(formatSavedTime(rule.updatedAt))}</span>
            </div>
            <div class="space-y-2 mt-3">${answerHtml}</div>
            ${compact ? "" : `
                <div class="grid grid-cols-3 gap-2 mt-4">
                    <button onclick="toggleFamilyRuleConfirmed('${escapeJs(rule.id)}')" class="bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 text-emerald-800 rounded-xl py-2 text-[10px] font-black">${rule.confirmed ? "相談中へ戻す" : "家族と確認した"}</button>
                    <button onclick="rebuildFamilyRule('${escapeJs(rule.scenarioId)}')" class="bg-violet-50 hover:bg-violet-100 border border-violet-200 text-violet-800 rounded-xl py-2 text-[10px] font-black">作り直す</button>
                    <button onclick="deleteFamilyRule('${escapeJs(rule.id)}')" class="bg-slate-50 hover:bg-rose-50 border border-slate-200 text-slate-600 rounded-xl py-2 text-[10px] font-black">削除</button>
                </div>`}
        </div>`;
}

function renderSavedFamilyRules() {
    const container = document.getElementById("savedFamilyRulesList");
    const count = document.getElementById("familyRuleSavedCount");
    const rules = Array.isArray(offlineProfile.familyRules) ? offlineProfile.familyRules : [];
    if (count) count.innerText = String(rules.length);
    if (!container) return;

    if (rules.length === 0) {
        container.innerHTML = '<div class="text-center py-8 text-xs text-slate-400 bg-slate-50 rounded-2xl border border-dashed border-slate-300">まだ保存したルールはありません。<br>上の場面を選んで作ってみよう。</div>';
        return;
    }

    container.innerHTML = rules
        .slice()
        .sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")))
        .map(rule => familyRuleCardHtml(rule, false))
        .join("");
}

/* =====================================================
   オフライン安心メモ
===================================================== */
function setInputValue(id, value) {
    const input = document.getElementById(id);
    if (input) input.value = value || "";
}

function getInputValue(id) {
    return document.getElementById(id)?.value.trim() || "";
}

function hydrateOfflineForm() {
    const plan = offlineProfile.emergencyPlan || {};
    setInputValue("offlinePrimaryMeeting", plan.primaryMeeting);
    setInputValue("offlineSecondaryMeeting", plan.secondaryMeeting);
    setInputValue("offlineContactName1", plan.contactName1);
    setInputValue("offlineContactPhone1", plan.contactPhone1);
    setInputValue("offlineContactName2", plan.contactName2);
    setInputValue("offlineContactPhone2", plan.contactPhone2);
    setInputValue("offlineNoContactRule", plan.noContactRule);
    setInputValue("offlineNotes", plan.notes);
}

function saveOfflinePlan() {
    offlineProfile.emergencyPlan = {
        primaryMeeting: getInputValue("offlinePrimaryMeeting"),
        secondaryMeeting: getInputValue("offlineSecondaryMeeting"),
        contactName1: getInputValue("offlineContactName1"),
        contactPhone1: getInputValue("offlineContactPhone1"),
        contactName2: getInputValue("offlineContactName2"),
        contactPhone2: getInputValue("offlineContactPhone2"),
        noContactRule: getInputValue("offlineNoContactRule"),
        notes: getInputValue("offlineNotes")
    };

    const message = document.getElementById("offlineSaveMessage");
    if (!saveOfflineProfile(true)) {
        if (message) {
            message.innerText = "保存できませんでした。ブラウザの保存容量や設定を確認してください。";
            message.className = "mt-3 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 p-3 text-xs font-bold";
        }
        return;
    }

    if (message) {
        message.innerText = "✅ この端末に保存しました。通信がない時も、この画面から確認できます。";
        message.className = "mt-3 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-800 p-3 text-xs font-bold";
        setTimeout(() => message.classList.add("hidden"), 6000);
    }
    renderFamilyRuleScenarioGrid();
    renderOfflineKit();
}

function safeTelephoneValue(value) {
    return String(value || "").replace(/[^0-9+*#]/g, "");
}

function offlinePlaceCardHtml(place) {
    const isHelp = place.kind === "help";
    const category = getPlaceCategoryLabel(isHelp ? "help" : "danger", String(place.category || ""));
    const title = String(place.place_name || "").trim() || category;
    const lat = Number(place.latitude);
    const lon = Number(place.longitude);
    const hasCoordinates = Number.isFinite(lat) && Number.isFinite(lon);
    const mapUrl = hasCoordinates ? `https://www.google.com/maps?q=${encodeURIComponent(`${lat},${lon}`)}` : "";
    const location = String(place.location_label || "").trim();

    return `
        <div class="bg-white border ${isHelp ? "border-emerald-200" : "border-orange-200"} rounded-2xl p-3">
            <div class="flex justify-between items-start gap-2">
                <div>
                    <span class="text-[10px] font-black ${isHelp ? "text-emerald-700" : "text-orange-700"}">${isHelp ? "🆘 助け" : "⚠️ 危険"}</span>
                    <h4 class="text-xs font-black text-slate-800 mt-1">${escapeHtml(title)}</h4>
                    <p class="text-[10px] text-slate-400 mt-1">${escapeHtml(category)}</p>
                </div>
                <span class="text-[10px] text-slate-400">${escapeHtml(location || "場所指定なし")}</span>
            </div>
            <p class="text-xs text-slate-600 mt-2 leading-relaxed">${escapeHtml(place.text || "")}</p>
            ${mapUrl && navigator.onLine
                ? `<a href="${mapUrl}" target="_blank" rel="noopener noreferrer" class="inline-block mt-2 text-[10px] text-sky-600 underline font-bold">地図を開く</a>`
                : hasCoordinates
                    ? `<p class="mt-2 text-[10px] text-cyan-700">📴 緯度 ${lat.toFixed(5)} / 経度 ${lon.toFixed(5)}（地図を開くには通信が必要）</p>`
                    : ""}
        </div>`;
}

function renderOfflineKit() {
    const owner = document.getElementById("offlineOwnerLabel");
    if (owner) {
        const name = offlineProfile.ownerName || appState.userName || "この端末の利用者";
        owner.innerText = `${name}さんの保存情報`;
    }

    const badge = document.getElementById("offlineKitNetworkBadge");
    if (badge) {
        badge.innerText = navigator.onLine ? "オンライン" : "オフライン";
        badge.className = navigator.onLine
            ? "text-[10px] rounded-full px-3 py-1 font-black bg-emerald-100 text-emerald-700"
            : "text-[10px] rounded-full px-3 py-1 font-black bg-slate-800 text-white";
    }

    updateOfflineSavedLabels();

    const rulesContainer = document.getElementById("offlineRulesList");
    const rules = Array.isArray(offlineProfile.familyRules) ? offlineProfile.familyRules : [];
    if (rulesContainer) {
        rulesContainer.innerHTML = rules.length
            ? rules
                .slice()
                .sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")))
                .map(rule => familyRuleCardHtml(rule, true))
                .join("")
            : '<div class="text-xs text-slate-400 bg-slate-50 border border-dashed border-slate-300 rounded-2xl p-4 text-center">まだ家族ルールがありません。</div>';
    }

    const places = Array.isArray(offlineProfile.cachedPlaces) ? offlineProfile.cachedPlaces : [];
    const helpPlaces = places.filter(place => place.kind === "help");
    const dangerPlaces = places.filter(place => place.kind !== "help");
    const helpContainer = document.getElementById("offlineHelpPlacesList");
    const dangerContainer = document.getElementById("offlineDangerPlacesList");

    if (helpContainer) {
        helpContainer.innerHTML = helpPlaces.length
            ? helpPlaces.slice(0, 30).map(offlinePlaceCardHtml).join("")
            : '<div class="text-xs text-slate-400 bg-slate-50 border border-dashed border-slate-300 rounded-2xl p-4 text-center">まだ保存された助けの場所はありません。通信できる時に「まちの安全情報」を開くと保存されます。</div>';
    }
    if (dangerContainer) {
        dangerContainer.innerHTML = dangerPlaces.length
            ? dangerPlaces.slice(0, 30).map(offlinePlaceCardHtml).join("")
            : '<div class="text-xs text-slate-400 bg-slate-50 border border-dashed border-slate-300 rounded-2xl p-4 text-center">まだ保存された危ない場所はありません。</div>';
    }
}

function openLastSavedOfflineInfo() {
    const key = storageRead("otenkiLastOfflineProfileKey");
    if (!key || !storageRead(key)) {
        alert("この端末には、まだ安心メモが保存されていません。");
        return;
    }
    loadOfflineProfile(key);
    switchScreen("offline-kit");
}

function backFromOfflineKit() {
    if (appState.userName && appState.accountId && appState.securityKey) {
        switchScreen("dashboard");
    } else {
        switchScreen("login");
    }
}

/* =====================================================
   ネット接続表示・PWAインストール
===================================================== */
function updateNetworkState() {
    const online = navigator.onLine;
    if (emergencyModeActive) {
        setTimeout(renderEmergencyMode, 0);
    }
    const banner = document.getElementById("networkBanner");
    const status = document.getElementById("networkStatusText");
    const globalStatus = document.getElementById("globalConnectionStatus");

    banner?.classList.toggle("hidden", online);
    if (status) {
        status.innerText = online
            ? "🟢 オンライン：最新情報を取得できます。"
            : "⚫ オフライン：保存した家族ルール・安心メモを利用できます。";
    }
    if (globalStatus && !online) {
        globalStatus.innerText = "オフライン";
    }

    if (online) {
        if (appState.accountId) startPolling();
    } else {
        stopPolling();
    }
    renderOfflineKit();
}

async function installPwaApp() {
    if (!deferredInstallPrompt) {
        alert("このブラウザでは自動の追加画面を出せません。ブラウザのメニューから『ホーム画面に追加』または『アプリをインストール』を選んでください。");
        return;
    }

    deferredInstallPrompt.prompt();
    try {
        await deferredInstallPrompt.userChoice;
    } finally {
        deferredInstallPrompt = null;
        document.getElementById("installAppButton")?.classList.add("hidden");
    }
}

function handlePwaInstallPrompt(event) {
    event.preventDefault();
    deferredInstallPrompt = event;
    document.getElementById("installAppButton")?.classList.remove("hidden");
}

function handlePwaInstalled() {
    deferredInstallPrompt = null;
    document.getElementById("installAppButton")?.classList.add("hidden");
    triggerPushNotification("アプリを追加しました", "ホーム画面からすぐ開けます。大切な安心メモは端末にも保存されます。");
}

function initJSTBackgroundMonitors() {
    if (jstMonitorStarted) return;
    jstMonitorStarted = true;

    setInterval(() => {
        if (!appState.userName) return;
        const jst = getJSTNow();
        const h = jst.getHours();
        const m = jst.getMinutes();
        const dateKey = `${jst.toDateString()}-${h}-${m}`;

        if (h === 6 && m === 0 && lastNotifiedKey !== dateKey) {
            lastNotifiedKey = dateKey;
            triggerPushNotification("朝6:00 定時お天気レポート", "【JST】本日の天気予報と生活アドバイスをお届けします。");
        } else if (h === 18 && m === 30 && lastNotifiedKey !== dateKey) {
            lastNotifiedKey = dateKey;
            triggerPushNotification("夜18:30 翌日お天気レポート", "【JST】明日の天気予報と夜間見守りのお知らせをお届けします。");
        }
    }, 30000);
}

/* =====================================================
   文字列エスケープ
===================================================== */
function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
    }[ch]));
}

function escapeJs(value) {
    // onclick属性にも安全に埋め込めるよう、文字列とHTML属性の両方をエスケープ。
    return escapeHtml(String(value).replace(/\\/g,"\\\\").replace(/'/g,"\\'").replace(/\r/g,"\\r").replace(/\n/g,"\\n"));
}

/* =====================================================
   イベントリスナー・初期化
===================================================== */
function closeFriendRequestModal() {
    currentFriendRequest = null;
    document.getElementById("friendRequestModal")?.classList.add("hidden");
}

function acceptCurrentFriendRequest() {
    if (!currentFriendRequest?.id) {
        closeFriendRequestModal();
        return;
    }
    acceptFriendRequest(currentFriendRequest.id);
    closeFriendRequestModal();
}

function rejectCurrentFriendRequest() {
    if (!currentFriendRequest?.id) {
        closeFriendRequestModal();
        return;
    }
    rejectFriendRequest(currentFriendRequest.id);
    closeFriendRequestModal();
}

window.addEventListener("online", updateNetworkState);
window.addEventListener("offline", updateNetworkState);
window.addEventListener("beforeinstallprompt", handlePwaInstallPrompt);
window.addEventListener("appinstalled", handlePwaInstalled);

window.addEventListener("storage", event => {
    if (!event.key) return;
    if (event.key === currentOfflineStorageKey || event.key === "otenkiLastOfflineProfileKey") {
        loadOfflineProfile(currentOfflineStorageKey || undefined);
        renderFamilyRuleScenarioGrid();
        renderSavedFamilyRules();
        hydrateOfflineForm();
        renderOfflineKit();
    }
});

document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
        closeFriendModal();
        closeFriendRequestModal();
        closeHazardPostModal();
    }
    if (event.key === "Enter" && event.target?.id === "familyRuleCustomInput") {
        event.preventDefault();
        saveFamilyRuleCustomAnswer();
    }
});

document.addEventListener("click", event => {
    const friendModal = document.getElementById("friendModal");
    if (friendModal && event.target === friendModal) closeFriendModal();

    const requestModal = document.getElementById("friendRequestModal");
    if (requestModal && event.target === requestModal) closeFriendRequestModal();

    const hazardModal = document.getElementById("hazardPostModal");
    if (hazardModal && event.target === hazardModal) closeHazardPostModal();

    const enableButton = event.target.closest("#enablePushButton");
    if (enableButton) enableRealPushNotifications();

    const disableButton = event.target.closest("#disablePushButton");
    if (disableButton) disableRealPushNotifications();
});

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("loginForm")?.addEventListener("submit", event => {
        event.preventDefault();
        if (!event.isComposing) void handleAuth("login");
    });
    document.getElementById("loginSecurityKey")?.addEventListener("keydown", event => {
        const caps = document.getElementById("capsLockHint");
        if (caps) caps.hidden = !event.getModifierState?.("CapsLock");
        if (event.isComposing && event.key==="Enter") event.preventDefault();
    });
    document.getElementById("loginApiTarget").textContent = API_BASE_URL || "未設定：HTMLを直接開かないでください";
    const previous=storageRead("otenkiLastLoginName");
    if (previous) document.getElementById("loginName").value=previous;
    closePushBanner();
    loadAppState(); loadOfflineProfile(); updateOfflineEntryAvailability();
    setPlaceKind("danger"); updateQuizModeButtons();
    renderFamilyRuleScenarioGrid(); renderSavedFamilyRules(); hydrateOfflineForm(); renderOfflineKit();
    if (appState.accountId && appState.securityKey) {
        updateUserHeader(); renderFriends(); renderFriendRequests(); switchScreen("dashboard");
        initJSTBackgroundMonitors(); void restoreSavedLogin();
    } else switchScreen("login");
    // 必ず画面・入力イベントを先に準備。以降の通信は失敗してもログインを妨げない。
    void registerPushServiceWorker();
    void updatePushPermissionStatus();
    updateNetworkState();
    ["tomorrowPlanTimeNote","tomorrowPlanCautionNote","tomorrowPlanFamilyDecision"].forEach(id=>{
        document.getElementById(id)?.addEventListener("input",saveTomorrowPlanDraft);
    });
});


function accountStorageKey(kind) {
    const id=appState.accountId || offlineProfile.ownerId || "guest";
    return `otenki:${API_BASE_URL}:${id}:${kind}`;
}
function readSavedArray(key) {
    const raw=storageRead(key);
    if(!raw)return[];
    const value=JSON.parse(raw);
    if(!Array.isArray(value))throw new Error("InvalidSavedArray");
    return value;
}
function tomorrowDate() {
    return new Intl.DateTimeFormat("sv-SE",{timeZone:"Asia/Tokyo"}).format(new Date(Date.now()+86400000));
}
function numberOrNaN(value) { return value===null || value===undefined || value==="" ? NaN : Number(value); }
function planMessage(message,ok) {
    const el=document.getElementById("tomorrowPlanSaveMessage");if(!el)return;
    el.className=`mt-3 rounded-2xl p-3 text-sm border ${ok?"bg-emerald-50 border-emerald-200 text-emerald-900":"bg-amber-50 border-amber-200 text-amber-900"}`;
    el.textContent=message;
}
let tomorrowForecastRequest = null;
async function getTomorrowForecast() {
    const key=accountStorageKey("forecast"), date=tomorrowDate();
    let cached=null;
    try {cached=JSON.parse(storageRead(key)||"null");}catch{}
    const usable=cached?.forecastDate===date;
    if(!navigator.onLine) return usable?{...cached,cached:true}:null;
    if(usable && Date.now()-Date.parse(cached.fetchedAt)<300000)return cached;
    if(!tomorrowForecastRequest) {
        tomorrowForecastRequest=apiRequest("/api/weather/tomorrow",{skipAuth:true},12000)
            .finally(()=>{tomorrowForecastRequest=null;});
    }
    const result=await tomorrowForecastRequest;
    if(!result.ok)return usable?{...cached,cached:true}:null;
    const data=result.data;
    if(data.date!==date)return null;
    const forecast={description:String(data.description||"天候不明"),tempMax:finiteOrNull(data.temp_max),
        tempMin:finiteOrNull(data.temp_min),pop:finiteOrNull(data.pop),wind:finiteOrNull(data.wind_speed_max),
        forecastDate:date,fetchedAt:String(data.fetched_at||new Date().toISOString()),cached:false};
    storageWrite(key,JSON.stringify(forecast));
    return forecast;
}
function finiteOrNull(value) { const n=numberOrNaN(value);return Number.isFinite(n)?n:null; }
function loadLegacyTomorrowDraft() {
    const raw=storageRead(TOMORROW_PLAN_DRAFT_KEY);
    if(!raw){alert("旧版の下書きはありません。");return;}
    if(!confirm("この端末で以前に作った共通の下書きです。内容を自分の下書きとして読み込みますか？"))return;
    try{
        const old=JSON.parse(raw);
        resetTomorrowPlanState();
        tomorrowPlanState={...tomorrowPlanState,...old,id:newLocalId(),saved:false,weather:null,
            step:1,items:Array.isArray(old.items)?old.items:[],cautions:Array.isArray(old.cautions)?old.cautions:[],
            consultChoice:"pending",forecastDate:tomorrowDate()};
        renderTomorrowPlan();saveTomorrowPlanDraft(false);void fetchTomorrowForPlan();
    }catch{alert("旧版の下書きを読み込めません。元データは変更していません。");}
}

function newLocalId() {
    // randomUUIDはHTTPS/localhost以外で使えない場合があるため、記録IDには代替を用意。
    if (typeof crypto.randomUUID==="function") return crypto.randomUUID();
    const b=crypto.getRandomValues(new Uint8Array(16));
    return Array.from(b,v=>v.toString(16).padStart(2,"0")).join("");
}
