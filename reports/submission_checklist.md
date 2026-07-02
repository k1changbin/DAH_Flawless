# Submission Checklist

## Current Evidence Status

| Item | Status | Evidence |
|---|---|---|
| Core 3 attacks execute | Done | `tests/test_attacks_e2e.py`, `data/logs/round_logs.jsonl` |
| Red/Blue do not receive world | Done | `red_input_redacted=true`, `blue_input_redacted=true`, `tests/test_redaction.py` |
| Invariant-based Blue detection | Done | `src/dah_flawless/blue/invariants.py`, `decision_log` |
| Detect/Contain/Recover logs | Done | `defense_actions`, `detect_contain_recover.png` |
| Fixed scorer rules | Done | `src/dah_flawless/scoring/scorer.py`, `tests/test_scorer.py` |
| Seed reproducibility | Done | `tests/test_seed_reproducibility.py` |
| Hash-chain log integrity | Done | `tests/test_hash_log.py` |
| Report figures | Done | `reports/figures/*.svg`, `reports/figures/*.png` |
| Source ZIP builder | Done | `scripts/build_submission_zip.py` |
| Final team roster | Needs team input | Fill report cover and section 3 |
| Draft PDF export | Done | `reports/DAH2026_prelim_report_DAH_Flawless_draft.pdf` |
| Final PDF export | Needs final team input | Fill final team fields, then export final filename |

## Final Submission Checks

- PDF filename: `DAH2026_예선보고서_[팀명].pdf`
- Source ZIP filename: `DAH2026_소스코드_[팀명].zip`
- PDF size: below 50 MB
- Report order: cover, table of contents, team, attack scenarios, defense architecture, AI agent design, conclusion, references
- Cloud link permission: anyone with the link can download
- ZIP excludes `.venv/`, `__pycache__/`, `.DS_Store`, `.pytest_cache/`, and local `dist/`

Build source ZIP:

```bash
PYTHONPATH=src python3 scripts/build_submission_zip.py --team-name DAH_Flawless
```

Render draft PDF:

```bash
python3 scripts/render_report_pdf.py \
  --source reports/prelim_report_draft.md \
  --out reports/DAH2026_prelim_report_DAH_Flawless_draft.pdf
```
