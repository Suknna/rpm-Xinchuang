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
    def test_ubuntu_receipt_is_verified_and_cannot_downgrade_or_change_rpm_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "version.json"
            state.write_text(json.dumps({"openssh": "10.5p1", "openssh_centos7": None}))
            metadata = root / "published/metadata/openssh-ubuntu2204.json"
            metadata.parent.mkdir(parents=True)
            receipt = root / "published/receipts/openssh-ubuntu2204.json"
            receipt.parent.mkdir(parents=True)
            for version in ("10.6p1", "10.5p1"):
                metadata.write_text(json.dumps({"package": "openssh", "platform": "ubuntu2204",
                                                "architecture": "amd64", "version": version,
                                                "release": "2ubuntu22.04", "deb_version": "1:" + version + "-2ubuntu22.04"}))
                receipt.write_text(json.dumps({"package": "openssh", "el": "ubuntu2204", "version": version,
                                               "metadata_sha256": hashlib.sha256(metadata.read_bytes()).hexdigest()}))
                record_versions.record(state, [receipt], root / "spec")
                self.assertEqual(json.loads(state.read_text()), {"openssh": "10.5p1", "openssh_centos7": None,
                                                               "openssh_ubuntu2204": "10.6p1"})
                self.assertFalse((root / "spec").exists())
            wrong = json.loads(metadata.read_text())
            wrong["architecture"] = "arm64"
            metadata.write_text(json.dumps(wrong))
            row = json.loads(receipt.read_text())
            row["metadata_sha256"] = hashlib.sha256(metadata.read_bytes()).hexdigest()
            receipt.write_text(json.dumps(row))
            with self.assertRaisesRegex(ValueError, "unexpected published"):
                record_versions.record(state, [receipt])
            metadata.write_text("modified")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                record_versions.record(state, [receipt])

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

    def test_centos_receipts_only_advance_their_own_baselines(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            version_file = root / "version.json"
            version_file.write_text(json.dumps({"openssh": "10.5p1", "openssh_centos7": None,
                                               "sudo": {"el7": "1.8.23", "el8": "1.9.5p2"}}))
            shared = root / "spec/sudo/el7.spec"
            shared.parent.mkdir(parents=True)
            shared.write_text("UBI7 published spec\n")
            ssh_spec = root / "spec/openssh.spec"
            ssh_spec.write_text("%global ver 10.5p1\n")
            receipts = []
            for package, version in (("sudo", "1.9.17p2"), ("openssh", "10.6p1")):
                spec = root / "published/spec" / package / "centos7.spec"
                spec.parent.mkdir(parents=True)
                spec.write_text("Name: %s\nVersion: %s\n" % (package, version))
                receipt = root / "published/receipts" / (package + "-centos7.json")
                receipt.parent.mkdir(parents=True, exist_ok=True)
                receipt.write_text(json.dumps({"package": package, "el": "centos7", "version": version,
                                               "spec_sha256": hashlib.sha256(spec.read_bytes()).hexdigest()}))
                receipts.append(receipt)
            record_versions.record(version_file, receipts, root / "spec")
            state = json.loads(version_file.read_text())
            self.assertEqual(state["openssh"], "10.5p1")
            self.assertEqual(state["openssh_centos7"], "10.6p1")
            self.assertEqual(state["sudo"], {"el7": "1.8.23", "el8": "1.9.5p2", "centos7": "1.9.17p2"})
            self.assertEqual(shared.read_text(), "UBI7 published spec\n")
            self.assertEqual(ssh_spec.read_text(), "%global ver 10.5p1\n")
            self.assertFalse((root / "spec/sudo/centos7.spec").exists())
            spec.write_text("modified")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                record_versions.record(version_file, [receipts[-1]], root / "spec")


if __name__ == "__main__":
    unittest.main()
