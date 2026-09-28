"""The publish job must select the installed main RPM, not the source RPM name."""

import pathlib
import subprocess
import tempfile
import unittest


SELECTOR = pathlib.Path(__file__).resolve().parents[1] / "scripts/select-release-rpm.sh"
WORKFLOW = SELECTOR.parents[1] / ".github/workflows/rpm-xinchuang.yml"


class ReleaseSelectionTest(unittest.TestCase):
    def test_publish_job_uses_the_selector(self):
        workflow = WORKFLOW.read_text()
        self.assertIn('selection="$(bash scripts/select-release-rpm.sh "$dir" "$PKG" "$VERSION" "$EL")"', workflow)
        self.assertNotIn('candidates=("$dir/$PKG-$VERSION-"', workflow)

    def select(self, directory, package, version, el):
        return subprocess.run(
            ["bash", str(SELECTOR), str(directory), package, version, el],
            capture_output=True,
            text=True,
        )

    def test_vim_uses_enhanced_binary_package_on_both_platforms(self):
        with tempfile.TemporaryDirectory() as directory:
            for el in ("el7", "el8"):
                rpm = pathlib.Path(directory) / f"vim-enhanced-9.2.1135-1.{el}.x86_64.rpm"
                rpm.touch()
                (pathlib.Path(directory) / f"vim-common-9.2.1135-1.{el}.x86_64.rpm").touch()
                result = self.select(directory, "vim", "9.2.1135", el)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), f"{rpm}\t1.{el}")

    def test_other_packages_use_own_name(self):
        with tempfile.TemporaryDirectory() as directory:
            rpm = pathlib.Path(directory) / "ntp-4.2.8p18-2.el7.x86_64.rpm"
            rpm.touch()
            result = self.select(directory, "ntp", "4.2.8p18", "el7")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), f"{rpm}\t2.el7")

    def test_missing_and_duplicate_main_rpms_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertNotEqual(self.select(directory, "vim", "9.2.1135", "el8").returncode, 0)
            for release in (1, 2):
                (pathlib.Path(directory) / f"vim-enhanced-9.2.1135-{release}.el8.x86_64.rpm").touch()
            self.assertNotEqual(self.select(directory, "vim", "9.2.1135", "el8").returncode, 0)


if __name__ == "__main__":
    unittest.main()
