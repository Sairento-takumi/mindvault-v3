---
name: handoff-review-feedback-sprint3
description: Sprint 3 review feedback (Richard → Bob) — memory_review_cli approve/reject path traversal Must Fix 지적 후 _safe_staged_path() basename+.md 검증 도입으로 재리뷰 cleared
---

# Review Feedback — Sprint 3 (SessionEnd staging + `/memory review`)

*Written by Richard (Reviewer). Read by Bob (Builder) and Arch.*

Date: 2026-04-15
Ready for Builder: **YES** (Must Fix 수정 완료, 재리뷰 Cleared)

**재리뷰 결과 (Bob fix 확인)**: `_safe_staged_path()` 도입으로 path traversal 4개 케이스 모두 `invalid filename` 차단 확인. `Path(filename).name == filename` + `.md` 확장자 검증으로 단일 basename만 허용. approve/reject 양쪽 적용. **Step 3 is clear.**

---

*(원본 리뷰는 기록 목적으로 보존)*

---

Reviewed: `src/memory_extractor.py`, `src/session_memory_end.py`, `src/memory_review_cli.py`, `skill/memory_review.md`, `src/session_memory.py` (변경분), `install.sh`, `uninstall.sh`.

---

## Must Fix

1. **`memory_review_cli.cmd_approve/cmd_reject` — path traversal 취약점** (`src/memory_review_cli.py:80, 142`)
   - 증상: `filename` 인자를 `STAGED_DIR / filename` 으로 바로 조립. `filename = "../../../../etc/hosts"` 같은 값 전달 시 `src = /etc/hosts`가 되어 `src.is_file()` 통과. 이어서 `_promoted_slug(filename)`은 stem만 추출하므로 `hosts` 같은 slug가 되어 `MEMORY_DIR/hosts.md`에 임의 파일 내용이 복사될 수 있음. reject는 파일 삭제.
   - 리얼리티: 로컬 단독 사용자 머신이고 `filename`은 LLM이 `list` 결과에서 가져와 전달하므로 공격면 거의 없음. 그러나 LLM이 오작동/환각으로 비정상 filename을 생성하면 memory/ 손상 가능. Richard 원칙상 승인 불가.
   - 수정: approve/reject 진입 시 다음 2개 체크 추가.
     ```python
     if os.sep in filename or filename.startswith(".") or "/" in filename:
         sys.stdout.write(json.dumps({"ok": False, "error": "invalid filename"}))
         return 0
     ```
     또는 `Path(filename).name == filename` 동치 검증. `src = STAGED_DIR / Path(filename).name`로도 보완.
   - 동일 원칙을 `cmd_reject`에도 적용.

---

## Should Fix

1. **`session_memory_end.existing_slugs` — memory/ 파일과 staged 파일의 slug 추출 규칙 불일치** (`src/session_memory_end.py:43–47`)
   - 현재: 두 디렉토리 모두에 대해 `f.stem.split("_", 2)[-1]` 적용. 실제 memory 파일(예: `feedback_north_star_flexible.md`)은 stem 전체가 slug인데 휴리스틱이 `star_flexible`만 추출 → 신규 staged의 `star_flexible` slug가 잘못된 기준으로 차단될 수 있음.
   - 수정: memory/ 파일은 stem 전체를 slug로 취급, staged/ 파일만 timestamp_type 접두사 제거.
     ```python
     for d in (STAGED_DIR, MEMORY_DIR):
         for f in d.glob("*.md"):
             stem = f.stem
             if d is STAGED_DIR:
                 m = re.match(r"\d{8}-\d{6}_[a-z]+_(.+)$", stem)
                 stem = m.group(1) if m else stem
             slugs.add(stem)
     ```

2. **`memory_extractor.TRIGGER_RE` — 질문형 오발** (`src/memory_extractor.py:24`)
   - "이거 기억해?" 같은 단순 확인 질문도 트리거. Gemma가 빈 배열로 거르겠지만 불필요한 API 호출 비용.
   - 수정: 공백·마침표·구두점 경계 조건 추가. 예: `r"기억해(?=[\s.!,:]|$)"` 등. 다만 한국어 조사 붙는 케이스 감안 (`기억해라`, `기억해야` 등) — regex만으로 완벽 분리는 어려움. Arch 판단 요청이 더 적절할 수 있음 → **Escalate**로 재분류. (아래 참조)

3. **`install.sh` register() 함수 — 기존 항목 제거 기준** (`install.sh`)
   - 멱등 재실행 시 `target in h.command`로 매칭. `target`이 `session-memory.py`이고 다른 훅이 그 경로를 포함한 이름으로 들어있으면 오발. 실제 구조상 중복 훅명 없으니 현행 괜찮으나 주석으로 가정 명시 권장.

---

## Escalate to Architect

1. **자동 테스트 파일 미작성** — 브리프 요구 `test_extractor.py`, 이월 `test_indexer.py`/`test_search.py` 3개 모두 미작성. Sprint 2에서 내가 Sprint 3와 함께 작성 권장했는데 결국 밀림. Arch 판단:
   - (a) 이번 sprint에서 작성 Must Fix
   - (b) Sprint 3 마감 후 별도 커밋(테스트 전용)
   - (c) 수용 — E2E 증거로 충분
   - Richard 의견: **(b) 별도 커밋**. 테스트 레이어는 기능 완료 후 안정 상태에서 작성이 효율적. 현 브랜치 merge 후 별도 PR 권장.

2. **트리거 질문형 오발 규칙화** — Should Fix 2를 Arch 판단으로 올림. 비용 이슈는 미미하나 사용자 UX(불필요 staged 생성)에 영향.
   - Richard 의견: **현행 유지 수용**. 질문형도 "사용자가 그 사실을 상기하려 함"으로 해석 가능. 실제 staged 오염은 `list`에서 형이 즉시 reject 가능해 위험도 낮음.

3. **`/memory review` 슬래시 대화형 flow 미검증** — CLI 단독은 통과했으나 LLM이 스킬 body 지시대로 y/n/e/s 응답 파싱·approve 호출 연쇄를 정확히 수행하는지는 실전 테스트 필요.
   - Richard 의견: SESSION-CHECKPOINT에 "다음 세션 최초 할 일 — 테스트 staged 생성 후 `/memory review` 호출" 명시하고, 거기서 버그 나면 Sprint 3.5로 fix.

4. **`edit_approve` CLI 엔드포인트 부재** — Bob이 escalate. 현재는 스킬 body가 Edit 도구로 staged 직접 수정 후 approve 호출하는 2단 구조.
   - Richard 의견: **현행 유지**. 별도 CLI 엔드포인트 추가는 스킬 복잡도만 늘림. Edit → approve 두 단계로 충분.

---

## Cleared (조건부)

코드 전반의 설계, 에러 처리, Sprint 1/2 비회귀, staged 엄격성(approve만이 memory 쓰기 경로)은 모두 통과.

**Must Fix 1건(path traversal) 수정 후 재제출하면 즉시 Cleared.** 수정 범위 작음 (6~10줄, 2분).
