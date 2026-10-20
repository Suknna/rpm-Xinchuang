"""Release retention must preserve the highest complete RPM set per platform."""

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import prune_releases  # noqa: E402


class ReleaseRetentionTest(unittest.TestCase):
    def setUp(self):
        self.pages = [[]]
        self.downloads = {}
        self.deleted = []
        self.next_id = 1
        self.api = mock.patch.object(prune_releases, "github", side_effect=self.github).start()
        self.addCleanup(mock.patch.stopall)

    def release(self, tag):
        key = prune_releases.parse_tag(tag)
        release = {"id": self.next_id, "tag_name": tag, "draft": False, "prerelease": False, "assets": []}
        self.next_id += 1
        self.pages[-1].append(release)
        if key is None:
            return release
        platforms = ("el7", "el8") if key.package == "openssh" else (key.el,)
        for el in platforms:
            revision = key.release + "." + el if key.package == "openssh" else key.release
            packages = ("openssh", "openssh-clients", "openssh-server") if key.package == "openssh" else (key.package, key.package + "-devel")
            checksums = []
            for package in packages:
                name = "%s-%s-%s.x86_64.rpm" % (package, key.version, revision)
                data = name.encode()
                checksum = hashlib.sha256(data).hexdigest()
                release["assets"].append({"name": name, "size": len(data), "state": "uploaded", "digest": "sha256:" + checksum})
                self.downloads[tag, name] = data
                checksums.append(checksum + "  ./" + name)
            manifest = "SHA256SUMS-" + el if key.package == "openssh" else "SHA256SUMS"
            self.downloads[tag, manifest] = "\n".join(checksums) + "\n"
            release["assets"].append({"name": manifest, "size": len(self.downloads[tag, manifest]), "state": "uploaded"})
        return release

    def github(self, *args, text=True):
        if args == ("api", "--paginate", "--slurp", "repos/owner/repo/releases?per_page=100"):
            return json.dumps(self.pages)
        if args[:2] == ("release", "download"):
            self.assertEqual(args[3:6], ("--repo", "owner/repo", "--pattern"))
            self.assertEqual(args[7:], ("--output", "-"))
            data = self.downloads[args[2], args[6]]
            self.assertEqual(text, isinstance(data, str))
            return data
        self.assertEqual(args[:3], ("api", "--method", "DELETE"))
        self.assertTrue(args[3].startswith("repos/owner/repo/releases/"))
        self.deleted.append(int(args[3].rsplit("/", 1)[1]))
        return ""

    def test_numeric_order_and_pagination_preserve_other_platforms_and_components(self):
        old = self.release("chrony-el7-4.9-9.el7")
        other_el = self.release("chrony-el8-4.9-1.el8")
        other_component = self.release("bash-el7-5.3-1.el7")
        unrelated = self.release("backup-el7-999-1.el7")
        self.pages.append([])
        current = self.release("chrony-el7-4.10-2.el7")
        keeper = self.release("chrony-el7-4.10-10.el7")
        self.assertEqual(prune_releases.prune("owner/repo", current["tag_name"]), keeper["tag_name"])
        self.assertCountEqual(self.deleted, [old["id"], current["id"]])
        for release in (other_el, other_component, unrelated, keeper):
            self.assertNotIn(release["id"], self.deleted)

    def test_sudo_patchlevel_and_rpm_distro_revision_are_compared_numerically(self):
        for old_tag, new_tag in (
            ("sudo-el7-1.8.23-10.el7_9.3", "sudo-el7-1.9.17p2-1.el7"),
            ("sudo-el7-1.9.17p2-10.el7", "sudo-el7-1.9.17p10-1.el7"),
            ("sudo-el8-1.9.5p2-1.el8_9.9", "sudo-el8-1.9.5p2-1.el8_10.5"),
        ):
            with self.subTest(old=old_tag):
                self.pages = [[]]
                self.deleted.clear()
                old = self.release(old_tag)
                keeper = self.release(new_tag)
                self.assertEqual(prune_releases.prune("owner/repo", old_tag), new_tag)
                self.assertEqual(self.deleted, [old["id"]])
                self.assertNotIn(keeper["id"], self.deleted)

    def test_old_openssh_tags_are_removed_with_both_platforms_kept_together(self):
        first = self.release("v10.5p1")
        second = self.release("v10.5p1-2")
        keeper = self.release("v10.6p1-2")
        self.assertEqual(prune_releases.prune("owner/repo", keeper["tag_name"]), keeper["tag_name"])
        self.assertCountEqual(self.deleted, [first["id"], second["id"]])
        for el in ("el7", "el8"):
            self.api.assert_any_call("release", "download", keeper["tag_name"], "--repo", "owner/repo", "--pattern", "SHA256SUMS-" + el, "--output", "-")

    def test_failed_openssh_platform_preserves_all_existing_releases(self):
        self.release("v10.5p1-2")
        keeper = self.release("v10.6p1-2")
        keeper["assets"] = [asset for asset in keeper["assets"] if "el8" not in asset["name"]]
        with self.assertRaisesRegex(ValueError, "primary RPM"):
            prune_releases.prune("owner/repo", keeper["tag_name"])
        self.assertEqual(self.deleted, [])

    def test_drafts_prereleases_and_unrecognized_tags_are_not_cleanup_candidates(self):
        current = self.release("bash-el7-5.3-1.el7")
        draft = self.release("bash-el7-5.4-1.el7")
        draft["draft"] = True
        preview = self.release("bash-el7-5.5-1.el7")
        preview["prerelease"] = True
        for tag in ("bash-el7-6.0-1.el8", "bash-el7-6.1-custom", "v99.0", "vim-el7-9.2-1.el7"):
            self.release(tag)
        self.assertEqual(prune_releases.prune("owner/repo", current["tag_name"]), current["tag_name"])
        self.assertEqual(self.deleted, [])

    def test_missing_or_unpublished_current_release_cannot_trigger_deletion(self):
        self.release("ntp-el7-4.2.8p17-1.el7")
        self.release("ntp-el7-4.2.8p18-1.el7")
        with self.assertRaisesRegex(ValueError, "not found"):
            prune_releases.prune("owner/repo", "ntp-el7-4.2.8p18-2.el7")
        current = self.release("ntp-el7-4.2.8p18-2.el7")
        current["draft"] = True
        with self.assertRaisesRegex(ValueError, "not found"):
            prune_releases.prune("owner/repo", current["tag_name"])
        self.assertEqual(self.deleted, [])

    def test_incomplete_newer_release_preserves_fallback(self):
        old = self.release("telnet-el8-2.7-1.el8")
        keeper = self.release("telnet-el8-2.8-1.el8")
        keeper["assets"] = [asset for asset in keeper["assets"] if "-devel-" not in asset["name"]]
        with self.assertRaisesRegex(ValueError, "checksum manifest"):
            prune_releases.prune("owner/repo", old["tag_name"])
        self.assertEqual(self.deleted, [])

    def test_incomplete_current_release_cannot_delete_itself_or_other_versions(self):
        current = self.release("telnet-el8-2.7-1.el8")
        self.release("telnet-el8-2.8-1.el8")
        current["assets"][0]["state"] = "new"
        with self.assertRaisesRegex(ValueError, "incomplete asset"):
            prune_releases.prune("owner/repo", current["tag_name"])
        self.assertEqual(self.deleted, [])

    def test_corrupt_checksums_preserve_previous_release(self):
        self.release("bash-el8-5.2-1.el8")
        keeper = self.release("bash-el8-5.3-1.el8")
        keeper["assets"][0]["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            prune_releases.prune("owner/repo", keeper["tag_name"])
        self.assertEqual(self.deleted, [])

    def test_noarch_and_differently_named_subpackages_are_kept(self):
        old = self.release("ntp-el8-4.2.8p17-1.el8")
        keeper = self.release("ntp-el8-4.2.8p18-1.el8")
        for name in ("ntp-doc-4.2.8p18-1.el8.noarch.rpm", "sntp-4.2.8p18-1.el8.x86_64.rpm"):
            checksum = hashlib.sha256(name.encode()).hexdigest()
            keeper["assets"].append({"name": name, "size": 10, "state": "uploaded", "digest": "sha256:" + checksum})
            self.downloads[keeper["tag_name"], "SHA256SUMS"] += checksum + "  ./" + name + "\n"
        self.assertEqual(prune_releases.prune("owner/repo", keeper["tag_name"]), keeper["tag_name"])
        self.assertEqual(self.deleted, [old["id"]])

    def test_legacy_assets_without_digest_are_downloaded_and_verified(self):
        old = self.release("chrony-el7-4.8-1.el7")
        keeper = self.release("chrony-el7-4.9-1.el7")
        for asset in keeper["assets"]:
            asset.pop("digest", None)
        prune_releases.prune("owner/repo", keeper["tag_name"])
        self.assertEqual(self.deleted, [old["id"]])
        self.api.assert_any_call("release", "download", keeper["tag_name"], "--repo", "owner/repo", "--pattern", "chrony-4.9-1.el7.x86_64.rpm", "--output", "-", text=False)

    def test_manifest_must_cover_the_complete_rpm_set(self):
        self.release("chrony-el7-4.8-1.el7")
        keeper = self.release("chrony-el7-4.9-1.el7")
        manifest = keeper["tag_name"], "SHA256SUMS"
        original = self.downloads[manifest]
        for contents in ("", original.splitlines()[0], original + original, "invalid\n"):
            with self.subTest(contents=contents):
                self.downloads[manifest] = contents
                with self.assertRaisesRegex(ValueError, "checksum manifest"):
                    prune_releases.prune("owner/repo", keeper["tag_name"])
                self.assertEqual(self.deleted, [])

    def test_equal_legacy_openssh_version_prefers_successful_current_tag(self):
        old = self.release("v10.5p1")
        current = self.release("v10.5p1-1")
        self.assertEqual(prune_releases.prune("owner/repo", current["tag_name"]), current["tag_name"])
        self.assertEqual(self.deleted, [old["id"]])

    def test_dry_run_verifies_without_deletion(self):
        self.release("bash-el7-5.2-1.el7")
        keeper = self.release("bash-el7-5.3-1.el7")
        self.assertEqual(prune_releases.prune("owner/repo", keeper["tag_name"], dry_run=True), keeper["tag_name"])
        self.assertEqual(self.deleted, [])

    def test_old_retry_does_not_allow_version_writeback(self):
        current = self.release("bash-el7-5.2-1.el7")
        keeper = self.release("bash-el7-5.3-1.el7")
        with tempfile.TemporaryDirectory() as folder:
            output = pathlib.Path(folder) / "output"
            self.assertEqual(prune_releases.main(["--repo", "owner/repo", "--tag", current["tag_name"], "--output", str(output)]), 0)
            self.assertEqual(output.read_text(), "retained=false\nretained_tag=" + keeper["tag_name"] + "\n")
        self.assertEqual(self.deleted, [current["id"]])

    def test_current_keeper_allows_writeback_and_cleanup_can_be_retried(self):
        old = self.release("bash-el7-5.2-1.el7")
        current = self.release("bash-el7-5.3-1.el7")
        with tempfile.TemporaryDirectory() as folder:
            output = pathlib.Path(folder) / "output"
            self.assertEqual(prune_releases.main(["--repo", "owner/repo", "--tag", current["tag_name"], "--output", str(output)]), 0)
            self.assertEqual(output.read_text(), "retained=true\nretained_tag=" + current["tag_name"] + "\n")
        self.assertEqual(self.deleted, [old["id"]])
        self.pages = [[current]]
        self.deleted.clear()
        self.assertEqual(prune_releases.prune("owner/repo", current["tag_name"]), current["tag_name"])
        self.assertEqual(self.deleted, [])

    def test_failed_deletion_does_not_emit_a_success_receipt(self):
        self.release("bash-el7-5.2-1.el7")
        current = self.release("bash-el7-5.3-1.el7")
        def fail_delete(*args, **kwargs):
            if args[:3] == ("api", "--method", "DELETE"):
                raise subprocess.CalledProcessError(1, "gh")
            return self.github(*args, **kwargs)
        self.api.side_effect = fail_delete
        with tempfile.TemporaryDirectory() as folder:
            output = pathlib.Path(folder) / "output"
            self.assertEqual(prune_releases.main(["--repo", "owner/repo", "--tag", current["tag_name"], "--output", str(output)]), 1)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
