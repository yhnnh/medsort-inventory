const ACCENTS = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)"];
const POLL_MS = 3000;

// Must match MEDSORT_API_KEY on the server. Fine for a local demo; for a
// real deployment, put dispensing behind a staff login instead of a
// client-side key (see README "Notes on security").
const CLIENT_API_KEY = "changeme-dev-key";

const binsEl = document.getElementById("bins");
const feedEl = document.getElementById("feed");
const distEl = document.getElementById("dist");
const totalCountEl = document.getElementById("totalCount");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const clockEl = document.getElementById("clock");
const resetBtn = document.getElementById("resetBtn");

let lastCounts = {}; // medicine -> count, to detect changes for pulse animation
let binCardEls = {}; // medicine -> DOM node

function tickClock() {
  clockEl.textContent = new Date().toLocaleTimeString();
}
setInterval(tickClock, 1000);
tickClock();

function setStatus(ok) {
  statusDot.classList.toggle("live", ok);
  statusDot.classList.toggle("down", !ok);
  statusText.textContent = ok ? "live" : "offline — retrying";
}

const STATUS_LABEL = {
  ok: "In stock",
  low_stock: "Low stock",
  out_of_stock: "Out of stock",
};

function buildBinCards(items) {
  binsEl.innerHTML = "";
  binCardEls = {};
  items.forEach((item, i) => {
    const accent = ACCENTS[i % ACCENTS.length];
    const card = document.createElement("div");
    card.className = "bin-card";
    card.dataset.medicine = item.medicine;
    card.style.setProperty("--accent", accent);
    card.innerHTML = `
      <div class="bin-top">
        <div>
          <div class="bin-number">BIN ${String(item.bin_number).padStart(2, "0")}</div>
          <div class="bin-name">${item.medicine}</div>
          <div class="bin-generic">${item.generic}</div>
        </div>
        <span class="status-badge">In stock</span>
      </div>
      <div class="bin-gauge">
        <div class="bin-gauge-fill" style="height:0%"></div>
      </div>
      <div class="bin-bottom">
        <div>
          <div class="bin-count">0</div>
          <div class="bin-count-label">units on hand</div>
        </div>
        <button class="dispense-btn" title="Record medicine taken out of this bin">− Dispense</button>
      </div>
      <div class="bin-threshold">reorder at ≤ ${item.low_stock_threshold}</div>
    `;
    card.querySelector(".dispense-btn").addEventListener("click", () => dispense(item.medicine));
    binsEl.appendChild(card);
    binCardEls[item.medicine] = card;
  });
}

async function dispense(medicine) {
  const qtyRaw = prompt(`Dispense how many units of ${medicine}?`, "1");
  if (qtyRaw === null) return;
  const quantity = parseInt(qtyRaw, 10);
  if (!Number.isInteger(quantity) || quantity <= 0) {
    alert("Enter a positive whole number.");
    return;
  }
  try {
    const res = await fetch("/api/dispense", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: CLIENT_API_KEY, medicine, quantity }),
    });
    if (res.ok) {
      poll();
    } else {
      const err = await res.json();
      alert("Dispense failed: " + (err.error || res.status));
    }
  } catch {
    alert("Could not reach the server.");
  }
}

