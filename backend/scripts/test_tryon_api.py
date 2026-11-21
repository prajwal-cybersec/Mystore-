import urllib.request
import json

def run_checks():
    def req(url, data=None):
        r = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8') if data else None,
            headers={'Content-Type': 'application/json'} if data else {}
        )
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read().decode('utf-8')

    # 1. Health
    st, _ = req("http://localhost:8000/health")
    print(f"[CHECK 1] Health: {st}")

    # 2. Search
    st, body = req("http://localhost:8000/search?city=Bengaluru&size=20")
    data = json.loads(body)
    hits = data.get("hits", [])
    print(f"[CHECK 2] Hits returned: {len(hits)}")
    supported = [h for h in hits if h.get("tryon_supported")]
    print(f"[CHECK 2] Try-On supported products in catalogue: {len(supported)}")
    for s in supported:
        print(f"  - {s['sku']}: type={s.get('tryon_type')} asset={s.get('tryon_asset')} config={s.get('tryon_config')}")

    # 3. Calibrate
    st, body = req("http://localhost:8000/api/tryon/calibrate/FAS-0002", {
        "tryon_config": {"scale": 1.05, "scaleX": 1.0, "scaleY": 1.0, "offsetX": 0, "offsetY": 8, "rotation": 0, "opacity": 1.0}
    })
    print(f"[CHECK 3] Calibrate POST: {st} -> {json.loads(body).get('message')}")

    # 4. Analytics event
    st, body = req("http://localhost:8000/api/tryon/events", {
        "event_type": "tryon_started",
        "product_id": "FAS-0002",
        "sku": "FAS-0002",
        "tryon_type": "tshirt"
    })
    print(f"[CHECK 4] Event POST: {st} -> {body}")

    # 5. Stats
    st, body = req("http://localhost:8000/api/tryon/stats")
    print(f"[CHECK 5] Stats GET: {st} -> {body}")

if __name__ == "__main__":
    run_checks()
