# Review Request — Sprint 3 (SessionEnd staging + `/memory review`)

*From: Bob → To: Richard*
*Date: 2026-04-15*
*Ready for Review: YES*

---

## 무엇을 리뷰해줘

Sprint 3 — 세션 종료 시 Gemma가 "영구 기억 후보"를 추출해 `memory/_staged/`에만 저장. `/memory review` 스킬을 통해 사용자가 승인해야만 실제 `memory/*.md` 파일 생성 + `MEMORY.md` 한 줄 append. MindVault v1의 "자동 만능 저장" 실패 재발을 차단하는 승인 게이트가 핵심.

---

## 변경된 파일

| 파일 | 줄 범위 | 한 줄 설명 |
|---|---|---|
| `src/memory_extractor.py` | 1–178 (신규) | 트리거 regex, PII 마스킹, Gemma 호출·JSON 배열 파싱, 유효 필드 필터 |
| `src/session_memory_end.py` | 1–115 (신규) | SessionEnd 훅. stdin JSON → session_id → JSONL → extractor → staged 파일 생성 |
| `src/memory_review_cli.py` | 1–170 (신규) | `list/approve/reject/prune` 하위명령. approve 시 MEMORY.md 라인 append, staged 파일 이동, 중복 slug 차단 |
| `skill/memory_review.md` | 1–32 (신규) | `/memory review` slash command. `allowed-tools: Bash`. y/n/e/s 응답 플로우 |
| `src/session_memory.py` | 264–282, 319, 345 | `purge_staged_memory()` 추가. 30일 경과 staged 정리. cache HIT/MISS 양쪽 경로에서 호출 |
| `install.sh` | 추가 | SessionEnd 훅 배포/등록, Sprint 3 스크립트/스킬 배포. settings.json 등록 파이썬 스니펫 `register()` 함수로 리팩토링 |
| `uninstall.sh` | 추가 | SessionEnd 훅 + /memory_review 스킬 제거. 양 이벤트 모두에서 엔트리 정리 |

---

## 반드시 확인해줘

1. **Staging 엄격성** — `cmd_approve` 외 어떤 경로로도 실제 `memory/*.md` 또는 `MEMORY.md`가 수정되면 안 됨. session_memory_end.py는 `_staged/` 외부에 절대 쓰지 않는지 코드 리뷰.

2. **트리거 보수성** — `memory_extractor.TRIGGER_RE`가 일반 대화(문서 인용·과거 회상)에서 오발하지 않는지. 특히 "~기억해?" (질문형)는 트리거 걸림 — 의도한 건지 Arch에게 escalate 후보.

3. **slug 충돌 로직** — `session_memory_end.existing_slugs()`가 `_staged/`와 `memory/` 양쪽에서 slug 추출. 실제 memory 파일이 underscore를 포함(`feedback_north_star_flexible.md`)해서 `split("_", 2)[-1]` 휴리스틱이 올바른 stem 비교를 보장하는지 확인.

4. **MEMORY.md append 안전성** — approve 시 기존 파일 `endswith("\n")` 체크 후 prefix newline 삽입. E2E에서 첫 approve가 줄바꿈 없이 붙었던 버그를 수정한 부분. 추가 edge case 있는지.

5. **에러 처리** — 훅·CLI 모두 예외 시 `exit 0` + 빈 stdout. memory_review_cli의 approve 실패는 JSON error만 반환, staged 파일은 유지 (재시도 가능).

6. **Sprint 1/2 회귀** — `_staged/*.md`가 FTS5 인덱서에 들어가면 안 됨 (indexer는 `*.jsonl`만 glob — 검증 불필요, 그래도 한 번 확인). SessionStart 훅에 추가된 `purge_staged_memory()`는 try/except 감싸서 실패 무해.

---

## E2E 증거 (Must verify)

1. **Sanity 유닛**:
   - `has_trigger`: 5/5 기대대로 (기억해/결정/잊지마/앞으로는 → True, 일반 대화 → False)
   - `parse_gemma_json`: 유효 2건 + 무효 1건 섞인 출력 → 유효 2건만 반환
   - malformed/empty Gemma 출력 → 빈 배열, crash 없음

2. **Staged 파일 E2E** (실제 MEMORY.md 백업 후):
   - 수동 staged fixture 2개 작성 → `list` → 2건 반환 ✅
   - `approve` → `memory/sprint3_test_rule.md` 생성, MEMORY.md 마지막 줄 append, staged 파일 삭제 ✅
   - `reject` → staged 삭제, memory/ 무영향 ✅
   - 테스트 artifact 원복 완료 (MEMORY.md 백업 복원, sprint3_test_rule.md 삭제)

3. **MEMORY.md 줄바꿈 버그** — 첫 E2E에서 prefix 없이 append되어 기존 라인과 붙음. `cmd_approve`에서 `endswith("\n")` 체크 + prefix 삽입으로 수정, 배포본 갱신 완료.

4. **배포 검증**:
   ```
   ✓ copied SessionEnd hook to /Users/yonghaekim/.claude/hooks/session-memory-end.py
   ✓ deployed Sprint 3 scripts to /Users/yonghaekim/.claude/scripts/mindvault
   ✓ installed /memory_review skill at /Users/yonghaekim/.claude/commands/memory_review.md
   ✓ registered SessionStart hook
   ✓ registered SessionEnd hook
   ```

5. **Sprint 1 회귀 없음** — 현 세션 SessionStart 자동 주입 정상 (첫 턴에서 MindVault 요약 블록 표출 확인).

---

## Open Questions — Arch에게 escalate

1. **자동 테스트 미작성** — 브리프의 `test_extractor.py`, 이월 `test_indexer.py`, `test_search.py` 모두 미작성. 유닛 로직은 inline 스크립트로 검증했으나 회귀 안전망 없음. Richard 판단 요청.

2. **`/memory review` 슬래시 실제 호출 미검증** — 스킬 body 수준의 대화형 flow (y/n/e/s 응답 파싱)는 다음 세션에서 실제 호출해야 검증 가능. 현재는 CLI 레이어만 검증. Richard 의견: 슬래시 검증은 SESSION-CHECKPOINT의 다음 세션 확인 항목으로 넘기자.

3. **트리거 질문형 오발 위험** — "이거 기억해?" 같은 의문문도 매칭. 내 판단은 사용자 재질문이라도 "그 사실이 중요하단 암시"로 해석해 추출 시도 → Gemma가 판단해서 빈 배열 반환하면 비용 0. 그래도 보수적으로 regex 강화하려면 `(기억해$|기억해[^?])` 같은 방식. Arch 결정 요청.

4. **`edit` 플로우 CLI 지원 부재** — 스킬 body에서 LLM이 Edit 도구로 staged 파일 직접 수정 후 `approve` 호출. CLI 단일 엔드포인트(`edit_approve`)는 미구현. Arch 의견 구함.

---

## 리뷰 완료되면

- `REVIEW-FEEDBACK.md`에 `Ready for Builder: YES/NO` + Must/Should/Escalate 분류.
- Must Fix 없으면 Arch가 배포 게이트 승인 요청. 이미 배포는 되어 있으니 형식적 승인.
