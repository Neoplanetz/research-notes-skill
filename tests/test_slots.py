import tempfile
import unittest
from datetime import date
from pathlib import Path

import _path  # noqa: F401
from slots import build_slots, existing_dates, load_holidays, mark_existing, parse_period, scan_existing


def slots_for(period):
    return build_slots(*parse_period(period), *load_holidays())


class SlotsTest(unittest.TestCase):
    def test_parse_period_forms(self):
        for text in ("2026.04~2026.12", "2026-04~2026-12", "2026.04-2026.12", "2026.04 ~ 2026.12"):
            self.assertEqual(parse_period(text), (date(2026, 4, 1), date(2026, 12, 31)))

    def test_bad_period(self):
        with self.assertRaises(ValueError):
            parse_period("2026년 4월부터")
        with self.assertRaises(ValueError):
            parse_period("2026.12~2026.04")

    def test_2026_full_year(self):
        s = slots_for("2026.01~2026.12")
        self.assertEqual(len(s), 24)
        by = {x["nominal"]: x for x in s}
        self.assertEqual(by[date(2026, 9, 25)]["date"], date(2026, 9, 23))   # 추석 + 추석 전날
        self.assertEqual(by[date(2026, 9, 25)]["shift_reason"], "추석")
        self.assertEqual(by[date(2026, 10, 9)]["date"], date(2026, 10, 8))   # 한글날
        self.assertEqual(by[date(2026, 12, 25)]["date"], date(2026, 12, 24))  # 기독탄신일
        self.assertEqual(by[date(2026, 4, 10)]["date"], date(2026, 4, 10))
        self.assertIsNone(by[date(2026, 4, 10)]["shift_reason"])
        self.assertEqual([x["order"] for x in s[:2]], [2, 4])
        self.assertTrue(all(x["status"] == "todo" and not x["holiday_unknown"] for x in s))

    def test_cross_year_and_unknown(self):
        s = slots_for("2030.11~2031.02")
        self.assertEqual(len(s), 8)
        self.assertTrue(all(x["holiday_unknown"] for x in s if x["date"].year == 2031))
        self.assertFalse(any(x["holiday_unknown"] for x in s if x["date"].year == 2030))

    def test_existing_six_notes(self):
        names = ["ABC_260112_a.pdf", "ABC_260123_b.pdf", "ABC_260210_c.pdf",
                 "ABC_260225_d.pdf", "ABC_260317_e.pdf", "ABC_260327_f.pdf",
                 "XYZ_260410_other.pdf", "notes.txt", "ABC_251226_old.pdf"]
        with tempfile.TemporaryDirectory() as tmp:
            for n in names:
                (Path(tmp) / n).touch()
            found = existing_dates(Path(tmp), "ABC")
        s = slots_for("2026.01~2026.12")
        left = mark_existing(s, found)
        self.assertEqual(sum(x["status"] == "written" for x in s), 6)
        self.assertEqual([x["nominal"] for x in s if x["status"] == "todo"][0], date(2026, 4, 10))
        self.assertEqual(len(left), 1)   # 2025-12-26 is outside the period

    def test_existing_name_forms_and_subfolders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pdf").mkdir()
            for n in ("[ABC] 260313 도커 구성.pdf", "ABC-260327-서비스.pdf", "ABC_260410.pdf",
                      "pdf/ABC_260424_x.pdf", "random.pdf", "ABC_9999xx_bad.pdf", "plan.md"):
                (root / n).touch()
            dates, unknown = scan_existing(root, "ABC")
        self.assertEqual(dates, [date(2026, 3, 13), date(2026, 3, 27), date(2026, 4, 10), date(2026, 4, 24)])
        self.assertEqual(sorted(Path(u).name for u in unknown), ["ABC_9999xx_bad.pdf", "random.pdf"])

    def test_existing_missing_folder(self):
        with self.assertRaises(ValueError):
            scan_existing(Path("/nonexistent/notes"), "ABC")

    def test_existing_only_fourth(self):
        s = slots_for("2026.04~2026.04")
        self.assertEqual(mark_existing(s, [date(2026, 4, 24)]), [])
        self.assertEqual([x["status"] for x in s], ["todo", "written"])

    def test_existing_too_many_in_month(self):
        s = slots_for("2026.04~2026.04")
        left = mark_existing(s, [date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 3)])
        self.assertEqual([x["status"] for x in s], ["written", "written"])
        self.assertEqual(len(left), 1)


if __name__ == "__main__":
    unittest.main()
