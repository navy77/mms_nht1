import requests

url = "http://192.168.1.61:8086/query"

payload={'q': 'select * from mqtt_consumer order by time limit 1',
'db': 'influx'}
files=[]
headers = {}

response = requests.request("POST", url, headers=headers, data=payload, files=files)

print(response.json())
