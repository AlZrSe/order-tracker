import urllib.request
import json
import base64

credentials = base64.b64encode(b'admin:admin').decode()
req = urllib.request.Request('http://127.0.0.1:3000/api/dashboards/uid/order-tracker-requests')
req.add_header('Authorization', 'Basic ' + credentials)
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    for panel in data['dashboard']['panels']:
        ds = panel.get('datasource', {})
        print('Panel {}: {} -> datasource: {}'.format(panel['id'], panel['title'], ds))