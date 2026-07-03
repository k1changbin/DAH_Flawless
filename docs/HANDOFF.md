# DAH 2026 — 세션 인계 문서 (HANDOFF)

> **목적:** 세션이 끊겨도 이 파일을 먼저 읽으면 어디서든 이어갈 수 있게 한다.
> **갱신 규칙:** 큰 결정·진척이 생기면 갱신한다. (오래된 인계는 거짓말이 된다)
> 최종 갱신: 2026-07-03 (**가용성 회복/교차검증/단계방어/Red 경계탐색 구현 + Claude 정리/push 핸드오프 추가**)

---

## 0. 한 줄 현황

**통합 코드베이스(창빈 base + 유명현 강점 이식) 전 파이프라인 실행 검증 완료 후, 우선 개발 3종까지 구현.** 시뮬→그림(6종 SVG/PNG)→보고서 PDF(reportlab 설치·requirements 추가)→제출 ZIP까지 다 돌고 기존 테스트 12개 통과했으며, 이번에 회귀 테스트 4개를 더해 **테스트 16개 통과**. streamlit 대시보드 실행 후 사이드바에 이식 기능(`Scenario`/`Red stealth`) 셀렉트박스 추가. 공식 안내서(`tmp/pdfs`)와 대조 → 8항목·배점(30/25/25/10/10)·제출형식 모두 부합 확인(남은 건 팀명 기입·최종 PDF). **가용성 0 미회복 버그 수정 완료:** clean/off 30R 기준 final availability **0.682**, RED_ATTRITION **0회**. **공격·방어 흐름 개선 구현:** telemetry/GNSS/IMU/time 교차검증, domain trust 누적 및 단계방어, Red telemetry boundary_probe. 모든 변경 아직 **로컬 미커밋**. **다음: 보고서에 새 실험 로그 반영 → 커밋/push 조율 → 최종 PDF/ZIP.**

---

## 1. 지금 코드베이스 상태 (가장 중요)

- **`main` = 창빈 정본** (`src/dah_flawless/` 패키지). origin/main과 동기화됨(+로컬 미푸시 문서 커밋 있을 수 있음).
- **`my-mvp-backup` = 유명현 단독 MVP 전체 보존** (`src/`, 테스트 12개, figures.py, degraded_start/capabilities, StealthController). `git switch my-mvp-backup` 로 언제든 복귀/참조 가능. **절대 삭제 금지.**
- 두 코드는 공통 조상 `5eec6f1`에서 갈라진 별개 구현. 구조가 달라 자동 머지 불가 → 필요한 것만 **포팅**.

### 실행법 (창빈 코드)
```bash
# 시뮬레이션
PYTHONPATH=src python -m dah_flawless.main --seed 42 --rounds 5 \
  --out data/logs/round_logs.jsonl --summary data/logs/summary.json
# 테스트 (pyproject pythonpath=src)
python -m pytest -q
# 시나리오/스텔스 옵트인 (이식 기능)
PYTHONPATH=src python -m dah_flawless.main --scenario degraded_start --red-stealth adaptive
# 대시보드 (사이드바에 Scenario/Red stealth 셀렉트박스 있음)
PYTHONPATH=src streamlit run streamlit_app.py
# 보고서 그림/PDF/제출zip
PYTHONPATH=src python -m dah_flawless.reports.figures
python scripts/render_report_pdf.py --source reports/prelim_report_draft.md --out reports/DAH2026_prelim_report_DAH_Flawless_draft.pdf
PYTHONPATH=src python scripts/build_submission_zip.py --team-name DAH_Flawless
```
> 의존성: `streamlit`, `Pillow`, `reportlab` (모두 `requirements.txt`. reportlab은 이번 세션에 추가).

---

## 2. 문서 지도

