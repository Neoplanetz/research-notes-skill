"""Run inputs and remembered project profiles.

usage:
  config.py list                      print remembered profiles as JSON
  config.py save OUT_DIR --json JSON  write OUT_DIR/research-notes.json and remember the profile
"""
import argparse
import json
import os
import sys
from pathlib import Path

PROFILE_KEYS = ("project", "prefix", "pi", "author", "repos")


def config_dir() -> Path:
    env = os.environ.get("RESEARCH_NOTES_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".config" / "research-notes"


def load_profiles() -> list[dict]:
    path = config_dir() / "profiles.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"WARN {path} 읽기 실패, 저장된 프로필 없이 진행: {e}", file=sys.stderr)
        return []


def remember(cfg: dict) -> None:
    """Add or replace (same prefix) the project profile."""
    profile = {k: cfg[k] for k in PROFILE_KEYS if k in cfg}
    profiles = [p for p in load_profiles() if p.get("prefix") != profile.get("prefix")]
    profiles.insert(0, profile)
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "profiles.json").write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")


def save_run(out_dir: Path, cfg: dict) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "research-notes.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    remember(cfg)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sp = sub.add_parser("save")
    sp.add_argument("out_dir")
    sp.add_argument("--json", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "list":
        print(json.dumps(load_profiles(), ensure_ascii=False, indent=2))
    else:
        print(save_run(Path(a.out_dir).expanduser(), json.loads(a.json)))


if __name__ == "__main__":
    sys.exit(main())
