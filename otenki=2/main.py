/* Auth5: local shell only; API/auth responses are NEVER cached. */
const CACHE = "otenki-auth5-20260911-2";
const REQUIRED = ["/index.html","/main.js?v=20260911-auth5","/api-config.js?v=20260911-auth5","/app.css?v=20260911-auth5","/manifest.webmanifest",
    "/quiz.json","/icon-192.png","/icon-512.png","/badge-96.png","/tyokin.png"];
const ASSET_PATHS = new Set(REQUIRED.map(path=>path.split("?")[0]));
self.addEventListener("install",event=>{
    event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(REQUIRED)).then(()=>self.skipWaiting()));
});
self.addEventListener("activate",event=>{
    event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith("otenki")&&k!==CACHE)
        .map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener("message",event=>{if(event.data?.type==="SKIP_WAITING")self.skipWaiting();});
self.addEventListener("fetch",event=>{
    const request=event.request,url=new URL(request.url);
    if(request.method!=="GET" || url.origin!==self.location.origin || url.pathname.startsWith("/api/"))return;
    if(request.mode==="navigate") {
        event.respondWith((async()=>{
            const cache=await caches.open(CACHE);
            const controller=new AbortController();
            const timer=setTimeout(()=>controller.abort(),5000);
            try{
                const response=await fetch(request,{cache:"no-store",signal:controller.signal});
                if(response.ok && (url.pathname==="/"||url.pathname==="/index.html"))await cache.put("/index.html",response.clone());
                return response;
            }catch{
                return await cache.match("/index.html") || new Response("オフラインです。一度通信できる時にアプリを開いてください。",{status:503,headers:{"Content-Type":"text/plain; charset=utf-8"}});
            }finally{clearTimeout(timer);}
        })());
        return;
    }
    if(!ASSET_PATHS.has(url.pathname) && !["/icon.png","/badge.png","/quiz.txt"].includes(url.pathname))return;
    event.respondWith((async()=>{
        const cache=await caches.open(CACHE);
        const stored=await cache.match(request);
        if(stored)return stored;
        const fresh=await fetch(request);
        if(fresh.ok)await cache.put(request,fresh.clone());
        return fresh;
    })());
});
self.addEventListener("push",event=>{
    let data={};try{data=event.data?.json()||{};}catch{data={body:event.data?.text()||""};}
    event.waitUntil(self.registration.showNotification(String(data.title||"防災アプリ"),{
        body:String(data.body||"新しい情報があります"),icon:"/icon-192.png",badge:"/badge-96.png",
        tag:String(data.event_id||data.tag||data.type||"otenki-notice"),
        data:{url:"/"},renotify:true
    }));
});
self.addEventListener("notificationclick",event=>{
    event.notification.close();
    event.waitUntil((async()=>{
        const windows=await self.clients.matchAll({type:"window",includeUncontrolled:true});
        const existing=windows.find(w=>new URL(w.url).origin===self.location.origin);
        if(existing){await existing.focus();return;}
        await self.clients.openWindow("/");
    })());
});
