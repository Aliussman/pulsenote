"""PulseNote: Interactive Clinical Provenance & Auditor Dashboard.

Zero external dependencies: runs with standard library Python http.server.
Usage:
    python demo/app.py [port]
    # Open http://localhost:8080 in your browser
"""

import json
import os
import sys
from difflib import SequenceMatcher
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Ensure project root is in path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.grounding import is_hard_failure, quote_matches, validate_sentence
from src.posthoc import post_hoc_check
from src.schemas import RawSentence, Support, Turn
from src.textnorm import content_words, has_negation, normalize, numbers


def load_reference_metadata():
    meta = {}
    path = ROOT_DIR / "data" / "reference_notes.json"
    if path.exists():
        with open(path) as f:
            refs = json.load(f)
        for eid, data in refs.items():
            comp = data.get("presenting_complaint", "")
            note = data.get("note", "")
            imp = ""
            for line in note.splitlines():
                line_clean = line.strip().lower()
                if line_clean.startswith("imp:") or line_clean.startswith("impression:"):
                    imp = line.split(":", 1)[1].strip().strip("?").strip()
                    break
            meta[eid] = {
                "complaint": comp,
                "impression": imp or "Primary Care Consultation",
                "highlights": data.get("highlights", []),
            }
    return meta


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
    # Load from results_eval (20 held-out) first, then fallback to results (dev set)
    for p in [ROOT_DIR / "results_eval" / "per_sentence.jsonl", ROOT_DIR / "results" / "per_sentence.jsonl"]:
        if p.exists():
            with open(p) as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        eid = row["encounter_id"]
                        if eid not in results:
                            results[eid] = {"baseline": [], "grounded": []}
                        if row["system"] == "baseline" and row["check"] == "posthoc":
                            # deduplicate by text
                            if not any(x["text"] == row["text"] for x in results[eid]["baseline"]):
                                results[eid]["baseline"].append(row)
                        elif row["system"] == "grounded" and row["check"] == "citation":
                            if not any(x["text"] == row["text"] for x in results[eid]["grounded"]):
                                results[eid]["grounded"].append(row)
    return results


