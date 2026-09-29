import urllib.request
import json
import urllib.parse

# Check 5xx rate for current instance
query = 'sum(rate(order_tracker_http_server_duration_milliseconds_count{job="otel-collector",http_status_code=~"5..",exported_instance="2e127019-b0b8-4f20-a250-7661a9e5484d"}[5m])) by (http_target)'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('5xx rate current instance:', json.dumps(data, indent=2))

# Check total rate for current instance
query = 'sum(rate(order_tracker_http_server_duration_milliseconds_count{job="otel-collector",exported_instance="2e127019-b0b8-4f20-a250-7661a9e5484d"}[5m])) by (http_target)'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('Total rate current instance:', json.dumps(data, indent=2))