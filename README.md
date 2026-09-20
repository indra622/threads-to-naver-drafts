# Threads → Naver Blog drafts

Threads의 내 게시물을 공식 API로 읽고, 원문을 바꾸지 않은 채 네이버 블로그의 **임시저장 초안**으로 옮긴다. LLM은 사용하지 않으며 자동 공개도 하지 않는다.

## 동작 원칙

- 게시물 1개 → 네이버 초안 1개
- 본문은 Threads 원문을 그대로 사용
- 제목은 첫 번째 비어 있지 않은 줄의 앞 100자(본문은 그대로 유지)
- 답글과 리포스트는 기본 제외
- Threads 게시물 ID를 SQLite에 기록해 중복 초안 방지
- 상단의 `저장`/`임시저장`이라고 확인된 컨트롤만 클릭하며 `발행`은 클릭하지 않음
- 임시저장 수가 98개 이상이면 기존 초안 보호를 위해 새 초안 생성을 중단
- Threads 토큰은 평문 설정 파일이 아니라 macOS Keychain에 저장
- 장기 토큰은 발급 24시간 이후 일배치 실행 중 공식 API로 자동 갱신
- 네이버 비밀번호는 스크립트가 받지 않고 전용 브라우저 프로필의 로그인 세션만 사용

## 설치

```bash
cd ~/codes/threads-to-naver-drafts
cp config.example.toml config.toml
# 블로그가 여러 개면 config.toml에 naver_blog_id와 전용 글쓰기 URL을 설정
uv sync --extra dev
uv run playwright install chromium
```

Meta Developer 앱에서 Threads 사용 사례를 추가하고, 자신의 게시물을 읽을 수 있는 사용자 액세스 토큰을 발급한다. 토큰은 아래 명령의 가려진 입력창에서 한 번만 입력한다.

```bash
uv run threads-to-naver setup-token
```

네이버 로그인 세션도 한 번 만든다. 비밀번호는 열린 브라우저에 직접 입력한다. 스크립트가 로그인 쿠키를 감지하면 자동으로 끝난다.

```bash
uv run threads-to-naver login
```

## 안전한 첫 실행

어제 게시물 목록만 가져와 JSON으로 확인한다. 이 단계에서는 네이버를 열지 않는다.

```bash
uv run threads-to-naver run --dry-run
```

특정 날짜를 확인하려면:

```bash
uv run threads-to-naver run --date 2026-09-19 --dry-run
```

확인 후 실제 초안을 만든다.

```bash
uv run threads-to-naver run --date 2026-09-19
```

가장 최근 게시물 한 건만 실험할 때는 다음 명령을 사용한다.

```bash
uv run threads-to-naver run --latest --dry-run
uv run threads-to-naver run --latest
```

실패한 게시물은 SQLite에 완료 처리되지 않아 다음 실행에서 다시 시도된다. 실행 화면은 `artifacts/`에 남는다.

전체 과거 원 게시물을 오래된 순서대로 백필하려면 다음 명령을 사용한다. 성공한 건은 즉시 SQLite에 기록되므로 중단 후 같은 명령으로 안전하게 재개된다.

```bash
uv run threads-to-naver backfill --dry-run
uv run threads-to-naver backfill
```

네이버 임시저장 공간과 브라우저 상태를 보며 여러 묶음으로 나눌 때는 `--limit`을 사용한다.

```bash
uv run threads-to-naver backfill --limit 50
```

## 매일 실행(선택)

현재 운영 설정은 매일 11:00에 **전날 게시물**을 초안으로 만든다.

```bash
uv run python scripts/install_launchd.py --hour 11 --minute 0
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.threads-to-naver-drafts.plist
```

스케줄을 설치하기 전 최소 한 번은 실제 초안 생성까지 확인한다. 브라우저를 표시하는 기본 설정에서는 로그인 만료나 네이버 편집기 변경을 눈으로 확인할 수 있다.

## 현재 한계

네이버는 공식 글쓰기 API를 제공하지 않으므로 편집기 화면이 바뀌면 선택자 보정이 필요할 수 있다. 안전을 위해 `임시저장` 컨트롤을 찾지 못하면 즉시 실패하며 공개 발행으로 대체하지 않는다.

임시저장 수가 98개에 도달하면 기존 초안 유실 가능성을 피하기 위해 일배치와 백필이 새 초안을 만들지 않는다. 초안을 검토해 발행하거나 삭제한 뒤 같은 명령을 다시 실행하면 SQLite 완료 기록 다음 항목부터 재개된다.
