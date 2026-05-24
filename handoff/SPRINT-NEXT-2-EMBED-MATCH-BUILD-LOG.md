---
name: handoff-sprint-next-2-embed-match
description: V3-NEXT-IMPROVEMENTS #2 — memory_compiler 의 _find_existing_memory 에 임베딩 의미 매칭(3순위 fallback) 추가. name exact·slug 매칭이 모두 실패한 candidate body 에 한해 Arctic-ko passage 임베딩을 memories_vec 와 cosine 비교, top-1 ≥ 0.75 일 때만 매칭 인정. Karpathy LLM-as-compiler 패턴의 자연스러운 다음 단계.
---

MindVault v3 → 차기 보강 #2 — embedding 의미 매칭 빌드 로그

## 요약

V3-NEXT-IMPROVEMENTS.md #2 해결. Sprint 14 Memory Compiler 가 keyword 매칭(name exact → slug fallback) 만 지원해서, 형이 같은 주제를 자연어 변형(예: "claude --bg" vs "백그라운드 세션 시작") 으로 가리키면 update 가 안 되고 신규 staged 가 쌓이는 한계를 풀었다. 3순위 임베딩 fallback 으로 cosine ≥ 0.75 일 때만 매칭 인정 — 보수 임계로 잘못된 update overwrite 차단.

master HEAD `7f96207` (Sprint NEXT-1) 기준 worktree `worktree-next-2-embed-match` 에서 작업.

## 자율 결정 사유

- **threshold = 0.75** — V3-NEXT-IMPROVEMENTS brief 의 권장 임계 채택. memory_search 의 raw_cosine 게이트(0.40 default / 0.32 hinted) 보다 한참 엄격. 이유: 회수 게이트는 "조금이라도 관련 있는 메모리 보여주기" 의도라 관대해도 무해, 그러나 compiler 는 잘못된 매칭이 곧 `.bak` 거치고 본문 overwrite 로 이어지는 destructive flow. false-merge 비용이 false-miss 비용보다 훨씬 비싸다. 추후 self_eval 측정으로 튜닝.
- **passage-passage 매칭** — Arctic-ko 의 query/passage 분리 학습 구조상 메모리간 의미 비교는 passage-passage 가 정합. memories_vec 인덱싱이 `kind="passage"` 로 저장되므로 candidate 임베딩도 passage 로 호출.
- **title + body 결합 query 텍스트** — body 만으로는 짧은 procedural fact (예: `claude --bg "prompt"`) 의 의미가 묻힘. title 까지 합쳐 임베딩 → 운영 메모리의 title-rich frontmatter 와 정합.
- **1·2순위와 fallback 통합** — `_find_existing_memory` 안에서 name/slug 시도 → 모두 실패한 경우만 `_find_by_embedding` 호출. name 매칭은 신뢰 강해서 embedding 우회 가능 + 임베딩 비용(서버 호출) 절약.
- **path traversal 방어** — embedding 매칭이 무관 디렉토리 경로를 best_sim 으로 반환할 수 있는 시나리오 대비. memory_dirs 루트 안에 있을 때만 매칭 인정.
- **모듈 attribute 호출 패턴** — `from memory_indexer import embed_text` 대신 `import memory_indexer; memory_indexer.embed_text(...)`. 테스트가 `patch.object(memory_indexer, 'embed_text', ...)` 로 깔끔 격리. 초기 구현은 lazy `from ... import` 였으나 sys.modules monkey-patch 가 다른 테스트(test_memory_indexer, test_memory_search) 오염 일으켜 즉시 수정.
- **embedding 의존성 graceful degrade** — numpy/memory_indexer 가 import 안 되거나 embed_text 가 None 반환(서버 다운)이면 silent None → name/slug 만으로 동작하는 기존 Sprint 14 흐름 그대로 유지. 운영 안정성.

## 변경 상세

### A. `src/memory_compiler.py`

**신규 상수**:
```python
EMBED_MATCH_THRESHOLD = 0.75
```

**`_find_existing_memory` 확장**: 1·2순위 모두 실패 시 3순위 호출.
```python
if fallback_match is not None:
    return fallback_match
try:
    return _find_by_embedding(candidate, memory_dirs)
except Exception as e:
    _debug(f"embed match fail: {type(e).__name__} {e}")
    return None
```

