"""
web_app.py
Flask-based web dashboard for the Smart Ward AIoT Toilet Safety System.
Provides a live monitoring dashboard, data management console, and AI assistant chat.
"""

from flask import Flask, request, redirect, url_for, render_template_string, jsonify
import json
import db_manager
import os

app = Flask(__name__)

# ==========================================
# HTML Templates
# ==========================================

# --- Shared Layout Shell ---
LAYOUT = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Smart Ward AIoT Safety Manager</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    /* === CSS Reset & Variables === */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg-body: #0f1117;
      --bg-card: #1a1d2e;
      --bg-card-hover: #222640;
      --bg-sidebar: #141622;
      --bg-input: #252840;
      --border: #2a2d42;
      --text-primary: #e4e6f0;
      --text-secondary: #8b8fa8;
      --text-muted: #5a5e78;
      --accent-blue: #4f8cff;
      --accent-green: #34d399;
      --accent-orange: #f59e0b;
      --accent-red: #ef4444;
      --accent-purple: #a78bfa;
      --radius: 12px;
      --shadow: 0 4px 24px rgba(0,0,0,0.25);
    }

    body {
      font-family: 'Inter', system-ui, sans-serif;
      background: var(--bg-body);
      color: var(--text-primary);
      display: flex;
      min-height: 100vh;
    }

    /* === Sidebar === */
    .sidebar {
      width: 220px;
      background: var(--bg-sidebar);
      border-right: 1px solid var(--border);
      padding: 24px 16px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      position: fixed;
      top: 0; left: 0; bottom: 0;
      z-index: 100;
    }
    .sidebar .logo {
      font-size: 13px;
      font-weight: 700;
      color: var(--accent-blue);
      text-transform: uppercase;
      letter-spacing: 1.5px;
      margin-bottom: 28px;
      padding: 0 8px;
      line-height: 1.4;
    }
    .sidebar a {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      border-radius: 8px;
      text-decoration: none;
      color: var(--text-secondary);
      font-size: 14px;
      font-weight: 500;
      transition: all 0.2s;
    }
    .sidebar a:hover { background: var(--bg-card); color: var(--text-primary); }
    .sidebar a.active { background: var(--accent-blue); color: #fff; }
    .sidebar .nav-icon { font-size: 18px; width: 22px; text-align: center; }

    /* === Main Content === */
    .main {
      margin-left: 220px;
      flex: 1;
      display: flex;
      flex-direction: column;
    }

    /* === Header === */
    .header {
      background: linear-gradient(135deg, #1e2235 0%, #161829 100%);
      border-bottom: 1px solid var(--border);
      padding: 20px 32px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .header h1 {
      font-size: 22px;
      font-weight: 700;
      background: linear-gradient(90deg, var(--accent-blue), var(--accent-purple));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .header .clock {
      font-size: 13px;
      color: var(--text-muted);
      font-variant-numeric: tabular-nums;
    }

    /* === Page Body === */
    .page-body { padding: 24px 32px; flex: 1; }

    /* === Dashboard Grid === */
    .dash-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-bottom: 24px;
    }

    /* === Cards === */
    .card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
      box-shadow: var(--shadow);
    }
    .card-title {
      font-size: 13px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--text-muted);
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .card-title .dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      display: inline-block;
    }
    .dot-blue  { background: var(--accent-blue); }
    .dot-red   { background: var(--accent-red); animation: pulse-red 1.5s infinite; }
    .dot-green { background: var(--accent-green); }

    @keyframes pulse-red {
      0%, 100% { opacity: 1; box-shadow: 0 0 6px var(--accent-red); }
      50%      { opacity: 0.4; box-shadow: none; }
    }

    /* === Tables === */
    table { width: 100%; border-collapse: collapse; }
    th {
      text-align: left;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--text-muted);
      padding: 8px 12px;
      border-bottom: 1px solid var(--border);
    }
    td {
      padding: 10px 12px;
      font-size: 13px;
      border-bottom: 1px solid rgba(42,45,66,0.5);
      color: var(--text-secondary);
    }
    tr:hover td { background: var(--bg-card-hover); }

    /* === Status Badges === */
    .badge {
      display: inline-block;
      padding: 3px 10px;
      border-radius: 20px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
    }
    .badge-occupied { background: rgba(79,140,255,0.15); color: var(--accent-blue); }
    .badge-warning  { background: rgba(245,158,11,0.15); color: var(--accent-orange); }
    .badge-accident { background: rgba(239,68,68,0.15); color: var(--accent-red); }
    .badge-idle     { background: rgba(52,211,153,0.15); color: var(--accent-green); }

    /* === Empty State === */
    .empty-state {
      text-align: center;
      padding: 40px 20px;
      color: var(--text-muted);
      font-size: 14px;
    }
    .empty-state .icon { font-size: 36px; margin-bottom: 12px; }

    /* === Management Page === */
    .mgmt-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
      gap: 20px;
    }
    .mgmt-grid label {
      display: block;
      margin-top: 10px;
      font-size: 12px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .mgmt-grid input, .mgmt-grid select {
      width: 100%;
      padding: 8px 12px;
      margin-top: 4px;
      background: var(--bg-input);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text-primary);
      font-size: 14px;
      outline: none;
      transition: border-color 0.2s;
    }
    .mgmt-grid input:focus { border-color: var(--accent-blue); }
    .mgmt-grid button {
      margin-top: 16px;
      padding: 10px 20px;
      background: var(--accent-blue);
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: opacity 0.2s;
    }
    .mgmt-grid button:hover { opacity: 0.85; }
    .btn-danger { background: var(--accent-red) !important; }

    /* === Flash Messages === */
    .flash {
      margin-bottom: 20px;
      padding: 12px 16px;
      border-radius: 8px;
      font-size: 14px;
    }
    .flash-ok  { background: rgba(52,211,153,0.1); border: 1px solid var(--accent-green); color: var(--accent-green); }
    .flash-err { background: rgba(239,68,68,0.1); border: 1px solid var(--accent-red); color: var(--accent-red); }

    /* === AI Chat Widget === */
    .chat-fab {
      position: fixed;
      bottom: 24px; right: 24px;
      width: 56px; height: 56px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
      border: none;
      color: #fff;
      font-size: 24px;
      cursor: pointer;
      box-shadow: 0 4px 20px rgba(79,140,255,0.4);
      z-index: 1000;
      transition: transform 0.2s;
    }
    .chat-fab:hover { transform: scale(1.1); }

    .chat-panel {
      display: none;
      position: fixed;
      bottom: 92px; right: 24px;
      width: 380px;
      max-height: 520px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 16px;
      box-shadow: 0 8px 40px rgba(0,0,0,0.5);
      z-index: 1001;
      flex-direction: column;
      overflow: hidden;
    }
    .chat-panel.open { display: flex; }

    .chat-header {
      padding: 16px;
      border-bottom: 1px solid var(--border);
      font-weight: 600;
      font-size: 14px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .chat-header .ai-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: var(--accent-green);
    }

    .chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      max-height: 340px;
    }
    .chat-msg {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 12px;
      font-size: 13px;
      line-height: 1.5;
      word-wrap: break-word;
    }
    .chat-msg.bot {
      align-self: flex-start;
      background: var(--bg-input);
      color: var(--text-primary);
    }
    .chat-msg.user {
      align-self: flex-end;
      background: var(--accent-blue);
      color: #fff;
    }

    .chat-suggestions {
      padding: 8px 16px;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .chat-suggestions button {
      padding: 6px 12px;
      background: var(--bg-input);
      border: 1px solid var(--border);
      border-radius: 20px;
      color: var(--text-secondary);
      font-size: 12px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .chat-suggestions button:hover {
      border-color: var(--accent-blue);
      color: var(--accent-blue);
    }

    .chat-input-row {
      padding: 12px 16px;
      border-top: 1px solid var(--border);
      display: flex;
      gap: 8px;
    }
    .chat-input-row input {
      flex: 1;
      padding: 8px 12px;
      background: var(--bg-input);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text-primary);
      font-size: 13px;
      outline: none;
    }
    .chat-input-row button {
      padding: 8px 16px;
      background: var(--accent-blue);
      border: none;
      border-radius: 8px;
      color: #fff;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }

    .chat-typing {
      display: none;
      align-self: flex-start;
      padding: 10px 14px;
      background: var(--bg-input);
      border-radius: 12px;
      color: var(--text-muted);
      font-size: 13px;
    }
    .chat-typing.show { display: block; }

    /* Think block (collapsible reasoning) */
    .think-toggle {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 3px 10px;
      margin-bottom: 6px;
      background: rgba(167,139,250,0.1);
      border: 1px solid rgba(167,139,250,0.25);
      border-radius: 6px;
      color: var(--accent-purple);
      font-size: 11px;
      cursor: pointer;
      user-select: none;
    }
    .think-toggle:hover { background: rgba(167,139,250,0.2); }
    .think-content {
      display: none;
      padding: 8px 10px;
      margin-bottom: 6px;
      background: rgba(167,139,250,0.05);
      border-left: 2px solid var(--accent-purple);
      border-radius: 0 6px 6px 0;
      font-size: 12px;
      color: var(--text-muted);
      line-height: 1.5;
      white-space: pre-wrap;
    }
    .think-content.open { display: block; }
  </style>
</head>
<body>

  <!-- Sidebar Navigation -->
  <nav class="sidebar">
    <div class="logo">Smart Ward<br>AIoT Safety</div>
    <a href="/" class="{{ 'active' if active_page == 'dashboard' else '' }}">
      <span class="nav-icon">📊</span> Live Monitor
    </a>
    <a href="/manage" class="{{ 'active' if active_page == 'manage' else '' }}">
      <span class="nav-icon">⚙️</span> Data Management
    </a>
  </nav>

  <!-- Main Content Area -->
  <div class="main">
    <!-- Header -->
    <div class="header">
      <h1>Smart Ward AIoT Safety Manager</h1>
      <div class="clock" id="live-clock"></div>
    </div>

    <!-- Page Body (injected per page) -->
    <div class="page-body">
      {{ page_content | safe }}
    </div>
  </div>

  <!-- AI Chat FAB -->
  <button class="chat-fab" id="chatFab" title="AI Assistant">🤖</button>
  <div class="chat-panel" id="chatPanel">
    <div class="chat-header">
      <span class="ai-dot"></span> AI System Assistant
    </div>
    <div class="chat-messages" id="chatMessages">
      <div class="chat-msg bot">
        Hello! I'm the Smart Ward AI Assistant. I can answer questions about this system, its hardware, AI models, and operating procedures. Try asking me something below!
      </div>
    </div>
    <div class="chat-suggestions" id="chatSuggestions">
      <button class="suggest-btn">How does the system work?</button>
      <button class="suggest-btn">What AI models are used?</button>
      <button class="suggest-btn">What happens during an emergency?</button>
    </div>
    <div class="chat-input-row">
      <input type="text" id="chatInput" placeholder="Ask a question...">
      <button id="chatSendBtn">Send</button>
    </div>
  </div>

  <script>
  {% raw %}
    // --- Live Clock ---
    function updateClock() {
      const now = new Date();
      document.getElementById('live-clock').textContent = now.toLocaleString('en-US', {
        year: 'numeric', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
      });
    }
    setInterval(updateClock, 1000);
    updateClock();

    // --- Dashboard Auto-Refresh (every 10 seconds, only on dashboard page) ---
    if (window.location.pathname === '/') {
      setInterval(() => {
        fetch('/api/dashboard_data')
          .then(r => r.json())
          .then(data => {
            // Update in-use table
            const inUseBody = document.getElementById('in-use-body');
            if (inUseBody) {
              if (data.in_use.length === 0) {
                inUseBody.innerHTML = '<tr><td colspan="4" class="empty-state"><div class="icon">✅</div>All toilets are currently vacant.</td></tr>';
              } else {
                inUseBody.innerHTML = data.in_use.map(r => `
                  <tr>
                    <td style="color:var(--text-primary);font-weight:500">${r.room}</td>
                    <td>${r.patient_id}</td>
                    <td>${r.entry_time}</td>
                    <td><span class="badge badge-occupied">Occupied</span></td>
                  </tr>`).join('');
              }
            }
            // Update alerts table
            const alertBody = document.getElementById('alert-body');
            if (alertBody) {
              if (data.alerts.length === 0) {
                alertBody.innerHTML = '<tr><td colspan="4" class="empty-state"><div class="icon">🛡️</div>No active incidents. All clear.</td></tr>';
              } else {
                alertBody.innerHTML = data.alerts.map(r => `
                  <tr>
                    <td style="color:var(--text-primary);font-weight:500">${r.room}</td>
                    <td>${r.patient_id}</td>
                    <td>${r.entry_time}</td>
                    <td><span class="badge badge-accident">Accident</span></td>
                  </tr>`).join('');
              }
            }
            // Update logs table
            const logBody = document.getElementById('log-body');
            if (logBody) {
              if (data.recent_logs.length === 0) {
                logBody.innerHTML = '<tr><td colspan="5" class="empty-state">No events recorded yet.</td></tr>';
              } else {
                logBody.innerHTML = data.recent_logs.map(r => `
                  <tr>
                    <td>${r.time}</td>
                    <td>${r.patient_id}</td>
                    <td>${r.room}</td>
                    <td>${r.event}</td>
                    <td>${r.duration || '-'}</td>
                  </tr>`).join('');
              }
            }
          })
          .catch(err => console.error('Dashboard refresh failed:', err));
      }, 10000);
    }

    // --- AI Chat ---
    document.getElementById('chatFab').addEventListener('click', function() {
      document.getElementById('chatPanel').classList.toggle('open');
    });

    document.querySelectorAll('.suggest-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        document.getElementById('chatInput').value = this.textContent;
        sendChat();
      });
    });

    document.getElementById('chatSendBtn').addEventListener('click', sendChat);
    document.getElementById('chatInput').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') sendChat();
    });

    function sendChat() {
      const input = document.getElementById('chatInput');
      const msg = input.value.trim();
      if (!msg) return;

      const messagesDiv = document.getElementById('chatMessages');
      messagesDiv.innerHTML += `<div class="chat-msg user">${escapeHtml(msg)}</div>`;
      input.value = '';
      document.getElementById('chatSuggestions').style.display = 'none';

      // Create bot message container for streaming
      const botMsg = document.createElement('div');
      botMsg.className = 'chat-msg bot';
      botMsg.textContent = '';
      messagesDiv.appendChild(botMsg);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;

      // SSE streaming fetch
      fetch('/api/chat_stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg })
      })
      .then(response => {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';

        function pump() {
          return reader.read().then(({ done, value }) => {
            if (done) {
              // Streaming finished - render final content with think blocks
              botMsg.innerHTML = renderThinkBlocks(fullText);
              messagesDiv.scrollTop = messagesDiv.scrollHeight;
              return;
            }
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split(String.fromCharCode(10));
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = line.slice(6);
                if (data === '[DONE]') continue;
                try {
                  const parsed = JSON.parse(data);
                  if (parsed.token) {
                    fullText += parsed.token;
                    // Normalize missing <think> tag for reasoning models
                    let normalizedText = fullText;
                    if (normalizedText.includes('</think>') && !normalizedText.includes('<think>')) {
                        normalizedText = '<think>' + String.fromCharCode(10) + normalizedText;
                    }
                    // During streaming, hide think content
                    const visibleText = normalizedText.replace(/<think>[\s\S]*?<\/think>/g, '').replace(/<think>[\s\S]*/g, '');
                    botMsg.innerHTML = basicMarkdown(escapeHtml(visibleText || '🤔 Thinking...'));
                    messagesDiv.scrollTop = messagesDiv.scrollHeight;
                  }
                  if (parsed.error) {
                    botMsg.textContent = parsed.error;
                    botMsg.style.color = 'var(--accent-red)';
                  }
                } catch(e) {}
              }
            }
            return pump();
          });
        }
        return pump();
      })
      .catch(err => {
        botMsg.textContent = 'Error: Could not reach the AI service.';
        botMsg.style.color = 'var(--accent-red)';
      });
    }

    // Render <think>...</think> blocks as collapsible sections and apply markdown
    function renderThinkBlocks(text) {
      // Normalize missing <think>
      if (text.includes('</think>') && !text.includes('<think>')) {
        text = '<think>' + String.fromCharCode(10) + text;
      }
      
      let html = escapeHtml(text);
      const thinkRegex = /&lt;think&gt;([\s\S]*?)&lt;\/think&gt;/g;
      let counter = 0;
      
      html = html.replace(thinkRegex, (match, content) => {
        const id = 'think-' + Date.now() + '-' + (counter++);
        return `<div class="think-toggle" onclick="document.getElementById('${id}').classList.toggle('open')">💭 View Reasoning</div><div class="think-content" id="${id}">${basicMarkdown(content.trim())}</div>`;
      });
      
      // Remove any leftover incomplete <think> tags
      html = html.replace(/&lt;think&gt;[\s\S]*/g, '');
      
      return basicMarkdown(html);
    }

    function basicMarkdown(text) {
      if (!text) return text;
      // Bold
      text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      // Italic
      text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
      // Bullet lists
      text = text.replace(/^[\s]*-\s+(.*)/gm, '&bull; $1');
      // Line breaks
      text = text.replace(new RegExp(String.fromCharCode(10), 'g'), '<br>');
      return text;
    }

    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }
  {% endraw %}
  </script>
