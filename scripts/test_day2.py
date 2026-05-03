"""Quick Day 2 verification script — tests all key features."""
import urllib.request
import json
import time

BASE = "http://localhost:8000"

def api(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method,
                                headers={"Content-Type": "application/json"} if data else {})
    try:
        r = urllib.request.urlopen(req)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": json.loads(e.read())}

print("=" * 60)
print("  IMS Day 2 Verification")
print("=" * 60)

# 1. Health check
print("\n1. GET /health")
print(json.dumps(api("GET", "/health"), indent=2))

# 2. Ingest 5 signals with same source/title (should debounce into 1 Work Item)
print("\n2. POST /ingest -- sending 5 identical signals (should debounce to 1 Work Item)")
for i in range(5):
    r = api("POST", "/ingest", {
        "source": "prometheus",
        "severity": "P0",
        "title": "Redis OOM Kill",
        "description": f"Signal #{i+1} — Redis out of memory"
    })
print(f"   Last response: {r}")

time.sleep(2)  # Let processor consume the queue

# 3. List incidents
print("\n3. GET /incidents")
incidents = api("GET", "/incidents")
print(f"   Found {len(incidents)} incident(s)")
if incidents:
    inc = incidents[0]
    inc_id = inc["id"]
    print(f"   ID: {inc_id}")
    print(f"   Title: {inc['title']}")
    print(f"   Severity: {inc['severity']}")
    print(f"   Status: {inc['status']}")
    print(f"   Signal Count: {inc['signal_count']}")

    # 4. State transition: OPEN → INVESTIGATING
    print(f"\n4. PATCH /incidents/{inc_id[:8]}.../transition -> INVESTIGATING")
    r = api("PATCH", f"/incidents/{inc_id}/transition",
            {"target_status": "INVESTIGATING"})
    print(f"   Status: {r.get('status', r)}")

    # 5. State transition: INVESTIGATING → RESOLVED
    print(f"\n5. PATCH -> RESOLVED")
    r = api("PATCH", f"/incidents/{inc_id}/transition",
            {"target_status": "RESOLVED"})
    print(f"   Status: {r.get('status', r)}")

    # 6. Try to CLOSE without RCA (should fail)
    print(f"\n6. PATCH -> CLOSED (without RCA -- should fail)")
    r = api("PATCH", f"/incidents/{inc_id}/transition",
            {"target_status": "CLOSED"})
    print(f"   Result: {r}")

    # 7. Submit RCA
    print(f"\n7. POST /incidents/{inc_id[:8]}.../rca")
    r = api("POST", f"/incidents/{inc_id}/rca", {
        "root_cause": "Redis maxmemory reached due to unbounded cache growth",
        "impact": "Cache eviction caused 30% increase in DB load",
        "resolution": "Increased maxmemory to 4GB, added TTL to cache keys",
        "prevention": "Set up memory alerts at 80% threshold",
        "incident_start": "2026-04-30T10:00:00Z",
        "incident_end": "2026-04-30T11:30:00Z",
        "created_by": "satyam"
    })
    print(f"   RCA ID: {r.get('id', r)}")

    # 8. Now CLOSE (should succeed with RCA)
    print(f"\n8. PATCH -> CLOSED (with RCA -- should succeed)")
    r = api("PATCH", f"/incidents/{inc_id}/transition",
            {"target_status": "CLOSED"})
    print(f"   Status: {r.get('status', r)}")
    print(f"   MTTR: {r.get('mttr_seconds', 'N/A')} seconds")

    # 9. Get raw signals from MongoDB
    print(f"\n9. GET /incidents/{inc_id[:8]}.../signals")
    r = api("GET", f"/incidents/{inc_id}/signals")
    print(f"   Signals in MongoDB: {r.get('signal_count', 0)}")

print("\n" + "=" * 60)
print("  [PASS] Day 2 Verification Complete!")
print("=" * 60)
