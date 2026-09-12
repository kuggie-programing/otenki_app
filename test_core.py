
import unittest, tempfile, json, threading, base64, os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from app_core import JsonStore, DataStoreError, normalize_key, hash_key, decode_key_header, find_account, resolve_data_path

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"db.json"
        self.store=JsonStore(self.path,{"users":{},"friendships":{},"events":[]})
    def tearDown(self):self.tmp.cleanup()
    def test_exact_unicode_keys_and_legacy_hash(self):
        for key in ["ABC-abc-123", "ひみつのキー１２３🔑", "é-key", "a b"]:
            digest=hash_key(key)
            data={"users":{"user":{"name":"試験","security_key_hash":digest}}}
            self.assertEqual(find_account(data,key)["id"],"user")
            self.assertIsNone(find_account(data,key+"x"))
    def test_encoded_header_roundtrip(self):
        for key in ["ASCII_key","ひみつ１２３🔑"]:
            encoded=base64.b64encode(key.encode()).decode()
            self.assertEqual(decode_key_header({"X-Security-Key-Encoded":encoded}),key)
    def test_invalid_headers_rejected(self):
        for value in ["!!!!","a","/w=="]:
            self.assertEqual(decode_key_header({"X-Security-Key-Encoded":value}),"")
    def test_legacy_header(self):
        self.assertEqual(decode_key_header({"X-Security-Key":" abc "}),"abc")
        self.assertEqual(decode_key_header({"Authorization":"Bearer abc"}),"abc")
    def test_key_is_case_sensitive(self):
        self.assertNotEqual(hash_key("ABC"),hash_key("abc"))
        self.assertNotEqual(hash_key("１２３"),hash_key("123"))
    def test_input_validation(self):
        for v in [None,[],12,""," "*4,"a\nb","x"*257]:
            with self.assertRaises(ValueError):normalize_key(v)
        self.assertEqual(normalize_key(" \ufeff abc \ufeff "),"abc")
    def test_existing_data_survives_initialization(self):
        data=self.store.read();data["users"]["old"]={"security_key_hash":hash_key("old")};data["unknown_field"]="keep"
        self.store.write(data);before=self.path.read_bytes()
        self.store.ensure();self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.store.read()["unknown_field"],"keep")
    def test_corrupt_file_is_never_reset(self):
        self.path.write_text("{broken")
        with self.assertRaises(DataStoreError):self.store.read()
        with self.assertRaises(DataStoreError):self.store.write({"users":{},"friendships":{},"events":[]})
        self.assertEqual(self.path.read_text(),"{broken")
    def test_wrong_schema_is_never_reset(self):
        self.path.write_text('{"users":[]}')
        with self.assertRaises(DataStoreError):self.store.read()
        self.assertEqual(self.path.read_text(),'{"users":[]}')
    def test_backup_before_change(self):
        d=self.store.read();d["users"]["a"]={};self.store.write(d)
        d["users"]["b"]={};self.store.write(d)
        backup=json.loads(self.path.with_name("db.json.bak").read_text())
        self.assertIn("a",backup["users"]);self.assertNotIn("b",backup["users"])
    def test_parallel_transactions(self):
        def task(i):
            with self.store.lock:
                d=self.store.read();d["users"][str(i)]={"id":i};self.store.write(d)
        with ThreadPoolExecutor(max_workers=8) as executor:list(executor.map(task,range(50)))
        self.assertEqual(len(self.store.read()["users"]),50)
    def test_restart_reads_same_data(self):
        d=self.store.read();d["users"]["a"]={"security_key_hash":hash_key("key")};self.store.write(d)
        second=JsonStore(self.path,self.store.defaults)
        self.assertEqual(find_account(second.read(),"key")["id"],"a")
    def test_data_path_not_working_directory(self):
        with tempfile.TemporaryDirectory() as d:
            original=os.getcwd()
            try:
                os.chdir(d)
                self.assertEqual(resolve_data_path(self.tmp.name),Path(self.tmp.name)/"otenki_data.json")
                self.assertEqual(resolve_data_path(self.tmp.name,"data/live.json"),Path(self.tmp.name)/"data/live.json")
            finally:os.chdir(original)
    def test_nonfinite_data_not_written(self):
        self.store.ensure();before=self.path.read_bytes()
        data=self.store.read();data["number"]=float("nan")
        with self.assertRaises(DataStoreError):self.store.write(data)
        self.assertEqual(self.path.read_bytes(),before)
if __name__=="__main__":unittest.main()
