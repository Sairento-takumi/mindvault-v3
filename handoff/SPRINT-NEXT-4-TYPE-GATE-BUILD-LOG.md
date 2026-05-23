---
name: handoff-sprint-next-4-type-gate
description: V3-NEXT-IMPROVEMENTS #4 — recall_memory 가 path 의 _procedural/ marker 보고 raw_cosine 게이트 분기. procedural path 는 base + 0.05 엄격 (default 0.40→0.45, hinted 0.32→0.37). wikilink expand 도 같은 분기.
---

MindVault v3 → 차기 보강 #4 — type 별 회수 게이트 분리 빌드 로그

## 요약

V3-NEXT-IMPROVEMENTS #4 해결. SPRINT-13-BUILD-LOG 미해결 2번 "type 별 게이트 분리". procedural 메모리는 명령어 syntax 라 specific keyword 매칭 강도가 일반 결정·프로젝트 메모리보다 엄격해야 정확. 단일 raw_cosine_min 0.40 으로 모든 type 동일 게이트 두면 procedural 이 약한 매칭에도 노이즈로 끌려옴.

master HEAD `afa82f6` (NEXT-3 Gemma 보강) 기준 worktree `worktree-next-4-type-gate`.

## 자율 결정 사유

- **path marker 기반 분기 (`/_procedural/`)** — DB 에 type 컬럼 추가 안 했고 (Sprint 13 결정) frontmatter 매번 읽기는 cost. path 안의 `/_procedural/` 마커는 0-cost. _collect_md_files 가 이미 디렉토리 단위로 분리 보관해 path 가 사실상 type 의 1:1 마커.
- **bonus +0.05** — V3-NEXT-IMPROVEMENTS brief 의 권장값(0.45 vs 0.40). hinted 시에도 같은 보너스 적용 → 0.32 → 0.37. 절대 임계 (procedural 0.45) 가 아닌 상대 보너스로 hint flow 자연스럽게 보존.
- **wikilink expand 도 동일 분기** — target path 가 procedural 이면 base path_base = raw_cosine_min + PROCEDURAL_GATE_BONUS, gate = path_base × WIKILINK_GATE_FACTOR. 일반 메모리에서 wikilink 로 procedural 끌려올 때도 엄격 보장.
- **raw_cosine_min ≤ 0 일 때는 보너스 없음** — 게이트 비활성 모드 (테스트·디버그 용도) 보존.

## 변경 상세

### A. `src/memory_search.py`

- 새 상수:
  - `PROCEDURAL_GATE_BONUS = 0.05`
  - `PROCEDURAL_PATH_MARKER = "/_procedural/"`
- 새 헬퍼:
  - `_is_procedural_path(path) -> bool`: marker substring 매칭
  - `_gate_for_path(path, base_min) -> float`: procedural 이면 +bonus, 아니면 그대로
- `recall_memory` 의 메인 게이트 루프 변경: `threshold = _gate_for_path(path, raw_cosine_min)` 분기 적용 (fts source 는 ×0.5 완화 그대로).
- `_expand_wikilinks` 의 target 게이트 변경: `path_base = _gate_for_path(resolved_path, raw_cosine_min); gate = path_base × WIKILINK_GATE_FACTOR`. 이전엔 raw_cosine_min × WIKILINK_GATE_FACTOR 단일.

### B. 테스트 (`tests/test_memory_search.py`)

`TestProceduralTypeGate` 클래스 3 cases:

| 테스트 | 검증 |
|---|---|
| test_is_procedural_path | marker substring 매칭 + 운영 path / 빈 path edge |
| test_gate_for_path_procedural_bonus | default(0.40)/hinted(0.32) 모두 +0.05, non-procedural 보존 |
| test_gate_disabled_when_min_zero | base=0 일 때 procedural 도 0 (게이트 비활성 보존) |

## 측정 데이터

### memory_search 단독

```
14/14 PASS (0.10s)
신규 3건: TestProceduralTypeGate.*
기존 11건 보존 (TestRRFFusion, TestNormalization, TestRecallMemory)
```

### 전체 회귀

```
215/217 PASS (test_install_uninstall 제외, 99s)
2 fail = test_schema_v2.* — master HEAD `afa82f6` 동일 pre-existing.
```

신규 회귀 0건.

### 운영 효과 예상

- procedural memory coverage 0% baseline (`procedural_audit`) → NEXT-1 자동 trigger + NEXT-2 embedding compile + NEXT-4 게이트 분리 누적되어 procedural 메모리 양산 + 정밀 회수 가능.
- false positive 분포 변화는 Sprint 15 self_eval --hours 168 운영 누적 후 측정 필요.

## 안전 정책 준수

- `indexer.full_rebuild()` 호출 없음.
- Sprint 10 트랜잭션 패턴 무변경.
- BGE plist / `bge_m3_server.py` 무변경.
- launchctl 서비스 무관.
- raw_cosine_min 인자 시그니처 유지 — caller (hook) 변경 없음. 게이트는 path 단위에서 동적 계산.
- worktree 격리.

## 미해결 / 다음 #5~#7

- **bonus 0.05 실측 튜닝** — 0.45 임계가 너무 엄격해서 procedural 메모리 회수율이 0 에 가깝게 떨어지면 0.43 또는 0.42 로 완화 검토. self_eval intent_stats + 형이 hook 결과 검토 후 결정.
- **#5 diff UI 색상, #6 slug conflict, #7 scan latency** — 본 sprint 다음 사이클에서 순차 진행.

## 변경 파일

```
src/memory_search.py                              | +25 -3
tests/test_memory_search.py                       | +36
handoff/SPRINT-NEXT-4-TYPE-GATE-BUILD-LOG.md      | 신규
```
