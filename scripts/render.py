"""Render research notes (.md) to A4 PDF with a headless Chrome-family browser.

usage: render.py NOTE.md... --pdf-dir DIR [--summary FILE] [--browser PATH] [--check]
  --check   only validate the notes (no PDF)
Exit code 1 when any note fails (summary not 7 lines, missing image, over 4 pages, ...).
"""
import argparse
import errno
import html
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from string import Template

from common import copy_title, fmt_date_ko, note_basename
from mdlite import NoteError, body_to_html, parse_note

try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

ROOT = Path(__file__).resolve().parent.parent
MAX_PAGES = 4
TITLE_WARN = 37
SUMMARY_WARN = 45
SECTIONS = ("1. 목적", "2. 수행 내용", "3. 결과", "4. 다음 계획")
IMAGE_MAX_W = 2000
PAGE_TARGET = 2
SANDBOX_HINT = "샌드박스 안에서 실행했다면 샌드박스가 막은 것. render.py 를 샌드박스 밖에서 다시 실행 (sudo 아님)"
# How a sandbox that blocks socket calls (Codex on Linux) kills Chrome, e.g.
# "socket.cc:45] setsockopt: Operation not permitted" or "shutdown: Operation not permitted".
_SANDBOX_STDERR = re.compile(r"(sock|shutdown)[^\n]*Operation not permitted")
_BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
             "microsoft-edge", "msedge", "chrome")
_APP_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "~/Applications/Chromium.app/Contents/MacOS/Chromium",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


class RenderError(Exception):
    pass


def _as_program(name: str) -> str | None:
    """A path to an existing file, or a command name found on PATH."""
    if Path(name).expanduser().is_file():
        return str(Path(name).expanduser())
    return shutil.which(name)


def find_browser(explicit: str | None = None) -> str:
    if explicit:
        found = _as_program(explicit)
        if found:
            return found
        raise RenderError(f"브라우저 없음: {explicit}")
    env = os.environ.get("RESEARCH_NOTES_BROWSER")
    if env and _as_program(env):
        return _as_program(env)
    for name in _BROWSERS:
        found = shutil.which(name)
        if found:
            return found
    for p in _APP_PATHS:
        if Path(p).expanduser().is_file():
            return str(Path(p).expanduser())
    raise RenderError("Chrome / Chromium / Edge 를 찾지 못함. --browser 또는 RESEARCH_NOTES_BROWSER 로 경로 지정")


def check_note(meta: dict, body: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    if len(meta["summary"]) != 7:
        errors.append(f"실험내용요약 {len(meta['summary'])}줄 (7줄이어야 함)")
    if len(meta["title"]) > TITLE_WARN:
        warnings.append(f"제목 {len(meta['title'])}자 (권장 {TITLE_WARN}자 이하)")
    for i, line in enumerate(meta["summary"], 1):
        if len(line) > SUMMARY_WARN:
            warnings.append(f"요약 {i}번째 줄 {len(line)}자 (권장 {SUMMARY_WARN}자 안팎)")
    heads = re.findall(r"^##\s+(.+?)\s*$", body, re.M)
    for s in SECTIONS:
        if s not in heads:
            warnings.append(f"소제목 '{s}' 없음")
    return errors, warnings


def _css_string(s: str) -> str:
    # "<" as a CSS escape so a title cannot close the <style> block
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("<", "\\3C ")


def _flatten(im):
    """Shrink to IMAGE_MAX_W and put transparency on white (JPEG has no alpha)."""
    if im.width > IMAGE_MAX_W:
        im = im.resize((IMAGE_MAX_W, round(im.height * IMAGE_MAX_W / im.width)), Image.LANCZOS)
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return im.convert("RGB")


def _prepare_images(md_dir: Path, srcs: list[str], build: Path) -> dict[str, str]:
    """Copy (and shrink when Pillow is available) each figure into build/images."""
    mapping = {}
    (build / "images").mkdir(parents=True, exist_ok=True)
    for i, src in enumerate(srcs, 1):
        path = Path(src).expanduser()
        if not path.is_absolute():
            path = md_dir / path
        if not path.is_file():
            raise RenderError(f"그림 없음: {src}")
        dest = build / "images" / f"{i:02d}_{path.name}"
        if HAS_PIL and path.suffix.lower() in (".png", ".jpg", ".jpeg"):
            try:
                with Image.open(path) as src_im:
                    rotated = src_im.getexif().get(0x0112, 1) != 1
                    if src_im.width > IMAGE_MAX_W or rotated:
                        dest = dest.with_suffix(".jpg")
                        _flatten(ImageOps.exif_transpose(src_im)).save(dest, quality=85)
                    else:
                        shutil.copy(path, dest)
            except (OSError, ValueError) as e:
                raise RenderError(f"그림을 읽을 수 없음: {src} ({e})") from None
        else:
            shutil.copy(path, dest)
        mapping[src] = f"images/{dest.name}"
    return mapping


def build_html(meta: dict, body_html: str) -> str:
    tpl = Template((ROOT / "assets" / "note.html").read_text(encoding="utf-8"))
    esc = html.escape
    return tpl.substitute(
        css=(ROOT / "assets" / "note.css").read_text(encoding="utf-8"),
        doc_title=esc(note_basename(meta["prefix"], meta["date"], meta["title"])),
        footer_title=_css_string(meta["title"]),
        project=esc(meta["project"]), title=esc(meta["title"]), pi=esc(meta["pi"]),
        date_ko=fmt_date_ko(meta["date"]), author=esc(meta["author"]), body=body_html,
    )


def pdf_pages(pdf: Path) -> int:
    n = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", Path(pdf).read_bytes()))
    if n == 0 and shutil.which("pdfinfo"):
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout
        m = re.search(r"^Pages:\s+(\d+)", out, re.M)
        n = int(m[1]) if m else 0
    return n


def _print_pdf(browser: str, html_path: Path, pdf: Path) -> None:
    pdf.parent.mkdir(parents=True, exist_ok=True)
    if pdf.exists():
        pdf.unlink()
    # Short temp dir: Chrome's socket paths break under a long TMPDIR, and its leftover
    # url_fetcher dirs land inside this one and go away with it.
    short = "/tmp" if os.name == "posix" and os.path.isdir("/tmp") else None
    with tempfile.TemporaryDirectory(dir=short) as profile:
        cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--disable-extensions",
               "--no-pdf-header-footer", f"--user-data-dir={profile}", f"--print-to-pdf={pdf}",
               html_path.resolve().as_uri()]
        if platform.system() == "Linux" and hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.insert(1, "--no-sandbox")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                               env=dict(os.environ, TMPDIR=profile))
        except subprocess.TimeoutExpired:
            raise RenderError(f"브라우저 시간 초과: {html_path.name}") from None
    if not pdf.exists():
        hint = f" — {SANDBOX_HINT}" if _SANDBOX_STDERR.search(r.stderr) else ""
        raise RenderError(f"PDF 생성 실패 ({r.returncode}): {r.stderr.strip()[-300:]}{hint}")


