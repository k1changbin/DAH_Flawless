# Evidence Trace Matrix

This table maps preliminary-report claims to concrete code, logs, tests, and figures.

| Report claim | Evidence log field | Code reference | Figure |
|---|---|---|---|
| Red mutates Blue observations without reading world | `decision_log[].event=mutation_applied`, `red_input_redacted=true` | `src/dah_flawless/attacks/mutations.py`, `src/dah_flawless/environment/redaction.py` | `world_observed_diff.png`, `agent_architecture.png` |
| Blue never receives scorer-only truth | `blue_input_redacted=true` | `src/dah_flawless/environment/redaction.py`, `tests/test_redaction.py` | `agent_architecture.png` |
| Blue detects invariant violations rather than attack names | `situation_tags`, `threats[].tags`, `threats[].evidence` | `src/dah_flawless/blue/tagger.py`, `src/dah_flawless/blue/invariants.py` | `detect_contain_recover.png` |
| Each core attack has Detect/Contain/Recover evidence | `attack.name`, `defense_actions`, `score.recovery_success` | `src/dah_flawless/blue/defense_planner.py`, `tests/test_attacks_e2e.py` | `detect_contain_recover.png`, `attack_flow.png` |
| Scorer decisions are deterministic and auditable | `score`, `prev_hash`, `this_hash` | `src/dah_flawless/scoring/scorer.py`, `src/dah_flawless/environment/hash_log.py` | `scoreboard.png` |
| Defense has mission cost and over-defense risk | `defense_actions[].availability_cost`, `score.availability` | `src/dah_flawless/blue/defense_planner.py`, `src/dah_flawless/scoring/scorer.py` | `availability.png` |
| Results are reproducible under a fixed seed | `seed`, `summary.json` | `src/dah_flawless/environment/simulator.py`, `tests/test_seed_reproducibility.py` | `scoreboard.png` |

Minimum verification command:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests
```

Evidence generation command:

```bash
PYTHONPATH=src python3 -m dah_flawless.main --seed 42 --rounds 5 \
  --out data/logs/round_logs.jsonl \
  --summary data/logs/summary.json
PYTHONPATH=src python3 -m dah_flawless.reports.figures \
  --log data/logs/round_logs.jsonl \
  --out-dir reports/figures
```
