
import os, sys, unittest, tempfile, json, base64, importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
os.environ["OTENKI_ENABLE_MONITORS"]="0"
HERE=Path(__file__).resolve().parent
try:
    import flask
except ImportError:
    raise SystemExit("Flaskがありません。python -m pip install -r requirements.txt を実行してください。")

class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        db=Path(self.tmp.name)/"otenki_data.json"
        os.environ["OTENKI_DATA_FILE"]=str(db)
        spec=importlib.util.spec_from_file_location("test_otenki_main",HERE/"main.py")
        self.mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.mod)
        self.mod.app.config["TESTING"]=True
        self.app=self.mod.app
    def tearDown(self):self.tmp.cleanup()
    def req(self,path,method="GET",body=None,key=None,headers=None):
        hs=dict(headers or {})
        if key:hs["X-Security-Key-Encoded"]=base64.b64encode(key.encode()).decode()
        with self.app.test_client() as client:return client.open(path,method=method,json=body,headers=hs)
    def register(self,key="ABC_key_123",name="試験"):
        r=self.req("/api/account/register","POST",{"security_key":key,"name":name})
        self.assertEqual(r.status_code,200,r.get_json());return r.get_json()["user"]
    def test_repeat_login_after_registration(self):
        u=self.register()
        for _ in range(20):
            r=self.req("/api/account/login","POST",{"security_key":"ABC_key_123"})
            self.assertEqual(r.status_code,200)
            self.assertEqual(r.get_json()["user"]["id"],u["id"])
            self.assertEqual(self.req("/api/account/me",key="ABC_key_123").status_code,200)
    def test_unicode_login_and_authenticated_api(self):
        key="あしたのキー１２３🔑"
        self.register(key)
        self.assertEqual(self.req("/api/account/login","POST",{"security_key":key}).status_code,200)
        self.assertEqual(self.req("/api/account/me",key=key).status_code,200)
        self.assertEqual(self.req("/api/safety","POST",{"status":"safe"},key).status_code,200)
    def test_wrong_key_does_not_authenticate(self):
        self.register()
        r=self.req("/api/account/login","POST",{"security_key":"wrong"})
        self.assertEqual(r.status_code,401)
        self.assertEqual(self.req("/api/account/me",key="wrong").status_code,401)
    def test_empty_store_message(self):
        r=self.req("/api/account/login","POST",{"security_key":"key"})
        self.assertEqual(r.get_json()["code"],"ACCOUNT_STORE_EMPTY")
    def test_duplicate_registration_keeps_id(self):
        u=self.register()
        r=self.req("/api/account/register","POST",{"security_key":"ABC_key_123","name":"other"})
        self.assertEqual(r.status_code,409)
        self.assertEqual(self.req("/api/account/me",key="ABC_key_123").get_json()["user"]["id"],u["id"])
    def test_non_json_and_empty_key(self):
        for b in [[],{},{"security_key":""},{"security_key":123}]:
            self.assertEqual(self.req("/api/account/login","POST",b).status_code,400)
    def test_stale_header_does_not_override_body(self):
        self.register()
        r=self.req("/api/account/login","POST",{"security_key":"ABC_key_123"},headers={"X-Security-Key":"old"})
        self.assertEqual(r.status_code,200)
    def test_legacy_hash_and_raw_header_still_work(self):
        d=self.mod.load_data();d["users"]["legacy"]={"name":"旧ユーザー","security_key_hash":self.mod.hash_security_key("old")}
        self.mod.save_data(d)
        self.assertEqual(self.req("/api/account/me",headers={"X-Security-Key":"old"}).get_json()["user"]["id"],"legacy")
    def test_register_race_no_account_loss(self):
        def worker(i):
            return self.req("/api/account/register","POST",{"name":str(i),"security_key":f"parallel-{i}"}).status_code
        with ThreadPoolExecutor(max_workers=4) as ex:
            self.assertEqual(list(ex.map(worker,range(16))),[200]*16)
        self.assertEqual(len(self.mod.load_data()["users"]),16)
    def test_corrupt_store_protected(self):
        Path(self.mod.DATA_FILE).write_text("{corrupt")
        r=self.req("/api/account/login","POST",{"security_key":"key"})
        self.assertEqual(r.status_code,503)
        self.assertEqual(Path(self.mod.DATA_FILE).read_text(),"{corrupt")
    def test_assets_allowed_and_private_files_blocked(self):
        self.assertEqual(self.req("/").status_code,200)
        for file in ["main.js","app.css","sw.js","tyokin.png","manifest.webmanifest"]:
            self.assertEqual(self.req("/"+file).status_code,200)
        for file in ["main.py","app_core.py",".env","private_key.pem","otenki_data.json","otenki_data.json.bak"]:
            self.assertEqual(self.req("/"+file).status_code,404,file)
    def test_health_and_nocache(self):
        r=self.req("/api/health")
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.headers.get("Cache-Control"),"no-store")
        self.assertEqual(r.get_json()["app"],"otenki")
    def test_friend_safety_hazards_privacy_and_disconnect(self):
        a=self.register("alpha_key","A");b=self.register("beta_key","B");c=self.register("charlie_key","C")
        search=self.req("/api/users/search?q=B",key="alpha_key").get_json()
        self.assertEqual(search["users"][0]["id"],b["id"])
        r=self.req("/api/friends/request","POST",{"user_id":b["id"]},"alpha_key")
        reqid=r.get_json()["request"]["id"]
        self.assertEqual(self.req(f"/api/friends/requests/{reqid}/accept","POST",{},"beta_key").status_code,200)
        for state in ["safe","messy","sos"]:
            self.assertEqual(self.req("/api/safety","POST",{"status":state},"alpha_key").status_code,200)
        self.assertEqual(len(self.req("/api/safety",key="beta_key").get_json()["statuses"]),3)
        self.assertEqual(self.req("/api/safety",key="charlie_key").get_json()["statuses"],[])
        for kind in ["danger","help"]:
            body={"kind":kind,"text":"試験場所","place_name":"試験","latitude":32.4,"longitude":130.1}
            self.assertEqual(self.req("/api/hazards","POST",body,"alpha_key").status_code,200)
        self.assertEqual(len(self.req("/api/hazards",key="beta_key").get_json()["posts"]),2)
        self.assertEqual(self.req("/api/hazards",key="charlie_key").get_json()["posts"],[])
        self.assertEqual(self.req("/api/friends/"+b["id"],"DELETE",key="alpha_key").status_code,200)
        self.assertEqual(self.req("/api/hazards",key="beta_key").get_json()["posts"],[])
    def test_reject_and_cancel_requests(self):
        a=self.register("alpha","A");b=self.register("beta","B")
        r=self.req("/api/friends/request","POST",{"user_id":b["id"]},"alpha")
        reqid=r.get_json()["request"]["id"]
        self.assertEqual(self.req(f"/api/friends/requests/{reqid}/reject","POST",{},"beta").status_code,200)
        r=self.req("/api/friends/request","POST",{"user_id":b["id"]},"alpha")
        reqid=r.get_json()["request"]["id"]
        self.assertEqual(self.req(f"/api/friends/requests/{reqid}/cancel","POST",{},"alpha").status_code,200)
    def test_push_registration_and_unsubscribe(self):
        self.register()
        sub={"endpoint":"https://fcm.googleapis.com/test-fixture","keys":{"p256dh":"test-public","auth":"test-auth"}}
        self.assertEqual(self.req("/api/push/subscribe","POST",{"subscription":sub},"ABC_key_123").status_code,200)
        self.assertEqual(self.req("/api/push/unsubscribe","POST",{"endpoint":sub["endpoint"]},"ABC_key_123").status_code,200)
    def test_key_missing_weather_does_not_break_login(self):
        self.mod.OPENWEATHER_API_KEY=""
        self.assertEqual(self.req("/api/weather/tomorrow").status_code,500)
        self.register()
        self.assertEqual(self.req("/api/account/login","POST",{"security_key":"ABC_key_123"}).status_code,200)
    def test_jma_standard_namespace_parser(self):
        xml=b"""<Report xmlns="http://xml.kishou.go.jp/jmaxml1/"><Head xmlns="http://xml.kishou.go.jp/jmaxml1/informationBasis1/"><Title>\xe9\x9c\x87\xe5\xba\xa6\xe9\x80\x9f\xe5\xa0\xb1</Title><EventID>test</EventID><InfoType>test</InfoType></Head><Body xmlns="http://xml.kishou.go.jp/jmaxml1/body/seismology1/"><Intensity><Observation><MaxInt>4</MaxInt></Observation></Intensity></Body></Report>"""
        response=type("R",(),{"content":xml,"raise_for_status":lambda self:None})()
        with patch.object(self.mod.requests,"get",return_value=response):
            result=self.mod.parse_jma_earthquake_xml("https://example.invalid/fixture")
        self.assertEqual(result["max_intensity"],4)
        self.assertEqual(result["event_id"],"test")
    def test_tomorrow_forecast_date_and_missing_probability(self):
        from datetime import datetime, timezone, timedelta
        self.mod.OPENWEATHER_API_KEY="test-only"
        tz=timezone(timedelta(hours=9))
        target=(datetime.now(tz)+timedelta(days=1)).replace(hour=12,minute=0,second=0,microsecond=0)
        data={"city":{"name":"test","timezone":32400},"list":[
          {"dt":int(target.timestamp()),"main":{"temp_min":19,"temp_max":25},"wind":{"speed":2},
           "weather":[{"description":"test weather"}]}]}
        response=type("R",(),{"ok":True,"status_code":200,"json":lambda self:data})()
        with patch.object(self.mod.requests,"get",return_value=response):
            r=self.req("/api/weather/tomorrow")
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.get_json()["date"],target.date().isoformat())
        self.assertIsNone(r.get_json()["pop"])
        self.assertTrue(r.get_json()["representative_time"].endswith("+09:00"))
if __name__=="__main__":unittest.main()
