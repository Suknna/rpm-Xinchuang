"""Check pinned upstream identity, versions and per-platform update selection."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import check_versions  # noqa: E402


class VersionDetectionTest(unittest.TestCase):
    def test_retry_specific_component_and_version_without_touching_other_packages(self):
        ssh, matrix = check_versions.retry_component_matrix("chrony:4.9")
        self.assertEqual(ssh, "")
        self.assertEqual(matrix, [
            {"package": "chrony", "el": el, "version": "4.9",
             "url": "https://chrony-project.org/releases/chrony-4.9.tar.gz"}
            for el in ("el7", "el8", "centos7")
        ])
        for invalid in ("chrony", "chrony:bad", "other:1.0", "openssh:10.5p1", "vim:9.2.1202"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                check_versions.retry_component_matrix(invalid)

    def test_pam_repair_selects_only_ssh_and_el8_sudo_from_spec(self):
        with tempfile.TemporaryDirectory() as folder:
            spec = Path(folder) / "sudo.spec"
            spec.write_text("Name: sudo\nVersion: 1.9.17p2\nRelease: 2%{?dist}\n")
            ssh, matrix = check_versions.repair_pam_matrix({"openssh": "10.5p1"}, spec)
            self.assertEqual(ssh, "10.5p1")
            self.assertEqual(matrix, [check_versions.centos_openssh("10.5p1"), {
                "package": "sudo", "el": "el8", "version": "1.9.17p2",
                "url": "https://www.sudo.ws/dist/sudo-1.9.17p2.tar.gz",
            }])
            spec.write_text("Name: sudo\nVersion: invalid\n")
            with self.assertRaisesRegex(ValueError, "invalid sudo version"):
                check_versions.repair_pam_matrix({"openssh": "10.5p1"}, spec)

    def test_sudo_name_collision_cannot_select_a_different_project(self):
        projects = {"items": [
            {"id": 370631, "stable_versions": ["0.6.0"]},
            {"id": 4906, "stable_versions": ["1.9.17p2", "1.9.17p1"]},
        ]}
        self.assertEqual(check_versions.latest("sudo", lambda _: projects)[0], "1.9.17p2")
        with self.assertRaisesRegex(ValueError, "project missing"):
            check_versions.latest("ntp", lambda _: projects)

    def test_platforms_update_independently_and_old_versions_do_not_downgrade(self):
        state: dict = {name: {"el7": "1.0", "el8": "2.0", "centos7": "2.0"}
                 for name in check_versions.PROJECTS if name != "openssh"}
        state["openssh"] = "10.5p1"
        state["openssh_centos7"] = "10.5p1"
        state["openssh_ubuntu2204"] = "10.5p1"
        state["ntp"]["el8"] = None
        def versions(name):
            self.assertNotEqual(name, "vim", "paused Vim must not query upstream")
            return ["10.5p1", "10.4p1"] if name == "openssh" else ["2.0", "1.0"]
        ssh, matrix = check_versions.detect(state, versions)
        self.assertEqual(ssh, "")
        self.assertEqual(len(matrix), 6)
        self.assertEqual(sum(row["el"] == "el7" for row in matrix), 5)
        self.assertIn({"package": "ntp", "el": "el8", "version": "2.0",
                       "url": "https://downloads.nwtime.org/ntp/ntp-2.0.tar.gz"}, matrix)
        _, forced = check_versions.detect(state, versions, force=True)
        self.assertEqual({row["package"] for row in forced}, {"bash", "chrony", "ntp", "sudo", "telnet"})
        self.assertEqual(len(forced), 15)
        self.assertFalse(check_versions.is_newer(["2.0", "1.0"], "2.0"))
        self.assertFalse(check_versions.is_newer(["10.5p1"], "10.6p1"))

    def test_missing_centos_baselines_bootstrap_without_rebuilding_ubi(self):
        state: dict = {name: {"el7": "2.0", "el8": "2.0"}
                 for name in check_versions.PROJECTS if name != "openssh"}
        state["openssh"] = "10.5p1"
        state["openssh_ubuntu2204"] = "10.5p1"
        def versions(name):
            return ["10.5p1"] if name == "openssh" else ["2.0"]
        ssh, matrix = check_versions.detect(state, versions)
        self.assertEqual(ssh, "")
        self.assertEqual({row["package"] for row in matrix}, set(check_versions.PROJECTS))
        self.assertEqual({row["el"] for row in matrix}, {"centos7"})
        self.assertEqual(len(matrix), 6)
        for row in matrix:
            if row["package"] == "openssh":
                state["openssh_centos7"] = row["version"]
            else:
                state[row["package"]]["centos7"] = row["version"]
        self.assertEqual(check_versions.detect(state, versions), ("", []))
        state["openssh_centos7"] = "10.4p1"
        self.assertEqual(check_versions.detect(state, versions),
                         ("", [check_versions.centos_openssh("10.5p1")]))

    def test_manual_openssh_version_replaces_centos_candidate_in_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "version.json"
            path.write_text('{"openssh":"10.5p1"}')
            output = Path(folder) / "output"
            args = ["check_versions.py", "--version-file", str(path), "--output", str(output),
                    "--openssh-version", "10.6p1"]
            candidate = check_versions.centos_openssh("10.7p1")
            with mock.patch.object(sys, "argv", args), mock.patch.object(
                    check_versions, "detect", return_value=("10.7p1", [candidate])):
                check_versions.main()
            values = dict(line.split("=", 1) for line in output.read_text().splitlines())
            self.assertEqual(values["new_version"], "10.6p1")
            self.assertEqual(values["has_updates"], "true")
            self.assertEqual(json.loads(values["matrix"])["include"],
                             [check_versions.platform_openssh("10.6p1", platform)
                              for platform in check_versions.SSH_PLATFORMS])

    def test_ubuntu_bootstrap_and_updates_are_independent(self):
        state: dict = {name: {el: "2.0" for el in check_versions.PLATFORMS}
                 for name in check_versions.PROJECTS if name != "openssh"}
        state.update(openssh="10.6p1", openssh_centos7="10.6p1")
        def versions(name):
            return ["10.6p1"] if name == "openssh" else ["2.0"]
        self.assertEqual(check_versions.detect(state, versions),
                         ("", [check_versions.platform_openssh("10.6p1", "ubuntu2204")]))
        for baseline in ("10.6p1", "10.7p1"):
            state["openssh_ubuntu2204"] = baseline
            self.assertEqual(check_versions.detect(state, versions), ("", []))


if __name__ == "__main__":
    unittest.main()