function updateBins(items) {
  const maxCount = Math.max(1, ...items.map((i) => i.count));

  items.forEach((item) => {
    const card = binCardEls[item.medicine];
    if (!card) return;
    const fill = card.querySelector(".bin-gauge-fill");
    const countEl = card.querySelector(".bin-count");
    const badge = card.querySelector(".status-badge");
    const thresholdEl = card.querySelector(".bin-threshold");

    const pct = Math.min(100, (item.count / maxCount) * 100);
    fill.style.height = pct + "%";
    countEl.textContent = item.count;
    thresholdEl.textContent = `reorder at ≤ ${item.low_stock_threshold}`;

    badge.textContent = STATUS_LABEL[item.status] || "In stock";
    card.classList.remove("status-ok", "status-low", "status-out");
    card.classList.add(
      item.status === "out_of_stock" ? "status-out" : item.status === "low_stock" ? "status-low" : "status-ok"
    );

    if (lastCounts[item.medicine] !== undefined && item.count > lastCounts[item.medicine]) {
      card.classList.add("pulse");
      setTimeout(() => card.classList.remove("pulse"), 900);
    }
    lastCounts[item.medicine] = item.count;
  });

  renderAlerts(items);

  const total = items.reduce((sum, i) => sum + i.count, 0);
  totalCountEl.textContent = `${total} total`;

  distEl.innerHTML = "";
  items.forEach((item, i) => {
    const accent = ACCENTS[i % ACCENTS.length];
    const pct = total > 0 ? (item.count / total) * 100 : 0;
    const row = document.createElement("div");
    row.className = "dist-row";
    row.style.setProperty("--row-accent", accent);
    row.innerHTML = `
      <div class="dist-label">${item.medicine}</div>
      <div class="dist-track"><div class="dist-fill" style="width:${pct}%"></div></div>
      <div class="dist-value">${item.count}</div>
    `;
    distEl.appendChild(row);
  });
}

const alertsEl = document.getElementById("alerts");

function renderAlerts(items) {
  const outOfStock = items.filter((i) => i.status === "out_of_stock");
  const lowStock = items.filter((i) => i.status === "low_stock");

  if (outOfStock.length === 0 && lowStock.length === 0) {
    alertsEl.innerHTML = "";
    alertsEl.classList.remove("has-alerts");
    return;
  }

  alertsEl.classList.add("has-alerts");
  let html = "";

  if (outOfStock.length > 0) {
    html += `<div class="alert-group out">
      <div class="alert-title">Out of stock — ${outOfStock.length}</div>
      <div class="alert-chips">
        ${outOfStock.map((i) => `<span class="alert-chip">${i.medicine}</span>`).join("")}
      </div>
    </div>`;
  }
  if (lowStock.length > 0) {
    html += `<div class="alert-group low">
      <div class="alert-title">Running low — ${lowStock.length}</div>
      <div class="alert-chips">
        ${lowStock.map((i) => `<span class="alert-chip">${i.medicine} (${i.count} left)</span>`).join("")}
      </div>
    </div>`;
  }
  alertsEl.innerHTML = html;
}

function timeAgoLabel(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function updateFeed(events, medicineToBin) {
  if (!events.length) return;
  feedEl.innerHTML = "";
  events.forEach((ev) => {
    const idx = (ev.bin_number - 1) % ACCENTS.length;
    const row = document.createElement("div");
    row.className = "feed-row";
    row.style.setProperty("--row-accent", ACCENTS[idx]);
    row.innerHTML = `
      <span class="feed-time">${timeAgoLabel(ev.timestamp)}</span>
      <span class="feed-med">${ev.medicine}</span>
      <span class="feed-bin">BIN ${String(ev.bin_number).padStart(2, "0")}</span>
    `;
    feedEl.appendChild(row);
  });
}

let initialized = false;

async function poll() {
  try {
    const [invRes, histRes] = await Promise.all([
      fetch("/api/inventory"),
      fetch("/api/history?limit=20"),
    ]);
    if (!invRes.ok || !histRes.ok) throw new Error("bad response");

    const inventory = await invRes.json();
    const history = await histRes.json();

    if (!initialized) {
      buildBinCards(inventory);
      initialized = true;
    }
    updateBins(inventory);
    updateFeed(history);
    setStatus(true);
  } catch (err) {
    setStatus(false);
  }
}

resetBtn.addEventListener("click", async () => {
  const key = prompt("Enter API key to confirm reset:");
  if (key === null) return;
  try {
    const res = await fetch("/api/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key }),
    });
    if (res.ok) {
      lastCounts = {};
      poll();
    } else {
      alert("Reset failed — check the API key.");
    }
  } catch {
    alert("Could not reach the server.");
  }
});

poll();
setInterval(poll, POLL_MS);
