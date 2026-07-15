# MedSort Dashboard

Live inventory dashboard for the Automated Medicine Segregation and Inventory System.
The Raspberry Pi calls a REST API every time it sorts a medicine; the website updates in real time.

```
Camera + Classifier (Raspberry Pi)
        │  POST /api/sort  {medicine, confidence}
        ▼
   Flask backend (this project)
        │  stores count in SQLite
        ▼
   Dashboard (auto-refreshes every 3s)
```

## 1. Run it locally (in VS Code)

```bash
cd medsort-dashboard
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000** — you'll see 5 empty bins (Biogesic, Neozep, Medicol Advance,
Allerta, Tuseran Forte).

Test it without any hardware by sending a fake sort event from a second terminal:

```bash
curl -X POST http://localhost:5000/api/sort \
  -H "Content-Type: application/json" \
  -d '{"api_key": "changeme-dev-key", "medicine": "Biogesic", "confidence": 0.93}'
```

Refresh (or just watch — it polls automatically) and you'll see Bin 01's count go up, a new
row in the sort log, and the distribution bar update.

## 2. Wire up the Raspberry Pi

Open `raspberry_pi/pi_client_example.py`. Copy the `report_sort()` function into your existing
sorting script (the one that already talks to the ESP32) and call it right after your
classifier produces a label:

```python
from pi_client_example import report_sort

label, confidence = classify_medicine(image)   # your existing ResNet/OpenCV code
send_sort_command_to_esp32(label)               # your existing ESP32 code
report_sort(label, confidence)                  # <-- new: tell the dashboard
```

`report_sort()` never raises — if the internet or dashboard is down, it just logs and returns
`False`, so it can't stall your physical sorting loop.

## 3. Deploy it online

**Render.com (free tier, easiest)**
1. Push this folder to a GitHub repo.
2. On Render: New → Web Service → connect the repo.
3. Build command: `pip install -r requirements.txt`
   Start command: `gunicorn app:app`
4. Add environment variable `MEDSORT_API_KEY` = a real secret you choose.
5. Deploy. Render gives you a URL like `https://medsort-dashboard.onrender.com`.

**PythonAnywhere** also works well and has a generous always-on free tier for small Flask apps
if you'd rather not use GitHub.

Once deployed:
- Update `DASHBOARD_URL` and `API_KEY` in `raspberry_pi/pi_client_example.py` on the Pi.
- Make sure the Pi has internet access (Wi-Fi is fine).

## 4. Notes on the database

- Counts persist in `instance/inventory.db` (SQLite) — good for a school project / single demo unit.
- If you later need multiple sorting stations or want data to survive redeploys on Render's free
  tier (which wipes local disk on restart), swap SQLite for a hosted Postgres database — Render
  offers a free one. Only `get_db()`/`init_db()` in `app.py` would need to change.

## Stock alerts (out of stock / running low)

Each medicine has a **low-stock threshold** (default 10 units, editable per medicine). The
dashboard shows a red/amber banner automatically:
- **Out of stock** — count is 0
- **Running low** — count is at or below its threshold, but above 0
- **In stock** — everything else

`count` only goes up when the Pi sorts a medicine in. To see the alerts actually trigger over
time, something needs to take stock *out* too — use the **"− Dispense"** button on each bin
card (simulates a pharmacist handing out N units), or call `/api/dispense` directly from your
own dispensing script if you build one later.

## API reference

| Method | Endpoint          | Purpose                                          |
|--------|-------------------|---------------------------------------------------|
| POST   | `/api/sort`       | Pi reports one sorted medicine (count +1)          |
| POST   | `/api/dispense`   | Record medicine taken out (count −quantity)        |
| POST   | `/api/threshold`  | Set the low-stock warning level for one medicine   |
| GET    | `/api/inventory`  | Current count, threshold, and status per medicine  |
| GET    | `/api/history?limit=25` | Recent sort events                           |
| POST   | `/api/reset`      | Zero all counts (demo/testing)                     |

## Notes on security

The demo API key (`changeme-dev-key`) is visible in `static/dashboard.js` so the "Dispense"
button works out of the box — fine for a local demo or closed school network. Before putting
this in front of real patients/pharmacy staff, put dispensing behind a proper login (e.g.
Flask-Login) instead of a client-visible key, since anyone who opens the page's source can see
that key.
