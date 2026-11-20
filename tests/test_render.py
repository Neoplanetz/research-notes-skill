import io
import os
import shutil
import sys
from contextlib import redirect_stdout
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

import _path  # noqa: F401
import render
from mdlite import parse_note
from render import RenderError, check_note, find_browser, pdf_pages, render_note, write_summary

EXAMPLE_MD = _path.ROOT / "references" / "example-note.md"
EXAMPLE = EXAMPLE_MD.read_text(encoding="utf-8")


def browser_available() -> bool:
    try:
        find_browser()
        return True
    except RenderError:
        return False


def gray_png(path: Path, w: int, h: int) -> None:
    """Plain gray PNG without Pillow."""
    row = b"\x00" + b"\x90" * w
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * h)) + chunk(b"IEND", b""))
    path.write_bytes(data)


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def note(self, text: str, name="n.md", with_image=True) -> Path:
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        if with_image:
            (self.dir / "images").mkdir(exist_ok=True)
            shutil.copy(_path.ROOT / "references" / "images" / "example.jpg", self.dir / "images" / "example.jpg")
        return p

    def fake_browser(self, body: str) -> Path:
        """A 'browser' that runs `body` and exits without writing a PDF."""
        p = self.dir / "fake-browser.sh"
        p.write_text(f"#!/bin/sh\n{body}\nexit 133\n", encoding="utf-8")
        p.chmod(0o755)
        return p


