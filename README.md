<div align="center">

# research-notes

**레포 커밋으로 과제 연구노트 PDF와 붙여넣을 요약을 만들어 주는 Claude Code · Codex 스킬**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Claude Code skill](https://img.shields.io/badge/Claude%20Code-skill-d97757)](SKILL.md)
[![Codex skill](https://img.shields.io/badge/Codex-skill-10a37f)](SKILL.md)

**한국어** · [English](README.en.md)

<img src="references/images/example-page-1.png" width="420" alt="연구노트 예시 1쪽">

</div>

## 무엇을 하나요

노트 작성 기간 동안의 커밋을 읽고, 작성일마다 연구노트 PDF를 쓰고, 기관 시스템에 붙여넣을 텍스트까지 만듭니다.

- 작성일: 한 달에 2건 (둘째 · 넷째 금요일, 공휴일이면 직전 평일)
- 노트마다 A4 PDF 1개 (최대 4쪽, 목표 1~2쪽)
- 붙여넣을 텍스트: 실험 제목 + 실험내용요약 7줄
- 커밋 날짜와 상관없이, 기간 안의 커밋에서 중요한 것만 골라 노트 개수만큼 주제를 나눔
- 이미 쓴 노트가 있으면 그 칸은 건너뛰고 같은 내용을 반복하지 않음
- 쓰기 전에 계획표 (작성일 · 제목 · 근거 커밋)를 보여 주고 확인을 받음

레포의 코드 · 테스트 · 앱은 실행하지 않습니다. 내용은 커밋 · README · 문서에서만 가져오고, 그림은 레포에 있는 파일이나 사용자가 준 것만 씁니다.

## 설치

Claude Code나 Codex에 이렇게 말하면 설치해 줍니다:

```text
이 스킬 설치해줘: https://github.com/Neoplanetz/research-notes-skill
```

[skills](https://github.com/vercel-labs/skills) CLI로 설치 (Node.js 22.20 이상, 설치할 도구를 고르는 화면이 나옴):

```bash
npx skills add Neoplanetz/research-notes-skill -g
```

파일은 `~/.agents/skills/research-notes`에 받고, Claude Code 쪽에는 링크를 겁니다. 이미 `research-notes`가 설치되어 있으면 그 자리를 덮어씁니다.

<details>
<summary>git으로 직접 받기</summary>

Claude Code:

```bash
git clone https://github.com/Neoplanetz/research-notes-skill.git ~/.claude/skills/research-notes
```

Codex:

```bash
git clone https://github.com/Neoplanetz/research-notes-skill.git ~/.agents/skills/research-notes
```

둘 다 쓸 때는 한 곳에만 받고 다른 곳에는 링크를 겁니다. 처음 받는다면:

```bash
git clone https://github.com/Neoplanetz/research-notes-skill.git ~/.agents/skills/research-notes
mkdir -p ~/.claude/skills && ln -s ~/.agents/skills/research-notes ~/.claude/skills/research-notes
```

Claude Code용으로 이미 받아 두었다면 Codex 쪽에 링크만 겁니다:

```bash
mkdir -p ~/.agents/skills && ln -s ~/.claude/skills/research-notes ~/.agents/skills/research-notes
```

</details>

설치한 뒤 Claude Code · Codex를 다시 열면 스킬이 잡힙니다.

### 업데이트

- git으로 받았으면: `git -C ~/.claude/skills/research-notes pull` (Codex는 `~/.agents/skills/research-notes`)
- skills CLI로 받았으면: `npx skills update`

## 사용

레포 폴더에서 Claude Code는 `/research-notes`, Codex는 `$research-notes`로 부르거나 그냥 요청합니다.

| 이렇게 말하면 | 일어나는 일 |
|---|---|
| `/research-notes` | 과제명부터 차례로 묻습니다. 전에 입력한 값이 있으면 선택지로 나옵니다 |
| `이 레포 커밋으로 올해 연구노트 만들어줘` | 현재 레포를 쓰고, 빠진 값만 묻습니다 |
| `2026.04~2026.12 연구노트 써줘. 이미 쓴 노트는 ~/Downloads/notes 에 있어` | 이미 쓴 칸은 건너뛰고, 그 노트와 겹치지 않게 주제를 나눕니다 |
| `레포 두 개 (URL 하나, 로컬 경로 하나)에서 내 커밋만으로 써줘` | 여러 레포에서 내 커밋만 모아 씁니다 |

## 작동 방식

1. **입력 받기**: 과제명 (과제번호 포함), 과제 약칭 (파일명 앞부분), 과제 책임자, 작성자, 노트 작성 기간, 이미 쓴 노트 폴더, 레포 (현재 레포 · URL · 로컬 경로 여러 개), 커밋 범위 · 대상. 입력값은 저장되어 다음 실행 때 선택지로 나옵니다.
2. **작성일 칸 계산**: 공휴일과 이미 쓴 노트를 반영합니다.
3. **커밋 모으기**
4. **계획표 확인**: 작성일 · 제목 · 다룰 내용 · 근거 커밋을 먼저 보여 주고, 확인을 받은 뒤에 씁니다.
5. **노트 작성 → PDF → 검사**: 요약 7줄, 4쪽 이하, 권장 길이를 검사합니다.
6. **복사용 텍스트 출력**

## 결과물

```
~/research-notes/<과제 약칭>/
  research-notes.json   입력값
  commits.txt           모은 커밋
  plan.md               확인한 계획표
  notes/*.md            노트 원본 (고쳐서 다시 렌더링 가능)
  notes/images/
  pdf/<약칭>_<YYMMDD>_<제목>.pdf
  summary.txt           복사용 텍스트
```

`summary.txt` 예:

```
[2026.02.13(금)] ABC_260213_표준_시뮬레이션_도커_구성_및_Clearpath_J100_적용.pdf
실험 제목
[ABC] 260213 표준 시뮬레이션 도커 구성 및 Clearpath J100 적용

실험내용요약
- 플랫폼 등록용 표준 시뮬레이션 도커 구성
- ...(7줄)
```

노트 한 건만 고친 뒤 다시 만들기 (`summary.txt`는 폴더의 모든 노트로 다시 만들어지고, 제목이 바뀌면 예전 PDF는 지워짐). Codex에 설치했으면 `~/.claude/skills`를 `~/.agents/skills`로 바꿉니다:

```bash
python3 ~/.claude/skills/research-notes/scripts/render.py ~/research-notes/ABC/notes/<파일>.md \
  --pdf-dir ~/research-notes/ABC/pdf --summary ~/research-notes/ABC/summary.txt
```

## 필요한 것

- Claude Code 또는 Codex
- Python 3.10 이상 (추가 패키지 없음. Pillow가 있으면 큰 그림을 줄여서 넣음)
- Chrome, Chromium, Edge 중 하나, 버전 131 이상 (PDF 인쇄용. 그보다 낮으면 쪽 번호 · 꼬리말이 빠짐)
- 한국어 글꼴 (Noto Sans CJK KR, 맑은 고딕, Apple SD Gothic Neo, 나눔고딕 중 하나)
- (Codex) 이미 쓴 PDF 노트를 읽으려면 `pdftotext` (poppler-utils)
- 운영체제: Linux에서 개발 · 확인. macOS · Windows는 브라우저 경로 찾기만 지원하며 확인하지 않음

## Codex에서 쓸 때

Codex는 명령을 샌드박스 안에서 실행합니다. 샌드박스 안에서는 PDF용 브라우저가 실행되지 않고, 작업 폴더 밖에 쓰거나 네트워크를 쓸 수 없어서 아래 단계에서 승인 창이 뜹니다.

- PDF 만들기 (`render.py`), 입력값 저장 (`config.py save`): 항상
- 커밋 모으기 (`collect.py`): 출력 폴더가 작업 폴더 밖이거나 레포가 URL일 때
- 계획표 · 노트 파일 쓰기: 출력 폴더가 작업 폴더 밖일 때

스크립트 승인 창에는 `python3 …/scripts/<이름>.py`로 시작하는 명령을 다시 묻지 않는 선택지가 함께 나옵니다. 이것을 고르면 그 스크립트는 다음부터 **어떤 인자로든**(파일을 쓰는 위치 포함) 묻지 않고 샌드박스 밖에서 실행됩니다. 레포 내용(커밋 메시지, README)을 믿을 수 있을 때만 고르세요.

출력 폴더를 처음부터 쓰기 허용으로 열면 계획표 · 노트 쓰기 승인 창이 없어집니다. 이때 폴더가 없으면 Codex의 모든 명령이 실패하므로 먼저 만듭니다:

```bash
mkdir -p ~/research-notes
codex --add-dir ~/research-notes
```

## 레포 구성

```
SKILL.md               에이전트가 읽는 스킬 지침
agents/openai.yaml     Codex 화면에 보이는 이름 · 설명
scripts/               아래 표의 스크립트 (+ 공용 모듈 common.py · mdlite.py)
assets/                PDF 양식 (HTML · CSS)
references/            작성 규칙, 예시 노트, 예시 그림
data/kr_holidays.json  2024~2030년 한국 공휴일
tools/gen_holidays.py  공휴일 표 갱신
tests/                 단위 테스트
```

| 스크립트 | 하는 일 |
|---|---|
| `scripts/slots.py` | 기간 → 작성일 칸 (`--existing`으로 이미 쓴 노트 반영) |
| `scripts/collect.py` | 레포 여러 개의 커밋 모으기 (`--list-authors`, `--author`) |
| `scripts/render.py` | 노트 `.md` → PDF, 검사, `summary.txt` |
| `scripts/config.py` | 입력값 저장 · 프로필 |

## 개발

테스트 (브라우저가 없으면 PDF 렌더링 테스트는 건너뜀):

```bash
python3 -m unittest discover -s tests -v
```

공휴일 표 갱신 (범위 밖 연도는 계획표에 "공휴일 확인 필요"로 표시됨):

```bash
pip install holidays
python3 tools/gen_holidays.py 2024 2035
```

## 라이선스

[MIT](LICENSE)