**`_find_by_embedding(candidate, memory_dirs) -> dict | None` 신규**:
1. body 비어있으면 None
2. query_text = `title\n\nbody` (또는 body 만, title 없을 때)
3. lazy import 로 `memory_indexer`, `indexer`, `numpy`. 실패 시 None
4. `memory_indexer.embed_text(text, kind="passage")` 호출. None 이면 None
5. `indexer.open_db()` → memories_vec 전체 row 가져옴 (try/finally 로 close)
6. numpy 로 cosine top-1 계산
7. `best_sim < EMBED_MATCH_THRESHOLD` 면 None
8. best path 가 memory_dirs 루트 안 + 파일 존재 검증 → 외부면 None
9. frontmatter/body 읽어 `{"path", "frontmatter", "body", "match_kind": "embedding", "cosine": best_sim}` 반환

**`_is_within(p, root)` 신규**: 3.8 호환 path-within 헬퍼 (is_relative_to 폴리필).

### B. 테스트 (`tests/test_memory_compiler.py`)

`TestEmbeddingFallback` 클래스 4 cases (+ helper `_mock_db_with_rows` — sqlite in-memory + memories_vec 스키마 그대로 mocking):

| 테스트 | 검증 |
|---|---|
| test_embedding_hit_above_threshold | 같은 방향 벡터 → cosine ≈ 1.0 → name/slug 안 맞아도 매칭. match_kind="embedding", cosine ≥ 0.75 |
| test_embedding_miss_below_threshold | 직교 벡터 → cosine 0 < 0.75 → None |
| test_embedding_called_only_after_name_slug_fail | name 매칭이면 embed_text 호출 0회 (call_count 카운터 검증) |
| test_embedding_failure_returns_none_gracefully | embed_text 가 None 반환 → 예외 없이 None |

## 측정 데이터

### memory_compiler 단독

```
25/25 PASS (0.12s)
신규 4건: TestEmbeddingFallback.*
기존 21건 보존 (TestSlugifyEquivalence, TestDiffSummary, TestUnifiedDiffText,
              TestFindExistingMemory, TestCompileCandidates, TestAutoCompileEnabled,
              TestSessionEndIntegration, TestReviewCliUpdateFlow)
```

### 전체 회귀

```
200/202 PASS (test_install_uninstall 제외, 100s)
2 fail = test_schema_v2.* — schema_version 가 3 인데 테스트는 2 기대. master HEAD `7f96207` 동일 pre-existing. 본 sprint 변경 무관.
```

초기 구현은 sys.modules monkey-patch 사용 → 10 fail (test_memory_indexer.TestEmbedText 4 + test_memory_search.TestRecallMemory 3 + schema_v2 2 + 신규 1). attribute 호출 패턴 + patch.object 로 수정 후 2 fail 만 남음. 신규 회귀 0건.

### 매칭 정밀도 sanity

- cosine = 1.0 (동일 방향) → 매칭 ✓
- cosine = 0.0 (직교) → 미매칭 ✓
- threshold 경계는 단위 테스트 외 운영 누적 후 self_eval 측정 필요. 본 sprint 의 0.75 는 보수치 — 초기 운영에서 false-miss 가 잦으면 0.70 으로 완화 검토.

## 안전 정책 준수

- `indexer.full_rebuild()` 호출 없음.
- Sprint 10 트랜잭션 패턴 무변경. open_db 만 사용, write 없음.
- BGE plist / `bge_m3_server.py` 무변경.
- launchctl 서비스 (`arctic-ko-mlx`, `gemma-mlx`, `mv3-env`) 무관.
- path traversal 방어 (`_is_within`) — embedding 매칭이 memory_dirs 외 path 가리키면 거부.
- Sprint 14 의 cmd_diff + cmd_approve `.bak` 백업 안전망 그대로 유지 — embedding 매칭도 동일 flow 거침.
- worktree `next-2-embed-match` 격리.

## 미해결 / 다음 #3~#7 후보

- **threshold 실측 튜닝** — 0.75 는 보수치. Memory Compiler ON 상태 (`MV3_AUTO_COMPILE=1`) + 본 휴리스틱 가동 후 며칠 누적, `/memory_review` diff 검토 시 형이 reject 한 update 의 cosine 분포 봐야 적정 임계 결정 가능. self_eval 에 컬럼 추가 후보.
- **title 비어 있고 body 만 있는 경우 동작 확인** — 코드는 `body 만으로 query` 처리하나 운영 candidate 는 거의 title 있음. 가설 검증은 운영 누적 후.
- **다음 #3 Gemma 보강 classifier** — unknown intent 짧은 query 만 Gemma 호출. 본 sprint 와 무관, 별도 사이클.
- **#4 type 별 회수 게이트, #5 diff UI 색상, #6 slug conflict, #7 scan latency 캐시** — 형 지시 시 진행.

## 변경 파일

```
src/memory_compiler.py                              | +85 -2
tests/test_memory_compiler.py                       | +95
handoff/SPRINT-NEXT-2-EMBED-MATCH-BUILD-LOG.md      | 신규
```