| 파일 | 내용 |
|---|---|
| `README.md` | **창빈 사용설명서**(핵심개념·폴더구조·CLI·로그해석·FAQ). 위협모델 전제 블록 §2에 추가됨 |
| `docs/DAH2026_integrated_plan.md` | 창빈 통합 플래닝 |
| `docs/implementation_plan.md` | 창빈 구현 계획 |
| `docs/schema_design.md` · `field_formats.md` | 데이터 구조·필드 형식 |
| `docs/situation_tags.md` · `attack_mapping.md` | 태그·공격 매핑 |
| `docs/world_observed_model.md` | world/observed 개념 |
| `docs/encrypted_channel_attack_ai.md` | 암호화 채널 공격 방향(10종·최소접근 근거) |
| `docs/DAH2026_쉬운설명_팀원용.md` | 고등학생 수준 개념 설명 + 용어사전(백업에서 복구) |
| `docs/HANDOFF.md` | 이 파일 |

---

## 3. 확정된 핵심 결정 (재논의 금지)

1. **최소 접근 권한 전제:** Red는 시스템 장악 못 하고 `blue_observed` 외형만 조작. 암호 못 깬다 가정. "전원 끄기/직접 복호화"는 범위 밖. (박지성, 2026-06-30)
2. **진실 분리:** world는 scorer만. Red·Blue 둘 다 world 안 봄. Blue는 redacted state만.
3. **불변식 탐지:** Blue는 공격명 모른 채 observed 내부 모순으로 탐지.
4. **공격 3종만 깊게:** PRIORITY_POISONING / TELEMETRY_FDI / TIME_DESYNC_REPLAY. 나머지 카탈로그.
5. **피로스의 승리:** 과방어로 availability 고갈 시 RED_ATTRITION.
6. **팀 정본은 창빈 `src/dah_flawless/`** (2026-07-02 결정). 유명현 코드는 백업 보존.
7. **LLM 헛소리 주의:** 해킹법·전장 데이터는 실제 근거(MAVLink·GNSS 규격)에만 grounding, 지어내지 말 것.

---

## 4. 다음 할 일

### 4.1 백업 강점 포팅 — ✅ 완료 (2026-07-02)
- ✅ **degraded_start 시나리오 + capabilities 마비** — `state_factory`에 `scenario` 인자, `--scenario` CLI. capabilities 3필드(cross_check_telemetry/trusted_restore/time_validation) 저하 시 `invariants`가 탐지 confidence 약화(OK=1.0/DEGRADED=0.75/UNAVAILABLE=0.5, `config.CAPABILITY_FACTORS`). degraded_start는 avail 0.55 시작 → RED_ATTRITION 다발로 복구 난이도 실증.
- ✅ **StealthController(적응형 은폐)** — `mutations.apply_attack(..., stealth=)`, `RedAgent(stealth_mode=)`, `--red-stealth off|on|adaptive`. 초기 포팅 때는 텔레메트리 `battery=44(FAULT)`가 단일 임계(`TELEMETRY_CONFLICT`)를 회피했지만, 2026-07-03 교차검증 구현 이후에는 `BATTERY_ENERGY_IMPOSSIBLE`로 탐지됨. 현재 Red는 telemetry에서 `boundary_probe`/`probe_delta`로 탐지경계를 탐침. priority/replay는 임계=불일치 경계가 겹쳐 실질 은폐여지 없음.
- ⚠️ **기본값 off** — `--red-stealth`·`--scenario` 기본은 창빈 원본 재현(off/clean_start). 스텔스·마비는 옵트인.
- ✅ 테스트 6→12개 (신규 `tests/test_scenario_and_stealth.py`).
- **미포팅:** "Blue 임계값 공진화"는 백업 코드에도 실제 미구현(HANDOFF 설명뿐)이라 포팅 없음. Red 공진화는 창빈 `update_weight`에 이미 존재.
- ✅ (07-03) streamlit 사이드바에 `Scenario`/`Red stealth` 셀렉트박스 노출(`streamlit_app.py`), reportlab을 requirements 추가.

