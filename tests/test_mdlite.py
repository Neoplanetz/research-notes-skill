import unittest
from datetime import date

import _path  # noqa: F401
from mdlite import NoteError, body_to_html, parse_note

EXAMPLE = """---
project: ABC 과제 (A0000000)
prefix: ABC
title: 시뮬레이션 도커 구성
pi: 홍길동 책임
date: 2026-02-13
author: 홍길동
summary:
- 줄 1
- 줄 2
- 줄 3
- 줄 4
- 줄 5
- 줄 6
- 줄 7
---

## 1. 목적
- 도커 구성
"""


class MdliteTest(unittest.TestCase):
    def test_parse_note(self):
        meta, body = parse_note(EXAMPLE)
        self.assertEqual(meta["date"], date(2026, 2, 13))
        self.assertEqual(meta["prefix"], "ABC")
        self.assertEqual(meta["summary"], [f"줄 {i}" for i in range(1, 8)])
        self.assertTrue(body.lstrip().startswith("## 1. 목적"))

    def test_missing_key(self):
        with self.assertRaises(NoteError) as cm:
            parse_note("---\ntitle: x\n---\n")
        self.assertIn("없음", str(cm.exception))

    def test_no_front_matter(self):
        with self.assertRaises(NoteError):
            parse_note("## 1. 목적\n- a\n")

    def test_body_to_html(self):
        md = ("## 1. 목적\n- a <b>\n  - c\n- d `run.sh`\n\n"
              "### 2.1 구성\n\n![화면](images/f.jpg)\n\n```\n./run.sh   # 실행\n<tag>\n```\n\n문단 줄\n")
        html, imgs = body_to_html(md)
        self.assertIn("<h2>1. 목적</h2>", html)
        self.assertIn("<h3>2.1 구성</h3>", html)
        self.assertIn("a &lt;b&gt;", html)
        self.assertEqual(html.count("<ul>"), 2)
        self.assertIn("<code>run.sh</code>", html)
        self.assertIn("[그림 1] 화면", html)
        self.assertIn('<img src="images/f.jpg"', html)
        self.assertIn('./run.sh   <span class="c"># 실행</span>', html)
        self.assertIn("&lt;tag&gt;", html)
        self.assertIn("<p>문단 줄</p>", html)
        self.assertEqual(imgs, ["images/f.jpg"])

    def test_figures_numbered(self):
        html, imgs = body_to_html("![가](a.png)\n\n![나](b.png)\n")
        self.assertIn("[그림 2] 나", html)
        self.assertEqual(imgs, ["a.png", "b.png"])


if __name__ == "__main__":
    unittest.main()
