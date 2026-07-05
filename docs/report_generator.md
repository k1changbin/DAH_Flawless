# Training/Holdout Report Generator

Report Generator는 training summary와 holdout summary를 보고서용 Markdown/JSON으로 변환한다.

입력:

- training summary JSON
- optional training JSONL logs
- optional holdout summary JSON
- optional holdout JSONL logs

출력:

- Markdown report
- optional structured JSON companion

보고서에 들어가는 핵심 항목:

| 섹션 | 내용 |
|---|---|
| Executive Summary | 학습/holdout 성공률, 인과성, 다양성 요약 |
| Training Overview | runner, episode, step, hash chain 상태 |
| Training Metrics | detection, attack success, goal success, causal consistency, entropy |
| Training Blocks | Blue-update, Red-update, fixed-eval block별 요약 |
| Policy Delta | Red attack weight 변화, Blue domain trust/sensitivity/threshold 변화 |
| Holdout Overview | holdout case, scenario 수, scripted coverage off 여부 |
| Holdout Scenario Results | scenario/seed별 승패, goal success, causal consistency, availability |
| Generalization Flags | 낮은 다양성, 낮은 causal consistency, availability floor pressure 등 |

시뮬레이션 실행과 동시에 생성:

```powershell
python -m dah_flawless.main --seed 42 --training-schedule --holdout-eval --report-out data/reports/training_holdout_report.md --report-json data/reports/training_holdout_report.json
```

이미 생성된 summary/log 파일에서 다시 생성:

```powershell
python scripts/generate_training_report.py --training-summary data/logs/training_summary.json --training-logs data/logs/training_logs.jsonl --holdout-summary data/logs/holdout_summary.json --holdout-logs data/logs/holdout_logs.jsonl --out data/reports/training_holdout_report.md --json-out data/reports/training_holdout_report.json
```

주의:

- Report Generator는 새 점수를 계산하지 않는다.
- scorer truth나 raw world 원문을 직접 읽지 않는다.
- simulator/evaluator가 이미 남긴 summary/log만 요약한다.
