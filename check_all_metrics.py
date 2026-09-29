import urllib.request
import json
import urllib.parse

# Check all metrics with their labels
query = 'order_tracker_http_server_duration_milliseconds_count{job="otel-collector"}'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    for r in data['data']['result']:
        print(r['metric'])