"""
simulate_outage.py — Mock RDBMS + MCP failure simulation.

Sends 300 signals across 3 failure scenarios.
Thanks to debouncing, only 3 Work Items should be created (not 300).

Usage:
    python scripts/simulate_outage.py
"""

import json
import time
import urllib.request

BASE = "http://localhost:8000"


def api(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        r = urllib.request.urlopen(req)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": json.loads(e.read())}


# ── Define 3 failure scenarios ───────────────────────────────────────────

SCENARIOS = [
    {
        "name": "PostgreSQL Primary Failover",
        "count": 100,
        "signal": {
            "source": "prometheus",
            "severity": "P0",
            "title": "PostgreSQL Primary Node Unreachable",
            "description": "Connection refused on pg-primary:5432. "
                           "Replication lag exceeding 30s. "
                           "Automated failover initiated.",
        },
    },
    {
        "name": "Redis Cluster Split-Brain",
        "count": 100,
        "signal": {
            "source": "datadog",
            "severity": "P0",
            "title": "Redis Cluster Split-Brain Detected",
            "description": "Nodes redis-01 and redis-02 disagree on master. "
                           "CLUSTER INFO shows cluster_state:fail. "
                           "Cache writes are being rejected.",
        },
    },
    {
        "name": "API Gateway Certificate Expiry",
        "count": 100,
        "signal": {
            "source": "cloudwatch",
            "severity": "P1",
            "title": "TLS Certificate Expired on API Gateway",
            "description": "Certificate for api.example.com expired at "
                           "2026-04-30T00:00:00Z. All HTTPS connections "
                           "failing with ERR_CERT_DATE_INVALID.",
        },
    },
]


def run_simulation():
    print("=" * 60)
    print("  IMS Outage Simulation")
    print("  Sending 300 signals across 3 failure scenarios")
    print("  Expected: 3 Work Items (not 300)")
    print("=" * 60)

    # Check health first
    health = api("GET", "/health")
    print(f"\nHealth: {health.get('status', 'unknown')}")
    if health.get("status") != "healthy":
        print("ERROR: Backend is not healthy. Start it first.")
        return

    # Count existing incidents
    before = api("GET", "/incidents")
    before_count = len(before) if isinstance(before, list) else 0
    print(f"Incidents before simulation: {before_count}")

    # Send signals for each scenario
    total_sent = 0
    for scenario in SCENARIOS:
        name = scenario["name"]
        count = scenario["count"]
        signal = scenario["signal"]

        print(f"\n--- Scenario: {name} ---")
        print(f"    Sending {count} signals...")

        for i in range(count):
            sig = dict(signal)
            sig["description"] = f"[{i+1}/{count}] {sig['description']}"
            r = api("POST", "/ingest", sig)
            total_sent += 1

            # Print progress every 25 signals
            if (i + 1) % 25 == 0:
                print(f"    Sent {i+1}/{count}...")

        print(f"    Done. {count} signals sent.")

    # Wait for processor to consume the queue
    print(f"\nTotal signals sent: {total_sent}")
    print("Waiting 5 seconds for signal processor to finish...")
    time.sleep(5)

    # Count incidents after
    after = api("GET", "/incidents")
    after_list = after if isinstance(after, list) else []
    after_count = len(after_list)
    new_count = after_count - before_count

    print(f"\nIncidents after simulation: {after_count}")
    print(f"NEW incidents created: {new_count}")

    # Show the new incidents
    print("\n--- New Incidents ---")
    for inc in after_list:
        print(f"  [{inc['severity']}] {inc['title']}")
        print(f"       Status: {inc['status']} | Signals: {inc['signal_count']} | Source: {inc['source']}")

    # Verdict
    print("\n" + "=" * 60)
    if new_count <= 3:
        print(f"  [PASS] {total_sent} signals -> {new_count} Work Items")
        print(f"  Debouncing reduced noise by {((total_sent - new_count) / total_sent * 100):.0f}%")
    else:
        print(f"  [WARN] Expected 3 Work Items, got {new_count}")
        print(f"  Check if debounce window is too short")
    print("=" * 60)


if __name__ == "__main__":
    run_simulation()
