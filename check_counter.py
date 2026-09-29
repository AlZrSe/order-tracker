import urllib.request
import json
import urllib.parse

# Check raw counter values
query = 'order_tracker_http_server_duration_milliseconds_count{job="otel-collector",exported_instance="d599713c-efc1-4ee2-aae4-bb1e77a1622b",http_status_code=~"5.."}'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    print('5xx counter:', json.dumps(data, indent=2))

# Check all counter values for the instance
query = 'order_tracker_http_server_duration_milliseconds_count{job="otel-collector",exported_instance="d599713c-efc1-4ee2-aae4-bb1e77a1622b"}'
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/query?query=' + urllib.parse.quote(query))
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    for r in data['data']['result']:
        target = r['metric'].get('http_target', 'N/A')
        status = r['metric'].get('http_status_code', 'N/A')
        print(f"  {target} {status}: {r['value'][1]}")