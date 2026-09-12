#!/usr/bin/env python3
"""check_update.py 的行为测试（unittest，无网络依赖）。

运行：python3 -m unittest discover -s tests -v
覆盖：版本数值比较（非字符串）、上游解析、更新判定、
      version.txt 读取、GITHUB_OUTPUT 写出、Release 查询（伪造 HTTP 层）。
"""

import os
import sys
import tempfile
import unittest
import urllib.error
from io import BytesIO
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import check_update  # noqa: E402


def make_listing(names):
    """构造形如镜像目录的 HTML 片段。"""
    rows = "".join(
        '<a href="%s">%s</a><br></td>' % (n, n) for n in names
    )
    return "<html><body><table><tr><td>%s</td></tr></table></body></html>" % rows


class ParseVersionTest(unittest.TestCase):
    def test_accepts_standard_format(self):
        self.assertEqual(check_update.parse_version("10.5p1"), (10, 5, 1))
        self.assertEqual(check_update.parse_version("9.9p2"), (9, 9, 2))

    def test_rejects_garbage(self):
        for bad in ("", None, "10.5", "10.5p", "v10.5p1", "10.5p1x", "  "):
            self.assertIsNone(check_update.parse_version(bad), bad)

    def test_numeric_ordering_not_lexicographic(self):
        # 关键回归：字符串比较会得出 10.10p1 < 10.9p1
        self.assertGreater(
            check_update.parse_version("10.10p1"),
            check_update.parse_version("10.9p1"),
        )
        self.assertGreater(
            check_update.parse_version("10.0p1"),
            check_update.parse_version("9.99p9"),
        )
        self.assertGreater(
            check_update.parse_version("10.0p2"),
            check_update.parse_version("10.0p1"),
        )


class LatestUpstreamTest(unittest.TestCase):
    def test_picks_highest(self):
        html = make_listing(
            [
                "openssh-9.9p2.tar.gz",
                "openssh-10.0p1.tar.gz",
                "openssh-10.5p1.tar.gz",
                "openssh-10.5p1.tar.gz.asc",
            ]
        )
        self.assertEqual(check_update.latest_upstream_version(html), "10.5p1")

    def test_ignores_non_release_files(self):
        html = make_listing(
            [
                "openssh-10.5p1-vs-openbsd.diff.gz",
                "openssh-10.5p1.tar.gz.asc",
                " портals.txt",
                "hpn-ssh-1.0.tar.gz",
            ]
        )
        self.assertIsNone(check_update.latest_upstream_version(html))

    def test_numeric_across_minor(self):
        html = make_listing(
            [
                "openssh-10.9p1.tar.gz",
                "openssh-10.10p1.tar.gz",
                "openssh-10.5p1.tar.gz",
            ]
        )
        self.assertEqual(check_update.latest_upstream_version(html), "10.10p1")


class CheckUpdateTest(unittest.TestCase):
    def test_newer_upstream_detected(self):
        html = make_listing(["openssh-10.0p1.tar.gz", "openssh-10.5p1.tar.gz"])
        self.assertEqual(check_update.check_update(html, "10.0p1"), "10.5p1")

    def test_equal_means_no_update(self):
        html = make_listing(["openssh-10.0p1.tar.gz"])
        self.assertIsNone(check_update.check_update(html, "10.0p1"))

    def test_current_ahead_is_no_update(self):
        html = make_listing(["openssh-10.5p1.tar.gz"])
        self.assertIsNone(check_update.check_update(html, "10.6p1"))

    def test_empty_listing_raises(self):
        with self.assertRaises(ValueError):
            check_update.check_update("", "10.0p1")

    def test_invalid_current_raises(self):
        html = make_listing(["openssh-10.5p1.tar.gz"])
        with self.assertRaises(ValueError):
            check_update.check_update(html, "not-a-version")


class ReadCurrentVersionTest(unittest.TestCase):
    def test_reads_trimmed_value(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write("  10.0p1\n\n")
            path = fh.name
        try:
            self.assertEqual(check_update.read_current_version(path), "10.0p1")
        finally:
            os.unlink(path)

    def test_missing_file_returns_none(self):
        self.assertIsNone(
            check_update.read_current_version("/nonexistent/version.txt")
        )


class WriteOutputTest(unittest.TestCase):
    def test_appends_key_value(self):
        with tempfile.NamedTemporaryFile("r", suffix=".out", delete=False) as fh:
            path = fh.name
        try:
            check_update.write_output(path, "new_version", "10.5p1")
            check_update.write_output(path, "new_version", "")
            with open(path) as fh:
                self.assertEqual(
                    fh.read(), "new_version=10.5p1\nnew_version=\n"
                )
        finally:
            os.unlink(path)


class ReleaseExistsTest(unittest.TestCase):
    class _FakeResp(BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _Fake404(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                url="x", code=404, msg="Not Found", hdrs=None, fp=None
            )

    def _patch_urlopen(self, resp):
        return mock.patch.object(
            check_update.urllib.request, "urlopen", return_value=resp
        )

    def test_existing_release_true(self):
        with self._patch_urlopen(self._FakeResp(b"[]")):
            self.assertTrue(
                check_update.release_exists("o/r", "v10.5p1", token="t")
            )

    def test_missing_release_404_false(self):
        with self._patch_urlopen(self._Fake404()) as mocked:
            mocked.side_effect = mocked.return_value
            self.assertFalse(
                check_update.release_exists("o/r", "v10.5p1", token="t")
            )

    def test_auth_header_sent_when_token_given(self):
        captured = {}

        def fake_urlopen(request, timeout=30):
            captured["headers"] = dict(request.header_items())
            return self._FakeResp(b"[]")

        with mock.patch.object(
            check_update.urllib.request, "urlopen", side_effect=fake_urlopen
        ):
            check_update.release_exists("o/r", "v10.5p1", token="tok")
        # urllib 会规范化 header 大小写
        joined = " ".join(str(v) for v in captured["headers"].values())
        self.assertIn("Bearer tok", joined)


class MainCheckFlowTest(unittest.TestCase):
    """端到端走 main()：临时 version.txt + 本地文件输出。"""

    def test_check_flow_outputs_new_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            vfile = os.path.join(tmp, "version.txt")
            out = os.path.join(tmp, "gh_output")
            with open(vfile, "w") as fh:
                fh.write("10.0p1\n")

            listing = make_listing(
                ["openssh-10.0p1.tar.gz", "openssh-10.5p1.tar.gz"]
            )
            with mock.patch.object(
                check_update, "fetch_url", return_value=listing.encode()
            ):
                rc = check_update.main(
                    ["check", "--version-file", vfile, "--output", out]
                )
            self.assertEqual(rc, check_update.EXIT_UPDATED)
            with open(out) as fh:
                self.assertIn("new_version=10.5p1", fh.read())

    def test_check_flow_up_to_date_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            vfile = os.path.join(tmp, "version.txt")
            with open(vfile, "w") as fh:
                fh.write("10.5p1\n")
            listing = make_listing(["openssh-10.5p1.tar.gz"])
            with mock.patch.object(
                check_update, "fetch_url", return_value=listing.encode()
            ):
                rc = check_update.main(
                    ["check", "--version-file", vfile, "--output", ""]
                )
            self.assertEqual(rc, check_update.EXIT_UPTODATE)

    def test_check_flow_bad_version_file_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = check_update.main(
                [
                    "check",
                    "--version-file",
                    os.path.join(tmp, "missing.txt"),
                    "--output",
                    "",
                ]
            )
            self.assertEqual(rc, check_update.EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
