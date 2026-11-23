import unittest
from datetime import date

import _path  # noqa: F401
from common import copy_title, fmt_date_ko, fmt_yymmdd, note_basename, safe_title


class CommonTest(unittest.TestCase):
    def test_dates(self):
        d = date(2026, 4, 10)
        self.assertEqual(fmt_date_ko(d), "2026.04.10(금)")
        self.assertEqual(fmt_date_ko(date(2026, 9, 23)), "2026.09.23(수)")
        self.assertEqual(fmt_yymmdd(d), "260410")

    def test_safe_title(self):
        self.assertEqual(safe_title('Base/Extend 서비스: "OTA" 검증'), "BaseExtend_서비스_OTA_검증")
        self.assertEqual(safe_title("  a   b  "), "a_b")
        self.assertEqual(safe_title("벽 · 문 · 바닥 구성"), "벽_문_바닥_구성")
        self.assertEqual(safe_title("도면 → SDF 월드 생성"), "도면_SDF_월드_생성")

    def test_names(self):
        d = date(2026, 4, 10)
        self.assertEqual(note_basename("ABC", d, "도커 구성 및 검증"), "ABC_260410_도커_구성_및_검증")
        self.assertEqual(copy_title("ABC", d, "도커 구성 및 검증"), "[ABC] 도커 구성 및 검증 ('26, 4/10)")

    def test_copy_title_drops_leading_zeros(self):
        self.assertEqual(copy_title("ABC", date(2026, 5, 8), "제목"), "[ABC] 제목 ('26, 5/8)")
        self.assertEqual(copy_title("ABC", date(2027, 12, 24), "제목"), "[ABC] 제목 ('27, 12/24)")


if __name__ == "__main__":
    unittest.main()
