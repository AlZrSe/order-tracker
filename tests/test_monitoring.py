import threading
import time
import pytest
import requests


APP_URL = "http://127.0.0.1:8000"
PROMETHEUS_URL = "http://127.0.0.1:9090"
GRAFANA_URL = "http://127.0.0.1:3000"
GRAFANA_AUTH = ("admin", "admin")


def wait_for_service(url: str, timeout: int = 30) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def prometheus_series(query: str) -> list:
    response = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={"query": query},
        timeout=5,
    )
    response.raise_for_status()
    return response.json()["data"]["result"]


def wait_for_prometheus(query: str, min_total: float = 0.0, timeout: int = 90) -> list:
    """Poll until Prometheus has scraped a matching series above min_total.

    scrape_interval is 15s, so a fixed short sleep is not enough to know a
    counter increment has actually been scraped. A series can also exist with
    value 0 before the increment lands, hence the min_total threshold.
    """
    deadline = time.time() + timeout
    result = []
    while time.time() < deadline:
        result = prometheus_series(query)
        if result and sum(float(s["value"][1]) for s in result) >= min_total:
            return result
        time.sleep(2)
    return result


def generate_500s(stop: "threading.Event", interval: float = 2.0) -> None:
    while not stop.is_set():
        try:
            requests.get(f"{APP_URL}/test/500", timeout=2)
        except Exception:
            pass
        stop.wait(interval)


@pytest.fixture(scope="session", autouse=True)
def ensure_services_running():
    assert wait_for_service(f"{APP_URL}/healthz"), "App not responding"
    assert wait_for_service(f"{PROMETHEUS_URL}/-/healthy"), "Prometheus not responding"
    assert wait_for_service(f"{GRAFANA_URL}/api/health"), "Grafana not responding"
    yield


def test_app_exposes_metrics():
    # A labeled series only exists once its route has been exercised, so drive
    # the traffic this test asserts on instead of relying on ambient requests.
    requests.get(f"{APP_URL}/api/orders/standard-1001", timeout=2)
    requests.get(f"{APP_URL}/api/orders/missing-order", timeout=2)

    response = requests.get(f"{APP_URL}/metrics")
    assert response.status_code == 200
    metrics_text = response.text
    assert "order_tracker_order_lookup_requests_total" in metrics_text
    assert 'route="/api/orders/{order_id}"' in metrics_text
    assert "status_code" in metrics_text


def test_prometheus_scrapes_app_metrics():
    query = 'order_tracker_order_lookup_requests_total{job="order-tracker"}'
    response = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={"query": query},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["data"]["result"]) > 0


def test_5xx_errors_increment_counter():
    query = 'increase(order_tracker_order_lookup_requests_total{job="order-tracker",status_code=~"5.."}[1m])'

    # A one-shot burst is invisible to increase(): if every 5xx lands before the
    # series' first sample, there is no delta between consecutive scrapes and
    # the series drops out of the result. Keep generating while we poll.
    stop = threading.Event()
    worker = threading.Thread(target=generate_500s, args=(stop,), daemon=True)
    worker.start()
    try:
        result = wait_for_prometheus(query, min_total=3)
    finally:
        stop.set()
        worker.join(timeout=5)

    total = sum(float(series["value"][1]) for series in result)
    assert total >= 3, f"Expected at least 3 5xx errors, got {total}"


def test_alert_rule_exists():
    response = requests.get(
        f"{GRAFANA_URL}/api/v1/provisioning/alert-rules",
        auth=GRAFANA_AUTH,
    )
    assert response.status_code == 200
    # This endpoint returns a flat list of rules, not groups with nested rules.
    rule_found = any(
        "High 5xx Error Rate" in rule.get("title", "") for rule in response.json()
    )
    assert rule_found, "Alert rule 'High 5xx Error Rate' not found in Grafana"


def test_alert_fires_on_5xx():
    query = 'sum(increase(order_tracker_order_lookup_requests_total{job="order-tracker",status_code=~"5.."}[1m])) by (route)'
    assert wait_for_prometheus(query, min_total=1), "No 5xx series scraped from the app within 90s"

    # Keep generating 5xx while we wait: the rule evaluates increase(...[1m]) > 0
    # and must hold that for `for: 30s`, so sustained errors are required to fire.
    stop = threading.Event()
    worker = threading.Thread(target=generate_500s, args=(stop,), daemon=True)
    worker.start()
    try:
        deadline = time.time() + 120
        firing = False
        while time.time() < deadline:
            response = requests.get(
                f"{GRAFANA_URL}/api/alertmanager/grafana/api/v2/alerts",
                auth=GRAFANA_AUTH,
            )
            assert response.status_code == 200
            if any(
                "High 5xx Error Rate" in alert.get("labels", {}).get("alertname", "")
                for alert in response.json()
            ):
                firing = True
                break
            time.sleep(5)
    finally:
        stop.set()
        worker.join(timeout=5)

    assert firing, "Alert 'High 5xx Error Rate' should be firing"