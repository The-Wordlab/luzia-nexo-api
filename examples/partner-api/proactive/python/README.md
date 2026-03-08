# Proactive API -- Python

Python examples for sending proactive messages via the Nexo Partner API.

- `proactive_messaging.py` -- List subscribers, get threads, send a proactive message (delivery notification use case).
- `lifestyle_demo_server.py` -- FastAPI demo server that sends scheduled lifestyle notifications.

```bash
pip install requests python-dotenv
cp ../.env.example ../.env   # fill in APP_ID, APP_SECRET, NEXO_API_URL
python proactive_messaging.py
```