### 4.2 🐛 가용성 회복 버그 — ✅ 수정 완료 (2026-07-03)
- **문제:** 가용성이 0에 박히면 영영 회복 안 됨. 30라운드 돌리면 후반 전부 RED_ATTRITION(off모드 25/30).
- **수정:** `simulator._advance_normal_state()`에 라운드 시작 회복 단계(`_recover_operational_budget`) 추가. 이전 라운드 방어비용이 클수록 회복량은 줄지만, 최소 회복을 남겨 0 고착을 방지. `mission.availability`와 `mission.trust_budget` 모두 회복.
- **추가 수정:** `HOLD_COMMAND`가 sequence/command만 복구하고 timestamp를 공격값으로 남겨 다음 라운드에 `COMMAND_TIMING_INCONSISTENT`가 누적되던 문제 수정(`defense_planner._apply_single_action`).
- **검증:** clean/off 30R 기준 final availability **0.682**, min availability **0.674**, RED_ATTRITION **0회**.

### 4.3 공격·방어 "흐름" 개선 — ✅ 1·2·3순위 구현 완료 (2026-07-03)
지금 공방이 "양쪽이 아는 고정 임계값·단일필드·단일틱" 게임이던 문제를 완화.
1. **교차검증 탐지 (최우선) — 구현 완료.** 한 필드 임계 → **여러 독립신호 모순**으로 확장. `blue/tagger.py`에서 `BATTERY_ENERGY_IMPOSSIBLE`, `GNSS_INTERNAL_CONFLICT`, `IMU_TELEMETRY_DIVERGENCE`, `COMMAND_TIMING_INCONSISTENT` 태그 추가. `blue/invariants.py`에서 telemetry/GNSS/IMU/time evidence 수에 따라 confidence 계산. 기존 단일필드 stealth(`battery=44`)는 이제 `BATTERY_ENERGY_IMPOSSIBLE`로 탐지됨.
2. **신뢰 누적/단계적 방어 — 구현 완료.** `defense_runtime.domain_trust` 추가. `blue/defense_planner.py`가 threat confidence와 domain trust를 함께 보고, 약한 이상은 `OBSERVE_DOMAIN`+`REQUEST_REVALIDATION` 저비용 대응, 확증/반복 이상은 `QUARANTINE_FIELD`/`FALLBACK_TO_TRUSTED_STATE`/`HOLD_COMMAND`로 승격.
3. **경계 탐색형 Red — 구현 완료.** `attacks/red_agent.py`가 telemetry stealth에서 `boundary_probe` tactic과 `probe_delta`를 로그로 남김. 탐지되면 조작 폭을 줄이고, 미탐지되면 조금 키워 탐지경계를 탐침. `attacks/mutations.py`는 tactic 기반 배터리 조작 폭을 적용.

### 4.4 창빈 코드 자체 개선
- **detection_window / recovery_window 실사용** — `config.py`에 `DETECTION_WINDOW=2`, `RECOVERY_WINDOW=2` 정의돼 있으나 `scorer.py`는 현재 라운드만 봄. README 채점 정의(N=2)와 어긋남.

### 4.5 조율·마무리 필요
- **커밋/push** — 이번+지난 세션 변경 전부 로컬 미커밋. 창빈 공용 레포라 특히 README(위협모델)·src 변경 push 전 팀 조율.
- **보고서 반영** — 이식한 스텔스/degraded 케이스를 `reports/prelim_report_draft.md` §4·§5에 로그 증거와 함께 추가하면 공격(30)·방어(25) 깊이 ↑.
- **제출 마무리** — 팀명·팀원 명단(보고서 Cover/§3), 최종 PDF export(`DAH2026_예선보고서_[팀명].pdf`). 대회 보고서 마감 **2026-07-10 23:59 KST**.

---

## 5. Git / 레포

- **레포:** `k1changbin/DAH_Flawless`, `main`. (창빈 소유, 유명현 collaborator, gh 계정 `famouxsss24`)
- **origin = 창빈 정본**(문서+코드 전체). 로컬 `main`은 여기 맞춰짐.
- **백업 브랜치 `my-mvp-backup` 은 로컬 전용**(push 안 함, 유명현 원본 보존용).