class RenderUnitTest(_Base):
    def test_check_summary_must_be_seven(self):
        meta, body = parse_note(EXAMPLE)
        self.assertEqual(check_note(meta, body), ([], []))
        meta["summary"] = meta["summary"][:6]
        errors, _ = check_note(meta, body)
        self.assertTrue(errors)

    def test_check_warnings(self):
        meta, body = parse_note(EXAMPLE)
        meta["title"] = "가" * 38
        meta["summary"][0] = "나" * 46
        _, warnings = check_note(meta, body.replace("## 4. 다음 계획", "## 4. 기타"))
        self.assertEqual(len(warnings), 3)

    def test_summary_format(self):
        meta, _ = parse_note(EXAMPLE)
        out = self.dir / "summary.txt"
        write_summary([meta], out)
        lines = out.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[:3], [
            "[2026.02.13(금)] ABC_260213_표준_시뮬레이션_도커_구성_및_Clearpath_J100_적용.pdf",
            "실험 제목",
            "[ABC] 260213 표준 시뮬레이션 도커 구성 및 Clearpath J100 적용",
        ])
        self.assertEqual(lines[4], "실험내용요약")
        self.assertEqual(len([ln for ln in lines if ln.startswith("- ")]), 7)

    def test_missing_image(self):
        md = self.note(EXAMPLE.replace("images/example.jpg", "images/nope.jpg"))
        with self.assertRaises(RenderError) as cm:
            render_note(md, self.dir / "pdf", sys.executable)
        self.assertIn("nope.jpg", str(cm.exception))

    def test_summary_error_blocks_render(self):
        md = self.note(EXAMPLE.replace("- run.sh 단일 실행 Gazebo · Nav2 · RViz 동시 구동 확인\n", "", 1))
        with self.assertRaises(RenderError):
            render_note(md, self.dir / "pdf", sys.executable)

    def test_summary_covers_every_note_in_folder(self):
        self.note(EXAMPLE, name="a.md")
        second = EXAMPLE.replace("date: 2026-02-13", "date: 2026-02-27").replace("title: 표준", "title: 두번째")
        self.note(second, name="b.md")
        out = self.dir / "summary.txt"
        self.assertEqual(render.main([str(self.dir / "a.md"), "--check", "--summary", str(out)]), 0)
        text = out.read_text(encoding="utf-8")
        self.assertIn("[ABC] 260213", text)
        self.assertIn("[ABC] 260227 두번째", text)

    @unittest.skipUnless(render.HAS_PIL, "no Pillow")
    def test_shrink_keeps_transparent_background_white(self):
        from PIL import Image
        (self.dir / "img").mkdir()
        Image.new("RGBA", (2400, 200), (0, 0, 0, 0)).save(self.dir / "img" / "t.png")
        m = render._prepare_images(self.dir, ["img/t.png"], self.dir / "b")
        with Image.open(self.dir / "b" / m["img/t.png"]) as out:
            self.assertEqual(out.width, 2000)
            self.assertEqual(out.convert("RGB").getpixel((0, 0)), (255, 255, 255))

    @unittest.skipUnless(render.HAS_PIL, "no Pillow")
    def test_shrink_applies_exif_orientation(self):
        from PIL import Image
        (self.dir / "img").mkdir()
        im = Image.new("RGB", (3000, 2000), (200, 200, 200))
        exif = im.getexif()
        exif[0x0112] = 6
        im.save(self.dir / "img" / "p.jpg", exif=exif)
        m = render._prepare_images(self.dir, ["img/p.jpg"], self.dir / "b")
        with Image.open(self.dir / "b" / m["img/p.jpg"]) as out:
            self.assertGreater(out.height, out.width)

    def test_find_browser_accepts_command_name(self):
        self.assertTrue(find_browser("python3"))

    def test_style_breakout_in_title(self):
        meta, _ = parse_note(EXAMPLE)
        meta["title"] = "a</style><b>x"
        self.assertEqual(render.build_html(meta, "").count("</style>"), 1)

    def test_missing_note_file_is_a_fail_line(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = render.main([str(self.dir / "nope.md"), "--check"])
        self.assertEqual(code, 1)
        self.assertIn("FAIL", buf.getvalue())

    @unittest.skipUnless(render.HAS_PIL, "no Pillow")
    def test_corrupt_image_is_render_error(self):
        (self.dir / "img").mkdir()
        (self.dir / "img" / "bad.png").write_bytes(b"not an image")
        with self.assertRaises(RenderError):
            render._prepare_images(self.dir, ["img/bad.png"], self.dir / "b")

    def test_home_relative_image_path(self):
        old = os.environ.get("HOME")
        os.environ["HOME"] = str(self.dir)
        try:
            gray_png(self.dir / "h.png", 20, 10)
            m = render._prepare_images(self.dir / "notes", ["~/h.png"], self.dir / "b")
            self.assertTrue((self.dir / "b" / m["~/h.png"]).exists())
        finally:
            os.environ["HOME"] = old

    def test_find_browser_explicit_and_env(self):
        self.assertEqual(find_browser(sys.executable), sys.executable)
        with self.assertRaises(RenderError):
            find_browser("/nonexistent/chrome")

    @unittest.skipUnless(os.name == "posix", "shell-script fake browser")
    def test_sandbox_browser_failure_hints(self):
        fake = self.fake_browser("echo '...socket.cc:45] setsockopt: Operation not permitted (1)' >&2")
        with self.assertRaises(RenderError) as cm:
            render_note(self.note(EXAMPLE), self.dir / "pdf", str(fake))
        self.assertIn(render.SANDBOX_HINT, str(cm.exception))

    @unittest.skipUnless(os.name == "posix", "shell-script fake browser")
    def test_other_browser_failure_has_no_hint(self):
        fake = self.fake_browser("echo 'some other crash' >&2")
        with self.assertRaises(RenderError) as cm:
            render_note(self.note(EXAMPLE), self.dir / "pdf", str(fake))
        self.assertNotIn(render.SANDBOX_HINT, str(cm.exception))
        self.assertIn("PDF 생성 실패", str(cm.exception))


@unittest.skipUnless(browser_available(), "no Chrome-family browser")
class RenderBrowserTest(_Base):
    def test_render_example_with_odd_title(self):
        md = self.note(EXAMPLE.replace("title: 표준", 'title: "표준": 경로/'))
        r = render_note(md, self.dir / "pdf", find_browser())
        self.assertTrue(r["pdf"].name.startswith("ABC_260213_표준_경로"))
        self.assertTrue(r["pdf"].exists())
        self.assertLessEqual(r["pages"], 4)
        self.assertEqual(r["pages"], pdf_pages(r["pdf"]))
        self.assertGreaterEqual(r["pages"], 1)

    def test_long_tmpdir(self):
        deep = self.dir / ("t" * 60) / ("u" * 60)
        deep.mkdir(parents=True)
        old = os.environ.get("TMPDIR")
        os.environ["TMPDIR"] = str(deep)
        tempfile.tempdir = None
        try:
            r = render_note(self.note(EXAMPLE), self.dir / "pdf", find_browser())
            self.assertTrue(r["pdf"].exists())
        finally:
            if old is None:
                os.environ.pop("TMPDIR", None)
            else:
                os.environ["TMPDIR"] = old
            tempfile.tempdir = None

    def test_three_pages_warns(self):
        filler = "\n".join(f"- 항목 {i}" for i in range(60))
        r = render_note(self.note(EXAMPLE.replace("## 3. 결과", filler + "\n\n## 3. 결과")),
                        self.dir / "pdf", find_browser())
        self.assertEqual(r["pages"], 3)
        self.assertTrue(any("목표 1~2쪽" in w for w in r["warnings"]))

    def test_two_pages_no_page_warning(self):
        r = render_note(self.note(EXAMPLE), self.dir / "pdf", find_browser())
        self.assertFalse(any("쪽" in w for w in r["warnings"]))

    def test_rerender_with_new_title_removes_old_pdf(self):
        md = self.note(EXAMPLE)
        render_note(md, self.dir / "pdf", find_browser())
        md.write_text(EXAMPLE.replace("title: 표준", "title: 바뀐"), encoding="utf-8")
        r = render_note(md, self.dir / "pdf", find_browser())
        self.assertEqual([p.name for p in (self.dir / "pdf").glob("ABC_260213_*.pdf")], [r["pdf"].name])

    def test_too_long(self):
        filler = "\n".join(f"- 항목 {i}" for i in range(400))
        md = self.note(EXAMPLE.replace("## 3. 결과", filler + "\n\n## 3. 결과"))
        with self.assertRaises(RenderError) as cm:
            render_note(md, self.dir / "pdf", find_browser())
        self.assertIn("4쪽", str(cm.exception))

    def test_large_image_without_pillow(self):
        old = render.HAS_PIL
        render.HAS_PIL = False
        try:
            md = self.note(EXAMPLE.replace("images/example.jpg", "images/big.png"), with_image=False)
            (self.dir / "images").mkdir(exist_ok=True)
            gray_png(self.dir / "images" / "big.png", 6000, 2400)
            r = render_note(md, self.dir / "pdf", find_browser())
            self.assertLessEqual(r["pages"], 4)
        finally:
            render.HAS_PIL = old


if __name__ == "__main__":
    unittest.main()
