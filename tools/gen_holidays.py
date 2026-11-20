"""Regenerate data/kr_holidays.json (development only).

usage: pip install holidays && python3 tools/gen_holidays.py [FIRST_YEAR LAST_YEAR]
"""
import json
import sys
from pathlib import Path

import holidays

first, last = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) == 3 else (2024, 2030)
kr = holidays.KR(years=range(first, last + 1), language="ko")
data = {
    "source": f"python-holidays {holidays.__version__} KR",
    "years": list(range(first, last + 1)),
    "dates": {d.isoformat(): name for d, name in sorted(kr.items())},
}
out = Path(__file__).resolve().parent.parent / "data" / "kr_holidays.json"
out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(out, len(data["dates"]), "dates")
