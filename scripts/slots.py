"""Note dates for a period: the 2nd and 4th Friday of each month, moved back to the
previous weekday when they fall on a public holiday.

usage: slots.py --period 2026.04~2026.12 [--existing DIR --prefix ABC] [--json]
"""
import argparse
import calendar
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from common import fmt_date_ko

HOLIDAYS = Path(__file__).resolve().parent.parent / "data" / "kr_holidays.json"
_PERIOD = re.compile(r"^\s*(\d{4})[.\-/](\d{1,2})\s*[~\-]\s*(\d{4})[.\-/](\d{1,2})\s*$")


def parse_period(text: str) -> tuple[date, date]:
    m = _PERIOD.match(text)
    if not m:
        raise ValueError(f"기간 형식은 YYYY.MM~YYYY.MM 입니다: {text!r}")
    y1, m1, y2, m2 = map(int, m.groups())
    if not (1 <= m1 <= 12 and 1 <= m2 <= 12) or (y1, m1) > (y2, m2):
        raise ValueError(f"기간이 올바르지 않습니다: {text!r}")
    return date(y1, m1, 1), date(y2, m2, calendar.monthrange(y2, m2)[1])


def load_holidays(path: Path | None = None) -> tuple[dict[date, str], set[int]]:
    data = json.loads(Path(path or HOLIDAYS).read_text(encoding="utf-8"))
    return {date.fromisoformat(k): v for k, v in data["dates"].items()}, set(data["years"])


def _fridays(year: int, month: int) -> list[date]:
    d = date(year, month, 1)
    d += timedelta(days=(4 - d.weekday()) % 7)
    return [d + timedelta(weeks=i) for i in range(5) if (d + timedelta(weeks=i)).month == month]


def _months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def build_slots(start: date, end: date, holidays: dict[date, str], years: set[int]) -> list[dict]:
    slots = []
    for y, m in _months(start, end):
        fr = _fridays(y, m)
        for order, nominal in ((2, fr[1]), (4, fr[3])):
            d = nominal
            while d.weekday() >= 5 or d in holidays:
                d -= timedelta(days=1)
            slots.append({
                "month": f"{y:04d}-{m:02d}", "order": order, "nominal": nominal, "date": d,
                "shift_reason": holidays.get(nominal), "holiday_unknown": y not in years,
                "status": "todo",
            })
    return slots


NOTE_EXT = (".pdf", ".md", ".docx", ".hwp", ".hwpx")


def scan_existing(folder: Path, prefix: str) -> tuple[list[date], list[str]]:
    """Dates of notes already written in folder (and one level of subfolders).
    Recognizes PREFIX_YYMMDD_title, PREFIX-YYMMDD-title, PREFIX_YYMMDD and [PREFIX] YYMMDD title.
    Returns (dates, note-like files that were not recognized)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"이미 쓴 노트 폴더 없음: {folder}")
    pat = re.compile(rf"^\[?{re.escape(prefix)}\]?[ _-]+(\d{{2}})(\d{{2}})(\d{{2}})(?:[ _-].*)?$", re.I)
    files = [p for p in folder.iterdir() if p.is_file()]
    files += [p for d in folder.iterdir() if d.is_dir() and not d.name.startswith(".") for p in d.iterdir() if p.is_file()]
    found, unknown = set(), []
    for p in sorted(files):
        if p.suffix.lower() not in NOTE_EXT:
            continue
        m = pat.match(p.stem)
        if not m and p.suffix.lower() == ".md" and not p.stem.upper().startswith((prefix.upper(), "[")):
            continue  # plan.md, README.md: working files, not notes
        try:
            found.add(date(2000 + int(m[1]), int(m[2]), int(m[3])))
        except (TypeError, ValueError):
            unknown.append(str(p))
    return sorted(found), unknown


def existing_dates(folder: Path, prefix: str) -> list[date]:
    return scan_existing(folder, prefix)[0]


def mark_existing(slots: list[dict], dates: list[date]) -> list[str]:
    """Mark slots already covered by existing notes. Returns dates that matched no slot."""
    left = []
    by_month: dict[str, list[date]] = {}
    for d in sorted(dates):
        by_month.setdefault(f"{d:%Y-%m}", []).append(d)
    for month, ds in by_month.items():
        cells = [s for s in slots if s["month"] == month]
        if not cells:
            left += [f"{fmt_date_ko(d)}: 기간 밖" for d in ds]
            continue
        rest = []
        for d in ds:
            hit = next((c for c in cells if c["status"] == "todo" and d in (c["date"], c["nominal"])), None)
            if hit:
                hit["status"] = "written"
            else:
                rest.append(d)
        for d in rest:
            hit = next((c for c in cells if c["status"] == "todo"), None)
            if hit:
                hit["status"] = "written"
            else:
                left.append(f"{fmt_date_ko(d)}: 그 달 칸이 이미 다 참")
    return left


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--period", required=True)
    ap.add_argument("--existing")
    ap.add_argument("--prefix")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    slots = build_slots(*parse_period(a.period), *load_holidays())
    left, unknown = [], []
    if a.existing:
        if not a.prefix:
            ap.error("--existing 에는 --prefix 가 필요합니다")
        try:
            dates, unknown = scan_existing(Path(a.existing).expanduser(), a.prefix)
        except ValueError as e:
            print(f"ERROR {e}", file=sys.stderr)
            return 1
        left = mark_existing(slots, dates)
    if a.json:
        out = [{**s, "nominal": s["nominal"].isoformat(), "date": s["date"].isoformat()} for s in slots]
        print(json.dumps({"slots": out, "unmatched": left, "unrecognized": unknown}, ensure_ascii=False, indent=1))
        return 0
    for s in slots:
        note = ""
        if s["date"] != s["nominal"]:
            note = f"← {fmt_date_ko(s['nominal'])} {s['shift_reason'] or '주말'}"
        if s["holiday_unknown"]:
            note += " (공휴일 확인 필요)"
        print(f"{fmt_date_ko(s['date'])}  {'작성됨' if s['status'] == 'written' else '작성할 칸'}  {note}".rstrip())
    todo = sum(s["status"] == "todo" for s in slots)
    print(f"\n전체 {len(slots)}칸, 작성할 칸 {todo}")
    for line in left:
        print("반영 안 된 기존 노트:", line)
    for f in unknown:
        print("날짜를 못 읽은 파일 (직접 확인):", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
