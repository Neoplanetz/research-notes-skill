"""Date, file name and title formats shared by the research-notes scripts."""
import re
from datetime import date

KO_WEEKDAYS = "월화수목금토일"

_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_SEPARATORS = re.compile("[·•・→←↔⇒]")


def fmt_date_ko(d: date) -> str:
    """2026.04.10(금)"""
    return f"{d:%Y.%m.%d}({KO_WEEKDAYS[d.weekday()]})"


def fmt_yymmdd(d: date) -> str:
    return f"{d:%y%m%d}"


def safe_title(title: str) -> str:
    """Title as a file-name part: unsafe characters removed, middle dots, arrows and whitespace runs -> '_'."""
    return "_".join(_SEPARATORS.sub(" ", _BAD_CHARS.sub("", title)).split())


def note_basename(prefix: str, d: date, title: str) -> str:
    return f"{prefix}_{fmt_yymmdd(d)}_{safe_title(title)}"


def copy_title(prefix: str, d: date, title: str) -> str:
    """Title as entered in the institute system: [ABC] <title> ('26, 4/10)"""
    return f"[{prefix}] {title} ('{d:%y}, {d.month}/{d.day})"
