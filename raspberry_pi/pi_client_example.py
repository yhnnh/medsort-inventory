"""
Runs ON the Raspberry Pi. Call `report_sort(medicine, confidence)` right
after your ResNet/OpenCV classifier decides what medicine was just seen,
and right before (or after) you send the sorting command to the ESP32.

Install once on the Pi:
    pip install requests

Set the dashboard URL to your deployed site once it's online, e.g.
    https://medsort-dashboard.onrender.com
"""

import requests

DASHBOARD_URL = "https://your-deployed-site.example.com"  # <-- change after deploying
API_KEY = "changeme-dev-key"  # <-- must match MEDSORT_API_KEY on the server

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
# Example integration into your existing sort loop
# ------------------------------------------------------------------
if __name__ == "__main__":
    # This block simulates what your real loop already does:
    #   1. IR sensor triggers capture
    #   2. classifier (ResNet) returns a label + confidence
    #   3. ESP32 gets the sort command
    #   4. dashboard gets told about it (this call)

    classified_medicine = "Biogesic"   # <- replace with your model's output
    classifier_confidence = 0.94       # <- replace with your model's confidence score

    # send_sort_command_to_esp32(classified_medicine)   # your existing ESP32 code
    report_sort(classified_medicine, classifier_confidence)