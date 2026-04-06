"""
SYMBIONT Dashboard — lightweight web UI for monitoring.

Serves a single-page HTML dashboard that shows:
- Organism status (agents, castes, phases)
- Mycelium topology (channels, hub nodes, message flow)
- Colony health (online/offline)
- Alert state
- Recent messages

Auto-refreshes via JavaScript polling.
Zero external dependencies — pure stdlib + inline HTML/CSS/JS.
"""

from __future__ import annotations

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SYMBIONT Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'SF Mono', 'Fira Code', monospace;
    background: #0a0a0a; color: #e0e0e0;
    padding: 20px; line-height: 1.5;
  }
  h1 { color: #00ff88; font-size: 1.4em; margin-bottom: 4px; }
  h2 { color: #00cc66; font-size: 1.1em; margin: 16px 0 8px; border-bottom: 1px solid #1a3a2a; padding-bottom: 4px; }
  .subtitle { color: #666; font-size: 0.85em; margin-bottom: 16px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
  .card {
    background: #111; border: 1px solid #1a3a2a; border-radius: 8px;
    padding: 16px; min-height: 120px;
  }
  .card.alert { border-color: #ff4444; }
  .card.healthy { border-color: #00ff88; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
  th { text-align: left; color: #00cc66; padding: 4px 8px; border-bottom: 1px solid #1a3a2a; }
  td { padding: 4px 8px; border-bottom: 1px solid #0d1a0d; }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 0.8em; font-weight: bold;
  }
  .badge.green { background: #003d1a; color: #00ff88; }
  .badge.red { background: #3d0000; color: #ff4444; }
  .badge.yellow { background: #3d3d00; color: #ffcc00; }
  .badge.blue { background: #001a3d; color: #4488ff; }
  .stat { display: inline-block; margin-right: 16px; }
  .stat .val { font-size: 1.8em; color: #00ff88; font-weight: bold; }
  .stat .label { font-size: 0.75em; color: #666; }
  .channel-bar {
    height: 6px; background: #1a3a2a; border-radius: 3px;
    margin: 2px 0; overflow: hidden;
  }
  .channel-bar .fill { height: 100%; background: #00ff88; border-radius: 3px; }
  #lastUpdate { color: #444; font-size: 0.75em; position: fixed; bottom: 8px; right: 12px; }
  .pulse { animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }
</style>
</head>
<body>
<h1>SYMBIONT</h1>
<div class="subtitle">Symbiotic Multi-pattern Bio-intelligent Organism for Networked Tasks</div>

<div style="margin-bottom:16px">
  <div class="stat"><div class="val" id="agentCount">-</div><div class="label">Agents</div></div>
  <div class="stat"><div class="val" id="channelCount">-</div><div class="label">Channels</div></div>
  <div class="stat"><div class="val" id="totalMsgs">-</div><div class="label">Messages</div></div>
  <div class="stat"><div class="val" id="phase">-</div><div class="label">Phase</div></div>
</div>

<div class="grid">
  <div class="card" id="agentsCard">
    <h2>Agents by Caste</h2>
    <table><thead><tr><th>Caste</th><th>Count</th><th>Model</th></tr></thead>
    <tbody id="casteTable"></tbody></table>
  </div>

  <div class="card" id="coloniesCard">
    <h2>Colonies</h2>
    <table><thead><tr><th>Name</th><th>Host</th><th>Status</th></tr></thead>
    <tbody id="colonyTable"></tbody></table>
  </div>

  <div class="card" id="channelsCard">
    <h2>Mycelium Channels</h2>
    <div id="channelList"></div>
  </div>

  <div class="card" id="hubsCard">
    <h2>Hub Nodes</h2>
    <table><thead><tr><th>Agent</th><th>Score</th></tr></thead>
    <tbody id="hubTable"></tbody></table>
  </div>

  <div class="card" id="alertsCard">
    <h2>Alert State</h2>
    <div id="alertInfo"></div>
  </div>

  <div class="card" id="healthCard">
    <h2>Homeostasis</h2>
    <div id="healthInfo"></div>
  </div>
</div>

<div id="lastUpdate"></div>

<script>
const BRIDGE = window.location.protocol + '//' + window.location.hostname + ':7777';
const CASTE_MODELS = {
  'Caste.QUEEN': 'Opus', 'Caste.MAJOR': 'Opus', 'Caste.MEDIA': 'Sonnet',
  'Caste.SCOUT': 'Haiku', 'Caste.MINIMA': 'Haiku',
  'QUEEN': 'Opus', 'MAJOR': 'Opus', 'MEDIA': 'Sonnet', 'SCOUT': 'Haiku', 'MINIMA': 'Haiku',
};

async function fetchJSON(path) {
  try {
    const r = await fetch(BRIDGE + path);
    return await r.json();
  } catch(e) { return null; }
}

function badge(text, cls) { return `<span class="badge ${cls}">${text}</span>`; }

async function refresh() {
  const [status, channels, alerts, metrics] = await Promise.all([
    fetchJSON('/status'),
    fetchJSON('/channels'),
    fetchJSON('/alerts'),
    fetchJSON('/metrics'),
  ]);

  if (status) {
    const a = status.agents || {};
    document.getElementById('agentCount').textContent = a.total || 0;
    document.getElementById('phase').textContent = (status.governance || {}).phase || '?';

    const castes = a.by_caste || {};
    document.getElementById('casteTable').innerHTML = Object.entries(castes)
      .map(([k,v]) => `<tr><td>${k.replace('Caste.','')}</td><td>${v}</td><td>${CASTE_MODELS[k]||'?'}</td></tr>`)
      .join('');

    const health = (status.mound || {}).health || {};
    document.getElementById('healthInfo').innerHTML = `
      <table>
        <tr><td>Healthy</td><td>${health.is_healthy ? badge('YES','green') : badge('NO','red')}</td></tr>
        <tr><td>Latency</td><td>${(health.latency_ms||0).toFixed(0)}ms</td></tr>
        <tr><td>Error Rate</td><td>${(health.error_rate||0).toFixed(3)}</td></tr>
      </table>
    `;

    const hCard = document.getElementById('healthCard');
    hCard.className = health.is_healthy ? 'card healthy' : 'card alert';
  }

  if (channels) {
    const topo = channels.topology || {};
    const chData = topo.channels || {};
    const totalMsgs = topo.total_messages || 0;
    const hubs = topo.hub_nodes || [];

    document.getElementById('channelCount').textContent = Object.keys(chData).length;
    document.getElementById('totalMsgs').textContent = totalMsgs;

    const maxW = Math.max(1, ...Object.values(chData).map(c => c.weight || 1));
    document.getElementById('channelList').innerHTML = Object.entries(chData)
      .sort((a,b) => (b[1].message_count||0) - (a[1].message_count||0))
      .map(([name, ch]) => {
        const pct = ((ch.weight||1)/maxW*100).toFixed(0);
        return `<div style="margin-bottom:6px">
          <div style="display:flex;justify-content:space-between;font-size:0.85em">
            <span>${name}</span><span>${ch.message_count||0} msgs / ${ch.subscribers||0} subs</span>
          </div>
          <div class="channel-bar"><div class="fill" style="width:${pct}%"></div></div>
        </div>`;
      }).join('');

    document.getElementById('hubTable').innerHTML = hubs
      .map(([id, score]) => `<tr><td>${id}</td><td>${score.toFixed(1)}</td></tr>`)
      .join('');
  }

  if (alerts) {
    const down = alerts.colonies_down || [];
    const tgOk = alerts.telegram_configured;
    document.getElementById('alertInfo').innerHTML = `
      <table>
        <tr><td>Telegram</td><td>${tgOk ? badge('ON','green') : badge('OFF','yellow')}</td></tr>
        <tr><td>Bridge</td><td>${alerts.bridge_down ? badge('DOWN','red') : badge('UP','green')}</td></tr>
        <tr><td>Colonies Down</td><td>${down.length ? badge(down.join(', '),'red') : badge('None','green')}</td></tr>
        <tr><td>Last Check</td><td>${alerts.last_check ? new Date(alerts.last_check*1000).toLocaleTimeString() : '-'}</td></tr>
      </table>
    `;
    const aCard = document.getElementById('alertsCard');
    aCard.className = (down.length || alerts.bridge_down) ? 'card alert' : 'card healthy';
  }

  if (metrics) {
    const colonies = metrics.colonies || {};
    document.getElementById('colonyTable').innerHTML = Object.entries(colonies)
      .map(([name, info]) => {
        const st = info.alive ? badge('ONLINE','green') : badge('OFFLINE','red');
        return `<tr><td>${name}</td><td>${info.host}</td><td>${st}</td></tr>`;
      }).join('');

    const cCard = document.getElementById('coloniesCard');
    const anyDown = Object.values(colonies).some(c => !c.alive);
    cCard.className = anyDown ? 'card alert' : 'card healthy';
  }

  document.getElementById('lastUpdate').textContent = 'Updated: ' + new Date().toLocaleTimeString();
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>"""


def get_dashboard_html() -> str:
    """Return the dashboard HTML."""
    return DASHBOARD_HTML
