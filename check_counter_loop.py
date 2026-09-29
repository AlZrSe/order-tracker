import urllib.request
import json
import urllib.parse
import time

# Query counter multiple times
for i in range(5):
    query = 'order_tracker_http_server_duration_milliseconds_count{job="otel-collector",exported_instance="d599713c-efc1-4ee2-aae4-bb1e77a1622b",http_status_code=~"5..",http_target="/api/orders/{order_id}"}'
    req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        for r in data['data']['result']:
            print('Counter:', r['value'][1])
    time.sleep(10)