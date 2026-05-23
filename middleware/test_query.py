import requests

url = "https://core2-middleware-337108994948.europe-west1.run.app/api/voice/query"
data = {
    "query": "",
    "context": {
        "temperature": 25.0,
        "humidity": 50,
        "tvoc": 0,
        "eco2": 400,
        "weather": {
            "current": {
                "temp": 12.0,
                "description": "clear sky"
            }
        }
    }
}
r = requests.post(url, json=data)
print(r.status_code)
print(r.text)
