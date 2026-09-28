"""Behavior checks for the mirror's trust boundary and failure recovery."""

import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("portal_sync", Path(__file__).resolve().parents[1] / "sync.py")
assert SPEC is not None and SPEC.loader is not None
portal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(portal)


def release(tag, published, assets, **kwargs):
    return dict(tag_name=tag, published_at=published, assets=assets, draft=False, prerelease=False, **kwargs)


class ReleaseSelectionTests(unittest.TestCase):
    def test_latest_is_independent_per_platform_and_skips_drafts(self):
        older = release("v10.5p1-1", "2026-09-20", [{"name": "openssh-10.5p1-1.el7.x86_64.rpm"}, {"name": "openssh-10.5p1-1.el8.x86_64.rpm"}])
        newer = release("v10.5p1-2", "2026-09-28", [{"name": "openssh-10.5p1-2.el8.x86_64.rpm"}])
        draft = release("v10.6p1-1", "2026-09-29", [{"name": "openssh-10.6p1-1.el7.x86_64.rpm"}])
        draft["draft"] = True
        selected = portal.latest_releases([draft, older, newer])
        self.assertEqual(selected[("openssh", "el7")][0]["tag_name"], "v10.5p1-1")
        self.assertEqual(selected[("openssh", "el8")][0]["tag_name"], "v10.5p1-2")

    def test_unsafe_paths_and_unrelated_tags_are_rejected(self):
        for name in ("../key", "/etc/passwd", ".hidden", "a/b", "a\\b"):
            with self.assertRaises(ValueError):
                portal.safe_name(name)
        self.assertIsNone(portal.release_identity("unrelated-1.2.3"))
        self.assertEqual(portal.release_identity("sudo-el8-1.9.17p2-2.el8"), ("sudo", "1.9.17p2", "el8"))

    def test_shared_checksum_is_mirrored_once_and_published_for_both_platforms(self):
        assets = [{"id": 1, "name": "openssh-10.5p1-2.el7.x86_64.rpm", "size": 10},
                  {"id": 2, "name": "openssh-10.5p1-2.el8.x86_64.rpm", "size": 10},
                  {"id": 3, "name": "SHA256SUMS", "size": 1}]
        value = release("v10.5p1-2", "2026-09-28", assets, html_url="https://github.com/test/release")
        class FakeGitHub:
            def releases(self):
                return [value]
        snapshots = []
        with tempfile.TemporaryDirectory() as temp, patch.object(portal, "mirror_asset", return_value="a" * 64) as mirror:
            result = portal.catalog(FakeGitHub(), {}, Path(temp), publish=lambda data: snapshots.append(json.loads(json.dumps(data))))
        self.assertEqual(mirror.call_count, 3)
        self.assertTrue(all(r["mirror_ok"] for r in result[0]["releases"]))
        self.assertFalse(snapshots[0][0]["releases"][0]["mirror_ok"])
        self.assertTrue(all(a["url"] for r in snapshots[-1][0]["releases"] for a in r["assets"]))


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.payload = b"rpm-test-payload"
        self.asset = {"id": 42, "name": "bash-5.3-1.el8.x86_64.rpm", "size": len(self.payload),
                      "updated_at": "2026-09-28", "digest": "sha256:" + hashlib.sha256(self.payload).hexdigest(),
                      "browser_download_url": "https://github.com/example/repo/releases/download/test/bash.rpm"}

    def mirror(self):
        return portal.mirror_asset(self.asset, self.root / "download", self.root / "receipts")

    def download(self, payload):
        def run(command, **kwargs):
            Path(command[command.index("--output") + 1]).write_bytes(payload)
        return run

    def test_atomic_publish_then_receipt_avoids_redownload(self):
        with patch.object(portal.subprocess, "run", side_effect=self.download(self.payload)) as fetch:
            digest = self.mirror()
            self.assertEqual(digest, hashlib.sha256(self.payload).hexdigest())
            self.assertEqual((self.root / "download" / self.asset["name"]).read_bytes(), self.payload)
            self.assertEqual(self.mirror(), digest)
            self.assertEqual(fetch.call_count, 1)

    def test_corrupt_download_never_replaces_existing_file(self):
        directory = self.root / "download"
        directory.mkdir()
        destination = directory / self.asset["name"]
        destination.write_bytes(b"previous verified release")
        with patch.object(portal.subprocess, "run", side_effect=self.download(b"X" * len(self.payload))):
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                self.mirror()
        self.assertEqual(destination.read_bytes(), b"previous verified release")
        self.assertEqual(list(directory.glob("*.part")), [])
        self.assertFalse((self.root / "receipts/42.json").exists())

    def test_truncated_file_is_not_published(self):
        with patch.object(portal.subprocess, "run", side_effect=self.download(b"short")):
            with self.assertRaisesRegex(ValueError, "incomplete"):
                self.mirror()
        self.assertFalse((self.root / "download" / self.asset["name"]).exists())

    def test_timeout_retains_partial_and_next_run_resumes_it(self):
        partial = self.root / "download" / ("." + self.asset["name"] + ".part")
        def interrupted(command, **kwargs):
            partial.write_bytes(self.payload[:4])
            raise portal.subprocess.CalledProcessError(28, command)
        with patch.object(portal.subprocess, "run", side_effect=interrupted):
            with self.assertRaises(portal.subprocess.CalledProcessError):
                self.mirror()
        self.assertEqual(partial.read_bytes(), self.payload[:4])
        def resumed(command, **kwargs):
            self.assertIn("--continue-at", command)
            self.assertEqual(partial.read_bytes(), self.payload[:4])
            with partial.open("ab") as stream:
                stream.write(self.payload[4:])
        with patch.object(portal.subprocess, "run", side_effect=resumed):
            self.mirror()
        self.assertFalse(partial.exists())
        self.assertEqual((self.root / "download" / self.asset["name"]).read_bytes(), self.payload)

    def test_seeded_file_requires_matching_official_digest(self):
        directory = self.root / "download"
        directory.mkdir()
        (directory / self.asset["name"]).write_bytes(self.payload)
        with patch.object(portal.subprocess, "run") as fetch:
            self.mirror()
        fetch.assert_not_called()


