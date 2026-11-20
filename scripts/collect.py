"""Collect commits from one or more repositories (local paths or URLs) into one text file.

usage:
  collect.py --since 2026-01-01 --until 2026-12-31 [--author EMAIL_OR_NAME]... [--cache DIR] --out FILE REPO...
  collect.py --list-authors REPO...
"""
import argparse
import hashlib
import os
import re
import signal
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
_HASH = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
NET_TIMEOUT = 300  # seconds per clone/fetch: a credential helper waiting for input must not hang the run


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


def _git(*args, cwd=None, timeout=None) -> subprocess.CompletedProcess:
    """New session: no controlling terminal to prompt on, and on timeout the whole group
    (credential helper, ssh, remote helper) is killed, not only git."""
    p = subprocess.Popen(["git", *args], cwd=cwd, env=_git_env(), stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace", start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (AttributeError, ProcessLookupError):  # no killpg on Windows
            p.kill()
        try:
            p.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        raise
    return subprocess.CompletedProcess(p.args, p.returncode, out, err)


def _plain(text: str) -> str:
    return _CTRL.sub(" ", text)


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


def _origin(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    return _git("config", "--get", "remote.origin.url", cwd=path).stdout.strip()


def _cache_dest(spec: str, cache: Path) -> Path:
    """Different URLs can map to one cache path (a/s and a/s.git, a and a/b): never reuse
    a folder that holds something else."""
    dest = _cache_path(spec, cache)
    if dest.exists() and _origin(dest) != spec:
        dest = dest.with_name(f"{dest.name}@{hashlib.sha256(spec.encode()).hexdigest()[:10]}")
        if dest.exists() and _origin(dest) != spec:
            raise RepoError(f"{spec}: 캐시 폴더 {dest} 가 다른 레포로 차 있음")
    return dest


def resolve_repo(spec: str, cache: Path) -> Path:
    if spec.startswith("-"):
        raise RepoError(f"{spec}: 잘못된 레포 주소")
    if _URL.match(spec):
        dest = _cache_dest(spec, Path(cache))
        try:
            if dest.exists():
                r = _git("fetch", "--all", "--prune", "--quiet", cwd=dest, timeout=NET_TIMEOUT)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                r = _git("clone", "--quiet", "--filter=blob:none", "--", spec, str(dest), timeout=NET_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise RepoError(f"{spec}: {NET_TIMEOUT}초 안에 응답 없음 (인증 대기 또는 큰 레포). "
                            "로컬에 clone 후 경로를 주세요.") from None
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
        try:
            r = _git("log", "--no-walk=unsorted", "--format=%x1e%H", "--shortstat", "--end-of-options",
                     *hashes[i:i + 200], cwd=repo, timeout=NET_TIMEOUT)  # may fetch blobs
        except subprocess.TimeoutExpired:
            raise RepoError(f"{repo}: 변경량 집계가 {NET_TIMEOUT}초 안에 끝나지 않음") from None
        for rec in r.stdout.split("\x1e")[1:]:
            h, _, rest = rec.partition("\n")
            m = _STAT.search(rest)
            stats[h.strip()] = (int(m[1]), int(m[2] or 0), int(m[3] or 0)) if m else (0, 0, 0)
    return stats


def read_commits(repo: Path, since: date, until: date, authors: list[str] | None = None) -> list[dict]:
    # NUL ends every field and record (-z); no commit text can hold a NUL, any other byte is fine
    r = _git("log", *REFS, "-z", "--reverse", "--date=short", "--format=%H%x00%h%x00%ad%x00%an%x00%ae%x00%P%x00%s%x00%b",
             cwd=repo)
    if r.returncode != 0:
        raise RepoError(f"{repo}: git log 실패 ({r.stderr.strip()})")
    fields = r.stdout.split("\0")[:-1]
    if len(fields) % 8:
        raise RepoError(f"{repo}: git log 출력 해석 실패")
    wanted = {a.lower() for a in authors} if authors else None
    out = []
    for i in range(0, len(fields), 8):
        h, short, d, an, ae, parents, subject, body = fields[i:i + 8]
        if not (_HASH.fullmatch(h) and _DAY.fullmatch(d) and all(_HASH.fullmatch(p) for p in parents.split())):
            raise RepoError(f"{repo}: git log 출력 해석 실패")
        an, ae, subject = _plain(an), _plain(ae), _plain(subject)
        if not (since.isoformat() <= d <= until.isoformat()):
            continue
        if wanted and an.lower() not in wanted and ae.lower() not in wanted:
            continue
        is_merge = len(parents.split()) > 1
        out.append({
            "hash": h, "short": short, "date": d, "author": an, "email": ae, "is_merge": is_merge,
            "subject": subject, "body": "" if is_merge else _plain(_clean_body(body)),
            "files": 0, "ins": 0, "dels": 0,
        })
    stats = _stats(repo, [c["hash"] for c in out if not c["is_merge"]])
    for c in out:
        c["files"], c["ins"], c["dels"] = stats.get(c["hash"], (0, 0, 0))
    out.sort(key=lambda c: c["date"])
    return out


def list_authors(repo: Path) -> list[tuple[str, str, int]]:
    r = _git("log", *REFS, "-z", "--format=%an%x00%ae", cwd=repo)
    f = [_plain(x) for x in r.stdout.split("\0")[:-1]]
    counts = Counter(zip(f[0::2], f[1::2]))
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
    if not a.list_authors and not (a.since and a.until and a.out):
        ap.error("--since, --until, --out 이 필요합니다")
    try:
        repos = [resolve_repo(s, a.cache) for s in a.repos]
        if not a.list_authors:
            items = [(f"{r.name}, {r}", read_commits(r, a.since, a.until, a.author)) for r in repos]
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
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(format_report(items), encoding="utf-8")
    for name, cs in items:
        print(f"{len(cs):5d}  {name}")
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
