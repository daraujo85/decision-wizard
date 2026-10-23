#!/usr/bin/env python3
"""Self-check for wizard.css: required tokens/classes present. Run: python3 test_wizard_css.py"""
import os

REQUIRED = [
    "--color-bg", "--color-accent", "--color-text",
    "border-radius:var(--radius)", ".wz-header", ".wz-tab", ".wz-badge-waiting",
    ".wz-metrics", ".wz-metric", ".wz-waiting-card", ".wz-decision", ".wz-tip-box",
    ".wz-options", ".wz-option", ".wz-option-selected", ".wz-followup",
    ".wz-crumbs", ".wz-tree-bottom", ".wz-tree-overlay", ".wz-chat-panel", ".wz-review-row",
    ".wz-chip", ".wz-footer", ".wz-btn-primary",
]

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wizard.css")
css = open(path, encoding="utf-8").read()
missing = [tok for tok in REQUIRED if tok not in css]
assert not missing, f"tokens/classes faltando em wizard.css: {missing}"
assert "border-radius:0" not in css.replace(" ", ""), "radius deve vir do token --radius, nao hardcoded"
print("ok")
