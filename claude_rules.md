# claude_rules.md — DAH Flawless 프론트엔드 작업 규칙

> Claude(및 다른 코딩 에이전트)가 이 저장소에서 UI를 만지기 전에 반드시 읽는다.
> 한 번 실제로 발생한 실수를 재발시키지 않기 위한 규칙 모음이다. 새 실수가 확인되면 여기에 추가한다.
>
> **범위 정책**: 이 파일에는 **이 저장소에만 해당하는** 규칙을 둔다. 모든 프로젝트에 통하는 범용 규칙은
> 전역 `C:\Users\famouxsss24\Desktop\광운대_정융 유명현\claude_rules.md`(및 같은 폴더의 Codex `agents.md`)에 둔다.

---

## RULE-UI-001 — 재생/스크럽 중 컨트롤 버튼은 절대 위치가 흔들리면 안 된다

### 문제 정의 (실제 발생)
Combat Replay 대시보드 상단 `CommandBar`에서 **배속 재생을 켜면 재생/일시정지·스텝 이동·배속·결과보기 등
눌러야 하는 컨트롤 버튼 전체가 좌우로 흔들려서** 클릭이 어려웠다.

### 근본 원인
`CommandBar`는 **한 줄 flex row** 안에 다음 순서로 요소가 들어간다:

```
로고 | LearningPath(flex-1) | [prev/play/next] | [배속] | [결과보기] | STEP카운터 | 승패배지 | 나가기
```

- 가운데 `LearningPath`가 `flex-1`(= `flex: 1 1 0%`)이라 **남는 공간을 전부 흡수**하며 오른쪽 컨트롤 묶음을 밀어 오른쪽 정렬시킨다.
- 그런데 컨트롤 **오른쪽에 있는 `STEP 카운터`와 `승패 배지`는 프레임마다 텍스트 폭이 바뀐다.**
  - STEP: `phase`(adapt~finalize, 4~8자)와 스텝 숫자가 매 스텝 변함.
  - 승패 배지: `{side} · {winner_detail}`가 매 **라운드** 변함 (`RED · BREACH` ↔ `BLUE · PARTIAL_CONTAINMENT`, 12~26자).
- 이 폭 변화를 **`flex-1` LearningPath가 흡수**하면서, 컨트롤 묶음의 좌측 시작점(x)이 매 프레임 달라진다 → **버튼이 흔들린다.**
- 배속이 높을수록(특히 8x에서 라운드가 통째로 넘어감) 폭 변화가 잦아 더 심하게 흔들린다.

### 규칙
1. **재생/스크럽 중에도 사용자가 눌러야 하는 컨트롤(재생·스텝·배속·결과보기·나가기)은 레이아웃상 위치가 프레임마다 변하면 안 된다.**
2. **flex row에서, 폭이 실시간으로 변하는 값(카운터·상태 배지·라벨)이 컨트롤과 같은 줄에 있고 그 사이에 `flex-1`/`flex-grow` spacer가 끼면 안 된다.** spacer가 폭 변화를 흡수해 컨트롤을 움직인다.
3. 값 폭이 변하는 요소는 **폭을 상수로 예약(reserve)** 한다. 픽셀값을 추측하지 말고, 폰트에 독립적인 방법을 쓴다:
   - **monospace 텍스트**: 최댓값 글자수만큼 `min-w-[{N}ch]` + `inline-block` (예: phase는 최장 8자 → `min-w-[8ch]`).
   - **비례폭(proportional) 텍스트**: "고스트 사이저" — 가장 긴 가능한 문자열을 `invisible`로 겹쳐 폭을 잡고 실제 값을 그 위에 렌더한다.
     ```tsx
     <div className="inline-grid place-items-center …">
       <span aria-hidden className="invisible col-start-1 row-start-1 whitespace-nowrap">
         BLUE · PARTIAL_CONTAINMENT   {/* 가능한 최장 조합 */}
       </span>
       <span className="col-start-1 row-start-1 whitespace-nowrap">
         {side} · {detail}
       </span>
     </div>
     ```
   - **숫자**: `tabular-nums` + `padStart`로 자릿수 고정.
4. 폭을 못 고정하는 요소는 **컨트롤 밖(오른쪽 끝 등)으로 빼거나, `flex-1` spacer의 반대편**에 두어 그 흔들림이 컨트롤에 전파되지 않게 한다.

### 확인 방법 (수정 후 반드시)
- 8x 배속으로 재생하며 상단 컨트롤 버튼의 **좌측 x좌표가 고정**되는지 눈으로/스크린샷으로 확인.
- `phase = finalize`, `winner_detail = PARTIAL_CONTAINMENT`(가장 긴 값)일 때 텍스트가 **잘리지 않는지** 확인.
- 좁은 화면(`max-[1023px]`)에서 wrap 동작이 깨지지 않는지 확인.

### 적용 위치
- `frontend/src/components/CommandBar.tsx` — STEP 카운터, 승패 배지.
- `frontend/src/components/LearningPath.tsx` — phase 라벨 배지(`RED PRESSURE`↔`BLUE MOMENTUM`, `justify-between` 우측 그룹에서 N·R 입력창을 밀던 원인).

> 교훈: "재생 버튼만" 잡으면 부족하다. **재생 중 텍스트가 바뀌는 배지·라벨은 컨트롤 근처든 아니든 전부** 폭을 예약해야 한다. 한 줄 안의 `justify-between`·`flex-1`은 어디서 생긴 폭 변화든 옆 요소로 전파한다.

---

## 일반 원칙 (이 저장소 공통)

- **백엔드 스키마/로그 JSON은 소비만 하고 수정하지 않는다.** 타입은 `frontend/src/types/replay.ts`에 실물에서 역추출돼 있다.
- 프론트 수정 후에는 `cd frontend && npm run build`로 `dist/index.html` 단일 번들을 재생성해야 Docker(`:8080`) 서빙에 반영된다 (`npm run build` = `tsc --noEmit && vite build`).
- 레이아웃 안정성(위 RULE-UI-001)처럼 "실시간으로 값이 변하는 화면"에서는 **값이 변해도 주변 요소가 리플로우되지 않게** 폭/높이를 예약하는 것을 기본값으로 삼는다.