</body>
</html>
"""

# --- Dashboard Page Content ---
DASHBOARD_CONTENT = """
<div class="dash-grid">
  <!-- Left: Toilets In Use -->
  <div class="card">
    <div class="card-title"><span class="dot dot-blue"></span> Currently In Use</div>
    <table>
      <thead><tr><th>Room</th><th>Patient</th><th>Entry Time</th><th>Status</th></tr></thead>
      <tbody id="in-use-body">
        {% if in_use %}
          {% for row in in_use %}
          <tr>
            <td style="color:var(--text-primary);font-weight:500">{{ row.room }}</td>
            <td>{{ row.patient_id }}</td>
            <td>{{ row.entry_time }}</td>
            <td><span class="badge badge-occupied">Occupied</span></td>
          </tr>
          {% endfor %}
        {% else %}
          <tr><td colspan="4" class="empty-state"><div class="icon">✅</div>All toilets are currently vacant.</td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>

  <!-- Right: Active Alerts -->
  <div class="card">
    <div class="card-title"><span class="dot dot-red"></span> Incident Alerts</div>
    <table>
      <thead><tr><th>Room</th><th>Patient</th><th>Since</th><th>Severity</th></tr></thead>
      <tbody id="alert-body">
        {% if alerts %}
          {% for row in alerts %}
          <tr>
            <td style="color:var(--text-primary);font-weight:500">{{ row.room }}</td>
            <td>{{ row.patient_id }}</td>
            <td>{{ row.entry_time }}</td>
            <td><span class="badge badge-accident">Accident</span></td>
          </tr>
          {% endfor %}
        {% else %}
          <tr><td colspan="4" class="empty-state"><div class="icon">🛡️</div>No active incidents. All clear.</td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>
