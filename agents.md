# agents.md — DAH Flawless 코딩 에이전트 지침

> Codex / Claude / 기타 코딩 에이전트가 이 저장소에서 작업할 때 따르는 공통 지침.
> UI 관련 상세 규칙과 재발 방지 규칙은 [`claude_rules.md`](./claude_rules.md)에 있으며 **작업 전 함께 읽는다.**
>
> **범위 정책**: 이 파일은 **이 저장소 전용**이다. 모든 프로젝트에 통하는 범용 규칙은
> 전역 `C:\Users\famouxsss24\Desktop\광운대_정융 유명현\agents.md`(Codex) / `claude_rules.md`(Claude)에 둔다.

---

## 프로젝트 요약
- **DAH Flawless** — Red/Blue 사이버 AI 시뮬레이션. Red가 Blue의 관측을 오염, Blue가 탐지·격리·복구.
- 실제 침투 도구가 아니라 "관측을 믿을 수 있는가"를 AI 대 AI로 증명하는 **연구용 시뮬레이터**.
- 3층 구조:
  - 백엔드 `src/dah_flawless/` (Python) — world 생성 → Red mutation → Blue 방어 → scorer, 라운드별 정책 coevolution.
  - 프론트 `frontend/` (React 19 + Vite + R3F/Three.js) — 백엔드 결과를 **리플레이**로 시각화.
  - 서빙 Docker → `:8080`, `frontend/dist/index.html` 단일 번들(리플레이 JSON 인라인 임베드)을 Python 정적 서버로 서빙.

## 빌드/실행
- 프론트 개발: `cd frontend && npm install && npm run dev`
- 프론트 번들 재생성(배포 반영): `cd frontend && npm run build` → `dist/index.html`. (`build` = `tsc --noEmit && vite build`)
- 데모/심사: `docker compose up frontend` → http://localhost:8080

## 반드시 지키는 것
1. **백엔드 스키마·로그 JSON은 소비만 하고 수정하지 않는다.** 프론트 타입은 `frontend/src/types/replay.ts`에 실물에서 역추출됨.
2. **UI 수정 후 타입체크/빌드로 회귀를 확인**한다(`npm run build`). 단일 번들이 커서(수십 MB) 빌드가 오래 걸릴 수 있음.
3. **[`claude_rules.md`](./claude_rules.md)의 RULE-\* 를 위반하지 않는다.** 특히:
   - **RULE-UI-001**: 재생/스크럽처럼 값이 실시간으로 변하는 화면에서, 사용자가 눌러야 하는 컨트롤 버튼은 **위치가 프레임마다 흔들리면 안 된다.** flex row에서 폭이 변하는 값(카운터·상태 배지)과 컨트롤 사이에 `flex-1` spacer를 두지 말고, 변하는 값의 폭을 상수로 예약한다(mono는 `min-w-[Nch]`, 비례폭은 invisible "고스트 사이저", 숫자는 `tabular-nums`).
4. **표현 원칙**: Red는 관측값·시간·순서·메타데이터를 안전하게 변조할 뿐 시스템을 장악하지 않는다. 해킹법/전장 데이터는 실제 근거에 맞춰 표현하고 지어내지 않는다.

## 재발 방지 로그
새로 발견한 "같은 실수를 반복하기 쉬운 지점"은 `claude_rules.md`에 `RULE-<영역>-<번호>` 형식으로 추가하고, 여기 목록에 한 줄로 링크한다.

- **RULE-UI-001** — 재생/스크럽 중 컨트롤 버튼 위치가 흔들리는 문제 (CommandBar). → `claude_rules.md`
