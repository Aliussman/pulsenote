"""PulseNote Interactive Clinical Provenance & Auditor Web Demo.

Zero external dependencies: runs with standard library Python http.server.
Usage:
    python demo/app.py
    # Open http://localhost:8080 in your browser
"""

import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Ensure project root is in path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.grounding import is_hard_failure, validate_sentence
from src.posthoc import post_hoc_check
from src.schemas import RawSentence, Support, Turn


def load_encounters():
    encs = {}
    path = ROOT_DIR / "data" / "encounters.jsonl"
    if path.exists():
        with open(path) as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    encs[item["id"]] = item
    return encs


def load_precomputed_results():
    results = {}
    for p in [ROOT_DIR / "results" / "per_sentence.jsonl", ROOT_DIR / "results_eval" / "per_sentence.jsonl"]:
        if p.exists():
            with open(p) as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        eid = row["encounter_id"]
                        if eid not in results:
                            results[eid] = {"baseline": [], "grounded": []}
                        if row["system"] == "baseline" and row["check"] == "posthoc":
                            results[eid]["baseline"].append(row)
                        elif row["system"] == "grounded" and row["check"] == "citation":
                            results[eid]["grounded"].append(row)
    return results


ENCOUNTERS = load_encounters()
PRECOMPUTED = load_precomputed_results()

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PulseNote: Clinical Provenance & Audit Dashboard</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --accent-hover: #0ea5e9;
      --doctor: #38bdf8;
      --patient: #34d399;
      --flag-hard: #f43f5e;
      --flag-soft: #fbbf24;
      --pass: #10b981;
      --highlight: rgba(56, 189, 248, 0.25);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 20px;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 20px;
    }
    .logo {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .logo h1 { font-size: 1.5rem; font-weight: 700; color: #fff; }
    .badge {
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent);
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 600;
      border: 1px solid rgba(56, 189, 248, 0.3);
    }
    .controls {
      display: flex;
      gap: 12px;
      align-items: center;
    }
    select {
      background: var(--card-bg);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 0.9rem;
      cursor: pointer;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      height: calc(100vh - 130px);
    }
    .panel {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .panel-header {
      padding: 12px 16px;
      background: rgba(15, 23, 42, 0.6);
      border-bottom: 1px solid var(--border);
      font-weight: 600;
      font-size: 0.95rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .panel-body {
      padding: 16px;
      overflow-y: auto;
      flex: 1;
    }
    .turn {
      padding: 8px 12px;
      margin-bottom: 8px;
      border-radius: 6px;
      background: rgba(15, 23, 42, 0.3);
      border-left: 3px solid transparent;
      font-size: 0.9rem;
      transition: all 0.2s ease;
    }
    .turn.doctor { border-left-color: var(--doctor); }
    .turn.patient { border-left-color: var(--patient); }
    .turn.highlighted {
      background: var(--highlight) !important;
      border-left-color: #fff !important;
      box-shadow: 0 0 10px rgba(56, 189, 248, 0.4);
    }
    .turn-meta {
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-bottom: 2px;
      font-weight: 600;
    }
    .turn-meta span.Doctor { color: var(--doctor); }
    .turn-meta span.Patient { color: var(--patient); }
    .soap-section {
      margin-bottom: 20px;
    }
    .soap-section-title {
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--accent);
      font-weight: 700;
      margin-bottom: 8px;
      border-bottom: 1px solid rgba(56, 189, 248, 0.2);
      padding-bottom: 4px;
    }
    .sentence-card {
      padding: 10px 12px;
      margin-bottom: 10px;
      border-radius: 6px;
      background: rgba(15, 23, 42, 0.4);
      border: 1px solid var(--border);
      font-size: 0.9rem;
      transition: border-color 0.2s;
    }
    .sentence-card:hover {
      border-color: var(--accent);
    }
    .sentence-card.flagged {
      border-left: 3px solid var(--flag-hard);
    }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 0.75rem;
      margin-top: 6px;
      cursor: pointer;
      border: 1px solid rgba(56, 189, 248, 0.25);
    }
    .chip:hover {
      background: rgba(56, 189, 248, 0.3);
    }
    .flag-pill {
      display: inline-block;
      background: rgba(244, 63, 94, 0.15);
      color: var(--flag-hard);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 0.75rem;
      margin-top: 6px;
      font-weight: 600;
      border: 1px solid rgba(244, 63, 94, 0.3);
    }
    .stats-bar {
      display: flex;
      gap: 16px;
      font-size: 0.8rem;
    }
    .stat-item {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .stat-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
    }
    .tab-bar {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
    }
    .tab {
      background: transparent;
      color: var(--text-muted);
      border: 1px solid var(--border);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 0.85rem;
      cursor: pointer;
    }
    .tab.active {
      background: var(--accent);
      color: #0f172a;
      font-weight: 600;
      border-color: var(--accent);
    }
  </style>
</head>
<body>
  <header>
    <div class="logo">
      <h1>PulseNote</h1>
      <span class="badge">Validator-v2 Live Auditor</span>
    </div>
    <div class="controls">
      <label for="enc-select" style="font-size: 0.9rem; color: var(--text-muted);">Encounter:</label>
      <select id="enc-select" onchange="loadEncounter(this.value)">
        <!-- Populated dynamically -->
      </select>
    </div>
  </header>

  <main class="grid">
    <!-- Left: Dialogue Transcript -->
    <div class="panel">
      <div class="panel-header">
        <span>Doctor-Patient Transcript</span>
        <span id="turn-count" style="font-size: 0.8rem; color: var(--text-muted);">0 turns</span>
      </div>
      <div class="panel-body" id="transcript-body">
        <!-- Turns rendered here -->
      </div>
    </div>

    <!-- Right: Generated SOAP Note & Citations -->
    <div class="panel">
      <div class="panel-header">
        <div class="tab-bar" style="margin-bottom: 0;">
          <button class="tab active" onclick="switchView('grounded')">Grounded Pipeline (Citations)</button>
          <button class="tab" onclick="switchView('baseline')">Baseline Pipeline (Ungrounded)</button>
        </div>
        <div id="panel-stats" class="stats-bar"></div>
      </div>
      <div class="panel-body" id="note-body">
        <!-- Note sentences rendered here -->
      </div>
    </div>
  </main>

  <script>
    let currentData = null;
    let currentView = 'grounded';

    async function init() {
      const resp = await fetch('/api/encounters');
      const encounters = await resp.json();
      const select = document.getElementById('enc-select');
      encounters.forEach(e => {
        const opt = document.createElement('option');
        opt.value = e.id;
        opt.textContent = `${e.id} (${e.turn_count} turns)`;
        select.appendChild(opt);
      });
      if (encounters.length > 0) {
        loadEncounter(encounters[0].id);
      }
    }

    async function loadEncounter(id) {
      const resp = await fetch(`/api/encounter?id=${encodeURIComponent(id)}`);
      currentData = await resp.json();
      renderTranscript();
      renderNote();
    }

    function renderTranscript() {
      const container = document.getElementById('transcript-body');
      container.innerHTML = '';
      document.getElementById('turn-count').textContent = `${currentData.turns.length} turns`;

      currentData.turns.forEach(t => {
        const div = document.createElement('div');
        div.className = `turn ${t.speaker.toLowerCase()}`;
        div.id = `turn-${t.id}`;
        div.innerHTML = `
          <div class="turn-meta">
            [T${t.id}] <span class="${t.speaker}">${t.speaker}</span>
          </div>
          <div>${escapeHtml(t.text)}</div>
        `;
        container.appendChild(div);
      });
    }

    function switchView(view) {
      currentView = view;
      document.querySelectorAll('.tab').forEach((tab, i) => {
        tab.classList.toggle('active', (i === 0 && view === 'grounded') || (i === 1 && view === 'baseline'));
      });
      renderNote();
    }

    function renderNote() {
      const container = document.getElementById('note-body');
      container.innerHTML = '';
      const sentences = currentView === 'grounded' ? currentData.grounded : currentData.baseline;

      const hardCount = sentences.filter(s => s.flagged).length;
      document.getElementById('panel-stats').innerHTML = `
        <div class="stat-item">
          <span class="stat-dot" style="background: ${hardCount === 0 ? 'var(--pass)' : 'var(--flag-hard)'}"></span>
          <span>${hardCount} hard failures / ${sentences.length} claims</span>
        </div>
      `;

      const sections = ['subjective', 'objective', 'assessment', 'plan'];
      sections.forEach(sec => {
        const items = sentences.filter(s => s.section.toLowerCase() === sec);
        if (items.length === 0) return;

        const secDiv = document.createElement('div');
        secDiv.className = 'soap-section';
        secDiv.innerHTML = `<div class="soap-section-title">${sec} (${items.length})</div>`;

        items.forEach(s => {
          const card = document.createElement('div');
          card.className = `sentence-card ${s.flagged ? 'flagged' : ''}`;

          let supportHtml = '';
          if (s.support && s.support.length > 0) {
            supportHtml = s.support.map(sup => `
              <div class="chip" onmouseenter="highlightTurn(${sup.turn_id})" onmouseleave="unhighlightTurn(${sup.turn_id})" onclick="scrollToTurn(${sup.turn_id})">
                <span>📍 Turn ${sup.turn_id}: "${escapeHtml(sup.quote || '')}"</span>
              </div>
            `).join(' ');
          }

          let flagHtml = '';
          if (s.flagged) {
            flagHtml = s.hard_reasons.map(r => `
              <div class="flag-pill">⚠️ ${escapeHtml(r)}</div>
            `).join(' ');
          }

          card.innerHTML = `
            <div>${escapeHtml(s.text)}</div>
            <div>${supportHtml} ${flagHtml}</div>
          `;
          secDiv.appendChild(card);
        });

        container.appendChild(secDiv);
      });
    }

    function highlightTurn(turnId) {
      const el = document.getElementById(`turn-${turnId}`);
      if (el) el.classList.add('highlighted');
    }

    function unhighlightTurn(turnId) {
      const el = document.getElementById(`turn-${turnId}`);
      if (el) el.classList.remove('highlighted');
    }

    function scrollToTurn(turnId) {
      const el = document.getElementById(`turn-${turnId}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('highlighted');
        setTimeout(() => el.classList.remove('highlighted'), 2000);
      }
    }

    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }

    window.onload = init;
  </script>
</body>
</html>
"""


class PulseNoteDemoHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        if parsed.path == "/api/encounters":
            data = [{"id": eid, "turn_count": len(e["turns"])} for eid, e in ENCOUNTERS.items()]
            self.send_json(data)
            return

        if parsed.path == "/api/encounter":
            params = parse_qs(parsed.query)
            eid = params.get("id", [None])[0]
            if not eid or eid not in ENCOUNTERS:
                self.send_error(404, "Encounter not found")
                return

            enc = ENCOUNTERS[eid]
            computed = PRECOMPUTED.get(eid, {"baseline": [], "grounded": []})
            payload = {
                "id": eid,
                "turns": enc["turns"],
                "baseline": computed["baseline"],
                "grounded": computed["grounded"],
            }
            self.send_json(payload)
            return

        self.send_error(404, "Not Found")

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


def run_server(port=8080):
    server = HTTPServer(("0.0.0.0", port), PulseNoteDemoHandler)
    print(f"\\n PulseNote Auditor Web Demo running at http://localhost:{port}")
    print("Press Ctrl+C to stop.\\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\nShutting down server.")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port)
