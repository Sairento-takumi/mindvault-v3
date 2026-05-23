---
name: handoff-v3-master-brief
description: Sprint 13~16 자율 진행 brief — V3-PLAN 참조, sprint별 산출물(procedural slot / Memory Compiler / Self-eval Loop / Query Intent Classifier), 자율 결정 권한 + 안전 원칙(indexer.full_rebuild 금지, Sprint 10 트랜잭션 패턴, worktree 격리). 실행 결과 master HEAD 87c7a09→c03b7be→a81de70→f988483→63f32df→44df753
---

# MindVault V3 자율 진행 — Sprint 13~16 master brief

*Drafted: 2026-05-23, master HEAD `35c33f3` (v2.9.2 ship-ready, Sprint 12까지 머지됨).*
*Executed: 2026-05-23, master HEAD `44df753` (Sprint 13~16 + test isolation fix + dedup_cli).*

형은 자러 갔고 깨면 결과 검토 예정. **너는 Sprint 13~16 까지 자율 진행 권한**.
사용자 confirm 없이 결정 → 진행 → BUILD-LOG 에 결정 사유 명시.

## 핵심 참고 파일

- **`handoff/V3-PLAN.md`** — 이 작업의 master plan. **반드시 먼저 읽기**.
  - §1 v2.9 한계 (5가지 — 1.1 procedural type 누락, 1.2 false positive, 1.3 internal effort, 1.4 자기-수정 부재, 1.5 wikilink 노이즈 — 후자 둘은 Sprint 11/12 fix)
  - §1.6 Sprint 11+12 결과 (v2.9.2 보강 측정 데이터)
  - §2 패러다임 = LLM as compiler (Karpathy wiki)
  - §3 핵심 기능 A-F (Sprint 13~16+ 매핑)
  - §4 점진 호환 마이그레이션 (기존 memory/*.md 보존)
  - §5 검증 metric (v2.9 → v3 target 표)
  - §6 Sprint 분해 (13~17)
  - §7 위험·완화 매트릭스

- **`handoff/SPRINT-10-BUILD-LOG.md` ~ `SPRINT-12-BUILD-LOG.md`** — 직전 sprint
  교훈, 측정 데이터, 회귀 발견 패턴 참고.

- **`CLAUDE.md`** (repo 루트) — 프로젝트 컨텍스트, Three Man Team (Arch/Bob/Richard),
  토큰 룰, v1 폐기 교훈.

## 작업 범위 — Sprint 13~16

V3-PLAN §6 의 Sprint 분해 표 따라:

| Sprint | 주제 | 핵심 산출물 |
|---|---|---|
| **13** | Procedural Memory Slot | `memory/_procedural/` 슬롯, SessionEnd extract trigger 확장 (workflow·명령어·syntax 감지) |
| **14** | Memory Compiler | session raw → wiki 자동 정제, update vs 신규 자동 판단, diff review UI |
| **15** | Self-eval Loop | internal effort metric, false positive 추적, 자동 게이트 조정, 자기충족 메모리 감지 |
| **16** | Query Intent Classifier + Multi-source | mid-cosine zone discriminator (회수 필요 vs 잡담 자동 분류), 외부 repo 옵션 인덱싱 |

**Sprint 17 (ship) 은 이번 자율 작업에서 제외** — README v3, uninstall.sh,
GitHub 배포 같이 형 결정 영역. Sprint 16 완료 후 형이 깨면 검토.

## /goal condition

세션 시작 직후 다음 호출:

```
/goal Sprint 13, 14, 15, 16 모두 master 에 commit 완료. 각 sprint 별 handoff/SPRINT-{N}-BUILD-LOG.md 작성. master HEAD 가 Sprint 16 commit 이어야 종료.
```

각 sprint 완료 = ✓ commit on master + ✓ BUILD-LOG 작성 + ✓ 회귀 검증 통과.

## 자율 결정 권한 + 안전 원칙

**결정 권한** (사용자 confirm 없이 진행):
- 디자인 결정 (frontmatter 스키마, slot layout, trigger 정확 패턴, classifier 모델 선택 등) — BUILD-LOG 에 사유 명시.
- 커밋 묶음 방식 (sprint 별 1 커밋 권장. 회귀 fix 별도 커밋도 OK).
- 실패 시 sprint 단위 rollback. 다음 sprint 진행.
- false positive 발견 시 즉시 fix (Sprint 12 패턴).

**안전 원칙** (위반 금지):
- `indexer.full_rebuild()` 호출 금지. memory 인덱스 보존.
- Sprint 10 트랜잭션 패턴 (매 iter conn.commit + embed_text reordering) 유지.
- BGE plist + `bge_m3_server.py` 보존 (롤백 경로).
- 운영 launchctl 서비스 (`com.yonghaekim.arctic-ko-mlx`) 건드리지 말 것.
- 작업 시작 시 **EnterWorktree 격리** (예: `sprint13-procedural`).
  Sprint 별 별도 worktree 또는 누적 worktree 자율 결정.
- 변경 전 production 위치 (`~/.claude/scripts/mindvault/`) 백업.
- `.claude/worktrees/` 는 `.gitignore` 처리됨 — commit 시 영향 없음.
- 회귀 검증 필수 (잡담 차단, 도메인 hit, 동시성 lock 0건).

## 진행 순서 권장

1. **Setup**: V3-PLAN.md + 각 SPRINT-BUILD-LOG 읽기. v2.9.2 베이스라인 ack.
2. **/goal** 호출 (위 condition).
3. **Sprint 13**: EnterWorktree → Arch (설계) → Bob (구현) → Richard (검증) →
   commit → master 머지 (fast-forward).
4. **Sprint 14**: 같은 패턴. 단 Memory Compiler 는 본질적 새 설계 — V3-PLAN §3.B
   참고 + Gemma vs Claude Sonnet 정제 옵션 비교 시 Gemma 우선 (로컬, 비용 0).
5. **Sprint 15**: self-eval metric 정의 + 측정 인프라. 이 sprint 끝나면 4가지
   metric (hit rate, false positive rate, internal effort, 자기충족 감지율) 실측
   숫자 첫 측정.
6. **Sprint 16**: query intent classifier — Gemma small 또는 fastText. 회수 필요
   vs 잡담 자동 분류. mid-cosine zone 게이트 보강.
7. **종료**: master HEAD = Sprint 16 commit. handoff/SPRINT-13~16-BUILD-LOG.md
   4개 파일. V3-PLAN.md 의 §5 metric 표 v3 target 실측치 update.

## 환경

- 작업 dir: `/Users/yonghaekim/my-folder/apps/mindvault-v2`
- master HEAD (시작): `35c33f3 feat(sprint12): handoff frontmatter + FTS 게이트 강화`
- 운영 임베딩: Arctic-ko MLX 4bit, port 8081
- DB: `~/.claude/mindvault-v2/index.db` (WAL)
- Hook: `~/.claude/hooks/memory-recall.py` (raw_cosine_min DEFAULT 0.40, HINTED 0.32, HARD_TIMEOUT 400ms)
- 한국어 응답, 토큰 절약 룰 (CLAUDE.md 참조)
- Three Man Team 사용 가능 (Arch / Bob / Richard) — Sprint 14 (Memory Compiler) 처럼
  큰 설계는 Arch 먼저 권장.

## 메모리 (회수된 형 의도)

- **"작업량 줄이려는 본능 금지"** — 형이 자율 진행 명시한 작업에서 컨텍스트·시간
  추측으로 자꾸 멈춤 권고 금지. 컨텍스트 윈도우 여유 충분.
- **"no-v1-token-waste"** — 회수 hook 이 매 메시지마다 무관 메모리 주입하면 v1
  토큰 낭비 재현. Sprint 15 self-eval loop 의 false positive 추적이 이 메모리의
  자동화. 신중히 구현.
- **"reference-llm-wiki-pattern"** — Karpathy LLM Wiki 가 v3 의 이론적 토대.
  Sprint 14 Memory Compiler 가 핵심 구현체.

형은 자고 일어나서 한 번에 4 sprint 검토. 변명 없이, 깔끔하게 마무리하기.
