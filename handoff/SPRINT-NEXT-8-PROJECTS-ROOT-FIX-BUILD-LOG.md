---
name: handoff-sprint-next-8-projects-root-fix-build-log
description: V3-NEXT-IMPROVEMENTS #8 — session_memory_end.PROJECTS_DIR 단일 슬롯 하드코딩 fix. Sprint 6 multi-projects 패치가 indexer만 받고 SessionEnd hook 누락 → mindvault-v2 cwd 세션 jsonl missing → Memory Compiler 운영 fire 0건. 진단 4단계 + 한 줄 fix + backfill 24건 + 첫 fire 결과 + NEXT-9 schema test cleanup.
---

# MindVault v3 → 차기 보강 #8 — PROJECTS_ROOT 전체 슬롯 glob 빌드 로그

*Drafted: 2026-05-24, master HEAD `524e442` (NEXT-8 fix + NEXT-9 cleanup 머지 후).*
*Discovered & fixed: 2026-05-24 background 세션. Trigger: 형의 "v3 소개해줘" 요청에서 새 Claude 가 v3 의 존재를 모름 → dogfooding gap 노출.*

## 1. 문제 발견 경위

형이 새 세션에서 "MindVault V3 소개" 요청. 메모리·SessionStart 요약 모두 Sprint 7 (2026-05-22) 에서 멈춤. v3 실재 (master `b440d9e`, Sprint 13~16 + NEXT-1~7 누적) 인데 메모리 layer 가 완전히 사각지대. 형이 "v3 가 있는지조차 모르면 실패작" 이라 단정 → 진단 시작.

## 2. 진단 4단계

가설 차례대로 검증:

| # | 가설 | 결과 |
|---|---|---|
| 1 | `auto_compile_enabled()` False 리턴? | ❌. `launchctl getenv MV2_AUTO_COMPILE = 1` (`com.yonghaekim.mv2-env.plist` 영구화 효과) |
| 2 | SessionEnd hook 자체가 안 떠? | ❌. debug.log 에 5/23 22:40 ~ 5/24 09:54 사이 9건 fire 확인 |
| 3 | candidates 비어서 compile 분기 미진입? | ⚠️ 부분. 정확히는 **한 단계 전**, `extract_from_jsonl` 호출 자체 안 됨 |
| 4 | jsonl 탐색 경로 문제? | ✓ 확정. `PROJECTS_DIR / {sid}.jsonl` 가 단일 슬롯 — 다른 cwd 세션 100% miss |

### 결정타 증거

- `session_memory_end.py:40` 가 `PROJECTS_DIR = Path("...projects/-Users-yonghaekim-my-folder")` 단일 슬롯 하드코딩.
- `indexer.py:16` 는 Sprint 6 fix 로 `PROJECTS_ROOT = Path("...projects")` + `iter_jsonl_paths(root)` 전체 흡수.
- **즉, indexer/회수 layer 만 multi-projects 적응, 자동 추출 layer 는 패치 누락.**
- sid `949a8635` 실제 위치: `-Users-yonghaekim-my-folder-apps-mindvault-v2/949a8635-*.jsonl` (mindvault-v2 cwd 세션).
- hook 탐색 위치: `-Users-yonghaekim-my-folder/949a8635-*.jsonl` → 없음 → `jsonl missing for 949a8635` → line 186 early return.
- `extract_from_jsonl` 호출 안 됨 → candidates 0건 → `compile_candidates` 분기 진입 안 됨 → Memory Compiler 운영 fire 0건 → `_staged/`, `_procedural/` 디렉토리 자체 존재 안 함.

### dogfooding gap 의 정확한 좌표

형이 mindvault-v2 cwd 또는 그 worktree (`-Users-yonghaekim-my-folder-apps-mindvault-v2--claude-worktrees-v3-sprint-13-16`) 에서 v3 개발 → 그 cwd 의 모든 세션 jsonl 이 별도 슬롯에 쌓임 → 본인이 만든 자동화가 본인 개발 환경만 골라서 못 봄. 5/22~24 v3 핵심 sprint 진척이 메모리에 0건 캡처된 직접 원인.

