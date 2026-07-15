"""
Automated Medicine Segregation & Inventory System — Dashboard Backend
-----------------------------------------------------------------------
Flask REST API + web dashboard.

The Raspberry Pi (or ESP32) calls POST /api/sort every time a medicine
is classified and dropped into a bin. This app stores the running
count per medicine/bin in SQLite and serves a live dashboard.

Run locally:
    pip install -r requirements.txt
    python app.py
Then open http://localhost:5000
"""

import os
import sqlite3
from datetime import datetime, timezone

from flask import Flask, g, jsonify, render_template, request

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "inventory.db")

# The five medicines this system is built to sort. Adjust freely —
# nothing else in the code needs to change if you add/remove one.
# "threshold" = low-stock warning level (count at or below this = "Low stock").
KNOWN_MEDICINES = [
    {"name": "Biogesic",       "generic": "Paracetamol",     "bin": 1, "threshold": 10},
    {"name": "Amoxil",         "generic": "Amoxicillin",     "bin": 2, "threshold": 10},
    {"name": "Medicol Advance","generic": "Ibuprofen",       "bin": 3, "threshold": 10},
    {"name": "Allerta",        "generic": "Cetirizine",      "bin": 4, "threshold": 10},
    {"name": "Dolfenal",       "generic": "Mefenamic Acid",  "bin": 5, "threshold": 10},
]

# Optional shared-secret so random people on the internet can't spam
# your sort counts. Set this as an env var on your host, and set the
# same value in raspberry_pi/pi_client_example.py
API_KEY = os.environ.get("MEDSORT_API_KEY", "changeme-dev-key")

app = Flask(__name__)


# ----------------------------------------------------------------------
# Database helpers
# ----------------------------------------------------------------------
def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            medicine            TEXT PRIMARY KEY,
            generic             TEXT NOT NULL,
            bin_number          INTEGER NOT NULL,
            count               INTEGER NOT NULL DEFAULT 0,
            low_stock_threshold INTEGER NOT NULL DEFAULT 10,
            updated_at          TEXT
        )
        """
    )
    # Migration safety net: if an older database already exists without
    # this column, add it rather than crash.
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(inventory)")}
    if "low_stock_threshold" not in existing_cols:
        conn.execute("ALTER TABLE inventory ADD COLUMN low_stock_threshold INTEGER NOT NULL DEFAULT 10")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sort_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            medicine   TEXT NOT NULL,
            bin_number INTEGER NOT NULL,
            confidence REAL,
            timestamp  TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dispense_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            medicine   TEXT NOT NULL,
            bin_number INTEGER NOT NULL,
            quantity   INTEGER NOT NULL,
            timestamp  TEXT NOT NULL
        )
        """
    )
    # Seed the five known medicines if not already present
    for med in KNOWN_MEDICINES:
        conn.execute(
            """
            INSERT OR IGNORE INTO inventory (medicine, generic, bin_number, count, low_stock_threshold, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
            """,
            (med["name"], med["generic"], med["bin"], med.get("threshold", 10), datetime.now(timezone.utc).isoformat()),
        )
    conn.commit()
    conn.close()


# ----------------------------------------------------------------------
# Routes — Dashboard (HTML)
# ----------------------------------------------------------------------
@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# ----------------------------------------------------------------------
# Routes — REST API
# ----------------------------------------------------------------------
@app.route("/api/sort", methods=["POST"])
def record_sort():
    """
    Called by the Raspberry Pi every time it sorts one medicine.

    Expected JSON body:
    {
        "api_key": "changeme-dev-key",
        "medicine": "Biogesic",
        "confidence": 0.94        # optional, from the classifier
    }
    """
    data = request.get_json(silent=True) or {}

    if data.get("api_key") != API_KEY:
        return jsonify({"error": "invalid api_key"}), 401

    medicine = data.get("medicine")
    confidence = data.get("confidence")

    db = get_db()
    row = db.execute(
        "SELECT * FROM inventory WHERE medicine = ?", (medicine,)
    ).fetchone()

    if row is None:
        return jsonify({"error": f"unknown medicine '{medicine}'"}), 400

    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        "UPDATE inventory SET count = count + 1, updated_at = ? WHERE medicine = ?",
        (now, medicine),
    )
    db.execute(
        "INSERT INTO sort_events (medicine, bin_number, confidence, timestamp) VALUES (?, ?, ?, ?)",
        (medicine, row["bin_number"], confidence, now),
    )
    db.commit()

    updated = db.execute(
        "SELECT * FROM inventory WHERE medicine = ?", (medicine,)
    ).fetchone()

    return jsonify(
        {
            "medicine": updated["medicine"],
            "bin_number": updated["bin_number"],
            "new_count": updated["count"],
            "timestamp": now,
        }
    ), 201