ENCOUNTERS = load_encounters()
METADATA = load_reference_metadata()
PRECOMPUTED = load_precomputed_results()

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PulseNote: Clinical Provenance & Ambient Auditor</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #f8fafc;
      --surface: #ffffff;
      --surface-subtle: #f1f5f9;
      --border: #e2e8f0;
      --border-strong: #cbd5e1;
      --text: #0f172a;
      --text-muted: #64748b;
      --text-subtle: #94a3b8;
      --primary: #0284c7;
      --primary-light: #e0f2fe;
      --primary-hover: #0369a1;
      --doctor-bg: #e0f2fe;
      --doctor-text: #0369a1;
      --doctor-border: #bae6fd;
      --patient-bg: #ecfdf5;
      --patient-text: #047857;
      --patient-border: #a7f3d0;
      --flag-hard-bg: #ffe4e6;
      --flag-hard-text: #be123c;
      --flag-hard-border: #fecdd3;
      --flag-soft-bg: #fef3c7;
      --flag-soft-text: #b45309;
      --flag-soft-border: #fde68a;
      --pass-bg: #ecfdf5;
      --pass-text: #059669;
      --pass-border: #a7f3d0;
      --highlight: #fef08a;
      --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
      --shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1);
      --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
      --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1);
    }

    [data-theme="dark"] {
      --bg: #0b1120;
      --surface: #1e293b;
      --surface-subtle: #0f172a;
      --border: #334155;
      --border-strong: #475569;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --text-subtle: #64748b;
      --primary: #38bdf8;
      --primary-light: rgba(56, 189, 248, 0.15);
      --primary-hover: #7dd3fc;
      --doctor-bg: rgba(56, 189, 248, 0.15);
      --doctor-text: #38bdf8;
      --doctor-border: rgba(56, 189, 248, 0.3);
      --patient-bg: rgba(52, 211, 153, 0.15);
      --patient-text: #34d399;
      --patient-border: rgba(52, 211, 153, 0.3);
      --flag-hard-bg: rgba(244, 63, 94, 0.2);
      --flag-hard-text: #fb7185;
      --flag-hard-border: rgba(244, 63, 94, 0.4);
      --flag-soft-bg: rgba(251, 191, 36, 0.2);
      --flag-soft-text: #fcd34d;
      --flag-soft-border: rgba(251, 191, 36, 0.4);
      --pass-bg: rgba(16, 185, 129, 0.15);
      --pass-text: #34d399;
      --pass-border: rgba(16, 185, 129, 0.3);
      --highlight: rgba(234, 179, 8, 0.35);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    /* TOP NAVBAR */
    header {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 10px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      z-index: 20;
      box-shadow: var(--shadow-sm);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .brand-icon {
      width: 32px;
      height: 32px;
      background: var(--primary);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-weight: 700;
      font-size: 1.1rem;
    }
    .brand-name {
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--text);
    }
    .brand-tag {
      font-size: 0.72rem;
      font-weight: 600;
      background: var(--primary-light);
      color: var(--primary);
      padding: 2px 8px;
      border-radius: 999px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    /* STATS BANNER */
    .stat-banner {
      display: flex;
      align-items: center;
      gap: 20px;
      background: var(--surface-subtle);
      border: 1px solid var(--border);
      padding: 4px 14px;
      border-radius: 8px;
      font-size: 0.8rem;
    }
    .stat-metric {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .stat-val { font-weight: 700; color: var(--text); }
    .stat-lbl { color: var(--text-muted); }
    .stat-delta {
      color: #059669;
      font-weight: 700;
      background: var(--pass-bg);
      padding: 1px 6px;
      border-radius: 4px;
    }

    /* CONTROLS */
    .controls {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .btn {
      background: var(--surface);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 7px 12px;
      border-radius: 6px;
      font-size: 0.85rem;
      font-weight: 500;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s;
    }
    .btn:hover { background: var(--surface-subtle); border-color: var(--border-strong); }
    .btn.primary { background: var(--primary); color: #fff; border-color: var(--primary); }
    .btn.primary:hover { background: var(--primary-hover); }
    select.nav-select {
      background: var(--surface);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 7px 12px;
      border-radius: 6px;
      font-size: 0.85rem;
      font-weight: 500;
      cursor: pointer;
      max-width: 380px;
    }

    /* MAIN THREE-PANE LAYOUT */
    .workspace {
      display: grid;
      grid-template-columns: 380px 1fr 380px;
      flex: 1;
      overflow: hidden;
      background: var(--bg);
    }
    .pane {
      background: var(--surface);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .pane:last-child { border-right: none; }
    .pane-header {
      padding: 12px 16px;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }
    .pane-title {
      font-size: 0.9rem;
      font-weight: 700;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .pane-body {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      scroll-behavior: smooth;
    }

    /* TRANSCRIPT PANE */
    .search-box {
      width: 100%;
      padding: 8px 12px;
      background: var(--surface-subtle);
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 0.85rem;
      color: var(--text);
      margin-bottom: 12px;
    }
    .search-box:focus { outline: none; border-color: var(--primary); background: var(--surface); }
    .turn-card {
      padding: 10px 12px;
      margin-bottom: 8px;
      border-radius: 8px;
      background: var(--surface-subtle);
      border: 1px solid transparent;
      font-size: 0.88rem;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      position: relative;
    }
    .turn-card:hover {
      border-color: var(--border-strong);
      box-shadow: var(--shadow-sm);
    }
    .turn-card.highlighted {
      background: #fef9c3 !important;
      border-color: #facc15 !important;
      box-shadow: 0 0 0 2px rgba(234, 179, 8, 0.3), var(--shadow-md) !important;
      transform: translateY(-1px);
    }
    [data-theme="dark"] .turn-card.highlighted {
      background: rgba(234, 179, 8, 0.2) !important;
      border-color: #eab308 !important;
    }
    .turn-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 4px;
    }
    .turn-pill {
      font-size: 0.72rem;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .turn-pill.Doctor { background: var(--doctor-bg); color: var(--doctor-text); border: 1px solid var(--doctor-border); }
    .turn-pill.Patient { background: var(--patient-bg); color: var(--patient-text); border: 1px solid var(--patient-border); }
    .turn-id-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      color: var(--text-muted);
      font-weight: 500;
    }
    .turn-text mark {
      background: var(--highlight);
      color: inherit;
      padding: 1px 3px;
      border-radius: 3px;
      font-weight: 600;
    }

    /* NOTE DOCUMENT VIEW */
    .note-container {
      max-width: 760px;
      margin: 0 auto;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      box-shadow: var(--shadow);
      padding: 24px 28px;
    }
    .encounter-meta-banner {
      background: var(--surface-subtle);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 16px;
      margin-bottom: 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .chief-complaint { font-weight: 600; font-size: 0.95rem; color: var(--text); }
    .impression-pill {
      background: var(--primary-light);
      color: var(--primary);
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 600;
    }
    .filter-tabs {
      display: flex;
      gap: 6px;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--border);
    }
    .filter-tab {
      background: var(--surface-subtle);
      color: var(--text-muted);
      border: 1px solid var(--border);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }
    .filter-tab.active {
      background: var(--text);
      color: var(--surface);
      border-color: var(--text);
    }
    .soap-section {
      margin-bottom: 22px;
    }
    .soap-heading {
      font-size: 0.85rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--primary);
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 10px;
      padding-bottom: 4px;
      border-bottom: 1px solid var(--border);
    }
    .claim-item {
      padding: 10px 14px;
      margin-bottom: 8px;
      border-radius: 8px;
      background: var(--surface);
      border: 1px solid var(--border);
      cursor: pointer;
      transition: all 0.18s ease;
      position: relative;
    }
    .claim-item:hover {
      border-color: var(--primary);
      background: var(--primary-light);
      box-shadow: var(--shadow-sm);
    }
    .claim-item.active-claim {
      border-color: var(--primary);
      background: var(--primary-light);
      box-shadow: 0 0 0 2px var(--primary), var(--shadow-sm);
    }
    .claim-item.has-hard-failure {
      border-left: 4px solid var(--flag-hard-text);
      background: var(--flag-hard-bg);
    }
    .claim-text {
      font-size: 0.92rem;
      color: var(--text);
      line-height: 1.5;
      margin-bottom: 6px;
    }
    .claim-meta-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }
    .citation-pill {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: var(--surface);
      border: 1px solid var(--border-strong);
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 0.75rem;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text);
      font-weight: 500;
      transition: all 0.15s;
    }
    .citation-pill:hover {
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
    }
    .pill-alert {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 7px;
      border-radius: 4px;
      font-size: 0.72rem;
      font-weight: 600;
    }
    .pill-alert.hard {
      background: var(--flag-hard-bg);
      color: var(--flag-hard-text);
      border: 1px solid var(--flag-hard-border);
    }
    .pill-alert.soft {
      background: var(--flag-soft-bg);
      color: var(--flag-soft-text);
      border: 1px solid var(--flag-soft-border);
    }
    .pill-alert.pass {
      background: var(--pass-bg);
      color: var(--pass-text);
      border: 1px solid var(--pass-border);
    }

    /* INSPECTOR PANE */
    .inspector-card {
      background: var(--surface-subtle);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 14px;
    }
    .inspector-title {
      font-size: 0.8rem;
      text-transform: uppercase;
      font-weight: 700;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 8px;
      display: flex;
      justify-content: space-between;
    }
    .audit-rule {
      padding: 8px 10px;
      border-radius: 6px;
      background: var(--surface);
      border: 1px solid var(--border);
      margin-bottom: 6px;
      font-size: 0.82rem;
    }
    .audit-rule-header {
      display: flex;
      justify-content: space-between;
      font-weight: 600;
      margin-bottom: 3px;
    }
    .audit-status {
      font-size: 0.75rem;
      font-weight: 700;
    }
    .audit-status.ok { color: var(--pass-text); }
    .audit-status.fail { color: var(--flag-hard-text); }
    .quote-box {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      background: var(--surface);
      border: 1px solid var(--border);
      border-left: 3px solid var(--primary);
      padding: 8px 12px;
      border-radius: 4px;
      margin-top: 6px;
      color: var(--text);
    }

    /* LIVE PLAYGROUND MODAL */
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.6);
      backdrop-filter: blur(4px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 50;
    }
    .modal {
      background: var(--surface);
      border-radius: 12px;
      border: 1px solid var(--border);
      box-shadow: var(--shadow-lg);
      width: 90%;
      max-width: 640px;
      padding: 24px;
    }
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }
    .form-group {
      margin-bottom: 14px;
    }
    .form-group label {
      display: block;
      font-size: 0.82rem;
      font-weight: 600;
      margin-bottom: 6px;
      color: var(--text);
    }
    .form-input, .form-textarea, .form-select {
      width: 100%;
      padding: 8px 12px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: var(--surface-subtle);
      color: var(--text);
      font-size: 0.88rem;
    }
    .form-textarea { resize: vertical; min-height: 70px; }
    .playground-result {
      margin-top: 16px;
      padding: 12px;
      border-radius: 8px;
      background: var(--surface-subtle);
      border: 1px solid var(--border);
      font-size: 0.85rem;
    }
  </style>
</head>
<body>

  <!-- TOP HEADER -->
  <header>
    <div class="brand">
      <div class="brand-icon">⚡</div>
      <div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="brand-name">PulseNote</span>
          <span class="brand-tag">Validator-v2 Live</span>
        </div>
      </div>
    </div>

    <!-- STATS STRIP -->
    <div class="stat-banner">
      <div class="stat-metric">
        <span class="stat-lbl">Held-Out Set:</span>
        <span class="stat-val">20 Consultations (1,015 Claims)</span>
      </div>
      <div style="width: 1px; height: 16px; background: var(--border);"></div>
      <div class="stat-metric">
        <span class="stat-lbl">Grounded Hard Errors:</span>
        <span class="stat-val" style="color: var(--pass-text);">3.6%</span>
        <span class="stat-lbl">[2.4% - 5.3%]</span>
      </div>
      <div style="width: 1px; height: 16px; background: var(--border);"></div>
      <div class="stat-metric">
        <span class="stat-lbl">Baseline Hard Errors:</span>
        <span class="stat-val" style="color: var(--flag-hard-text);">7.0%</span>
        <span class="stat-lbl">[4.8% - 10.2%]</span>
      </div>
      <div class="stat-delta">-48.6% Relative Risk</div>
    </div>

    <!-- CONTROLS -->
    <div class="controls">
      <button class="btn" onclick="prevEncounter()" title="Previous encounter">←</button>
      <select id="enc-select" class="nav-select" onchange="loadEncounter(this.value)">
        <!-- Populated via API -->
      </select>
      <button class="btn" onclick="nextEncounter()" title="Next encounter">→</button>
      <button class="btn primary" onclick="openPlayground()">🧪 Live Auditor</button>
      <button class="btn" onclick="toggleTheme()" id="theme-btn">🌙</button>
    </div>
  </header>

  <!-- WORKSPACE -->
  <main class="workspace">

    <!-- LEFT PANE: TRANSCRIPT -->
    <section class="pane" style="width: 400px;">
      <div class="pane-header">
        <div class="pane-title">
          <span>🎙️ Consultation Transcript</span>
        </div>
        <span id="transcript-count" style="font-size: 0.78rem; font-weight: 600; color: var(--text-muted);">0 turns</span>
      </div>
      <div class="pane-body">
        <input type="text" id="turn-filter" class="search-box" placeholder="🔍 Search dialogue turns..." oninput="filterTurns(this.value)">
        <div id="transcript-list">
          <!-- Turns rendered dynamically -->
        </div>
      </div>
    </section>

    <!-- CENTER PANE: SOAP NOTE DOCUMENT -->
    <section class="pane" style="background: var(--bg);">
      <div class="pane-header">
        <div class="pane-title">
          <span>📋 Clinical SOAP Document</span>
        </div>
        <div style="display: flex; gap: 8px;">
          <button id="view-grounded-btn" class="btn primary" style="padding: 4px 10px; font-size: 0.78rem;" onclick="setViewMode('grounded')">Grounded (Citations)</button>
          <button id="view-baseline-btn" class="btn" style="padding: 4px 10px; font-size: 0.78rem;" onclick="setViewMode('baseline')">Baseline (Ungrounded)</button>
        </div>
      </div>
      <div class="pane-body">
        <div class="note-container">
          <!-- Metadata Banner -->
          <div class="encounter-meta-banner">
            <div>
              <div style="font-size: 0.72rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Presenting Complaint</div>
              <div class="chief-complaint" id="meta-complaint">—</div>
            </div>
            <div>
              <span class="impression-pill" id="meta-impression">—</span>
            </div>
          </div>

          <!-- Filter Toolbar -->
          <div class="filter-tabs">
            <button class="filter-tab active" onclick="setClaimFilter('all')">All Claims (<span id="count-all">0</span>)</button>
            <button class="filter-tab" onclick="setClaimFilter('disputed')">⚠️ Discrepancies Only (<span id="count-disputed">0</span>)</button>
            <button class="filter-tab" onclick="setClaimFilter('verified')">✓ Verified Only (<span id="count-verified">0</span>)</button>
          </div>

          <!-- SOAP Note Sections -->
          <div id="soap-content">
            <!-- Sections rendered dynamically -->
          </div>
        </div>
      </div>
    </section>

    <!-- RIGHT PANE: EVIDENCE & PROVENANCE INSPECTOR -->
    <section class="pane" style="width: 380px;">
      <div class="pane-header">
        <div class="pane-title">
          <span>🔬 Provenance Inspector</span>
        </div>
        <span id="inspect-status" class="pill-alert pass" style="display: none;">Verified</span>
      </div>
      <div class="pane-body" id="inspector-body">
        <div style="text-align: center; color: var(--text-muted); padding: 40px 10px;">
          <div style="font-size: 2.2rem; margin-bottom: 12px;">👆</div>
          <p style="font-weight: 600; font-size: 0.9rem; margin-bottom: 4px;">Select any clinical claim</p>
          <p style="font-size: 0.8rem;">Click a sentence in the note to inspect its verbatim quote alignment, number consistency, and clinical authority audit.</p>
        </div>
      </div>
    </section>

  </main>

  <!-- LIVE AUDITOR PLAYGROUND MODAL -->
  <div class="modal-backdrop" id="playground-modal" onclick="closePlayground(event)">
    <div class="modal" onclick="event.stopPropagation()">
      <div class="modal-header">
        <h3 style="font-size: 1.1rem; font-weight: 700;">🧪 Real-Time Claim Auditor</h3>
        <button class="btn" onclick="closePlayground()">✕</button>
      </div>
      <p style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 14px;">
        Test how the deterministic verification engine scores any custom clinical claim against dialogue evidence.
      </p>

      <div class="form-group">
        <label>Clinical Sentence</label>
        <input type="text" id="play-sentence" class="form-input" placeholder="e.g. The patient denies headache, fever, or vomiting.">
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
        <div class="form-group">
          <label>SOAP Section</label>
          <select id="play-section" class="form-select">
            <option value="S">Subjective (S)</option>
            <option value="O">Objective (O)</option>
            <option value="A">Assessment (A)</option>
            <option value="P">Plan (P)</option>
          </select>
        </div>
        <div class="form-group">
          <label>Cited Turn ID</label>
          <select id="play-turn" class="form-select">
            <!-- Dynamically populated from active encounter -->
          </select>
        </div>
      </div>

      <div class="form-group">
        <label>Verbatim Quoted Snippet</label>
        <input type="text" id="play-quote" class="form-input" placeholder="e.g. no fever, no vomiting">
      </div>

      <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px;">
        <button class="btn" onclick="closePlayground()">Cancel</button>
        <button class="btn primary" onclick="runPlaygroundAudit()">Audit Claim</button>
      </div>

      <div id="playground-output" style="display: none;"></div>
    </div>
  </div>

  <script>
    let encountersList = [];
    let currentEncounterId = null;
    let currentData = null;
    let currentView = 'grounded';
    let currentFilter = 'all';
    let activeClaimIndex = null;

    async function init() {
      const resp = await fetch('/api/encounters');
      encountersList = await resp.json();
      const select = document.getElementById('enc-select');
      select.innerHTML = '';

      encountersList.forEach((e, idx) => {
        const opt = document.createElement('option');
        opt.value = e.id;
        const impText = e.impression ? ` · ${e.impression}` : '';
        opt.textContent = `${e.id}${impText} (${e.turn_count} turns)`;
        select.appendChild(opt);
      });

      if (encountersList.length > 0) {
        loadEncounter(encountersList[0].id);
      }
    }

    async function loadEncounter(id) {
      currentEncounterId = id;
      document.getElementById('enc-select').value = id;
      const resp = await fetch(`/api/encounter?id=${encodeURIComponent(id)}`);
      currentData = await resp.json();

      document.getElementById('meta-complaint').textContent = currentData.complaint ? `"${currentData.complaint}"` : 'Routine Consultation';
      document.getElementById('meta-impression').textContent = currentData.impression || 'Primary Care Consultation';

      populatePlaygroundTurns();
      renderTranscript();
      renderSOAPNote();
      clearInspector();
    }

    function prevEncounter() {
      const idx = encountersList.findIndex(e => e.id === currentEncounterId);
      if (idx > 0) loadEncounter(encountersList[idx - 1].id);
    }

    function nextEncounter() {
      const idx = encountersList.findIndex(e => e.id === currentEncounterId);
      if (idx < encountersList.length - 1) loadEncounter(encountersList[idx + 1].id);
    }

    function setViewMode(mode) {
      currentView = mode;
      document.getElementById('view-grounded-btn').classList.toggle('primary', mode === 'grounded');
      document.getElementById('view-baseline-btn').classList.toggle('primary', mode === 'baseline');
      renderSOAPNote();
      clearInspector();
    }

    function setClaimFilter(filter) {
      currentFilter = filter;
      document.querySelectorAll('.filter-tab').forEach((tab, i) => {
        tab.classList.toggle('active', (i === 0 && filter === 'all') || (i === 1 && filter === 'disputed') || (i === 2 && filter === 'verified'));
      });
      renderSOAPNote();
    }

    function renderTranscript(filterQuery = '') {
      const container = document.getElementById('transcript-list');
      container.innerHTML = '';
      const q = filterQuery.toLowerCase().trim();
      let matchCount = 0;

      currentData.turns.forEach(t => {
        if (q && !t.text.toLowerCase().includes(q) && !t.speaker.toLowerCase().includes(q)) return;
        matchCount++;

        const div = document.createElement('div');
        div.className = 'turn-card';
        div.id = `turn-${t.id}`;
        div.innerHTML = `
          <div class="turn-header">
            <span class="turn-pill ${t.speaker}">${t.speaker}</span>
            <span class="turn-id-badge">Turn ${t.id}</span>
          </div>
          <div class="turn-text">${escapeHtml(t.text)}</div>
        `;
        container.appendChild(div);
      });

      document.getElementById('transcript-count').textContent = `${matchCount} / ${currentData.turns.length} turns`;
    }

    function filterTurns(query) {
      renderTranscript(query);
    }

    function renderSOAPNote() {
      const container = document.getElementById('soap-content');
      container.innerHTML = '';
      const sentences = currentView === 'grounded' ? currentData.grounded : currentData.baseline;

      const totalCount = sentences.length;
      const disputedCount = sentences.filter(s => s.flagged).length;
      const verifiedCount = totalCount - disputedCount;

      document.getElementById('count-all').textContent = totalCount;
      document.getElementById('count-disputed').textContent = disputedCount;
      document.getElementById('count-verified').textContent = verifiedCount;

      let filtered = sentences;
      if (currentFilter === 'disputed') filtered = sentences.filter(s => s.flagged);
      if (currentFilter === 'verified') filtered = sentences.filter(s => !s.flagged);

      if (filtered.length === 0) {
        container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 30px;">No claims matching filter criteria.</div>`;
        return;
      }

      const sectionOrder = [
        { code: 'S', title: 'Subjective (S)', icon: '🗣️' },
        { code: 'O', title: 'Objective (O)', icon: '🩺' },
        { code: 'A', title: 'Assessment (A)', icon: '🧠' },
        { code: 'P', title: 'Plan (P)', icon: '📝' },
      ];

      sectionOrder.forEach(sec => {
        const secClaims = filtered.filter(s => s.section.toUpperCase() === sec.code);
        if (secClaims.length === 0) return;

        const secDiv = document.createElement('div');
        secDiv.className = 'soap-section';
        secDiv.innerHTML = `<div class="soap-heading"><span>${sec.icon}</span> <span>${sec.title}</span></div>`;

        secClaims.forEach((claim, idx) => {
          const item = document.createElement('div');
          const isHard = claim.flagged;
          item.className = `claim-item ${isHard ? 'has-hard-failure' : ''}`;
          item.id = `claim-${sec.code}-${idx}`;

          let pillsHtml = '';
          if (claim.support && claim.support.length > 0) {
            pillsHtml += claim.support.map(sup => `
              <span class="citation-pill" onclick="event.stopPropagation(); jumpToTurn(${sup.turn_id}, '${escapeAttr(sup.quote)}')">
                📍 T${sup.turn_id}: "${escapeHtml(sup.quote || '')}"
              </span>
            `).join(' ');
          }

          if (claim.flagged) {
            pillsHtml += claim.hard_reasons.map(r => `
              <span class="pill-alert hard">⚠️ ${humanizeReason(r)}</span>
            `).join(' ');
          } else {
            pillsHtml += `<span class="pill-alert pass">✓ Verified</span>`;
          }

          item.innerHTML = `
            <div class="claim-text">${escapeHtml(claim.text)}</div>
            <div class="claim-meta-row">${pillsHtml}</div>
          `;

          item.onclick = () => selectClaim(claim, item);
          secDiv.appendChild(item);
        });

        container.appendChild(secDiv);
      });
    }

    function selectClaim(claim, element) {
      document.querySelectorAll('.claim-item').forEach(el => el.classList.remove('active-claim'));
      if (element) element.classList.add('active-claim');

      renderInspector(claim);

      if (claim.support && claim.support.length > 0) {
        jumpToTurn(claim.support[0].turn_id, claim.support[0].quote);
      }
    }

    function renderInspector(claim) {
      const container = document.getElementById('inspector-body');
      const statusPill = document.getElementById('inspect-status');
      statusPill.style.display = 'inline-block';
      statusPill.className = `pill-alert ${claim.flagged ? 'hard' : 'pass'}`;
      statusPill.textContent = claim.flagged ? 'Discrepancy' : 'Verified';

      let supportBox = '';
      if (claim.support && claim.support.length > 0) {
        supportBox = claim.support.map(sup => `
          <div class="inspector-card">
            <div class="inspector-title">
              <span>Cited Evidence (Turn ${sup.turn_id})</span>
              <button class="btn" style="padding: 2px 6px; font-size: 0.72rem;" onclick="jumpToTurn(${sup.turn_id}, '${escapeAttr(sup.quote)}')">Focus ↗</button>
            </div>
            <div class="quote-box">"${escapeHtml(sup.quote)}"</div>
          </div>
        `).join('');
      } else {
        supportBox = `
          <div class="inspector-card" style="background: var(--flag-hard-bg); border-color: var(--flag-hard-border);">
            <div class="inspector-title" style="color: var(--flag-hard-text);">Missing Turn Evidence</div>
            <p style="font-size: 0.8rem;">No explicit citation was produced by the generator for this claim.</p>
          </div>
        `;
      }

      const hardReasons = claim.hard_reasons || [];
      const hasNumberError = hardReasons.some(r => r.startsWith('numbers_not_in_source'));
      const hasNegationError = hardReasons.some(r => r.includes('negation'));
      const hasQuoteError = hardReasons.some(r => r.startsWith('quote_not_in_turn'));
      const hasClinicianError = hardReasons.some(r => r.startsWith('assessment_or_plan_not_from_clinician'));

      container.innerHTML = `
        <div class="inspector-card">
          <div class="inspector-title">Active Clinical Claim</div>
          <div style="font-size: 0.9rem; font-weight: 600; line-height: 1.4; color: var(--text);">
            ${escapeHtml(claim.text)}
          </div>
          <div style="margin-top: 8px; font-size: 0.75rem; color: var(--text-muted);">
            Section: <strong>${claim.section}</strong> · System: <strong>${claim.system}</strong> (${claim.check})
          </div>
        </div>

        ${supportBox}

        <div class="inspector-card">
          <div class="inspector-title">Deterministic Rule Audit</div>

          <div class="audit-rule">
            <div class="audit-rule-header">
              <span>1. Quote Alignment</span>
              <span class="audit-status ${hasQuoteError ? 'fail' : 'ok'}">${hasQuoteError ? 'FAILED' : 'PASS'}</span>
            </div>
            <div style="font-size: 0.75rem; color: var(--text-muted);">
              ${hasQuoteError ? 'Verbatim quote was not found in cited turn text (SequenceMatcher &lt; 0.90).' : 'Verbatim quote cleanly verifies against cited turn speech.'}
            </div>
          </div>

          <div class="audit-rule">
            <div class="audit-rule-header">
              <span>2. Quantities & Dosages</span>
              <span class="audit-status ${hasNumberError ? 'fail' : 'ok'}">${hasNumberError ? 'FAILED' : 'PASS'}</span>
            </div>
            <div style="font-size: 0.75rem; color: var(--text-muted);">
              ${hasNumberError ? 'Claim introduced quantities/durations absent from cited evidence.' : 'All extracted numbers match source dialogue tokens.'}
            </div>
          </div>

          <div class="audit-rule">
            <div class="audit-rule-header">
              <span>3. Negation Polarity</span>
              <span class="audit-status ${hasNegationError ? 'fail' : 'ok'}">${hasNegationError ? 'FAILED' : 'PASS'}</span>
            </div>
            <div style="font-size: 0.75rem; color: var(--text-muted);">
              ${hasNegationError ? 'Discrepancy in negation cues (dropped negation or unsupported denial).' : 'Negation polarity matches evidence accurately.'}
            </div>
          </div>

          <div class="audit-rule">
            <div class="audit-rule-header">
              <span>4. Clinical Authority</span>
              <span class="audit-status ${hasClinicianError ? 'fail' : 'ok'}">${hasClinicianError ? 'FAILED' : 'PASS'}</span>
            </div>
            <div style="font-size: 0.75rem; color: var(--text-muted);">
              ${hasClinicianError ? 'Assessment/Plan claim cites patient statements without clinician confirmation.' : 'Clinical decision authored by clinician turn.'}
            </div>
          </div>
        </div>
      `;
    }

    function clearInspector() {
      document.getElementById('inspector-body').innerHTML = `
        <div style="text-align: center; color: var(--text-muted); padding: 40px 10px;">
          <div style="font-size: 2.2rem; margin-bottom: 12px;">👆</div>
          <p style="font-weight: 600; font-size: 0.9rem; margin-bottom: 4px;">Select any clinical claim</p>
          <p style="font-size: 0.8rem;">Click a sentence in the note to inspect its verbatim quote alignment, number consistency, and clinical authority audit.</p>
        </div>
      `;
      document.getElementById('inspect-status').style.display = 'none';
    }

    function jumpToTurn(turnId, quote) {
      document.querySelectorAll('.turn-card').forEach(el => {
        el.classList.remove('highlighted');
        const textDiv = el.querySelector('.turn-text');
        if (textDiv) textDiv.innerHTML = escapeHtml(textDiv.textContent);
      });

      const el = document.getElementById(`turn-${turnId}`);
      if (!el) return;

      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('highlighted');

      if (quote) {
        const textDiv = el.querySelector('.turn-text');
        const raw = textDiv.textContent;
        const idx = raw.toLowerCase().indexOf(quote.toLowerCase());
        if (idx !== -1) {
          const before = raw.substring(0, idx);
          const match = raw.substring(idx, idx + quote.length);
          const after = raw.substring(idx + quote.length);
          textDiv.innerHTML = `${escapeHtml(before)}<mark>${escapeHtml(match)}</mark>${escapeHtml(after)}`;
        }
      }
    }

    function populatePlaygroundTurns() {
      const select = document.getElementById('play-turn');
      select.innerHTML = '';
      currentData.turns.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = `Turn ${t.id} (${t.speaker}): ${t.text.substring(0, 50)}...`;
        select.appendChild(opt);
      });
    }

    function openPlayground() {
      document.getElementById('playground-modal').style.display = 'flex';
    }

    function closePlayground(e) {
      if (!e || e.target.id === 'playground-modal' || e.target.tagName === 'BUTTON') {
        document.getElementById('playground-modal').style.display = 'none';
      }
    }

    async function runPlaygroundAudit() {
      const sentence = document.getElementById('play-sentence').value.trim();
      const section = document.getElementById('play-section').value;
      const turnId = parseInt(document.getElementById('play-turn').value, 10);
      const quote = document.getElementById('play-quote').value.trim();

      if (!sentence) {
        alert('Please enter a clinical sentence');
        return;
      }

      const payload = {
        encounter_id: currentEncounterId,
        sentence: sentence,
        section: section,
        turn_id: turnId,
        quote: quote
      };

      const resp = await fetch('/api/audit_custom', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const result = await resp.json();

      const out = document.getElementById('playground-output');
      out.style.display = 'block';
      out.className = `playground-result ${result.flagged ? 'has-hard-failure' : ''}`;

      let reasonsHtml = result.reasons.length > 0
        ? result.reasons.map(r => `<div>⚠️ <strong>${humanizeReason(r)}</strong> (<code>${r}</code>)</div>`).join('')
        : '<div style="color: var(--pass-text); font-weight: 600;">✓ Claim passed all deterministic validation rules cleanly!</div>';

      out.innerHTML = `
        <div style="font-weight: 700; margin-bottom: 6px; display: flex; justify-content: space-between;">
          <span>Audit Verdict:</span>
          <span class="pill-alert ${result.flagged ? 'hard' : 'pass'}">${result.flagged ? 'Discrepancy Flagged' : 'Clean Pass'}</span>
        </div>
        ${reasonsHtml}
      `;
    }

    function humanizeReason(reason) {
      const code = reason.split(':')[0];
      const arg = reason.split(':')[1] || '';
      switch (code) {
        case 'numbers_not_in_source':
          return `Uncited Number/Duration: "${arg}" not spoken in cited turn`;
        case 'quote_not_in_turn':
          return `Quote Mismatch in Turn ${arg}`;
        case 'possible_dropped_negation':
          return `Dropped Negation (evidence was negative, note asserted affirmative)`;
        case 'negation_not_in_quote':
          return `Uncited Negation (note denies symptom without negative quote clause)`;
        case 'assessment_or_plan_not_from_clinician':
          return `Clinician Authority Violation (Plan statement cited patient)`;
        case 'no_matching_turn':
          return `Factual Hallucination: No supporting dialogue turn exists`;
        case 'low_overlap':
          return `Low Lexical Overlap (${arg})`;
        default:
          return reason;
      }
    }

    function escapeHtml(text) {
      if (!text) return '';
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }

    function escapeAttr(text) {
      if (!text) return '';
      return text.replace(/'/g, "\\\\'").replace(/"/g, '&quot;');
    }

    function toggleTheme() {
      const isDark = document.body.getAttribute('data-theme') === 'dark';
      document.body.setAttribute('data-theme', isDark ? 'light' : 'dark');
      document.getElementById('theme-btn').textContent = isDark ? '🌙' : '☀️';
    }

    window.onload = init;
  </script>
</body>
</html>
"""


class PulseNoteDemoHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        if parsed.path == "/api/encounters":
            data = []
            for eid, e in ENCOUNTERS.items():
                m = METADATA.get(eid, {})
                data.append(
                    {
                        "id": eid,
                        "turn_count": len(e["turns"]),
                        "complaint": m.get("complaint", ""),
                        "impression": m.get("impression", ""),
                    }
                )
            self.send_json(data)
            return

        if parsed.path == "/api/encounter":
            params = parse_qs(parsed.query)
            eid = params.get("id", [None])[0]
            if not eid or eid not in ENCOUNTERS:
                self.send_error(404, "Encounter not found")
                return

            enc = ENCOUNTERS[eid]
            m = METADATA.get(eid, {})
            computed = PRECOMPUTED.get(eid, {"baseline": [], "grounded": []})
            payload = {
                "id": eid,
                "complaint": m.get("complaint", ""),
                "impression": m.get("impression", ""),
                "turns": enc["turns"],
                "baseline": computed["baseline"],
                "grounded": computed["grounded"],
            }
            self.send_json(payload)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/audit_custom":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))

            eid = data.get("encounter_id")
            sentence_text = data.get("sentence", "")
            section = data.get("section", "S")
            turn_id = int(data.get("turn_id", 0))
            quote = data.get("quote", "")

            enc = ENCOUNTERS.get(eid, {})
            turns = [Turn(**t) for t in enc.get("turns", [])]
            turns_by_id = {t.id: t for t in turns}

            raw = RawSentence(
                text=sentence_text,
                section=section,
                support=[Support(turn_id=turn_id, quote=quote)] if quote else [],
            )
            reasons = validate_sentence(raw, turns_by_id)
            hard = [r for r in reasons if is_hard_failure(r)]

            self.send_json(
                {
                    "flagged": bool(hard),
                    "reasons": reasons,
                    "hard_reasons": hard,
                }
            )
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
    print(f"\n=======================================================")
    print(f" PulseNote Interactive Clinical Auditor Web Demo")
    print(f" Running at: http://localhost:{port}")
    print(f" Press Ctrl+C to terminate.")
    print(f"=======================================================\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port)
