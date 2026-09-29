import urllib.request
import json
import urllib.parse

# Test Panel 1 query
query = 'sum(rate(order_tracker_http_server_duration_milliseconds_count{job="otel-collector"}[5m])) by (http_target, http_status_code)'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('Panel 1:', json.dumps(data, indent=2))

# Test Panel 3 query
query = 'histogram_quantile(0.95, sum(rate(order_tracker_http_server_duration_milliseconds_bucket{job="otel-collector"}[5m])) by (le, http_target))'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('Panel 3:', json.dumps(data, indent=2))

# Test Panel 4 query
query = 'sum(order_tracker_http_server_active_requests{job="otel-collector"})'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('Panel 4:', json.dumps(data, indent=2))