</div>

<!-- Bottom: Recent Event Logs -->
<div class="card">
  <div class="card-title"><span class="dot dot-green"></span> Recent Event Log</div>
  <table>
    <thead><tr><th>Time</th><th>Patient</th><th>Room</th><th>Event</th><th>Duration</th></tr></thead>
    <tbody id="log-body">
      {% if recent_logs %}
        {% for row in recent_logs %}
        <tr>
          <td>{{ row.time }}</td>
          <td>{{ row.patient_id }}</td>
          <td>{{ row.room }}</td>
          <td>{{ row.event }}</td>
          <td>{{ row.duration or '-' }}</td>
        </tr>
        {% endfor %}
      {% else %}
        <tr><td colspan="5" class="empty-state">No events recorded yet.</td></tr>
      {% endif %}
    </tbody>
  </table>
</div>
"""

# --- Management Page Content ---
MANAGE_CONTENT = """
{% if message %}
  <div class="flash {{ 'flash-ok' if success else 'flash-err' }}">{{ message }}</div>
{% endif %}

<div class="mgmt-grid">
  <div class="card">
    <div class="card-title">Add Patient</div>
    <form method="post" action="/add_patient">
      <label>Patient ID<input name="patient_id" required /></label>
      <label>Age<input name="age" type="number" min="1" required /></label>
      <label>Gender<input name="gender" required /></label>
      <label>Mobility Level (0-2)<input name="mobility_level" type="number" min="0" max="2" required /></label>
      <label>Has Gastro Issue (0/1)<input name="has_gastro_issue" type="number" min="0" max="1" required /></label>
      <label>Has Uro Issue (0/1)<input name="has_uro_issue" type="number" min="0" max="1" required /></label>
      <label>Self-Reported Max Seconds<input name="self_reported_max_seconds" type="number" min="1" required /></label>
      <label>Anomaly Count<input name="anomaly_count" type="number" min="1" value="5" required /></label>
      <button type="submit">Add Patient (+ anomalies)</button>
    </form>
  </div>

  <div class="card">
    <div class="card-title">Register Card</div>
    <p style="font-size:12px;color:var(--text-muted);margin-bottom:8px">Register a new RFID card without assigning it to any patient.</p>
    <form method="post" action="/register_card">
      <label>Card UID<input name="card_uid" required /></label>
      <button type="submit">Register Card</button>
    </form>
  </div>

  <div class="card">
    <div class="card-title">Assign / Activate Card</div>
    <p style="font-size:12px;color:var(--text-muted);margin-bottom:8px">Card must be registered and inactive first.</p>
    <form method="post" action="/assign_card">
      <label>Card UID<input name="card_uid" required /></label>
      <label>Patient ID<input name="patient_id" required /></label>
      <button type="submit">Assign Card</button>
    </form>
  </div>

  <div class="card">
    <div class="card-title">Deactivate Card</div>
    <p style="font-size:12px;color:var(--text-muted);margin-bottom:8px">Unlinks the card from its patient. Must reassign before use.</p>
    <form method="post" action="/deactivate_card">
      <label>Card UID<input name="card_uid" required /></label>
      <button type="submit" class="btn-danger">Deactivate Card</button>
    </form>
  </div>

  <div class="card">
    <div class="card-title">Generate Anomalies</div>
    <form method="post" action="/generate_anomalies">
      <label>Patient ID<input name="patient_id" required /></label>
      <label>Count<input name="count" type="number" min="1" value="5" required /></label>
      <button type="submit">Generate Anomalies</button>
    </form>
  </div>
