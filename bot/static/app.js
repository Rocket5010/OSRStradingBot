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

async function loadSettings() {
  const [capital, autoBudget, bondDays, webhook, curateDays, minMargin, autoStrats] =
    await Promise.all([
      api("/config/capital"), api("/config/auto_budget"), api("/config/bond_days"),
      api("/config/notify_webhook"), api("/config/curate_interval_days"),
      api("/config/min_margin_gp"), api("/config/auto_strategies"),
    ]);
  if (capital.value != null) $("set-capital").value = capital.value;
  if (autoBudget.value != null) $("set-auto-budget").value = autoBudget.value;
  if (bondDays.value != null) $("set-bond-days").value = bondDays.value;
  if (webhook.value != null) $("set-webhook").value = webhook.value;
  if (curateDays.value != null) $("set-curate-days").value = curateDays.value;
  if (minMargin.value != null) $("set-min-margin").value = minMargin.value;
  if (autoStrats.value != null) $("set-auto-strategies").value = autoStrats.value;
}

async function saveSettings() {
  const entries = [
    ["capital", $("set-capital").value.trim()],
    ["auto_budget", $("set-auto-budget").value.trim()],
    ["bond_days", $("set-bond-days").value.trim()],
    ["notify_webhook", $("set-webhook").value.trim()],
    ["curate_interval_days", $("set-curate-days").value.trim()],
    ["min_margin_gp", $("set-min-margin").value.trim()],
    ["auto_strategies", $("set-auto-strategies").value.trim()],
  ];
  for (const [key, value] of entries) {
    if (value !== "") await api(`/config/${key}`, "POST", { value });
  }
  $("set-status").textContent = "saved " + new Date().toLocaleTimeString();
  refresh();
}

function renderRuns(runs) {
  $("runs-body").innerHTML = runs.map((r) => `
    <tr><td>${r.strategy}</td><td>${fmt(r.budget_gp)}</td>
    <td>${fmt(r.spent_gp)}</td><td>${r.state}</td></tr>`
  ).join("");
}

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
  const act = o.active_strategies && o.active_strategies.length
    ? o.active_strategies : (o.active_strategy ? [o.active_strategy] : []);
  $("active-strategy").textContent = act.length
    ? `active: ${act.join(", ")}` : "idle — set auto-budget + run backtest";
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

let _lastCurateFinished = null;

function renderCurateStatus(cs) {
  if (cs.running) {
    $("set-status").textContent =
      `curating… ${cs.done}/${cs.total}`;
  } else if (cs.last_error) {
    $("set-status").textContent = "curation failed: " + cs.last_error;
  } else if (cs.last_count != null) {
    $("set-status").textContent =
      `last curation: ${cs.last_count} items selected`;
  }
  // When a curation completes, reload the watchlist field once so the new
  // auto-populated list shows without a page reload.
  if (!cs.running && cs.last_finished && cs.last_finished !== _lastCurateFinished) {
    _lastCurateFinished = cs.last_finished;
    loadSettings();
  }
}

function renderWatchlist(items) {
  const view = $("watchlist-view");
  if (!view) return;
  view.value = items.length
    ? items.map((it) => `${it.id}  ${it.name}`).join("\n")
    : "";
}

function renderBacktest(data) {
  const rows = data.ranking || [];
  $("bt-body").innerHTML = rows.length ? rows.map((r) => `
    <tr><td>${r.strategy}</td>
    <td class="${(r.profit_per_day || 0) >= 0 ? "up" : "down"}">${fmt(r.profit_per_day)}</td>
    <td class="${r.profit >= 0 ? "up" : "down"}">${fmt(r.profit)}</td>
    <td>${r.trades}</td><td>${Math.round(r.win_rate * 100)}%</td>
    <td>${Math.round((r.max_drawdown || 0) * 100)}%</td></tr>`
  ).join("") : `<tr><td colspan="6" class="mut">No backtest yet — click Run backtest</td></tr>`;
}

function renderBacktestStatus(s, data) {
  if (s.running) {
    $("bt-status").textContent = `running… ${s.done}/${s.total} items`;
  } else if (s.last_error) {
    $("bt-status").textContent = "backtest failed: " + s.last_error;
  } else if (data.finished) {
    $("bt-status").textContent =
      `ranked over ${data.n_items} items · ${new Date(data.finished).toLocaleString()}`;
  } else {
    $("bt-status").textContent = "";
  }
}

async function runBacktest() {
  $("bt-status").textContent = "backtest started…";
  try {
    await api("/backtest/run", "POST");
  } catch (e) {
    $("bt-status").textContent = "backtest failed: " + e.message;
  }
}

async function refresh() {
  try {
    const [overview, runs, positions, curate, watchlist, backtest, btStatus] =
      await Promise.all([
        api("/overview"), api("/runs"), api("/positions"),
        api("/curate/status"), api("/watchlist"),
        api("/backtest"), api("/backtest/status"),
      ]);
    renderOverview(overview);
    renderRuns(runs);
    renderPositions(positions);
    renderCurateStatus(curate);
    renderWatchlist(watchlist.items);
    renderBacktest(backtest);
    renderBacktestStatus(btStatus, backtest);
    $("status-text").textContent = "live · updated " + new Date().toLocaleTimeString();
  } catch (e) {
    $("status-text").textContent = "disconnected";
  }
}

async function curateNow() {
  $("set-status").textContent = "curating… (this can take minutes)";
  try {
    await api("/curate", "POST");
    $("set-status").textContent = "curation started";
  } catch (e) {
    $("set-status").textContent = "curate failed: " + e.message;
  }
}

async function resetBot() {
  if (!confirm("Reset the bot? This deletes all positions, runs, signals, " +
               "price cache and the watchlist. Your settings (capital, webhook, " +
               "bond/curate config) are kept.")) return;
  try {
    await api("/reset", "POST");
    $("set-status").textContent = "bot reset";
    loadSettings();
    refresh();
  } catch (e) {
    $("set-status").textContent = "reset failed: " + e.message;
  }
}

$("set-save").addEventListener("click", saveSettings);
$("set-curate").addEventListener("click", curateNow);
$("set-reset").addEventListener("click", resetBot);
$("bt-run").addEventListener("click", runBacktest);
loadSettings();
refresh();
setInterval(refresh, 5000);
