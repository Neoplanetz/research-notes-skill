"""Collect commits from one or more repositories (local paths or URLs) into one text file.

usage:
  collect.py --since 2026-01-01 --until 2026-12-31 [--author EMAIL_OR_NAME]... [--cache DIR] --out FILE REPO...
  collect.py --list-authors REPO...
"""
import argparse
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

DEFAULT_CACHE = Path.home() / ".cache" / "research-notes" / "repos"
REFS = ("--branches", "--remotes", "--tags")  # not --all: stashes and notes are not work
_URL = re.compile(r"^(https?|ssh|git|file)://|^[\w.-]+@[\w.-]+:")
_TRAILERS = ("co-authored-by:", "signed-off-by:", "claude-session:", "🤖 generated with")
_STAT = re.compile(r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?")


class RepoError(Exception):
    pass


def _git_env() -> dict:
    """Never wait for a password: no terminal prompt, no askpass helper, no credential-manager UI.
    BatchMode ssh only when the user has no ssh setup of their own."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="", SSH_ASKPASS="", GCM_INTERACTIVE="never")
    if not (env.get("GIT_SSH_COMMAND") or env.get("GIT_SSH")):
        own = subprocess.run(["git", "config", "--get", "core.sshCommand"], capture_output=True, text=True)
        if not own.stdout.strip():
            env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    return env


def _git(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, env=_git_env(), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def _cache_path(url: str, cache: Path) -> Path:
    m = re.match(r"^[\w.-]+@([\w.-]+):(.+)$", url)
    if m:
        host, path = m[1], m[2]
    else:
        rest = url.split("://", 1)[1]
        host, _, path = rest.partition("/")
        host = host.rsplit("@", 1)[-1] or "local"
    path = re.sub(r"\.git$", "", path.strip("/"))
    if ".." in Path(path).parts:
        raise RepoError(f"{url}: 잘못된 레포 주소 (.. 경로)")
    return cache / re.sub(r"[^\w.-]", "_", host) / path


def resolve_repo(spec: str, cache: Path) -> Path:
    if spec.startswith("-"):
        raise RepoError(f"{spec}: 잘못된 레포 주소")
    if _URL.match(spec):
        dest = _cache_path(spec, Path(cache))
        if (dest / ".git").exists():
            r = _git("fetch", "--all", "--prune", "--quiet", cwd=dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            r = _git("clone", "--quiet", "--filter=blob:none", "--", spec, str(dest))
        if r.returncode != 0:
            raise RepoError(f"{spec}: 받을 수 없음 ({(r.stderr.strip().splitlines() or [''])[-1]}). "
                            "비공개 레포라면 로컬에 clone 후 경로를 주세요.")
        return dest
    path = Path(spec).expanduser()
    r = _git("rev-parse", "--show-toplevel", cwd=path) if path.is_dir() else None
    if r is None or r.returncode != 0:
        raise RepoError(f"{spec}: git 레포가 아님")
    return Path(r.stdout.strip())


def _clean_body(body: str) -> str:
    lines = [ln for ln in body.splitlines() if not ln.strip().lower().startswith(_TRAILERS)]
    return "\n".join(lines).strip()


def _stats(repo: Path, hashes: list[str]) -> dict[str, tuple[int, int, int]]:
    """--shortstat for the given commits only (a partial clone fetches just their blobs)."""
    stats = {}
    for i in range(0, len(hashes), 200):
        r = _git("log", "--no-walk=unsorted", "--format=%x1e%H", "--shortstat", *hashes[i:i + 200], cwd=repo)
        for rec in r.stdout.split("\x1e")[1:]:
            h, _, rest = rec.partition("\n")
            m = _STAT.search(rest)
            stats[h.strip()] = (int(m[1]), int(m[2] or 0), int(m[3] or 0)) if m else (0, 0, 0)
    return stats


def read_commits(repo: Path, since: date, until: date, authors: list[str] | None = None) -> list[dict]:
    fmt = "%x1e%H%x1f%h%x1f%ad%x1f%an%x1f%ae%x1f%P%x1f%s%x1f%b"
    r = _git("log", *REFS, "--reverse", "--date=short", f"--format={fmt}", cwd=repo)
    if r.returncode != 0:
        raise RepoError(f"{repo}: git log 실패 ({r.stderr.strip()})")
    wanted = {a.lower() for a in authors} if authors else None
    out = []
    for rec in r.stdout.split("\x1e")[1:]:
        h, short, d, an, ae, parents, subject, body = rec.split("\x1f")
        if not (since.isoformat() <= d <= until.isoformat()):
            continue
        if wanted and an.lower() not in wanted and ae.lower() not in wanted:
            continue
        is_merge = len(parents.split()) > 1
        out.append({
            "hash": h, "short": short, "date": d, "author": an, "email": ae, "is_merge": is_merge,
            "subject": subject, "body": "" if is_merge else _clean_body(body),
            "files": 0, "ins": 0, "dels": 0,
        })
    stats = _stats(repo, [c["hash"] for c in out if not c["is_merge"]])
    for c in out:
        c["files"], c["ins"], c["dels"] = stats.get(c["hash"], (0, 0, 0))
    out.sort(key=lambda c: c["date"])
    return out


def list_authors(repo: Path) -> list[tuple[str, str, int]]:
    r = _git("log", *REFS, "--format=%an%x1f%ae", cwd=repo)
    counts = Counter(tuple(line.split("\x1f")) for line in r.stdout.splitlines() if line)
    return [(n, e, c) for (n, e), c in counts.most_common()]


def format_report(items: list[tuple[str, list[dict]]]) -> str:
    seen = set()
    parts = []
    for name, commits in items:
        fresh = [c for c in commits if c["hash"] not in seen]
        seen.update(c["hash"] for c in fresh)
        lines = [f"## {name} ({len(fresh)} commits)"]
        for c in fresh:
            tag = "merge" if c["is_merge"] else f"+{c['ins']}/-{c['dels']}, {c['files']} files"
            tag += f", {c['author']}"
            lines.append(f"- {c['date']} {c['short']} {c['subject']}  [{tag}]")
            lines += [f"    {ln}" for ln in c["body"].splitlines() if ln.strip()]
        parts.append("\n".join(lines))
    return "\n\n".join(parts) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repos", nargs="+")
    ap.add_argument("--since", type=date.fromisoformat)
    ap.add_argument("--until", type=date.fromisoformat)
    ap.add_argument("--author", action="append")
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--list-authors", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        repos = [resolve_repo(s, a.cache) for s in a.repos]
    except RepoError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 1
    if a.list_authors:
        name = _git("config", "--get", "user.name").stdout.strip()
        email = _git("config", "--get", "user.email").stdout.strip()
        if email:
            print(f"현재 git 사용자: {name} <{email}>")
        for repo in repos:
            print(f"## {repo.name}")
            for n, e, c in list_authors(repo):
                print(f"{c:5d}  {n} <{e}>")
        return 0
    if not (a.since and a.until and a.out):
        ap.error("--since, --until, --out 이 필요합니다")
    items = [(f"{r.name}, {r}", read_commits(r, a.since, a.until, a.author)) for r in repos]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(format_report(items), encoding="utf-8")
    for name, cs in items:
        print(f"{len(cs):5d}  {name}")
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