홈 cwd (`-Users-yonghaekim`) 세션은 정상 처리돼 sendmail/EPSON/grammar 등 일반 메모리는 갱신됨 — 사각지대가 v3 본인 메타정보에 정확히 집중된 아이러니.

## 3. fix — 한 줄짜리

`src/session_memory_end.py`:

```python
# Before (line 40)
PROJECTS_DIR = Path("/Users/yonghaekim/.claude/projects/-Users-yonghaekim-my-folder")

# After (line 40~43)
PROJECTS_ROOT = Path("/Users/yonghaekim/.claude/projects")
# memory 저장 base 는 항상 -Users-yonghaekim-my-folder 슬롯 (단일 원천).
# 단, jsonl 탐색은 PROJECTS_ROOT 의 모든 하위 슬롯에서 — Sprint 6 indexer 와 동일.
PROJECTS_DIR = PROJECTS_ROOT / "-Users-yonghaekim-my-folder"
```

```python
# Before (line 183~186)
jsonl = PROJECTS_DIR / f"{sid}.jsonl"
if not jsonl.is_file():
    _debug(f"jsonl missing for {sid[:8]}")
    return 0

# After (line 186~192)
matches = sorted(PROJECTS_ROOT.glob(f"*/{sid}.jsonl"))
if not matches:
    _debug(f"jsonl missing for {sid[:8]}")
    return 0
jsonl = matches[0]
if len(matches) > 1:
    _debug(f"jsonl multi-hit for {sid[:8]}: picked {jsonl.parent.name}")
```

핵심 설계:
- `PROJECTS_ROOT` 도입 — Sprint 6 indexer 와 동일 패턴.
- `PROJECTS_DIR` 는 **memory 저장 base 로만** 유지 (`MEMORY_DIR = PROJECTS_DIR / "memory"`). 메모리 단일 원천 보존 — 다른 cwd 슬롯에 staged 분산되지 않도록.
- `sorted(...).glob` → 결정론적 첫 hit. multi-hit 시 debug 로그로 가시화.

master commit: `eaa5434 fix(session-end): PROJECTS_ROOT 전체 슬롯 glob — Sprint 6 multi-projects fix 누락 보강`

## 4. 검증

### sanity check
```
sid prefix 949a8635 → -Users-yonghaekim-my-folder-apps-mindvault-v2 ✓
sid prefix fae488da → -Users-yonghaekim ✓
sid prefix 03269e96 → NONE (jsonl 사라짐, 의도된 동작)
```

### test suite
- `pytest tests/ -q` → 241 passed, 2 failed.
- 2건 fail = pre-existing `test_schema_v2` (NEXT-1, NEXT-2 BUILD-LOG 에 동일 보고). 본 fix 무관.
- → NEXT-9 곁다리 cleanup 으로 동시 해소 (아래 §6 참조).

### 첫 운영 fire — 949a8635 세션 수동 호출
```
[2026-05-24 10:19:12] session-end: compiled session=949a8635 updates=0/2
[2026-05-24 10:19:12] session-end: session 949a8635: staged 2/2
```

5/23 plist 영구화 이후 처음으로 Memory Compiler 가 실제 데이터 흐름 발생. `_procedural/_staged/` 슬롯 신규 생성. 추출된 2건:
- `procedural_Gemma_분류기_응답_파싱_버그_해결.md` — `enable_thinking=false` 적용, 평균 300ms latency (master `b440d9e` 작업의 정확한 핵심).
- `procedural_turns_cache_성능_최적화_완료_53배_단축.md` — `turns_cache ON 0.56s / OFF 2.95s, 1735 recalls, hit 0.881` (NEXT-7 결과 정확 재현).

**V3-PLAN §2 핵심 가설 ("LLM 이 컴파일러처럼 raw 세션 → 정제된 wiki 항목 누적 생성") 의 첫 실증.** Karpathy LLM Wiki 패턴 첫 작동.