---

## 6. Claude 검증/정리/push 핸드오프

> 나중에 Claude에게 "HANDOFF 봐줘"라고 하면 이 섹션을 우선 실행하면 된다. **지금 당장 삭제하지 말 것.** 삭제 전에는 반드시 `git status --short`와 테스트 결과를 확인하고, 삭제 목록을 사용자에게 한 번 보여준 뒤 진행한다.

### 6.1 목표
- 이번 Codex 구현분을 Claude가 재검증한다.
- GitHub에는 **실제 실행에 필요한 코드/설정 파일 + `docs/` 문서 폴더** 중심으로 올린다.
- 임시 산출물, 로컬 캐시, 보고서 실행 결과, 제출용 중간 산출물은 정리한다.

### 6.2 반드시 보존할 것
아래는 삭제하면 실행/검증/문서 인계가 깨질 수 있으므로 보존한다.

```text
.git/
.gitignore
README.md
pyproject.toml
requirements.txt
Dockerfile
streamlit_app.py
src/
tests/
docs/
```

선택 보존:
- `scripts/`는 보고서 PDF/제출 ZIP 재생성이 필요하면 보존한다. 앱/시뮬레이터만 올릴 목적이면 삭제 가능하지만, 대회 제출 파이프라인까지 남길 거면 보존 권장.
- `reports/prelim_report_draft.md`, `reports/evidence_trace.md`, `reports/submission_checklist.md`는 보고서 원문이 필요하면 `docs/`로 옮긴 뒤 보존한다. `reports/figures`, PDF, run 결과는 재생성 산출물이라 삭제 가능.

### 6.3 삭제 후보
아래는 보통 GitHub push 전 삭제해도 되는 로컬/산출물이다. 단, 삭제 전 사용자에게 최종 확인한다.

```text
.agents/
.claude/
.pytest_cache/
assets/
data/
dist/
reports/
tmp/
reports/deg/
reports/run/
reports/figures/
reports/*.pdf
```

주의:
- `.git/`은 절대 삭제 금지.
- `my-mvp-backup` 브랜치는 로컬 백업이므로 삭제 금지.
- `docs/reviews/`는 문서 폴더 안에 있으므로 사용자가 "docs 전체 보존"을 원하면 유지한다. 너무 크거나 지저분하면 사용자의 확인을 받고 정리한다.

### 6.4 Claude가 먼저 검증할 명령
PowerShell 기준:

```powershell
git status --short
python -m pytest -q
$env:PYTHONPATH='src'; python -m dah_flawless.main --seed 42 --rounds 30 --out data/logs/round_logs.jsonl --summary data/logs/summary.json
$env:PYTHONPATH='src'; @'
from dah_flawless.environment.simulator import run_simulation
for label, kwargs in [
    ('clean/off', dict(seed=42, rounds=30)),
    ('clean/adaptive', dict(seed=42, rounds=30, stealth_mode='adaptive')),
]:
    _, summary = run_simulation(**kwargs)
    print(label, summary)
'@ | python -
```

기대값:
- `python -m pytest -q` → **16 passed**
- clean/off 30R → final availability 약 **0.682**, RED_ATTRITION **0회**
- clean/adaptive 30R → detection_rate 약 **0.8333**, final availability 약 **0.93**

### 6.5 정리 절차
1. `git status --short`로 변경 파일을 확인한다.
2. 위 검증 명령을 모두 통과시킨다.
3. `docs/HANDOFF.md`와 README가 최신 동작(가용성 회복, 교차검증, domain trust, boundary_probe)을 설명하는지 확인한다.
4. 삭제 후보를 사용자에게 보여주고 확인받는다.
5. 보존 목록만 남기고 정리한다. PowerShell 삭제는 `Remove-Item -LiteralPath ...`를 쓰고, recursive 삭제 전 대상 경로가 현재 repo 안인지 확인한다.
6. 정리 후 다시 `python -m pytest -q`를 돌린다.
7. `git add` 전에 `git status --short`를 다시 보여준다.
8. 커밋 메시지 예시:
   ```text
   Implement recovery and cross-signal defense flow
   ```
