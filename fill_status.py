import urllib.request
import json

r = urllib.request.urlopen("http://127.0.0.1:8000/api/status", timeout=5)
d = json.loads(r.read().decode())
print("is_running:", d["is_running"])
fs = d.get("filler_status") or {}
print("filler status:", fs.get("status"))
print("filler running:", fs.get("running"))
