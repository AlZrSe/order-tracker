import urllib.request
import json
import urllib.parse

# Check increase over 1 minute
query = 'increase(order_tracker_http_server_duration_milliseconds_count{job="otel-collector",http_status_code=~"5..",exported_instance="d599713c-efc1-4ee2-aae4-bb1e77a1622b"}[1m])'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('5xx increase:', json.dumps(data, indent=2))

# Check total increase
query = 'increase(order_tracker_http_server_duration_milliseconds_count{job="otel-collector",exported_instance="d599713c-efc1-4ee2-aae4-bb1e77a1622b"}[1m])'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('Total increase:', json.dumps(data, indent=2))