## 5. backfill — 미처리 24건 일괄

### 호출 결과
- debug.log `jsonl missing for` 패턴 unique 31건 prefix 추출.
- `PROJECTS_ROOT.glob` 매칭 → resolved 24건, unresolved 7건 (jsonl 진짜 사라짐 — Claude Code 가 빈 세션 정리한 케이스).
- 24건 직렬 hook 호출 (`MV2_AUTO_COMPILE=1`, sleep 0.7s sqlite WAL 충돌 회피).
- 모두 exit 0.

### staged 결과 (의외)
- 24건 중 **1건만 staged 발생** (949a8635 첫 발의 2건). 나머지 23건 모두 "no candidates".
- 949a8635 자체도 두 번째 호출 (10:25:13) 은 0건 — extractor 가 stateless 한데 jsonl 새 turn 추가로 trigger 시그널 희석된 것으로 추정.

### 의미 — extractor recall 폭 한계 노출
- `memory_extractor.TRIGGER_RE` 명시 키워드 (`기억해`, `결정:`, `외워둬`, `이 명령어`) + NEXT-1 자동 휴리스틱 (special_binary OR non_trivial bash → NEXT_ACTION) **두 layer 만으로는 일반 세션의 의미있는 결정 사항 대부분이 추출 불가**.
- backfill 대상 23건은 짧은 잡담·도움말 호출·단발 명령이 다수였을 가능성 — 일부는 실제 가치 있는 결정 포함했을 수 있으나 trigger 미발화로 lost.
- v3 자동 wiki compile 의 진짜 가치는 extractor recall 폭에 비례. 본 fix 가 jsonl 탐색을 풀었지만, extractor 자체가 좁은 trigger 만 보면 fire 횟수만 늘 뿐 staged 산출량 미증.

→ **NEXT-10 backlog 후보: extractor recall 확장 (3rd layer 휴리스틱 또는 Gemma fulltext scan).**

## 6. 곁다리 cleanup — NEXT-9 schema test fix

NEXT-8 sanity 단계에서 매 sprint 보고되는 pre-existing 2건 fail 발견. 같은 background 세션에서 동시 해소.

### 문제
- `tests/test_schema_v2.py:14` 가 `SCHEMA_VERSION == 2` hard-coded expected.
- 실제 `src/indexer.py:35` 는 `SCHEMA_VERSION = 3` (Sprint 13/14 진화).
- NEXT-1, NEXT-2 BUILD-LOG 에 "pre-existing — 본 sprint 무관" 으로 매번 흘림. 노이즈 누적.

### fix
- `class TestSchemaV2` → `TestSchemaCurrent`
- `test_schema_version_is_2` → `test_schema_version_matches_current`, expected `SCHEMA_VERSION == 3`
- `test_v1_db_migrates_to_v2_*` → `test_v1_db_migrates_to_current_*`, expected `str(SCHEMA_VERSION)` 동적 비교 — 향후 v4 진화도 자동 추종
- 모듈 docstring 갱신 (v1→v3 직접 마이그레이션 검증으로 의미 갱신)
- 파일명 `test_schema_v2.py` 는 유지 (git mv 비용 vs 가치 trade-off — v2 라는 history marker 보존)

### 검증
```
pytest tests/test_schema_v2.py -v → 4 passed (0.08s)
```

master commit: `524e442 test(schema): expected v2 → 현재 SCHEMA_VERSION (v3) 갱신 — 2건 pre-existing fail 해소`

## 7. 남은 한계 (V3-NEXT 백로그 추가 후보)

### NEXT-10 (가장 시급) — extractor recall 폭 확장
- 현 trigger 2 layer (TRIGGER_RE + NEXT-1 휴리스틱) 만으로는 일반 세션의 결정·learnings 추출률 낮음 — backfill 24/24 중 1건만 fire 가 증거.
- 후보: (a) 3rd layer — assistant tool_use 결과 + 다음 user 짧은 ack ("좋아", "OK", "ㅇㅇ") 결합. (b) Gemma fulltext scan — 세션 전체를 Gemma 에게 "이 세션에 영구 기억할 만한 결정/사실 있나" 1회 prompt.
- 위험: false positive 폭증 + Gemma 호출 비용. opt-in env (`MV2_EXTRACTOR_DEEP_SCAN=1`) 로 시작.

