import json
import urllib.request

try:
    r = urllib.request.urlopen("http://127.0.0.1:8000/", timeout=5)
    print(f"Server: HTTP {r.status}")
except Exception as e:
    print(f"Server: DOWN - {e}")

try:
    with open("discography_webapp/filler_status.json") as f:
        data = json.load(f)
        print(f"Filler: {data}")
except FileNotFoundError:
    print("Filler: not running")