def stock_status(count: int, threshold: int) -> str:
    if count <= 0:
        return "out_of_stock"
    if count <= threshold:
        return "low_stock"
    return "ok"


@app.route("/api/inventory", methods=["GET"])
def get_inventory():
    db = get_db()
    rows = db.execute(
        """
        SELECT medicine, generic, bin_number, count, low_stock_threshold, updated_at
        FROM inventory ORDER BY bin_number
        """
    ).fetchall()

    result = []
    for r in rows:
        item = dict(r)
        item["status"] = stock_status(item["count"], item["low_stock_threshold"])
        result.append(item)
    return jsonify(result)


@app.route("/api/history", methods=["GET"])
def get_history():
    limit = request.args.get("limit", default=25, type=int)
    db = get_db()
    rows = db.execute(
        "SELECT medicine, bin_number, confidence, timestamp FROM sort_events ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/dispense", methods=["POST"])
def record_dispense():
    """
    Call this when medicine is taken OUT of a bin (given to a patient,
    pulled for restocking a shelf, etc.) so stock levels actually go down
    and low-stock/out-of-stock alerts mean something over time.

    Expected JSON body:
    {
        "api_key": "changeme-dev-key",
        "medicine": "Biogesic",
        "quantity": 1        # optional, defaults to 1
    }
    """
    data = request.get_json(silent=True) or {}

    if data.get("api_key") != API_KEY:
        return jsonify({"error": "invalid api_key"}), 401

    medicine = data.get("medicine")
    quantity = data.get("quantity", 1)

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        return jsonify({"error": "quantity must be an integer"}), 400

    if quantity <= 0:
        return jsonify({"error": "quantity must be positive"}), 400

    db = get_db()
    row = db.execute("SELECT * FROM inventory WHERE medicine = ?", (medicine,)).fetchone()
    if row is None:
        return jsonify({"error": f"unknown medicine '{medicine}'"}), 400

    now = datetime.now(timezone.utc).isoformat()
    new_count = max(0, row["count"] - quantity)  # never go negative

    db.execute(
        "UPDATE inventory SET count = ?, updated_at = ? WHERE medicine = ?",
        (new_count, now, medicine),
    )
    db.execute(
        "INSERT INTO dispense_events (medicine, bin_number, quantity, timestamp) VALUES (?, ?, ?, ?)",
        (medicine, row["bin_number"], quantity, now),
    )
    db.commit()

    return jsonify(
        {
            "medicine": medicine,
            "bin_number": row["bin_number"],
            "new_count": new_count,
            "status": stock_status(new_count, row["low_stock_threshold"]),
            "timestamp": now,
        }
    ), 201


@app.route("/api/threshold", methods=["POST"])
def set_threshold():
    """
    Update the low-stock warning level for one medicine.

    Expected JSON body:
    {
        "api_key": "changeme-dev-key",
        "medicine": "Biogesic",
        "threshold": 15
    }
    """
    data = request.get_json(silent=True) or {}
    if data.get("api_key") != API_KEY:
        return jsonify({"error": "invalid api_key"}), 401

    medicine = data.get("medicine")
    threshold = data.get("threshold")

    try:
        threshold = int(threshold)
        if threshold < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "threshold must be a non-negative integer"}), 400

    db = get_db()
    row = db.execute("SELECT * FROM inventory WHERE medicine = ?", (medicine,)).fetchone()
    if row is None:
        return jsonify({"error": f"unknown medicine '{medicine}'"}), 400

    db.execute("UPDATE inventory SET low_stock_threshold = ? WHERE medicine = ?", (threshold, medicine))
    db.commit()
    return jsonify({"medicine": medicine, "low_stock_threshold": threshold}), 200


@app.route("/api/reset", methods=["POST"])
def reset_counts():
    """Zero out all counts — handy for demos. Protected by api_key too."""
    data = request.get_json(silent=True) or {}
    if data.get("api_key") != API_KEY:
        return jsonify({"error": "invalid api_key"}), 401

    db = get_db()
    db.execute("UPDATE inventory SET count = 0, updated_at = ?", (datetime.now(timezone.utc).isoformat(),))
    db.execute("DELETE FROM sort_events")
    db.commit()
    return jsonify({"status": "reset"}), 200


# ----------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
else:
    # Also init when imported by a WSGI server (gunicorn, etc.)
    init_db()
