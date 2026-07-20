"""
Runs ON the Raspberry Pi. Call `report_sort(medicine, confidence)` right
after your classifier decides what medicine was just seen, and right
after you send the sorting command to the ESP32.

Install once on the Pi:
    pip install requests
"""

import requests

DASHBOARD_URL = "https://medsort-inventory.onrender.com"
API_KEY = "medsort2026secret"  # must match MEDSORT_API_KEY set on Render

# Must match the "medicine" values used in app.py's KNOWN_MEDICINES
VALID_MEDICINES = {"Biogesic", "Neozep", "Medicol Advance", "Allerta", "Tuseran Forte"}


def report_sort(medicine: str, confidence: float = None, timeout: float = 3.0) -> bool:
    """
    Tell the dashboard a medicine was just sorted.
    Returns True on success, False on failure (never raises — a dashboard
    outage should not stop the physical sorting process).
    """
    if medicine not in VALID_MEDICINES:
        print(f"[dashboard] skipped unknown medicine label: {medicine!r}")
        return False

    payload = {"api_key": API_KEY, "medicine": medicine}
    if confidence is not None:
        payload["confidence"] = float(confidence)

    try:
        resp = requests.post(f"{DASHBOARD_URL}/api/sort", json=payload, timeout=timeout)
        if resp.status_code == 201:
            data = resp.json()
            print(f"[dashboard] {medicine} -> bin {data['bin_number']} (new count: {data['new_count']})")
            return True
        else:
            print(f"[dashboard] failed ({resp.status_code}): {resp.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"[dashboard] network error, will retry next cycle: {e}")
        return False


# ------------------------------------------------------------------
# Quick standalone test — run this file directly to confirm the Pi
# can actually reach the live dashboard before wiring it into the
# full classifier/ESP32 loop.
#     python pi_dashboard_client.py
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("Sending a test sort event to:", DASHBOARD_URL)
    ok = report_sort("Biogesic", 0.94, timeout=60)  # longer timeout in case Render is asleep
    print("Success!" if ok else "Failed — check DASHBOARD_URL / API_KEY / your internet connection.")