def _os_error(e: OSError) -> str:
    """A sandbox makes paths outside its workspace read-only."""
    return f"{e} — {SANDBOX_HINT}" if e.errno == errno.EROFS else str(e)


def render_note(md: Path, pdf_dir: Path, browser: str) -> dict:
    md = Path(md)
    try:
        meta, body = parse_note(md.read_text(encoding="utf-8-sig"))
    except (NoteError, OSError) as e:
        raise RenderError(f"{md.name}: {e}") from None
    errors, warnings = check_note(meta, body)
    if errors:
        raise RenderError(f"{md.name}: " + "; ".join(errors))
    body_html, srcs = body_to_html(body)
    build = md.parent / ".build"
    mapping = _prepare_images(md.parent, srcs, build)
    for src, new in mapping.items():
        body_html = body_html.replace(f'src="{html.escape(src, quote=True)}"', f'src="{new}"')
    name = note_basename(meta["prefix"], meta["date"], meta["title"])
    html_path = build / f"{name}.html"
    html_path.write_text(build_html(meta, body_html), encoding="utf-8")
    pdf = Path(pdf_dir) / f"{name}.pdf"
    for old in Path(pdf_dir).glob(f"{meta['prefix']}_{meta['date']:%y%m%d}_*.pdf"):
        if old.name != pdf.name:
            old.unlink()  # same note rendered earlier under another title
    _print_pdf(browser, html_path, pdf)
    pages = pdf_pages(pdf)
    if pages > MAX_PAGES:
        raise RenderError(f"{md.name}: {pages}쪽 (최대 {MAX_PAGES}쪽), 내용을 줄여 다시 렌더링")
    if pages > PAGE_TARGET:
        warnings.append(f"{pages}쪽 (목표 1~{PAGE_TARGET}쪽)")
    return {"pdf": pdf, "pages": pages, "warnings": warnings, "meta": meta}


def write_summary(notes: list[dict], out: Path) -> None:
    blocks = []
    for m in sorted(notes, key=lambda m: m["date"]):
        name = note_basename(m["prefix"], m["date"], m["title"])
        blocks.append("\n".join([
            f"[{fmt_date_ko(m['date'])}] {name}.pdf",
            "실험 제목",
            copy_title(m["prefix"], m["date"], m["title"]),
            "",
            "실험내용요약",
            *[f"- {s}" for s in m["summary"]],
        ]))
    Path(out).write_text("\n\n\n".join(blocks) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("notes", nargs="+", type=Path)
    ap.add_argument("--pdf-dir", type=Path)
    ap.add_argument("--summary", type=Path)
    ap.add_argument("--browser")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if not a.check and not a.pdf_dir:
        ap.error("--pdf-dir 가 필요합니다 (검사만 하려면 --check)")
    browser = None
    if not a.check:
        try:
            browser = find_browser(a.browser)
        except RenderError as e:
            print(f"FAIL {e}")
            return 1
    failed = 0
    for md in a.notes:
        try:
            if a.check:
                meta, body = parse_note(md.read_text(encoding="utf-8-sig"))
                errors, warnings = check_note(meta, body)
                if errors:
                    raise RenderError(f"{md.name}: " + "; ".join(errors))
                print(f"OK   {md.name}")
            else:
                r = render_note(md, a.pdf_dir, browser)
                meta, warnings = r["meta"], r["warnings"]
                print(f"OK   {r['pdf'].name} {r['pages']}쪽")
            for w in warnings:
                print(f"WARN {md.name}: {w}")
        except (RenderError, NoteError, OSError) as e:
            failed += 1
            print(f"FAIL {md.name}: {_os_error(e)}" if isinstance(e, OSError) else f"FAIL {e}")
    if a.summary:
        metas = []
        for folder in sorted({md.resolve().parent for md in a.notes}):
            for md in sorted(folder.glob("*.md")):
                try:
                    meta, body = parse_note(md.read_text(encoding="utf-8-sig"))
                except (NoteError, OSError) as e:
                    print(f"WARN summary 제외 {md.name}: {e}")
                    continue
                if check_note(meta, body)[0]:
                    print(f"WARN summary 제외 {md.name}: 검사 오류")
                    continue
                metas.append(meta)
        try:
            write_summary(metas, a.summary)
        except OSError as e:
            print(f"FAIL {a.summary}: {_os_error(e)}")
            return 1
        print(f"{a.summary} ({len(metas)}건)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
