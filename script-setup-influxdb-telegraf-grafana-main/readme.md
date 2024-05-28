## influx

#### setup influx db
```
docker-compose up
```

#### influx command
```
influx
use influx
show measurements
select * from mqtt_consumer order by time desc limit 20

select * from mqtt_consumer where topic =~ /status*/ order by time desc limit 5


delete from mqtt_consumer
```

#### set auto delete
```
CREATE RETENTION POLICY oneweek ON influx DURATION 168h0m REPLICATION 1 DEFAULT
SHOW RETENTION POLICIES ON influx
```


#### select data with nodejs
```
const axios = require('axios');
const FormData = require('form-data');
let data = new FormData();
data.append('q', 'select * from mqtt_consumer order by time limit 1');
data.append('db', 'influx');

let config = {
  method: 'post',
  maxBodyLength: Infinity,
  url: 'http://192.168.1.61:8086/query',
  headers: { 
    ...data.getHeaders()
  },
  data : data
};

axios.request(config)
.then((response) => {
  console.log(JSON.stringify(response.data));
})
.catch((error) => {
  console.log(error);
});
```

#### select data with python
```
import requests

url = "http://192.168.1.61:8086/query"

payload={'q': 'select * from mqtt_consumer order by time limit 1',
'db': 'influx'}
files=[]
headers = {}

response = requests.request("POST", url, headers=headers, data=payload, files=files)

print(response.json())
```