import http.server
import io
import os
import subprocess
import tempfile
import threading
from contextlib import redirect_stdout
import unittest
from datetime import date
from pathlib import Path

import _path  # noqa: F401
import collect
from collect import RepoError, format_report, list_authors, read_commits, resolve_repo


def git(repo, *args, when=None, name="A", email="a@x.org"):
    env = dict(os.environ, GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email,
               GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email)
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{when}T12:00:00"
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=env, capture_output=True)


def commit(repo, fname, text, msg, when, **kw):
    (repo / fname).write_text(text)
    git(repo, "add", fname)
    git(repo, "commit", "-m", msg, when=when, **kw)


class CollectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.tmp.name) / "repo"
        cls.repo.mkdir()
        git(cls.repo, "init", "-b", "main")
        commit(cls.repo, "a.txt", "old\n", "old work", "2025-12-30")
        commit(cls.repo, "b.txt", "1\n2\n3\n",
               "Add docker build\n\n- build.sh added\n\nCo-Authored-By: Bot <bot@x.org>", "2026-02-25")
        git(cls.repo, "switch", "-c", "side")
        commit(cls.repo, "c.txt", "x\n", "Side work by B", "2026-03-05", name="B", email="b@x.org")
        git(cls.repo, "switch", "main")
        commit(cls.repo, "d.txt", "y\n", "Main work", "2026-03-06")
        git(cls.repo, "merge", "--no-ff", "side", "-m", "Merge side", when="2026-03-07")
        (cls.repo / "d.txt").write_text("stashed\n")
        git(cls.repo, "stash", when="2026-03-08")
        (cls.repo / "sub").mkdir()
        cls.cache = Path(cls.tmp.name) / "cache"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_read_commits_period_and_body(self):
        c = read_commits(self.repo, date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual([x["date"] for x in c if not x["is_merge"]], ["2026-02-25", "2026-03-05", "2026-03-06"])
        first = c[0]
        self.assertEqual(first["subject"], "Add docker build")
        self.assertIn("build.sh added", first["body"])
        self.assertNotIn("Co-Authored-By", first["body"])
        self.assertEqual((first["files"], first["ins"], first["dels"]), (1, 3, 0))
        merge = [x for x in c if x["is_merge"]]
        self.assertEqual(len(merge), 1)
        self.assertEqual(merge[0]["body"], "")

    def test_author_filter(self):
        c = read_commits(self.repo, date(2026, 1, 1), date(2026, 12, 31), ["B@X.org"])
        self.assertEqual([x["subject"] for x in c], ["Side work by B"])

    def test_list_authors(self):
        self.assertEqual(list_authors(self.repo)[0][:2], ("A", "a@x.org"))

    def test_resolve_local_subdir(self):
        self.assertEqual(resolve_repo(str(self.repo / "sub"), self.cache), self.repo)

    def test_resolve_url_clone_and_refetch(self):
        clone = resolve_repo(f"file://{self.repo}", self.cache)
        self.assertTrue((clone / ".git").exists())
        self.assertEqual(resolve_repo(f"file://{self.repo}", self.cache), clone)
        self.assertEqual(len(read_commits(clone, date(2026, 1, 1), date(2026, 12, 31))), 4)

    def test_resolve_bad_url_fails_fast(self):
        with self.assertRaises(RepoError) as cm:
            resolve_repo("file:///nonexistent/x.git", self.cache)
        self.assertIn("로컬에 clone", str(cm.exception))

    def test_resolve_not_a_repo(self):
        with self.assertRaises(RepoError):
            resolve_repo(self.tmp.name, self.cache)

    def test_partial_clone_fetches_no_blobs_outside_period(self):
        src = Path(self.tmp.name) / "src"
        src.mkdir()
        git(src, "init", "-b", "main")
        git(src, "config", "uploadpack.allowFilter", "true")
        for i in range(5):
            commit(src, "f.txt", f"{i}\n" * 50, f"old {i}", f"2025-03-0{i + 1}")  # old versions stay unfetched
        clone = resolve_repo(f"file://{src}", Path(self.tmp.name) / "pcache")

        def missing():
            r = subprocess.run(["git", "-C", str(clone), "rev-list", "--objects", "--all", "--missing=print"],
                               capture_output=True, text=True, env=dict(os.environ, GIT_NO_LAZY_FETCH="1"))
            return sum(1 for ln in r.stdout.splitlines() if ln.startswith("?"))

        before = missing()
        self.assertGreater(before, 0)
        self.assertEqual(read_commits(clone, date(2026, 1, 1), date(2026, 12, 31)), [])
        self.assertEqual(missing(), before)

    def test_stash_is_not_a_commit(self):
        c = read_commits(self.repo, date(2026, 1, 1), date(2026, 12, 31))
        self.assertFalse([x["subject"] for x in c if x["subject"].startswith(("WIP on", "index on"))])

    def test_report_shows_author(self):
        c = read_commits(self.repo, date(2026, 1, 1), date(2026, 12, 31))
        self.assertIn("Side work by B  [+1/-0, 1 files, B]", format_report([("repo", c)]))

    def test_error_message_has_no_python_list(self):
        with self.assertRaises(RepoError) as cm:
            resolve_repo("file:///nonexistent/x.git", self.cache)
        self.assertNotIn("['", str(cm.exception))

    def test_cache_path_rejects_dotdot(self):
        with self.assertRaises(RepoError) as cm:
            resolve_repo("https://example.invalid/a/../../escape.git", self.cache)
        self.assertIn("잘못된 레포 주소", str(cm.exception))

    def test_dash_spec_is_not_an_option(self):
        with self.assertRaises(RepoError) as cm:
            resolve_repo("-u@x:y", self.cache)
        self.assertIn("잘못된 레포 주소", str(cm.exception))
        self.assertFalse(any(p.name.startswith("-") for p in self.cache.rglob("*")))

    def test_env_respects_user_ssh_settings(self):
        old = os.environ.get("GIT_SSH")
        os.environ["GIT_SSH"] = "/usr/bin/ssh"
        try:
            env = collect._git_env()
            self.assertNotIn("GIT_SSH_COMMAND", {k: v for k, v in env.items() if k not in os.environ})
            self.assertEqual(env["GIT_ASKPASS"], "")
            self.assertEqual(env["GCM_INTERACTIVE"], "never")
        finally:
            if old is None:
                os.environ.pop("GIT_SSH", None)
            else:
                os.environ["GIT_SSH"] = old

    def test_auth_required_url_does_not_run_askpass(self):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="x"')
                self.end_headers()
            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        marker = Path(self.tmp.name) / "askpass-ran"
        script = Path(self.tmp.name) / "askpass.sh"
        script.write_text(f"#!/bin/sh\ntouch {marker}\necho x\n")
        script.chmod(0o755)
        old = {k: os.environ.get(k) for k in ("SSH_ASKPASS", "GIT_ASKPASS", "SSH_ASKPASS_REQUIRE")}
        os.environ.update(SSH_ASKPASS=str(script), SSH_ASKPASS_REQUIRE="force")
        os.environ.pop("GIT_ASKPASS", None)
        try:
            with self.assertRaises(RepoError):
                resolve_repo(f"http://127.0.0.1:{srv.server_port}/r.git", Path(self.tmp.name) / "acache")
            self.assertFalse(marker.exists())
        finally:
            srv.shutdown()
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_list_authors_shows_current_git_user(self):
        cfg = Path(self.tmp.name) / "gitconfig"
        cfg.write_text("[user]\n\tname = Me\n\temail = me@x.org\n")
        old = os.environ.get("GIT_CONFIG_GLOBAL")
        os.environ["GIT_CONFIG_GLOBAL"] = str(cfg)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                collect.main(["--list-authors", str(self.repo)])
            self.assertIn("me@x.org", buf.getvalue())
        finally:
            if old is None:
                os.environ.pop("GIT_CONFIG_GLOBAL", None)
            else:
                os.environ["GIT_CONFIG_GLOBAL"] = old

    def test_report_dedupes_hashes(self):
        c = read_commits(self.repo, date(2026, 1, 1), date(2026, 12, 31))
        text = format_report([("repo", c), ("copy", c)])
        self.assertIn("## repo (4 commits", text)
        self.assertEqual(text.count("Add docker build"), 1)


if __name__ == "__main__":
    unittest.main()