9. `git push origin main`은 팀 조율 후 실행한다.

### 6.6 Claude에게 줄 짧은 요청문
```text
docs/HANDOFF.md 읽고 6번 섹션대로 검증해줘. 테스트 통과하면 GitHub에 올릴 최소 구조로 정리할 거라, 보존 목록/삭제 후보 먼저 보여주고 내 확인 받고 정리해줘. .git, src, tests, docs, README, pyproject, requirements, Dockerfile, streamlit_app.py는 유지하고, scripts/reports는 보고서 파이프라인 유지 필요 여부를 물어봐.
```

---

## 7. 진행 로그 (최신이 위로)

- 2026-07-03 (2) — **우선 개발 1·2·3 구현.** 가용성/신뢰예산 라운드 회복 추가(`AVAILABILITY_RECOVERY_PER_ROUND`, `_recover_operational_budget`), command replay 방어 timestamp 복구. 교차검증 태그(`BATTERY_ENERGY_IMPOSSIBLE`, `GNSS_INTERNAL_CONFLICT`, `IMU_TELEMETRY_DIVERGENCE`, `COMMAND_TIMING_INCONSISTENT`) 및 evidence 기반 confidence 추가. `domain_trust` 기반 단계방어(`OBSERVE_DOMAIN`→격리/복구 승격) 추가. Red telemetry `boundary_probe`/`probe_delta` 경계탐색 추가. 테스트 **16개 통과**. clean/off 30R: final availability **0.682**, RED_ATTRITION **0회**. adaptive 30R: detection_rate **0.8333**, final availability **0.93**, telemetry probe가 18→12→6→2로 줄며 일부 `RED_BREACH` 발생.
- 2026-07-03 — **전 파이프라인 실행 검증 + 대시보드 노출 + 흐름개선 논의.** 시뮬→그림→PDF(reportlab 설치·requirements 추가)→제출ZIP 다 실행 성공, 테스트 12개 통과. streamlit 설치·실행, 사이드바에 `Scenario`/`Red stealth` 셀렉트박스 추가(`streamlit_app.py`). 공식 안내서(`tmp/pdfs`) 대조 → 8항목·배점·제출형식 부합 확인. **버그 발견:** 가용성 0 미회복(긴 판 전부 RED_ATTRITION). **실측:** adaptive 스텔스 30R 탐지율 83%→17% 학습곡선. 공격·방어 흐름 개선 3방향(교차검증/신뢰누적/경계탐색 Red) 논의만 함(미구현). 전부 로컬 미커밋. **다음: 가용성 회복 버그 수정 → 교차검증 탐지.**
- 2026-07-02 (2) — **백업 강점 창빈 base로 포팅 완료.** degraded_start 시나리오+capabilities 마비, StealthController(적응형 은폐)를 창빈 컨벤션으로 이식. `--scenario`/`--red-stealth` CLI 추가(기본 off/clean_start=창빈 원본 재현). 테스트 6→12개. 기본 실행이 창빈 원본 결과와 일치 확인. **다음: detection_window 실사용 + 커밋/push 조율.**
- 2026-07-02 — **팀 정본 코드 전환.** 창빈이 완성 코드(`src/dah_flawless/`, Docker·PDF·streamlit·체크리스트) push. 유명현 단독 MVP를 `my-mvp-backup`으로 보존 후 `main`을 창빈 origin으로 reset. 창빈 테스트 6개 통과·시뮬 정상 확인. 창빈 README(사용설명서)에 위협모델 전제 블록 추가, 쉬운설명 문서 복구. 박지성의 최소접근 전제 프레이밍 확정결정에 반영.
- 2026-07-01 — 유명현 단독 MVP 구현(공격3종·불변식·§9.3채점·해시로그·StealthController·capabilities, 테스트12개). Codex 크로스체크 1회. → 현재 `my-mvp-backup` 브랜치에 보존.
