import urllib.request
import json
import urllib.parse

# Check 5xx rate
query = 'sum(rate(order_tracker_http_server_duration_milliseconds_count{job="otel-collector",http_status_code=~"5.."}[5m])) by (http_target)'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('5xx rate:', json.dumps(data, indent=2))

# Check total rate
query = 'sum(rate(order_tracker_http_server_duration_milliseconds_count{job="otel-collector"}[5m])) by (http_target)'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('Total rate:', json.dumps(data, indent=2))

# Check error ratio
query = 'sum(rate(order_tracker_http_server_duration_milliseconds_count{job="otel-collector",http_status_code=~"5.."}[5m])) by (http_target) / sum(rate(order_tracker_http_server_duration_milliseconds_count{job="otel-collector"}[5m])) by (http_target)'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('Error ratio:', json.dumps(data, indent=2))