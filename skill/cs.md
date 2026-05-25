---
description: "[mv3-skill] /close-session 의 짧은 alias (MindVault v3). 본 SKILL 호출 시 즉시 close-session 본문 Read 후 그 단계 그대로 따른다."
argument-hint: [--dry-run]
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
---

사용자가 `/cs` 를 호출했다. `/close-session` 과 동일.

단일 진실 원천: `$HOME/.claude/commands/close-session.md`. 본 alias 호출 시 메인 Claude 는 즉시 그 본문을 `Read` 한 뒤 거기 단계를 그대로 따른다. 본 alias SKILL 내용이 본 SKILL 과 어긋나면 close-session 본 SKILL 이 우선.

Claude Code `Read` tool 은 absolute path 만 받는다 (`~` expansion 미지원). 메인 Claude 가 직접 `/Users/<user>/.claude/commands/close-session.md` 형태의 절대경로로 호출해야 한다. 다음 우선순위:

1. **권장**: `bash -c 'echo $HOME'` 으로 `$HOME` 값을 명시 얻은 뒤 `<HOME>/.claude/commands/close-session.md` 절대경로로 `Read` 호출. 시스템 컨텍스트의 `HOME` 환경변수 노출 여부와 무관해 가장 안정적.
2. 환경 메타데이터에 사용자 홈 디렉토리가 이미 명시돼 있으면 그 값을 직접 사용 (예: 현재 working directory `/Users/<user>/...` 헤더).
3. `~` 표기 또는 expand 안 된 `$HOME` 문자열은 Read tool 에 직접 넘기지 말 것 — InputValidationError 또는 ENOENT.

두 시도 모두 실패하면 `bash install.sh` 재실행 안내. 옛 personal `~/.claude/skills/{cs,close-session}/SKILL.md` 가 새 deploy 본을 가리고 있을 수 있다 (v3.1.0 → v3.1.1 install.sh 가 자동 정리).

**참고**: path 가 잘 resolve 됐어도 내용이 stale (예전 deploy 본) 일 수 있다. 본문에 `[mv3-skill]` 마커 확인 + frontmatter 가 close-session 의 9단계 구조와 일치하는지 메인 Claude 가 짧게 검증. 불일치면 사용자에게 `bash install.sh` 재실행 권장.

이후 그 본문의 §1 (메모리 슬롯 결정) 부터 §9 (요약 보고) 까지 진행.
