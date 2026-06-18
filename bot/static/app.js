const $ = (id) => document.getElementById(id);
const fmt = (n) => {
  n = Number(n) || 0;
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(0) + "K";
  return String(n);
};
async function api(path, method = "GET", body) {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body) opt.body = JSON.stringify(body);
  const r = await fetch("/api" + path, opt);
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.status === 204 ? null : r.json();
}

async function loadStrategies() {
  const list = await api("/strategies");
  $("run-strategy").innerHTML = list
    .map((s) => `<option value="${s.name}">${s.name}</option>`).join("");
}

async function loadSettings() {
  const [capital, bondDays, webhook, watchlist, curateDays] = await Promise.all([
    api("/config/capital"), api("/config/bond_days"), api("/config/notify_webhook"),
    api("/config/watchlist"), api("/config/curate_interval_days"),
  ]);
  if (capital.value != null) $("set-capital").value = capital.value;
  if (bondDays.value != null) $("set-bond-days").value = bondDays.value;
  if (webhook.value != null) $("set-webhook").value = webhook.value;
  if (watchlist.value != null) $("set-watchlist").value = watchlist.value;
  if (curateDays.value != null) $("set-curate-days").value = curateDays.value;
}

async function saveSettings() {
  const entries = [
    ["capital", $("set-capital").value.trim()],
    ["bond_days", $("set-bond-days").value.trim()],
    ["notify_webhook", $("set-webhook").value.trim()],
    ["watchlist", $("set-watchlist").value.trim()],
    ["curate_interval_days", $("set-curate-days").value.trim()],
  ];
  for (const [key, value] of entries) {
    if (value !== "") await api(`/config/${key}`, "POST", { value });
  }
  $("set-status").textContent = "saved " + new Date().toLocaleTimeString();
  refresh();
}

async function startRun() {
  const strategy = $("run-strategy").value;
  const budget_gp = parseInt($("run-budget").value || "0", 10);
  if (!budget_gp) return;
  await api("/runs", "POST", { strategy, budget_gp });
  $("run-budget").value = "";
  refresh();
}

function renderRuns(runs) {
  $("runs-body").innerHTML = runs.map((r) => `
    <tr><td>${r.strategy}</td><td>${fmt(r.budget_gp)}</td>
    <td>${fmt(r.spent_gp)}</td><td>${r.state}</td>
    <td>${r.state === "running"
      ? `<button class="btn ghost" onclick="stopRun(${r.id})">Stop</button>` : ""}</td></tr>`
  ).join("");
}
async function stopRun(id) { await api(`/runs/${id}/stop`, "POST"); refresh(); }

function renderPositions(positions) {
  const buys = positions.filter((p) => p.state === "proposed");
  $("buys-body").innerHTML = buys.length ? buys.map((p) => `
    <tr><td>${p.item_name}</td><td>${fmt(p.buy_price)}</td><td>${p.qty}</td>
    <td><button class="btn accept" onclick="act(${p.id},'accept')">Accept</button>
    <button class="btn ghost" onclick="act(${p.id},'dismiss')">Dismiss</button></td></tr>`
  ).join("") : `<tr><td colspan="4" class="mut">No buy signals</td></tr>`;

  const held = positions.filter((p) =>
    ["accepted", "filled", "selling"].includes(p.state));
  $("positions-body").innerHTML = held.length ? held.map((p) => {
    const pl = p.realized_pl != null ? fmt(p.realized_pl) : "–";
    let action = "";
    if (p.state === "accepted") action =
      `<button class="btn accept" onclick="act(${p.id},'fill')">Filled</button>
       <button class="btn ghost" onclick="act(${p.id},'cancel')">Cancel</button>`;
    else if (p.state === "filled") action =
      `<button class="btn sell" onclick="act(${p.id},'sell')">Sell</button>
       <button class="btn ghost" onclick="act(${p.id},'cancel')">Cancel</button>`;
    else if (p.state === "selling") action =
      `<button class="btn accept" onclick="sold(${p.id})">Sold</button>
       <button class="btn ghost" onclick="act(${p.id},'cancel')">Cancel</button>`;
    return `<tr><td>${p.item_name}</td><td class="mut">${p.state}</td>
      <td>${pl}</td><td>${action}</td></tr>`;
  }).join("") : `<tr><td colspan="4" class="mut">No open positions</td></tr>`;
}
async function act(id, action) { await api(`/positions/${id}/${action}`, "POST"); refresh(); }
async function sold(id) {
  const price = prompt("Sell price (gp)?");
  if (!price) return;
  await api(`/positions/${id}/sold`, "POST", { sell_price: parseInt(price, 10) });
  refresh();
}

function renderOverview(o) {
  $("stat-capital").textContent = fmt(o.capital);
  $("stat-capital-sub").textContent = `${fmt(o.free)} free · ${fmt(o.committed)} committed`;
  $("stat-profit").textContent = (o.period_profit >= 0 ? "+" : "") + fmt(o.period_profit);
  $("stat-profit").className = "big " + (o.period_profit >= 0 ? "up" : "down");
  $("stat-open").textContent = o.open_positions;
  $("stat-bond").textContent = fmt(o.bond_price);
  const pct = Math.max(0, Math.min(1, o.goal_progress)) * 100;
  $("goal-bar").style.width = pct + "%";
  $("goal-text").textContent = `${fmt(o.period_profit)} / ${fmt(o.bond_price)}`;
}

async function refresh() {
  try {
    const [overview, runs, positions] = await Promise.all([
      api("/overview"), api("/runs"), api("/positions"),
    ]);
    renderOverview(overview);
    renderRuns(runs);
    renderPositions(positions);
    $("status-text").textContent = "live · updated " + new Date().toLocaleTimeString();
  } catch (e) {
    $("status-text").textContent = "disconnected";
  }
}

$("run-start").addEventListener("click", startRun);
$("set-save").addEventListener("click", saveSettings);
loadStrategies();
loadSettings();
refresh();
setInterval(refresh, 5000);