class SummaryTests(unittest.TestCase):
    def test_failure_is_cached_without_private_error_details(self):
        with tempfile.TemporaryDirectory() as temp:
            config = {"model": {"endpoint": "https://private.invalid/v1/chat/completions", "name": "model", "api_key": "secret"}}
            with patch.object(portal, "source_notes", side_effect=RuntimeError("secret provider endpoint")) as source:
                first = portal.summarize("bash", "5.3", config, Path(temp))
                second = portal.summarize("bash", "5.3", config, Path(temp))
            self.assertEqual(first["status"], "unavailable")
            self.assertEqual(first, second)
            self.assertEqual(source.call_count, 1)
            self.assertNotIn("secret", json.dumps(first))

    def test_unconfigured_model_does_not_make_network_requests(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(portal, "request") as request:
            result = portal.summarize("bash", "5.3", {}, Path(temp))
        self.assertEqual(result["status"], "unconfigured")
        request.assert_not_called()

    def test_openssh_p1_uses_base_release_announcement(self):
        with patch.object(portal, "request", return_value=b"OpenSSH 10.5 release notes") as request:
            url, text = portal.source_notes("openssh", "10.5p1")
        self.assertTrue(url.endswith("release-10.5"))
        self.assertIn("10.5", text)


class RecoveryTests(unittest.TestCase):
    def test_truncated_github_response_is_retried(self):
        with patch.object(portal.urllib.request, "urlopen", side_effect=[portal.http.client.IncompleteRead(b"part"), io.BytesIO(b'{}')]) as fetch, patch.object(portal.time, "sleep"):
            self.assertEqual(portal.request("https://api.github.com/test"), b"{}")
            self.assertEqual(fetch.call_count, 2)

    def test_api_failure_preserves_last_good_data_and_marks_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "dist/public/data/index.json"
            previous = {"packages": [{"id": "bash"}], "builds": {"checked_at": "2026-09-27T00:00:00Z"}, "catalog_checked_at": "2026-09-27T00:00:00Z"}
            portal.atomic_json(target, previous)
            with patch.object(portal, "build_status", side_effect=OSError("offline")), patch.object(portal, "catalog", side_effect=OSError("offline")):
                with self.assertRaises(RuntimeError):
                    portal.sync({"repository": "owner/repo", "data_dir": temp})
            result = json.loads(target.read_text())
            self.assertEqual(result["packages"], previous["packages"])
            self.assertEqual(result["builds"], previous["builds"])
            self.assertEqual(result["catalog_checked_at"], previous["catalog_checked_at"])
            self.assertEqual(len(result["errors"]), 2)

    def test_schedule_comes_from_actual_workflow_and_keeps_failed_scheduled_run(self):
        class FakeGitHub:
            def get(self, path):
                if path.startswith("/contents/"):
                    return {"content": base64.b64encode(b"on:\n  schedule:\n    - cron: '17 1 * * *'\n").decode()}
                if "event=schedule" in path:
                    return {"workflow_runs": [{"id": 3, "conclusion": "failure", "status": "completed"}]}
                if "/runs?" in path:
                    return {"workflow_runs": []}
                return {"state": "active", "html_url": "https://github.com/owner/repo/actions", "path": ".github/workflows/build.yml"}
        with tempfile.TemporaryDirectory() as temp:
            result = portal.build_status(FakeGitHub(), {"workflow": "build.yml"}, Path(temp))
        self.assertEqual(result["cron"], ["17 1 * * *"])
        self.assertEqual(result["scheduled_runs"][0]["conclusion"], "failure")

    def test_eventually_consistent_job_response_is_not_cached_as_terminal(self):
        class FakeGitHub:
            job_calls = 0

            def get(self, path):
                if path.startswith("/contents/"):
                    return {"content": base64.b64encode(b"on:\n  schedule:\n    - cron: '17 1 * * *'\n").decode()}
                if "/attempts/" in path:
                    self.job_calls += 1
                    return {"jobs": [{"name": "build", "status": "completed" if self.job_calls > 1 else "in_progress",
                                      "conclusion": "failure" if self.job_calls > 1 else None}]}
                if "event=schedule" in path:
                    return {"workflow_runs": []}
                if "/runs?" in path:
                    return {"workflow_runs": [{"id": 1, "run_attempt": 1, "status": "completed"}]}
                return {"state": "active", "html_url": "https://github.com/owner/repo/actions", "path": ".github/workflows/build.yml"}
        github = FakeGitHub()
        with tempfile.TemporaryDirectory() as temp:
            first = portal.build_status(github, {"workflow": "build.yml"}, Path(temp))
            second = portal.build_status(github, {"workflow": "build.yml"}, Path(temp))
        self.assertEqual(first["runs"][0]["jobs"][0]["status"], "in_progress")
        self.assertEqual(second["runs"][0]["jobs"][0]["conclusion"], "failure")


if __name__ == "__main__":
    unittest.main()
