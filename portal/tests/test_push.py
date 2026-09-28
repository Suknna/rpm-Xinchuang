import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import yaml

ci = importlib.import_module("portal.ci")
receive = importlib.import_module("portal.receive")


class PushTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "dist/private").mkdir(parents=True)
        self.config = {"repository": "owner/repo", "workflow": ci.WORKFLOW, "data_dir": str(self.root)}

    def event(self, **overrides):
        return {"kind": "job", "repository": "owner/repo", "workflow": ci.WORKFLOW,
                "id": 123, "run_attempt": 1, "run_number": 7, "event": "schedule", "head_branch": "main",
                "created_at": "2026-09-28T01:18:00Z", "sent_at": "2026-09-28T01:19:00Z",
                "name": "check", "detail": "发现待构建版本：bash 5.3 / EL8",
                "status": "completed", "conclusion": "success", **overrides}

    def feed(self):
        return json.loads((self.root / "dist/public/data/events.json").read_text())

    def test_duplicate_and_out_of_order_job_updates_do_not_reopen_completed_job(self):
        receive.receive_event(self.event(), self.config)
        receive.receive_event(self.event(), self.config)
        receive.receive_event(self.event(status="in_progress", conclusion=None, sent_at="2026-09-28T01:18:00Z"), self.config)
        jobs = self.feed()["runs"][0]["jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["conclusion"], "success")
        self.assertIn("bash", jobs[0]["detail"])

    def test_final_result_is_preserved_when_late_jobs_arrive(self):
        receive.receive_event(self.event(), self.config)
        receive.receive_event(self.event(kind="run", jobs=[], conclusion="failure", sent_at="2026-09-28T02:00:00Z"), self.config)
        receive.receive_event(self.event(name="build-el7", status="in_progress", conclusion=None, sent_at="2026-09-28T02:01:00Z"), self.config)
        run = self.feed()["runs"][0]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["conclusion"], "failure")
        self.assertEqual(len(run["jobs"]), 1)

    def test_new_attempt_resets_previous_jobs_and_rejects_old_attempt(self):
        receive.receive_event(self.event(), self.config)
        receive.receive_event(self.event(run_attempt=2, status="in_progress", conclusion=None), self.config)
        receive.receive_event(self.event(kind="run", jobs=[], conclusion="failure"), self.config)
        run = self.feed()["runs"][0]
        self.assertEqual(run["run_attempt"], 2)
        self.assertEqual(run["status"], "in_progress")

    def test_delayed_nonterminal_snapshot_cannot_reopen_a_completed_run(self):
        receive.receive_event(self.event(kind="run", jobs=[], conclusion="cancelled"), self.config)
        receive.receive_event(self.event(kind="run", jobs=[], status="in_progress", conclusion=None,
                                         sent_at="2026-09-28T03:00:00Z"), self.config)
        self.assertEqual(self.feed()["runs"][0]["conclusion"], "cancelled")

    def test_final_snapshot_retains_check_decision_and_uses_real_job_link(self):
        receive.receive_event(self.event(), self.config)
        link = "https://github.com/owner/repo/actions/runs/123/job/999"
        jobs = [{"name": "check", "status": "completed", "conclusion": "success", "html_url": link}]
        receive.receive_event(self.event(kind="run", jobs=jobs, sent_at="2026-09-28T02:00:00Z"), self.config)
        job = self.feed()["runs"][0]["jobs"][0]
        self.assertEqual(job["html_url"], link)
        self.assertIn("bash", job["detail"])

    def test_foreign_repository_and_external_job_link_are_rejected(self):
        with self.assertRaises(ValueError):
            receive.receive_event(self.event(repository="other/repo"), self.config)
        with self.assertRaises(ValueError):
            receive.receive_event(self.event(html_url="https://example.com"), self.config)
        self.assertFalse((self.root / "dist/public/data/events.json").exists())

    def upload(self, body=b"RPM", name="bash-5.3-1.el8.x86_64.rpm", kind=tarfile.REGTYPE):
        sha = hashlib.sha256(b"RPM").hexdigest()
        header = {"repository": "owner/repo", "tag": "bash-el8-5.3-1.el8", "published_at": "2026-09-28T02:00:00Z",
                  "assets": [{"id": 99, "name": "bash-5.3-1.el8.x86_64.rpm", "size": 3, "sha256": sha,
                              "digest": "sha256:" + sha, "updated_at": "2026-09-28T02:00:00Z"}]}
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            member = tarfile.TarInfo(name)
            member.size = len(body)
            member.type = kind
            archive.addfile(member, io.BytesIO(body))
        stream.seek(0)
        return receive.receive_upload(header, stream, self.config)

    def test_valid_upload_is_immediately_downloadable_and_records_official_receipt(self):
        self.assertEqual(self.upload()["files"], 1)
        entry = self.feed()["releases"][0]
        self.assertTrue(entry["mirror_ok"])
        self.assertEqual(entry["platform"], "el8")
        self.assertEqual((self.root / entry["assets"][0]["url"].lstrip("/")).read_bytes(), b"RPM")
        receipt = json.loads((self.root / "dist/private/receipts/99.json").read_text())
        self.assertEqual(receipt["asset"]["digest"], "sha256:" + hashlib.sha256(b"RPM").hexdigest())

    def test_corrupt_or_traversing_upload_never_replaces_a_published_file(self):
        self.upload()
        with self.assertRaises(ValueError):
            self.upload(body=b"bad")
        with self.assertRaises(ValueError):
            self.upload(name="../config.yaml")
        with self.assertRaises(ValueError):
            self.upload(kind=tarfile.SYMTYPE)
        self.assertEqual((self.root / "download/bash-el8-5.3-1.el8/bash-5.3-1.el8.x86_64.rpm").read_bytes(), b"RPM")

    def test_client_archive_protocol_roundtrip(self):
        path = self.root / "bash-5.3-1.el8.x86_64.rpm"
        path.write_bytes(b"RPM")
        asset = {"id": 100, "name": path.name, "size": 3, "updated_at": "2026-09-28T02:00:00Z",
                 "digest": "sha256:" + hashlib.sha256(b"RPM").hexdigest()}
        release = {"published_at": "2026-09-28T02:00:00Z", "assets": [asset]}
        def transport(command, stream, **kwargs):
            self.assertEqual(command, "upload")
            header = json.loads(stream.readline())
            return receive.receive_upload(header, stream, self.config)
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}), patch.object(ci, "ssh", side_effect=transport):
            ci.publish("bash-el8-5.3-1.el8", [path], release)
        self.assertEqual(self.feed()["releases"][0]["assets"][0]["name"], path.name)

    def test_summary_failure_still_leaves_a_release_notes_file(self):
        output = self.root / "notes.md"
        with patch.object(ci, "ssh", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                ci.write_summary("bash", "5.3", output)
        self.assertIn("摘要暂不可用", output.read_text())


class WorkflowTests(unittest.TestCase):
    def test_every_pipeline_job_pushes_start_and_terminal_result(self):
        root = Path(__file__).resolve().parents[2]
        jobs = yaml.safe_load((root / ".github/workflows/rpm-xinchuang.yml").read_text())["jobs"]
        self.assertEqual(set(jobs), set(ci.NAMES))
        for name, job in jobs.items():
            with self.subTest(job=name):
                pushes = [s for s in job["steps"] if s.get("uses") == "./.github/actions/portal"
                          and s.get("with", {}).get("mode", "event") == "event"]
                self.assertEqual(len(pushes), 2)
                self.assertEqual(pushes[-1]["if"], "always()")
                self.assertEqual(pushes[-1]["with"]["status"], "${{ job.status }}")
                self.assertTrue(all(s["continue-on-error"] for s in pushes))
                self.assertEqual(job["steps"][-1], pushes[-1])
        self.assertIn("always()", jobs["scheduled-time"]["if"])

    def test_version_decision_distinguishes_no_update_from_pending_builds(self):
        self.assertIn("没有", ci.check_detail({"matrix": '{"include":[]}'}))
        detail = ci.check_detail({"new_version": "10.5p1", "matrix": json.dumps({"include": [
            {"package": "bash", "version": "5.3", "el": "el8"}]})})
        self.assertIn("OpenSSH 10.5p1", detail)
        self.assertIn("bash 5.3 / EL8", detail)

    def test_matrix_job_labels_match_github_names(self):
        event = ci.job_event({"GITHUB_JOB": "component-install", "GITHUB_REPOSITORY": "owner/repo",
                              "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_RUN_NUMBER": "7",
                              "GITHUB_EVENT_NAME": "schedule", "GITHUB_REF_NAME": "main",
                              "PORTAL_MATRIX": '{"package":"vim","el":"el8","version":"9.2.1"}',
                              "PORTAL_STATUS": "failure"})
        self.assertEqual(event["name"], "安装验证 vim (el8)")
        self.assertEqual(event["conclusion"], "failure")


if __name__ == "__main__":
    unittest.main()
