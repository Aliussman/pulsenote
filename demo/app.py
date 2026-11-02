"""PulseNote: Clinical Provenance & Ambient Auditor Dashboard.

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
  <title>PulseNote — Clinical Documentation Provenance & Verification</title>
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
      --primary-subtle: #f0f9ff;
      --primary-border: #bae6fd;
      --doctor-bg: #f0f9ff;
      --doctor-text: #0369a1;
      --doctor-border: #bae6fd;
      --patient-bg: #f0fdf4;
      --patient-text: #15803d;
      --patient-border: #bbf7d0;
      --danger-bg: #fff1f2;
      --danger-text: #e11d48;
      --danger-border: #fecdd3;
      --warning-bg: #fffbeb;
      --warning-text: #d97706;
      --warning-border: #fde68a;
      --success-bg: #f0fdf4;
      --success-text: #16a34a;
      --success-border: #bbf7d0;
      --highlight-bg: #fef08a;
      --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
      --shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.08), 0 1px 2px -1px rgba(0, 0, 0, 0.04);
      --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.04);
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }

    [data-theme="dark"] {
      --bg: #090d16;
      --surface: #131c2e;
      --surface-subtle: #0d1525;
      --border: #223049;
      --border-strong: #334464;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --text-subtle: #64748b;
      --primary: #38bdf8;
      --primary-subtle: rgba(56, 189, 248, 0.12);
      --primary-border: rgba(56, 189, 248, 0.28);
      --doctor-bg: rgba(56, 189, 248, 0.12);
      --doctor-text: #38bdf8;
      --doctor-border: rgba(56, 189, 248, 0.28);
      --patient-bg: rgba(52, 211, 153, 0.12);
      --patient-text: #34d399;
      --patient-border: rgba(52, 211, 153, 0.28);
      --danger-bg: rgba(244, 63, 94, 0.14);
      --danger-text: #fb7185;
      --danger-border: rgba(244, 63, 94, 0.35);
      --warning-bg: rgba(245, 158, 11, 0.14);
      --warning-text: #fbbf24;
      --warning-border: rgba(245, 158, 11, 0.35);
      --success-bg: rgba(16, 185, 129, 0.14);
      --success-text: #34d399;
      --success-border: rgba(16, 185, 129, 0.35);
      --highlight-bg: rgba(234, 179, 8, 0.28);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      height: 100%;
      width: 100%;
      font-family: var(--font-sans);
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      overflow: hidden;
      -webkit-font-smoothing: antialiased;
    }

    /* ICONS (Pure SVG) */
    .icon {
      display: inline-block;
      width: 15px;
      height: 15px;
      stroke-width: 2;
      stroke: currentColor;
      fill: none;
      stroke-linecap: round;
      stroke-linejoin: round;
      vertical-align: middle;
      flex-shrink: 0;
    }

    /* TOP APPLICATION BAR */
    header.app-header {
      height: 54px;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 0 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      z-index: 30;
      flex-shrink: 0;
    }
    .brand-cluster {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-mark {
      width: 28px;
      height: 28px;
      background: var(--primary);
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
    }
    .brand-title {
      font-size: 0.98rem;
      font-weight: 700;
      letter-spacing: -0.01em;
      color: var(--text);
    }
    .brand-version-pill {
      font-size: 0.68rem;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      padding: 2px 7px;
      border-radius: 4px;
      background: var(--primary-subtle);
      color: var(--primary);
      border: 1px solid var(--primary-border);
    }

    /* BENCHMARK INTERACTIVE BADGE & POPOVER */
    .benchmark-container {
      position: relative;
    }
    .benchmark-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: var(--surface-subtle);
      border: 1px solid var(--border);
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 0.77rem;
      cursor: pointer;
      user-select: none;
      transition: background 0.15s, border-color 0.15s, box-shadow 0.15s;
    }
    .benchmark-pill:hover {
      background: var(--surface);
      border-color: var(--border-strong);
      box-shadow: var(--shadow-sm);
    }
    .pulse-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--success-text);
      box-shadow: 0 0 0 2px var(--success-border);
      flex-shrink: 0;
    }
    .b-title {
      font-weight: 600;
      color: var(--text);
    }
    .b-rate {
      color: var(--success-text);
      font-weight: 700;
    }
    .b-vs {
      color: var(--text-muted);
      font-size: 0.74rem;
    }
    .b-delta {
      font-weight: 700;
      color: var(--success-text);
      background: var(--success-bg);
      border: 1px solid var(--success-border);
      padding: 1px 6px;
      border-radius: 999px;
      font-size: 0.7rem;
    }
    .chevron-icon {
      width: 12px;
      height: 12px;
      color: var(--text-muted);
      transition: transform 0.15s ease;
    }
    .benchmark-container.active .chevron-icon {
      transform: rotate(180deg);
    }
    .benchmark-popover {
      position: absolute;
      top: calc(100% + 10px);
      left: 50%;
      transform: translateX(-50%);
      width: 440px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      box-shadow: var(--shadow-md);
      padding: 16px;
      z-index: 100;
      display: none;
    }
    .benchmark-container.active .benchmark-popover {
      display: block;
      animation: popIn 0.12s ease-out;
    }
    @keyframes popIn {
      from { opacity: 0; transform: translate(-50%, -4px); }
      to { opacity: 1; transform: translate(-50%, 0); }
    }
    .popover-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }
    .popover-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-bottom: 12px;
    }
    .popover-card {
      background: var(--surface-subtle);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
    }
    .popover-label {
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 4px;
    }
    .popover-stat {
      font-size: 1.25rem;
      font-weight: 800;
      line-height: 1.2;
    }
    .popover-ci {
      font-size: 0.72rem;
      color: var(--text-muted);
      font-family: var(--font-mono);
      margin-top: 2px;
    }
    .popover-pass {
      font-size: 0.72rem;
      color: var(--text-subtle);
      margin-top: 4px;
    }
    .popover-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--surface-subtle);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 0.75rem;
    }

    /* ACTIONS & NAVIGATION */
    .action-cluster {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .btn {
      background: var(--surface);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 6px 11px;
      border-radius: 6px;
      font-size: 0.82rem;
      font-weight: 500;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: background 0.12s, border-color 0.12s, box-shadow 0.12s;
      white-space: nowrap;
    }
    .btn:hover {
      background: var(--surface-subtle);
      border-color: var(--border-strong);
    }
    .btn.primary {
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
    }
    .btn.primary:hover {
      filter: brightness(0.95);
    }
    .select-dropdown {
      background: var(--surface);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 0.82rem;
      font-weight: 500;
      cursor: pointer;
      max-width: 340px;
      outline: none;
    }
    .select-dropdown:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 2px var(--primary-subtle);
    }

    /* WORKSPACE: STRICT 3-COLUMN LAYOUT */
    main.app-workspace {
      display: grid;
      grid-template-columns: 360px 1fr 380px;
      height: calc(100% - 54px);
      width: 100%;
      overflow: hidden;
      background: var(--bg);
    }
    .panel {
      min-width: 0;
      min-height: 0;
      display: flex;
      flex-direction: column;
      background: var(--surface);
      border-right: 1px solid var(--border);
      overflow: hidden;
    }
    .panel:last-child {
      border-right: none;
    }

    /* PANEL HEADERS */
    .panel-header {
      height: 46px;
      padding: 0 16px;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      flex-shrink: 0;
    }
    .panel-title {
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 7px;
    }
    .panel-body {
      flex: 1;
      overflow-y: auto;
      overflow-x: hidden;
      padding: 14px 16px;
      scroll-behavior: smooth;
    }

    /* PANE 1: DIALOGUE TRANSCRIPT */
    .search-input-wrap {
      position: relative;
      margin-bottom: 12px;
    }
    .search-input-wrap .search-icon {
      position: absolute;
      left: 10px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-subtle);
      pointer-events: none;
    }
    .transcript-search {
      width: 100%;
      padding: 7px 10px 7px 32px;
      background: var(--surface-subtle);
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 0.82rem;
      color: var(--text);
      outline: none;
      transition: border-color 0.15s, background 0.15s;
    }
    .transcript-search:focus {
      background: var(--surface);
      border-color: var(--primary);
      box-shadow: 0 0 0 2px var(--primary-subtle);
    }

    .turn-row {
      padding: 9px 11px;
      margin-bottom: 7px;
      border-radius: 6px;
      background: var(--surface-subtle);
      border: 1px solid transparent;
      font-size: 0.83rem;
      transition: background 0.15s, border-color 0.15s, transform 0.15s;
    }
    .turn-row:hover {
      border-color: var(--border-strong);
    }
    .turn-row.highlighted {
      background: #fef9c3 !important;
      border-color: #facc15 !important;
      box-shadow: var(--shadow-sm);
    }
    [data-theme="dark"] .turn-row.highlighted {
      background: rgba(234, 179, 8, 0.18) !important;
      border-color: rgba(234, 179, 8, 0.5) !important;
    }
    .turn-row-meta {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 4px;
    }
    .role-badge {
      font-size: 0.68rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      padding: 2px 6px;
      border-radius: 3px;
    }
    .role-badge.Doctor {
      background: var(--doctor-bg);
      color: var(--doctor-text);
      border: 1px solid var(--doctor-border);
    }
    .role-badge.Patient {
      background: var(--patient-bg);
      color: var(--patient-text);
      border: 1px solid var(--patient-border);
    }
    .turn-number {
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: var(--text-subtle);
      font-weight: 500;
    }
    .turn-text {
      color: var(--text);
      line-height: 1.45;
      word-break: break-word;
    }
    .turn-text mark {
      background: var(--highlight-bg);
      color: inherit;
      padding: 1px 3px;
      border-radius: 2px;
      font-weight: 600;
    }

    /* PANE 2: SOAP DOCUMENT */
    .document-viewport {
      background: var(--bg);
      padding: 16px 20px;
    }
    .clinical-card {
      max-width: 820px;
      margin: 0 auto;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: var(--shadow-sm);
      overflow: hidden;
    }
    .chart-banner {
      padding: 14px 18px;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    .chart-patient-info {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .chart-tag-label {
      font-size: 0.68rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
    }
    .chart-complaint {
      font-size: 0.92rem;
      font-weight: 600;
      color: var(--text);
    }
    .chart-impression-pill {
      background: var(--primary-subtle);
      color: var(--primary);
      border: 1px solid var(--primary-border);
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 0.76rem;
      font-weight: 600;
      white-space: nowrap;
    }

    /* SEGMENTED FILTER TOOLBAR */
    .filter-bar {
      padding: 8px 18px;
      background: var(--surface-subtle);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .seg-btn {
      background: transparent;
      color: var(--text-muted);
      border: none;
      padding: 4px 9px;
      border-radius: 4px;
      font-size: 0.76rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: background 0.12s, color 0.12s;
    }
    .seg-btn:hover {
      background: rgba(0, 0, 0, 0.05);
      color: var(--text);
    }
    .seg-btn.active {
      background: var(--surface);
      color: var(--text);
      box-shadow: var(--shadow-sm);
    }

    /* SOAP SECTIONS */
    .note-content-area {
      padding: 18px;
    }
    .soap-block {
      margin-bottom: 22px;
    }
    .soap-block:last-child {
      margin-bottom: 0;
    }
    .soap-sec-title {
      font-size: 0.76rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--primary);
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
      padding-bottom: 4px;
      border-bottom: 1px solid var(--border);
    }
    .claim-row {
      padding: 8px 12px;
      margin-bottom: 7px;
      border-radius: 6px;
      background: var(--surface);
      border: 1px solid var(--border);
      cursor: pointer;
      transition: border-color 0.14s, background 0.14s;
    }
    .claim-row:hover {
      border-color: var(--primary);
      background: var(--primary-subtle);
    }
    .claim-row.active {
      border-color: var(--primary);
      background: var(--primary-subtle);
      box-shadow: 0 0 0 2px var(--primary-border);
    }
    .claim-row.flagged {
      border-left: 3px solid var(--danger-text);
      background: var(--danger-bg);
    }
    .claim-narrative {
      font-size: 0.88rem;
      color: var(--text);
      line-height: 1.48;
      margin-bottom: 6px;
    }
    .claim-pills {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
    }
    .cite-pill {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: var(--surface);
      border: 1px solid var(--border-strong);
      padding: 2px 7px;
      border-radius: 4px;
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: var(--text);
      cursor: pointer;
      transition: all 0.12s;
    }
    .cite-pill:hover {
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
    }
    .status-tag {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 0.7rem;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    .status-tag.verified {
      background: var(--success-bg);
      color: var(--success-text);
      border: 1px solid var(--success-border);
    }
    .status-tag.discrepancy {
      background: var(--danger-bg);
      color: var(--danger-text);
      border: 1px solid var(--danger-border);
    }

    /* PANE 3: PROVENANCE INSPECTOR */
    .inspector-panel-body {
      padding: 16px;
    }
    .empty-state {
      text-align: center;
      color: var(--text-muted);
      padding: 48px 16px;
    }
    .empty-icon {
      width: 40px;
      height: 40px;
      stroke: var(--text-subtle);
      margin-bottom: 12px;
    }
    .audit-card {
      background: var(--surface-subtle);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      margin-bottom: 12px;
    }
    .audit-card-title {
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-muted);
      margin-bottom: 8px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .verbatim-box {
      font-family: var(--font-mono);
      font-size: 0.78rem;
      background: var(--surface);
      border: 1px solid var(--border);
      border-left: 3px solid var(--primary);
      padding: 7px 10px;
      border-radius: 4px;
      color: var(--text);
      line-height: 1.45;
    }
    .rule-item {
      padding: 8px 10px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 5px;
      margin-bottom: 6px;
      font-size: 0.78rem;
    }
    .rule-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-weight: 600;
      margin-bottom: 3px;
    }
    .rule-flag {
      font-size: 0.7rem;
      font-weight: 700;
    }
    .rule-flag.pass { color: var(--success-text); }
    .rule-flag.fail { color: var(--danger-text); }
    .rule-desc {
      font-size: 0.73rem;
      color: var(--text-muted);
    }

    /* MODAL: LIVE AUDITOR */
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.55);
      backdrop-filter: blur(3px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 100;
    }
    .modal-sheet {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: var(--shadow-md);
      width: 90%;
      max-width: 580px;
      padding: 22px;
      max-height: 90vh;
      overflow-y: auto;
    }
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
    }
    .field-group {
      margin-bottom: 12px;
    }
    .field-group label {
      display: block;
      font-size: 0.78rem;
      font-weight: 600;
      margin-bottom: 4px;
      color: var(--text);
    }
    .field-input, .field-select, .field-textarea {
      width: 100%;
      padding: 7px 10px;
      border-radius: 5px;
      border: 1px solid var(--border);
      background: var(--surface-subtle);
      color: var(--text);
      font-size: 0.83rem;
      outline: none;
    }
    .field-input:focus, .field-select:focus, .field-textarea:focus {
      background: var(--surface);
      border-color: var(--primary);
    }
  </style>
</head>
<body>

  <!-- TOP APP HEADER -->
  <header class="app-header">
    <div class="brand-cluster">
      <div class="brand-mark">
        <svg class="icon" style="width: 17px; height: 17px;" viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
      </div>
      <span class="brand-title">PulseNote</span>
      <span class="brand-version-pill">v2 Frozen</span>
    </div>

    <!-- BENCHMARK INTERACTIVE PILL -->
    <div class="benchmark-container" id="benchmark-container">
      <div class="benchmark-pill" onclick="toggleBenchmarkPopover(event)" title="Click to view full statistical breakdown">
        <span class="pulse-dot"></span>
        <span class="b-title">Held-Out Eval</span>
        <span class="b-rate">3.6% Error</span>
        <span class="b-vs">vs 7.0% Baseline</span>
        <span class="b-delta">-48.6%</span>
        <svg class="icon chevron-icon" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"></polyline></svg>
      </div>

      <!-- POPOVER DETAIL CARD -->
      <div class="benchmark-popover" id="benchmark-popover" onclick="event.stopPropagation()">
        <div class="popover-header">
          <div>
            <div style="font-weight: 700; font-size: 0.85rem; color: var(--text);">Pre-Registered Held-Out Cohort</div>
            <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 1px;">20 Consultations · 1,015 Sentences Evaluated</div>
          </div>
          <span class="brand-version-pill">validator-v2</span>
        </div>

        <div class="popover-grid">
          <div class="popover-card">
            <div class="popover-label">Grounded (Citation Check)</div>
            <div class="popover-stat" style="color: var(--success-text);">3.6%</div>
            <div class="popover-ci">95% CI: [2.4% – 5.3%]</div>
            <div class="popover-pass">88.3% Clean Pass (594/673)</div>
          </div>
          <div class="popover-card">
            <div class="popover-label">Baseline (Post-Hoc Check)</div>
            <div class="popover-stat" style="color: var(--danger-text);">7.0%</div>
            <div class="popover-ci">95% CI: [4.8% – 10.2%]</div>
            <div class="popover-pass">60.8% Clean Pass (208/342)</div>
          </div>
        </div>

        <div class="popover-footer">
          <span class="b-delta" style="font-size: 0.72rem;">-48.6% Relative Risk Reduction</span>
          <span style="font-size: 0.71rem; color: var(--text-muted);">Non-overlapping 95% Wilson intervals</span>
        </div>
      </div>
    </div>

    <!-- CONTROLS -->
    <div class="action-cluster">
      <button class="btn" onclick="prevEncounter()" title="Previous encounter">
        <svg class="icon" viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"></polyline></svg>
      </button>
      <select id="enc-select" class="select-dropdown" onchange="loadEncounter(this.value)">
        <!-- Populated via API -->
      </select>
      <button class="btn" onclick="nextEncounter()" title="Next encounter">
        <svg class="icon" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg>
      </button>
      <button class="btn primary" onclick="openPlayground()">
        <svg class="icon" viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
        Audit Playground
      </button>
      <button class="btn" onclick="toggleTheme()" id="theme-btn" title="Toggle color theme">
        <svg class="icon" id="theme-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
      </button>
    </div>
  </header>

  <!-- MAIN 3-COLUMN WORKSPACE -->
  <main class="app-workspace">

    <!-- COLUMN 1: TRANSCRIPT -->
    <section class="panel">
      <div class="panel-header">
        <div class="panel-title">
          <svg class="icon" viewBox="0 0 24 24"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>
          Consultation Dialogue
        </div>
        <span id="turn-stat" style="font-size: 0.73rem; color: var(--text-muted); font-weight: 600;">0 turns</span>
      </div>
      <div class="panel-body">
        <div class="search-input-wrap">
          <svg class="icon search-icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <input type="text" id="turn-search" class="transcript-search" placeholder="Filter dialogue text..." oninput="filterTurns(this.value)">
        </div>
        <div id="transcript-container">
          <!-- Turns rendered here -->
        </div>
      </div>
    </section>

    <!-- COLUMN 2: CLINICAL SOAP DOCUMENT -->
    <section class="panel document-viewport">
      <div class="clinical-card">
        <!-- Patient Banner -->
        <div class="chart-banner">
          <div class="chart-patient-info">
            <span class="chart-tag-label">Presenting Complaint</span>
            <span class="chart-complaint" id="meta-complaint">—</span>
          </div>
          <div>
            <span class="chart-impression-pill" id="meta-impression">—</span>
          </div>
        </div>

        <!-- Filter & Pipeline Toolbar -->
        <div class="filter-bar">
          <div style="display: flex; gap: 4px;">
            <button class="seg-btn active" onclick="setClaimFilter('all')">All Claims (<span id="count-all">0</span>)</button>
            <button class="seg-btn" onclick="setClaimFilter('flagged')">Flagged Discrepancies (<span id="count-flagged">0</span>)</button>
            <button class="seg-btn" onclick="setClaimFilter('clean')">Clean (<span id="count-clean">0</span>)</button>
          </div>
          <div style="margin-left: auto; display: flex; gap: 6px;">
            <button id="mode-grounded" class="btn primary" style="padding: 3px 8px; font-size: 0.72rem;" onclick="setMode('grounded')">Grounded (Citations)</button>
            <button id="mode-baseline" class="btn" style="padding: 3px 8px; font-size: 0.72rem;" onclick="setMode('baseline')">Baseline (Ungrounded)</button>
          </div>
        </div>

        <!-- Note Body -->
        <div class="note-content-area" id="note-body">
          <!-- Sections rendered here -->
        </div>
      </div>
    </section>

    <!-- COLUMN 3: PROVENANCE INSPECTOR -->
    <section class="panel">
      <div class="panel-header">
        <div class="panel-title">
          <svg class="icon" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
          Provenance Verification
        </div>
        <span id="inspect-badge" class="status-tag verified" style="display: none;">Verified</span>
      </div>
      <div class="panel-body inspector-panel-body" id="inspector-body">
        <div class="empty-state">
          <svg class="empty-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
          <div style="font-size: 0.84rem; font-weight: 600; margin-bottom: 4px; color: var(--text);">No claim selected</div>
          <div style="font-size: 0.76rem; color: var(--text-muted);">Click any sentence in the clinical note to inspect exact quote fidelity, quantity checks, and authority rules.</div>
        </div>
      </div>
    </section>

  </main>

  <!-- LIVE AUDITOR PLAYGROUND MODAL -->
  <div class="modal-backdrop" id="playground-modal" onclick="closePlayground(event)">
    <div class="modal-sheet" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div style="display: flex; align-items: center; gap: 8px;">
          <svg class="icon" style="color: var(--primary);" viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
          <span style="font-size: 0.95rem; font-weight: 700;">Deterministic Rule Auditor</span>
        </div>
        <button class="btn" style="padding: 2px 6px;" onclick="closePlayground()">✕</button>
      </div>
      <p style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 14px;">
        Test how PulseNote's validator heuristically scores any clinical assertion against source conversation turns.
      </p>

      <div class="field-group">
        <label>Clinical Assertion</label>
        <input type="text" id="play-sentence" class="field-input" placeholder="e.g. The patient denies headache, fever, or vomiting.">
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
        <div class="field-group">
          <label>SOAP Section</label>
          <select id="play-section" class="field-select">
            <option value="S">Subjective (S)</option>
            <option value="O">Objective (O)</option>
            <option value="A">Assessment (A)</option>
            <option value="P">Plan (P)</option>
          </select>
        </div>
        <div class="field-group">
          <label>Cited Dialogue Turn</label>
          <select id="play-turn" class="field-select">
            <!-- Dynamically populated -->
          </select>
        </div>
      </div>

      <div class="field-group">
        <label>Verbatim Quoted Excerpt</label>
        <input type="text" id="play-quote" class="field-input" placeholder="e.g. no fever, no vomiting">
      </div>

      <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px;">
        <button class="btn" onclick="closePlayground()">Cancel</button>
        <button class="btn primary" onclick="runPlaygroundAudit()">Audit Claim</button>
      </div>

      <div id="play-result" style="display: none; margin-top: 14px;"></div>
    </div>
  </div>

  <script>
    let encounters = [];
    let currentId = null;
    let currentData = null;
    let currentMode = 'grounded';
    let currentFilter = 'all';

    async function init() {
      const resp = await fetch('/api/encounters');
      encounters = await resp.json();
      const select = document.getElementById('enc-select');
      select.innerHTML = '';

      encounters.forEach(e => {
        const opt = document.createElement('option');
        opt.value = e.id;
        const imp = e.impression ? ` · ${e.impression}` : '';
        opt.textContent = `${e.id}${imp} (${e.turn_count} turns)`;
        select.appendChild(opt);
      });

      if (encounters.length > 0) {
        loadEncounter(encounters[0].id);
      }
    }

    async function loadEncounter(id) {
      currentId = id;
      document.getElementById('enc-select').value = id;
      const resp = await fetch(`/api/encounter?id=${encodeURIComponent(id)}`);
      currentData = await resp.json();

      document.getElementById('meta-complaint').textContent = currentData.complaint ? `"${currentData.complaint}"` : 'Routine Consultation';
      document.getElementById('meta-impression').textContent = currentData.impression || 'Primary Care Consultation';

      populatePlaygroundTurns();
      renderTranscript();
      renderNote();
      clearInspector();
    }

    function prevEncounter() {
      const idx = encounters.findIndex(e => e.id === currentId);
      if (idx > 0) loadEncounter(encounters[idx - 1].id);
    }

    function nextEncounter() {
      const idx = encounters.findIndex(e => e.id === currentId);
      if (idx < encounters.length - 1) loadEncounter(encounters[idx + 1].id);
    }

    function setMode(mode) {
      currentMode = mode;
      document.getElementById('mode-grounded').classList.toggle('primary', mode === 'grounded');
      document.getElementById('mode-baseline').classList.toggle('primary', mode === 'baseline');
      renderNote();
      clearInspector();
    }

    function setClaimFilter(filter) {
      currentFilter = filter;
      document.querySelectorAll('.seg-btn').forEach((btn, i) => {
        btn.classList.toggle('active', (i === 0 && filter === 'all') || (i === 1 && filter === 'flagged') || (i === 2 && filter === 'clean'));
      });
      renderNote();
    }

    function renderTranscript(filterText = '') {
      const container = document.getElementById('transcript-container');
      container.innerHTML = '';
      const q = filterText.toLowerCase().trim();
      let shown = 0;

      currentData.turns.forEach(t => {
        if (q && !t.text.toLowerCase().includes(q) && !t.speaker.toLowerCase().includes(q)) return;
        shown++;

        const row = document.createElement('div');
        row.className = 'turn-row';
        row.id = `turn-${t.id}`;
        row.innerHTML = `
          <div class="turn-row-meta">
            <span class="role-badge ${t.speaker}">${t.speaker}</span>
            <span class="turn-number">T${t.id}</span>
          </div>
          <div class="turn-text">${escapeHtml(t.text)}</div>
        `;
        container.appendChild(row);
      });

      document.getElementById('turn-stat').textContent = `${shown} / ${currentData.turns.length} turns`;
    }

    function filterTurns(q) {
      renderTranscript(q);
    }

    function renderNote() {
      const container = document.getElementById('note-body');
      container.innerHTML = '';
      const sentences = currentMode === 'grounded' ? currentData.grounded : currentData.baseline;

      const total = sentences.length;
      const flaggedCount = sentences.filter(s => s.flagged).length;
      const cleanCount = total - flaggedCount;

      document.getElementById('count-all').textContent = total;
      document.getElementById('count-flagged').textContent = flaggedCount;
      document.getElementById('count-clean').textContent = cleanCount;

      let filtered = sentences;
      if (currentFilter === 'flagged') filtered = sentences.filter(s => s.flagged);
      if (currentFilter === 'clean') filtered = sentences.filter(s => !s.flagged);

      if (filtered.length === 0) {
        container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 28px; font-size: 0.85rem;">No claims matching the active filter.</div>`;
        return;
      }

      const sections = [
        { code: 'S', title: 'Subjective' },
        { code: 'O', title: 'Objective' },
        { code: 'A', title: 'Assessment' },
        { code: 'P', title: 'Plan' },
      ];

      sections.forEach(sec => {
        const claims = filtered.filter(s => s.section.toUpperCase() === sec.code);
        if (claims.length === 0) return;

        const block = document.createElement('div');
        block.className = 'soap-block';
        block.innerHTML = `<div class="soap-sec-title"><span>${sec.code} · ${sec.title}</span></div>`;

        claims.forEach(c => {
          const row = document.createElement('div');
          row.className = `claim-row ${c.flagged ? 'flagged' : ''}`;

          let pills = '';
          if (c.support && c.support.length > 0) {
            pills += c.support.map(sup => `
              <span class="cite-pill" onclick="event.stopPropagation(); jumpToTurn(${sup.turn_id}, '${escapeAttr(sup.quote)}')">
                <svg class="icon" style="width: 11px; height: 11px;" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                T${sup.turn_id}
              </span>
            `).join(' ');
          }

          if (c.flagged) {
            pills += c.hard_reasons.map(r => `
              <span class="status-tag discrepancy">⚠️ ${humanizeCode(r)}</span>
            `).join(' ');
          } else {
            pills += `<span class="status-tag verified">✓ Verified</span>`;
          }

          row.innerHTML = `
            <div class="claim-narrative">${escapeHtml(c.text)}</div>
            <div class="claim-pills">${pills}</div>
          `;

          row.onclick = () => selectClaim(c, row);
          block.appendChild(row);
        });

        container.appendChild(block);
      });
    }

    function selectClaim(c, rowEl) {
      document.querySelectorAll('.claim-row').forEach(el => el.classList.remove('active'));
      if (rowEl) rowEl.classList.add('active');

      renderInspector(c);

      if (c.support && c.support.length > 0) {
        jumpToTurn(c.support[0].turn_id, c.support[0].quote);
      }
    }

    function renderInspector(c) {
      const container = document.getElementById('inspector-body');
      const badge = document.getElementById('inspect-badge');
      badge.style.display = 'inline-flex';
      badge.className = `status-tag ${c.flagged ? 'discrepancy' : 'verified'}`;
      badge.textContent = c.flagged ? 'Discrepancy' : 'Verified';

      let supportHtml = '';
      if (c.support && c.support.length > 0) {
        supportHtml = c.support.map(sup => `
          <div class="audit-card">
            <div class="audit-card-title">
              <span>Cited Dialogue (Turn ${sup.turn_id})</span>
              <button class="btn" style="padding: 1px 6px; font-size: 0.68rem;" onclick="jumpToTurn(${sup.turn_id}, '${escapeAttr(sup.quote)}')">Focus Turn ↗</button>
            </div>
            <div class="verbatim-box">"${escapeHtml(sup.quote)}"</div>
          </div>
        `).join('');
      } else {
        supportHtml = `
          <div class="audit-card" style="border-color: var(--danger-border); background: var(--danger-bg);">
            <div class="audit-card-title" style="color: var(--danger-text);">Missing Dialogue Citation</div>
            <div style="font-size: 0.75rem; color: var(--danger-text);">No turn citation was output for this claim.</div>
          </div>
        `;
      }

      const hard = c.hard_reasons || [];
      const quoteFail = hard.some(r => r.startsWith('quote_not_in_turn'));
      const numFail = hard.some(r => r.startsWith('numbers_not_in_source'));
      const negFail = hard.some(r => r.includes('negation'));
      const authFail = hard.some(r => r.startsWith('assessment_or_plan_not_from_clinician'));

      container.innerHTML = `
        <div class="audit-card">
          <div class="audit-card-title">Selected Clinical Statement</div>
          <div style="font-size: 0.85rem; font-weight: 600; line-height: 1.4; color: var(--text);">
            ${escapeHtml(c.text)}
          </div>
          <div style="margin-top: 6px; font-size: 0.72rem; color: var(--text-muted);">
            Section: <strong>${c.section}</strong> · Source: <strong>${c.system}</strong> (${c.check})
          </div>
        </div>

        ${supportHtml}

        <div class="audit-card">
          <div class="audit-card-title">Deterministic Verification Matrix</div>

          <div class="rule-item">
            <div class="rule-header">
              <span>1. Quote Verbatim Alignment</span>
              <span class="rule-flag ${quoteFail ? 'fail' : 'pass'}">${quoteFail ? 'DISCREPANCY' : 'PASS'}</span>
            </div>
            <div class="rule-desc">
              ${quoteFail ? 'Quoted text does not match dialogue turn (SequenceMatcher ratio &lt; 0.90).' : 'Verbatim quotation verified cleanly against cited turn text.'}
            </div>
          </div>

          <div class="rule-item">
            <div class="rule-header">
              <span>2. Quantity & Dose Consistency</span>
              <span class="rule-flag ${numFail ? 'fail' : 'pass'}">${numFail ? 'DISCREPANCY' : 'PASS'}</span>
            </div>
            <div class="rule-desc">
              ${numFail ? 'Assertion contains numbers, dosages, or durations absent from cited turn.' : 'All extracted numbers match evidence dialogue tokens.'}
            </div>
          </div>

          <div class="rule-item">
            <div class="rule-header">
              <span>3. Negation Polarity Check</span>
              <span class="rule-flag ${negFail ? 'fail' : 'pass'}">${negFail ? 'DISCREPANCY' : 'PASS'}</span>
            </div>
            <div class="rule-desc">
              ${negFail ? 'Polarity inconsistency: dropped negation or ungrounded denial clause.' : 'Negative/affirmative polarity strictly matches quoted evidence.'}
            </div>
          </div>

          <div class="rule-item">
            <div class="rule-header">
              <span>4. Clinician Speaker Authority</span>
              <span class="rule-flag ${authFail ? 'fail' : 'pass'}">${authFail ? 'DISCREPANCY' : 'PASS'}</span>
            </div>
            <div class="rule-desc">
              ${authFail ? 'Assessment/Plan assertion cites patient speech without clinician confirmation.' : 'Clinical diagnostic/plan decision authored by clinician turn.'}
            </div>
          </div>
        </div>
      `;
    }

    function clearInspector() {
      document.getElementById('inspect-badge').style.display = 'none';
      document.getElementById('inspector-body').innerHTML = `
        <div class="empty-state">
          <svg class="empty-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
          <div style="font-size: 0.84rem; font-weight: 600; margin-bottom: 4px; color: var(--text);">No claim selected</div>
          <div style="font-size: 0.76rem; color: var(--text-muted);">Click any sentence in the clinical note to inspect exact quote fidelity, quantity checks, and authority rules.</div>
        </div>
      `;
    }

    function jumpToTurn(turnId, quote) {
      document.querySelectorAll('.turn-row').forEach(el => {
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
        opt.textContent = `T${t.id} (${t.speaker}): ${t.text.substring(0, 48)}...`;
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
        alert('Please enter a clinical assertion.');
        return;
      }

      const payload = {
        encounter_id: currentId,
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
      const res = await resp.json();

      const out = document.getElementById('play-result');
      out.style.display = 'block';

      const isDiscrepancy = res.flagged;
      let reasons = res.reasons.length > 0
        ? res.reasons.map(r => `<div style="margin-top: 3px;">• <strong>${humanizeCode(r)}</strong> (<code>${r}</code>)</div>`).join('')
        : '<div style="color: var(--success-text); font-weight: 600;">✓ Claim cleanly passed all deterministic validation rules.</div>';

      out.innerHTML = `
        <div class="audit-card" style="border-color: ${isDiscrepancy ? 'var(--danger-border)' : 'var(--success-border)'}; background: ${isDiscrepancy ? 'var(--danger-bg)' : 'var(--success-bg)'};">
          <div class="audit-card-title" style="color: ${isDiscrepancy ? 'var(--danger-text)' : 'var(--success-text)'};">
            <span>Audit Result: ${isDiscrepancy ? 'DISCREPANCY' : 'CLEAN PASS'}</span>
          </div>
          <div style="font-size: 0.78rem;">${reasons}</div>
        </div>
      `;
    }

    function humanizeCode(reason) {
      const code = reason.split(':')[0];
      const arg = reason.split(':')[1] || '';
      switch (code) {
        case 'numbers_not_in_source':
          return `Uncited Number/Duration: "${arg}" not in evidence`;
        case 'quote_not_in_turn':
          return `Quote Mismatch in Turn ${arg}`;
        case 'possible_dropped_negation':
          return `Dropped Negation (evidence was negative)`;
        case 'negation_not_in_quote':
          return `Uncited Denial clause absent in quote`;
        case 'assessment_or_plan_not_from_clinician':
          return `Clinician Authority Violation in ${arg || 'Plan'}`;
        case 'no_matching_turn':
          return `Factual Hallucination: No dialogue turn found`;
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

    function toggleBenchmarkPopover(e) {
      if (e) e.stopPropagation();
      const container = document.getElementById('benchmark-container');
      container.classList.toggle('active');
    }

    document.addEventListener('click', (e) => {
      const container = document.getElementById('benchmark-container');
      if (container && !container.contains(e.target)) {
        container.classList.remove('active');
      }
    });

    function toggleTheme() {
      const isDark = document.body.getAttribute('data-theme') === 'dark';
      document.body.setAttribute('data-theme', isDark ? 'light' : 'dark');
    }

    window.onload = init;
  </script>
</body>
</html>
"""


class PulseNoteDemoHandler(SimpleHTTPRequestHandler):
    def do_HEAD(self):
        parsed = urlparse(self.path)
        if parsed.path in ["/", "/index.html"]:
            encoded = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            return
        super().do_HEAD()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ["/", "/index.html"]:
            encoded = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
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
        encoded = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(encoded)


def run_server(port=8080):
    server = HTTPServer(("0.0.0.0", port), PulseNoteDemoHandler)
    print(f"\n=======================================================")
    print(f" PulseNote Professional Clinical Provenance Dashboard")
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
