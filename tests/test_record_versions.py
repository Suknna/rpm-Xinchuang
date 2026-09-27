"""A successful release alone advances that component's platform baseline."""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import record_versions  # noqa: E402


class RecordVersionsTest(unittest.TestCase):
    def test_preserves_unrelated_versions_and_checks_the_built_spec(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            version_file = root / "version.json"
            version_file.write_text(json.dumps({"openssh": "10.5p1", "sudo": {
                "el7": "1.8.23", "el8": "1.9.5p2"}}))
            spec = root / "published/spec/sudo/el8.spec"
            spec.parent.mkdir(parents=True)
            spec.write_text("Name: sudo\nVersion: 1.9.17p2\n")
            receipt = root / "published/receipts/sudo-el8.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps({"package": "sudo", "el": "el8", "version": "1.9.17p2",
                                           "spec_sha256": hashlib.sha256(spec.read_bytes()).hexdigest()}))
            record_versions.record(version_file, [receipt], root / "spec")
            versions = json.loads(version_file.read_text())
            self.assertEqual(versions["openssh"], "10.5p1")
            self.assertEqual(versions["sudo"], {"el7": "1.8.23", "el8": "1.9.17p2"})
            self.assertEqual((root / "spec/sudo/el8.spec").read_bytes(), spec.read_bytes())
            spec.write_text("modified")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                record_versions.record(version_file, [receipt], root / "spec")


if __name__ == "__main__":
    unittest.main()
