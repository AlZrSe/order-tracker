import urllib.request
import json
import urllib.parse

# Check if 5xx metrics exist
query = 'order_tracker_http_server_duration_milliseconds_count{job="otel-collector",http_status_code=~"5.."}'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('5xx metrics:', json.dumps(data, indent=2))

# Check 4xx metrics
query = 'order_tracker_http_server_duration_milliseconds_count{job="otel-collector",http_status_code=~"4.."}'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('4xx metrics:', json.dumps(data, indent=2))

# Check all http status codes
query = 'order_tracker_http_server_duration_milliseconds_count{job="otel-collector"}'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('All metrics:', json.dumps(data, indent=2))