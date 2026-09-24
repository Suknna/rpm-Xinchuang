"""Exercise multi-component update selection without contacting RPM repositories."""

import gzip
import hashlib
import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import check_sources  # noqa: E402


class SourcesTest(unittest.TestCase):
    def test_detect_only_changed_source_per_platform(self):
        def packages(repo):
            el = "el7" if "centos" in repo else "el8"
            for name in check_sources.PACKAGES:
                if el == "el8" and name == "ntp":
                    continue
                yield {"package": name, "checksum": name + el, "built": 100}

        state = {"el7": {name: name + "el7" for name in check_sources.PACKAGES},
                 "el8": {name: name + "el8" for name in check_sources.PACKAGES if name != "ntp"}}
        self.assertEqual(check_sources.detect(state, packages), [])
        state["el8"]["vim"] = "old"
        updates = check_sources.detect(state, packages)
        self.assertEqual([(p["package"], p["el"]) for p in updates], [("vim", "el8")])

    def test_missing_upstream_package_is_error_not_no_update(self):
        with self.assertRaisesRegex(ValueError, "missing source RPMs"):
            check_sources.detect({}, lambda repo: iter(()))

    def test_primary_checksum_prevents_tampered_source_index(self):
        base = "https://vault.centos.org/7.9.2009/os/Source/"
        body = gzip.compress(b"<metadata/>")
        root = ET.Element("{http://linux.duke.edu/metadata/repo}repomd")
        data = ET.SubElement(root, "{http://linux.duke.edu/metadata/repo}data", type="primary")
        ET.SubElement(data, "{http://linux.duke.edu/metadata/repo}location", href="repodata/primary.xml.gz")
        ET.SubElement(data, "{http://linux.duke.edu/metadata/repo}checksum", type="sha256").text = hashlib.sha256(body).hexdigest()
        resources = {base + "repodata/repomd.xml": ET.tostring(root),
                     base + "repodata/primary.xml.gz": body + b"altered"}
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            list(check_sources.source_packages(base, resources.__getitem__))


if __name__ == "__main__":
    unittest.main()
