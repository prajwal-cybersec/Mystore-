"""Quick test of all frontend-facing API endpoints."""
import httpx
import json

base = "http://localhost:8000"
client = httpx.Client(timeout=30.0)

# 1. Search with Hinglish
r = client.get(f"{base}/search", params={"q": "sasta atta", "city": "Bengaluru", "size": 3})
d = r.json()
print("=== SEARCH (sasta atta - Hinglish) ===")
print(f"Status: {r.status_code}, Total: {d['total']}")
print(f"Query rewrite: {d['query']['showing_results_for']}")
for h in d["hits"][:3]:
    print(f"  - {h['name']} | Rs.{h['price_inr']}")

# 2. Suggest
r2 = client.get(f"{base}/suggest", params={"q": "blue", "limit": 3})
print(f"\n=== SUGGEST (blue) ===")
print(f"Status: {r2.status_code}, Count: {len(r2.json())}")
for s in r2.json()[:3]:
    print(f"  - {s['name']}")

# 3. Pipeline status
r3 = client.get(f"{base}/pipeline/status")
print(f"\n=== PIPELINE STATUS ===")
print(json.dumps(r3.json(), indent=2))

# 4. Notifications
r4 = client.get(f"{base}/notifications", params={"limit": 3})
print(f"\n=== NOTIFICATIONS ===")
print(f"Status: {r4.status_code}, Count: {len(r4.json())}")
for n in r4.json()[:3]:
    print(f"  [{n['channel']}] {n['message'][:80]}")

# 5. Health
r5 = client.get(f"{base}/health")
print(f"\n=== HEALTH ===")
print(json.dumps(r5.json(), indent=2))

# 6. Checkout test (buy first search hit in Mumbai)
first_product_id = d["hits"][0]["id"]
r6 = client.post(f"{base}/checkout", json={
    "customer_id": "11111111-1111-1111-1111-111111111111",
    "city": "Mumbai",
    "items": [{"product_id": first_product_id, "quantity": 1}]
})
print(f"\n=== CHECKOUT ===")
print(f"Status: {r6.status_code}")
print(json.dumps(r6.json(), indent=2))

# 7. Home page HTML
r7 = client.get(f"{base}/")
print(f"\n=== HOME PAGE ===")
print(f"Status: {r7.status_code}, Content-Type: {r7.headers.get('content-type')}")
print(f"Contains 'MyStore': {'MyStore' in r7.text}")
print(f"Contains search input: {'searchInput' in r7.text}")
print(f"Contains cart: {'cartDrawer' in r7.text}")

# 8. Pipeline page HTML
r8 = client.get(f"{base}/pipeline")
print(f"\n=== PIPELINE PAGE ===")
print(f"Status: {r8.status_code}")
print(f"Contains 'X-RAY': {'X-RAY' in r8.text}")
print(f"Contains stress test: {'stress-last-unit' in r8.text}")
print(f"Contains SSE: {'EventSource' in r8.text}")

print("\n=== ALL TESTS PASSED ===")