### NEXT-11 — project narrative 메모리 자동화
- v3 가설은 procedural slot 우선 — `project_mindvault.md` 같은 narrative 진척은 여전히 `/close-session` 명시 호출 의존.
- 형이 매 큰 sprint 마다 close-session 호출 안 하면 (이번 사각지대처럼) narrative 메모리 영구 stale.
- 후보: SessionEnd 시 narrative 후보도 Gemma 가 1회 분류 → existing project_*.md 와 cosine 매칭 → update_of 후보로 staged.
- 부분적으로 NEXT-2 embed match (Sprint 14, cosine ≥ 0.75) 가 기반 — 그 위에 narrative trigger 1개 더.

### NEXT-12 — extractor stateless 가정 검증
- 949a8635 첫 호출 2건, 두 번째 호출 0건. jsonl 새 turn 추가로 trigger 시그널 희석된 것으로 추정했으나 정확한 메커니즘 미확정.
- 측정: 동일 jsonl 두 번 호출 → diff 분석. 결과에 따라 (1) extractor 가 마지막 N turn 만 본다 → window 조정 (2) trigger 위치 (assistant vs user turn) 영향 → 가중치 조정.

### NEXT-13 — backfill CLI 표준화
- 본 sprint 의 `/tmp/mv2-missing-prefixes.txt` + backfill.py 가 ad-hoc.
- `recall_cli.py` 옆에 `backfill_cli.py` 추가 — `--missing-only` (debug.log 스캔), `--last-hours N` (시간 범위), `--dry-run` (호출 안 함, target 만 표시).

## 8. master HEAD

```
524e442 test(schema): expected v2 → 현재 SCHEMA_VERSION (v3) 갱신 — 2건 pre-existing fail 해소
eaa5434 fix(session-end): PROJECTS_ROOT 전체 슬롯 glob — Sprint 6 multi-projects fix 누락 보강
b440d9e fix(query_intent): Gemma thinking 모드로 빈 응답 회귀 — enable_thinking=false  ← 이전 base
```

### production sync
- `~/.claude/hooks/session-memory-end.py` 백업: `bak-20260524-101759`
- production version = master `eaa5434` 동기화 완료
- launchctl 서비스 (`com.yonghaekim.arctic-ko-mlx`, `com.yonghaekim.gemma-mlx`, `com.yonghaekim.mv2-env`, `com.yonghaekim.mv2-gemma-intent`) 모두 손대지 않음. SessionEnd hook 만 갱신.

### 인덱스 영향
- DB 스키마 변경 없음. `indexer.full_rebuild` 호출 안 함 (안전 원칙 준수).
- `_procedural/_staged/` 2건 신규 — `/memory_review` 로 형 검토 대기.
- 다음 SessionEnd 부터 자동으로 mindvault-v2 cwd 세션도 추출 대상.

## 9. 관련

- [[handoff-v3-plan]] §1.4 자기-수정 메커니즘 — 이번 fix 가 그 데이터 흐름의 첫 활성화.
- [[handoff-sprint-next-1-auto-trigger-build-log]] — NEXT-1 자동 trigger 휴리스틱. 본 fix 후 첫 fire 에서 NEXT-1 trigger 가 procedural 2건 정확 추출하는 데 기여.
- [[handoff-sprint-next-2-embed-match-build-log]] — NEXT-2 embedding 의미 매칭. NEXT-11 narrative 자동화의 기반.
- [[handoff-sprint-next-7-scan-cache-build-log]] — 첫 fire 의 staged 결과 1건이 NEXT-7 결과 정확 재현.
- [[handoff-sprint10-brief]] — Sprint 10 sqlite WAL lock 패턴. backfill 직렬 호출 + sleep 의 근거.