</div>
"""


# ==========================================
# Dashboard Data Helpers
# ==========================================

def _get_dashboard_data():
    """Fetch live status data from the database for the dashboard."""
    import sqlite3
    with sqlite3.connect(db_manager.DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Currently in use: open sessions (entry_time exists, exit_time is NULL)
        cursor.execute("""
            SELECT tl.patient_id, tl.entry_time
            FROM Toilet_Logs tl
            WHERE tl.exit_time IS NULL AND tl.is_accident = 0
            ORDER BY tl.entry_time DESC
        """)
        in_use = []
        for row in cursor.fetchall():
            entry_short = row['entry_time'][:16].replace('T', ' ') if row['entry_time'] else '-'
            in_use.append({
                'room': 'Room 1-01',
                'patient_id': row['patient_id'],
                'entry_time': entry_short,
            })

        # Active accidents: open sessions with is_accident = 1
        cursor.execute("""
            SELECT tl.patient_id, tl.entry_time
            FROM Toilet_Logs tl
            WHERE tl.is_accident = 1 AND tl.exit_time IS NULL
            ORDER BY tl.entry_time DESC
        """)
        alerts = []
        for row in cursor.fetchall():
            entry_short = row['entry_time'][:16].replace('T', ' ') if row['entry_time'] else '-'
            alerts.append({
                'room': 'Room 1-01',
                'patient_id': row['patient_id'],
                'entry_time': entry_short,
            })

        # Recent logs (last 5 events, ordered by most recent entry_time)
        cursor.execute("""
            SELECT tl.patient_id, tl.entry_time, tl.exit_time,
                   tl.duration_seconds, tl.is_accident
            FROM Toilet_Logs tl
            ORDER BY tl.entry_time DESC
            LIMIT 5
        """)
        recent_logs = []
        for row in cursor.fetchall():
            entry_short = row['entry_time'][:16].replace('T', ' ') if row['entry_time'] else '-'
            if row['is_accident']:
                event = '🚨 Accident'
            elif row['exit_time'] is None:
                event = '🔵 In Use'
            else:
                event = '✅ Normal Exit'

            duration_str = None
            if row['duration_seconds'] is not None:
                mins = row['duration_seconds'] // 60
                secs = row['duration_seconds'] % 60
                duration_str = f"{mins}m {secs}s"

            recent_logs.append({
                'time': entry_short,
                'patient_id': row['patient_id'],
                'room': 'Room 1-01',
                'event': event,
                'duration': duration_str,
            })

    return in_use, alerts, recent_logs


# ==========================================
# Routes
# ==========================================


@app.route("/")
def dashboard():
    """Render the live monitoring dashboard."""
    in_use, alerts, recent_logs = _get_dashboard_data()
    page = render_template_string(DASHBOARD_CONTENT,
                                  in_use=in_use, alerts=alerts, recent_logs=recent_logs)
    return render_template_string(LAYOUT, page_content=page, active_page='dashboard')


@app.route("/manage")
def manage():
    """Render the data management page."""
    message = request.args.get("message", "")
    success = request.args.get("success", "1") == "1"
    page = render_template_string(MANAGE_CONTENT, message=message, success=success)
    return render_template_string(LAYOUT, page_content=page, active_page='manage')


# --- Dashboard Data API (for auto-refresh) ---
@app.route("/api/dashboard_data")
def api_dashboard_data():
    """Return live dashboard data as JSON for polling."""
    in_use, alerts, recent_logs = _get_dashboard_data()
    return jsonify(in_use=in_use, alerts=alerts, recent_logs=recent_logs)


# --- AI Chat Streaming API (SSE) ---
@app.route("/api/chat_stream", methods=["POST"])
def api_chat_stream():
    """Stream LLM response tokens via SSE."""
    from flask import Response
    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        def empty():
            yield f"data: {json.dumps({'error': 'Please enter a question.'})}\n\n"
        return Response(empty(), mimetype='text/event-stream')

    def generate():
        try:
            from llm_assistant import stream_reply
            for token in stream_reply(user_message):
                if token.startswith("[ERROR]"):
                    yield f"data: {json.dumps({'error': token[7:]})}\n\n"
                else:
                    yield f"data: {json.dumps({'token': token})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            print(f"Error in AI chat stream: {e}")
            yield f"data: {json.dumps({'error': 'The AI service encountered an error. Please try again.'})}\n\n"

    return Response(generate(), mimetype='text/event-stream')


# --- Management Form Handlers ---
@app.route("/add_patient", methods=["POST"])
def add_patient_route():
    try:
        result = db_manager.add_patient(
            patient_id=request.form.get("patient_id"),
            age=request.form.get("age"),
            gender=request.form.get("gender"),
            mobility_level=request.form.get("mobility_level"),
            has_gastro_issue=request.form.get("has_gastro_issue"),
            has_uro_issue=request.form.get("has_uro_issue"),
            self_reported_max_seconds=request.form.get("self_reported_max_seconds"),
            auto_generate_anomalies=True,
            anomaly_count=request.form.get("anomaly_count", 5),
        )
        msg = f"Patient {result['patient_id']} created. Generated {result['anomalies_generated']} anomalies."
        return redirect(url_for("manage", message=msg, success=1))
    except Exception as exc:
        return redirect(url_for("manage", message=str(exc), success=0))


@app.route("/register_card", methods=["POST"])
def register_card_route():
    try:
        result = db_manager.register_card(card_uid=request.form.get("card_uid"))
        msg = f"Card {result['card_uid']} registered (inactive, unassigned)."
        return redirect(url_for("manage", message=msg, success=1))
    except Exception as exc:
        return redirect(url_for("manage", message=str(exc), success=0))


@app.route("/assign_card", methods=["POST"])
def assign_card_route():
    try:
        result = db_manager.assign_card(
            card_uid=request.form.get("card_uid"),
            patient_id=request.form.get("patient_id"),
        )
        msg = f"Card {result['card_uid']} assigned to patient {result['patient_id']} and activated."
        return redirect(url_for("manage", message=msg, success=1))
    except Exception as exc:
        return redirect(url_for("manage", message=str(exc), success=0))


@app.route("/deactivate_card", methods=["POST"])
def deactivate_card_route():
    try:
        result = db_manager.deactivate_card(card_uid=request.form.get("card_uid"))
        msg = f"Card {result['card_uid']} deactivated and unlinked."
        return redirect(url_for("manage", message=msg, success=1))
    except Exception as exc:
        return redirect(url_for("manage", message=str(exc), success=0))


@app.route("/generate_anomalies", methods=["POST"])
def generate_anomalies_route():
    try:
        result = db_manager.generate_anomalies_for_patient(
            patient_id=request.form.get("patient_id"),
            count=request.form.get("count", 5),
        )
        msg = f"Generated {result['anomalies_generated']} anomalies for {result['patient_id']}."
        return redirect(url_for("manage", message=msg, success=1))
    except Exception as exc:
        return redirect(url_for("manage", message=str(exc), success=0))


# ==========================================
# Entry Point
# ==========================================
if __name__ == "__main__":
    db_manager.init_db()
    print("Starting Smart Ward Dashboard on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
