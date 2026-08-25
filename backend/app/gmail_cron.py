import os
import httpx

BASE_URL=os.getenv('KNOWN_BASE_URL','https://known-sbbp.onrender.com').rstrip('/')
SECRET=os.getenv('KNOWN_GMAIL_CRON_SECRET','')
if not SECRET:
    raise SystemExit('KNOWN_GMAIL_CRON_SECRET is required')
r=httpx.post(f'{BASE_URL}/api/internal/gmail/poll-all',headers={'X-Known-Cron-Secret':SECRET},timeout=120)
r.raise_for_status()
print(r.text)
