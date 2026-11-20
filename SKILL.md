---
name: research-notes
description: Use when writing 과제 연구노트 (Korean R&D project research notes) from git repository commits — e.g. "연구노트 만들어줘", notes due on the 2nd and 4th Friday of each month for a project period, or the 실험 제목 / 실험내용요약 text pasted into an institute research-note system.
---

# research-notes

Turns a project's commits into research notes: two per month (2nd and 4th Friday), one A4 PDF each (max 4 pages), plus copy-paste text (실험 제목 + 7-line 실험내용요약).

**Talk to the user in the language they write in (Korean if unclear).** Notes, `plan.md` and `summary.txt` are always in Korean. `SKILL_DIR` below is the folder holding this file; run scripts as `python3 SKILL_DIR/scripts/<name>.py` with absolute paths.

## Hard rules

- PDFs come only from `render.py`. Never hand-write HTML or print PDFs yourself: file names, footer, page and summary checks live there.
- Read-only. Never run tests, simulators, apps or builds, and never take new screenshots. Facts and numbers come from commits, README and docs only. Images come from files already in the repos or from the user.
- No note is written before the user confirms `plan.md`: ask and wait for the answer (end your turn if you have no question tool); no answer is not a confirmation. The only exception is the non-interactive run described after Steps.
- Every line follows `references/writing-rules.md`. Read it before writing the first note, and copy the structure of `references/example-note.md`.

## Steps

1. **Inputs.** Skip anything the request already gives. Saved values: `config.py list`.
   - If saved profiles exist, offer them as choices with your question tool (Claude Code: up to 4 questions per call). Otherwise ask in one plain message.
   - 과제명 (with 과제번호), 과제 약칭 (file prefix, e.g. `ABC`), 과제 책임자 (`이름 직책`), 작성자.
   - 노트 작성 기간 `YYYY.MM~YYYY.MM` · 이미 쓴 노트 폴더 (없음 / path) · 레포 (현재 레포 / URLs or paths, several allowed) · 커밋 범위 (노트 기간과 같음 / 올해 전체 / 직접) · 커밋 대상 (전체 / 내 커밋만 — offer emails from `collect.py --list-authors`; / 특정 레포·구현 내용).
   - Output folder: default `~/research-notes/<약칭>/`. Save with `config.py save OUT --json '<inputs>'`, keys: `project prefix pi author period existing repos commit_since commit_until authors out`.
2. **Slots.** `slots.py --period P [--existing DIR --prefix 약칭] --json`. Holiday-shifted dates and "공휴일 확인 필요" go into the plan. Read every existing note (PDF/MD; a PDF you cannot open: `pdftotext -layout FILE -`, or ask the user for its text) and list the topics it covered. For each `unrecognized` file, find its date inside the note and mark that slot as already written in the plan.
3. **Commits.** `collect.py --since … --until … [--author …] --out OUT/commits.txt REPO...`. On `RepoError` for a private URL, ask the user for a local clone path. Open README/docs or `git show --stat <hash>` only for commits you will use.
4. **Plan.** Split the work into exactly as many topics as `todo` slots, in work order, following "주제 나누기" in the writing rules. Write `OUT/plan.md` as a table: 작성일 · 제목 · 다룰 내용 한 줄 · 근거(레포: 짧은 해시들) · 비고(당긴 날짜, 그림 후보). Show it and **wait for confirmation**; apply edits. If the evidence cannot fill every slot, say how many are short and ask for more repos or scope instead of padding.
5. **Write.** One `OUT/notes/<약칭>_<YYMMDD>_<제목>.md` per slot in the example format (front matter `project prefix title pi date author summary`). Copy images into `OUT/notes/images/`; look at each image before captioning it.
6. **Render.** `render.py OUT/notes/*.md --check`, fix every FAIL and WARN you can, then `render.py OUT/notes/*.md --pdf-dir OUT/pdf --summary OUT/summary.txt` (`--summary` always covers every note in the folder). A `N쪽 (목표 1~2쪽)` WARN → trim the least important bullets or a figure; over 4 pages is a FAIL. Re-render only the files you changed.
7. **Deliver.** Paste `summary.txt` verbatim inside one fenced code block (so it copies exactly), then the PDF folder path and any WARN left.

Without the question tool, ask in a plain message and wait for the answer. Only in a run the user started as non-interactive (e.g. `claude -p`, `codex exec`) may notes be written without confirmation, and the reply must say the plan was not confirmed.

## Sandboxed shells (e.g. Codex)

The sandbox blocks the browser, the network and writes outside the workspace. Ask to run these outside it from the first call, with a prefix rule (`python3` + the script's absolute path) so one approval covers later calls:
- `render.py` always (not `--check`). A FAIL that mentions 샌드박스 means rerun outside; never make the PDF another way.
- `config.py save`, and `collect.py` when OUT is outside the workspace or a repo is a URL. Writing notes into such an OUT needs approval too.

Inside the sandbox: `config.py list`, `slots.py`, `render.py --check`, `collect.py --list-authors` on local repos.
