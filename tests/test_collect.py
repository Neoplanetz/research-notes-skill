import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

import _path  # noqa: F401
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

    def test_report_dedupes_hashes(self):
        c = read_commits(self.repo, date(2026, 1, 1), date(2026, 12, 31))
        text = format_report([("repo", c), ("copy", c)])
        self.assertIn("## repo (4 commits", text)
        self.assertEqual(text.count("Add docker build"), 1)


if __name__ == "__main__":
    unittest.main()
