"""Check pinned upstream identity, versions and per-platform update selection."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import check_versions  # noqa: E402


class VersionDetectionTest(unittest.TestCase):
    def test_pam_repair_selects_only_ssh_and_el8_sudo_from_spec(self):
        with tempfile.TemporaryDirectory() as folder:
            spec = Path(folder) / "sudo.spec"
            spec.write_text("Name: sudo\nVersion: 1.9.17p2\nRelease: 2%{?dist}\n")
            ssh, matrix = check_versions.repair_pam_matrix({"openssh": "10.5p1"}, spec)
            self.assertEqual(ssh, "10.5p1")
            self.assertEqual(matrix, [{
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
        state = {name: {"el7": "1.0", "el8": "2.0"} for name in check_versions.PROJECTS if name != "openssh"}
        state["openssh"] = "10.5p1"
        state["ntp"]["el8"] = None
        def versions(name):
            return ["10.5p1", "10.4p1"] if name == "openssh" else ["2.0", "1.0"]
        ssh, matrix = check_versions.detect(state, versions)
        self.assertEqual(ssh, "")
        self.assertEqual(len(matrix), 7)
        self.assertEqual(sum(row["el"] == "el7" for row in matrix), 6)
        self.assertIn({"package": "ntp", "el": "el8", "version": "2.0",
                       "url": "https://downloads.nwtime.org/ntp/ntp-2.0.tar.gz"}, matrix)
        self.assertFalse(check_versions.is_newer(["2.0", "1.0"], "2.0"))
        self.assertFalse(check_versions.is_newer(["10.5p1"], "10.6p1"))


if __name__ == "__main__":
    unittest.main()
