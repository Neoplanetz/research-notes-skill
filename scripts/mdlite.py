"""The small Markdown subset research notes are written in.

Front matter (between --- lines): project, prefix, title, pi, date (YYYY-MM-DD), author,
summary (a list of "- " lines). Body: ## / ### headings, "- " bullets (2-space indent for a
second level), ``` code blocks (text after " # " is a comment), a line holding only
![caption](path) for a figure, any other line as a paragraph, `inline code`.
"""
import html
import re
from datetime import date

REQUIRED = ("project", "prefix", "title", "pi", "date", "author", "summary")
_FIG = re.compile(r"^!\[(.*)\]\((.+)\)\s*$")
_BULLET = re.compile(r"^( *)- (.*)$")


class NoteError(Exception):
    pass


def parse_note(text: str) -> tuple[dict, str]:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        raise NoteError("앞머리(---) 없음")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise NoteError("앞머리 끝(---) 없음") from None
    meta: dict = {}
    key = None
    for ln in lines[1:end]:
        m = re.match(r"^\s*- (.*)$", ln)
        if m and key == "summary":
            meta["summary"].append(m[1].strip())
            continue
        m = re.match(r"^(\w+):\s*(.*)$", ln)
        if m:
            key = m[1]
            meta[key] = [] if key == "summary" else m[2].strip()
    for k in REQUIRED:
        if not meta.get(k):
            raise NoteError(f"{k} 없음")
    try:
        meta["date"] = date.fromisoformat(meta["date"])
    except ValueError:
        raise NoteError(f"date 형식 오류: {meta['date']!r} (YYYY-MM-DD)") from None
    return meta, "\n".join(lines[end + 1:])


def _inline(text: str) -> str:
    parts = re.split(r"`([^`]+)`", text)
    return "".join(f"<code>{html.escape(p)}</code>" if i % 2 else html.escape(p) for i, p in enumerate(parts))


def _code_line(line: str) -> str:
    head, sep, tail = line.partition(" # ")
    if not sep:
        return html.escape(line)
    return f'{html.escape(head)} <span class="c"># {html.escape(tail)}</span>'


def body_to_html(md: str) -> tuple[str, list[str]]:
    out: list[str] = []
    images: list[str] = []
    depth = 0  # open <ul> levels
    in_code = False
    code: list[str] = []

    def close_lists(to=0):
        nonlocal depth
        while depth > to:
            out.append("</li></ul>")
            depth -= 1

    for line in md.splitlines():
        if in_code:
            if line.strip().startswith("```"):
                out.append("<pre>" + "\n".join(code) + "</pre>")
                in_code, code = False, []
            else:
                code.append(_code_line(line))
            continue
        if line.strip().startswith("```"):
            close_lists()
            in_code = True
            continue
        b = _BULLET.match(line)
        if b:
            level = 1 if len(b[1]) < 2 else 2
            if level > depth:
                while depth < level:
                    out.append("<ul><li>")
                    depth += 1
            else:
                close_lists(level)
                out.append("</li><li>")
            out.append(_inline(b[2]))
            continue
        close_lists()
        s = line.strip()
        if not s:
            continue
        if s.startswith("### "):
            out.append(f"<h3>{_inline(s[4:])}</h3>")
        elif s.startswith("## "):
            out.append(f"<h2>{_inline(s[3:])}</h2>")
        elif _FIG.match(s):
            cap, src = _FIG.match(s).groups()
            images.append(src)
            out.append(f'<figure><img src="{html.escape(src, quote=True)}" alt="{html.escape(cap, quote=True)}">'
                       f"<figcaption>[그림 {len(images)}] {_inline(cap)}</figcaption></figure>")
        else:
            out.append(f"<p>{_inline(s)}</p>")
    if in_code:
        out.append("<pre>" + "\n".join(code) + "</pre>")
    close_lists()
    return "\n".join(out).replace("<li></li>", ""), images
