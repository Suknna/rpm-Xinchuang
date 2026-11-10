"""Baseline write-back: hash-anchored receipts, no downgrade, no spec rewrite.

RPM 凭据校验用真实 spec：共享 OpenSSH spec 的 Version/Release 是宏
（%{ver}/2%{?dist}），record 用 rpm.spec 宏展开后与 receipt 严格比对。
"""

import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import record_versions  # noqa: E402
import project_config  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REAL_SHARED_SPEC = ROOT / "packaging" / "common" / "openssh" / "openssh.spec"

UPSTREAMS_YAML = """\
projects:
  chrony:
    name: chrony
    anitya_id: 8810
    version_pattern: '\\d+(?:\\.\\d+)+'
    source_url: https://example.test/chrony-{version}.tar.gz
"""


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fake_target(platform, package):
    """宽松 fixture 目标解析（unknown 拒绝语义由 rejecting_target 单独验证）。"""
    return {"family": "deb" if platform == "ubuntu2204" else "rpm"}


def rejecting_target(platform, package):
    raise project_config.ConfigError("unknown platform %r (fixture targets only)" % platform)


class RecordVersionsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.published = self.root / "published"
        self.version_file = self.root / "version.json"
        self.state = {"platforms": {
            "el7": {"openssh": "10.5p1", "sudo": "1.8.23"},
            "ubuntu2204": {"openssh": "10.5p1"},
        }}

    def write_spec(self, platform, package, text):
        spec = self.published / "spec" / platform / (package + ".spec")
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text(text)
        return spec

    def write_rpm_receipt(self, platform, package, version, release, spec_text=None):
        package_spec = spec_text or (
            "Name: %s\nVersion: %s\nRelease: %s\nSummary: t\nLicense: MIT\n\n"
            "%%description\nt\n" % (package, version, release))
        spec = self.write_spec(platform, package, package_spec)
        receipt = self.published / "receipts" / ("%s-%s.json" % (platform, package))
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({
            "platform": platform, "package": package, "version": version,
            "release": release, "tag": "%s-%s-%s-%s" % (platform, package, version, release),
            "spec_sha256": sha256(spec)}))
        return receipt

    def write_deb_receipt(self, version, release="2ubuntu22.04", metadata=None):
        built = json.dumps(metadata or {
            "package": "openssh", "platform": "ubuntu2204", "architecture": "amd64",
            "version": version, "release": release, "deb_version": "1:" + version + "-" + release})
        meta = self.published / "metadata" / "ubuntu2204-openssh.json"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(built)
        receipt = self.published / "receipts" / "ubuntu2204-openssh.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({
            "platform": "ubuntu2204", "package": "openssh", "version": version,
            "release": release, "tag": "ubuntu2204-openssh-%s-%s" % (version, release),
            "metadata_sha256": sha256(meta)}))
        return receipt

    def record(self, receipts):
        self.version_file.write_text(json.dumps(self.state))
        return record_versions.record(self.version_file, receipts, get_target=fake_target)

    def test_deb_receipt_advances_its_own_baseline_and_never_downgrades(self):
        receipt = self.write_deb_receipt("10.6p2")
        state = self.record([receipt])
        self.assertEqual(state["platforms"]["ubuntu2204"]["openssh"], "10.6p2")
        self.assertEqual(state["platforms"]["el7"]["openssh"], "10.5p1")
        # 较低版本补发：基线不得回退。
        self.state = state
        state = self.record([self.write_deb_receipt("10.5p2")])
        self.assertEqual(state["platforms"]["ubuntu2204"]["openssh"], "10.6p2")

    def test_deb_metadata_must_match_the_receipt_exactly(self):
        receipt = self.write_deb_receipt("10.6p2", metadata={
            "package": "openssh", "platform": "ubuntu2204", "architecture": "arm64",
            "version": "10.6p2", "release": "2ubuntu22.04",
            "deb_version": "1:10.6p2-2ubuntu22.04"})
        with self.assertRaisesRegex(ValueError, "unexpected published Ubuntu"):
            self.record([receipt])
        receipt = self.write_deb_receipt("10.6p2", metadata={
            "package": "openssh", "platform": "ubuntu2204", "architecture": "amd64",
            "version": "10.6p1", "release": "2ubuntu22.04",
            "deb_version": "1:10.6p1-2ubuntu22.04"})
        with self.assertRaisesRegex(ValueError, "unexpected published Ubuntu"):
            self.record([receipt])
        receipt = self.write_deb_receipt("10.6p2")
        built = json.loads((self.published / "metadata" / "ubuntu2204-openssh.json").read_text())
        built["deb_version"] = "1:10.6p2-wrong"
        (self.published / "metadata" / "ubuntu2204-openssh.json").write_text(json.dumps(built))
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.record([receipt])

    def test_real_shared_spec_identity_is_verified_by_macro_expansion(self):
        # 真实共享 spec：Version: %{ver}、Release: 2%{?dist} —— 未展开原文必然不等于
        # receipt，必须经 rpm.spec 宏展开后严格比对（真实 spec，非简化 fixture）。
        shutil.copyfile(REAL_SHARED_SPEC, self.root / "shared-original.spec")
        spec_text = (self.root / "shared-original.spec").read_text()
        self.assertIn("%global ver 10.6p2", spec_text)
        spec = self.write_spec("el7", "openssh", spec_text)
        receipt = self.published / "receipts" / "el7-openssh.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({
            "platform": "el7", "package": "openssh", "version": "10.6p2",
            "release": "2.el7", "tag": "el7-openssh-10.6p2-2.el7",
            "spec_sha256": sha256(spec)}))
        state = self.record([receipt])
        self.assertEqual(state["platforms"]["el7"]["openssh"], "10.6p2")
        # dist 展开：centos7 平台的 Release 应展开为 2.centos7；receipt 写 2.el7 即拒绝。
        receipt_bad = json.loads(receipt.read_text())
        receipt_bad["platform"] = "centos7"
        receipt_bad["tag"] = "centos7-openssh-10.6p2-2.el7"
        receipt.write_text(json.dumps(receipt_bad))
        spec = self.write_spec("centos7", "openssh", spec_text)
        receipt_bad["spec_sha256"] = sha256(spec)
        receipt.write_text(json.dumps(receipt_bad))
        with self.assertRaisesRegex(ValueError, "release mismatch: 2.centos7 != 2.el7"):
            self.record([receipt])
        # receipt 声称别的版本 → spec 展开不一致，拒绝。
        receipt = self.published / "receipts" / "el7-openssh.json"
        receipt.write_text(json.dumps({
            "platform": "el7", "package": "openssh", "version": "10.7p1",
            "release": "2.el7", "tag": "el7-openssh-10.7p1-2.el7",
            "spec_sha256": sha256(spec)}))
        spec = self.write_spec("el7", "openssh", spec_text)
        with self.assertRaisesRegex(ValueError, "version mismatch: 10.6p2 != 10.7p1"):
            self.record([receipt])

    def test_literal_release_with_dist_macro_expands_for_components(self):
        # 组件 spec 形态：字面 Version + Release: 1%{?dist}，按平台 dist 展开。
        receipt = self.write_rpm_receipt(
            "el8", "chrony", "4.9", "1.el8",
            spec_text="Name: chrony\nVersion: 4.9\nRelease: 1%{?dist}\nSummary: t\n"
                      "License: MIT\n\n%description\nt\n")
        state = self.record([receipt])
        self.assertEqual(state["platforms"].get("el8", {}).get("chrony"), "4.9")

    def test_unregistered_platform_is_rejected_by_config_not_by_code_lists(self):
        # el9 未在 platforms/ 注册：拒绝来自 project_config 解析（unknown platform），
        # 而非代码内平台枚举——新平台只需注册 YAML 即可用。
        receipt = self.write_rpm_receipt("el9", "chrony", "4.10", "1.el9")
        self.version_file.write_text(json.dumps(self.state))
        with self.assertRaisesRegex(ValueError, "unknown platform 'el9'"):
            record_versions.record(self.version_file, [receipt])

    def test_new_platform_el9test_end_to_end_with_real_config_parsing(self):
        # 临时 YAML 注册全新平台 el9test：真实 project_config 解析 + 真实 spec 宏
        # 展开（dist = .el9test）+ receipt 回写成功，全程不 patch 平台枚举。
        config_root = self.root / "config"
        (config_root / "packaging").mkdir(parents=True)
        (config_root / "packaging" / "upstreams.yaml").write_text(UPSTREAMS_YAML)
        platform_dir = config_root / "platforms" / "el9test"
        platform_dir.mkdir(parents=True)
        (platform_dir / "platform.yaml").write_text(
            "image: example.test/img@sha256:" + "0" * 64 + "\n"
            "family: rpm\nel: el9test\npackages:\n"
            "  chrony:\n    spec: platforms/el9test/packages/chrony/chrony.spec\n")
        source_spec = platform_dir / "packages" / "chrony" / "chrony.spec"
        source_spec.parent.mkdir(parents=True, exist_ok=True)
        source_spec.write_text("Name: chrony\nVersion: 4.11\nRelease: 1%{?dist}\n"
                               "Summary: t\nLicense: MIT\n\n%description\nt\n")
        built = self.published / "spec" / "el9test" / "chrony.spec"
        built.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_spec, built)
        receipt = self.published / "receipts" / "el9test-chrony.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({
            "platform": "el9test", "package": "chrony", "version": "4.11",
            "release": "1.el9test", "tag": "el9test-chrony-4.11-1.el9test",
            "spec_sha256": sha256(built)}))
        self.version_file.write_text(json.dumps(self.state))

        def fixture_target(platform, package):
            return project_config.get_target(platform, package, root=config_root)

        state = record_versions.record(self.version_file, [receipt],
                                       get_target=fixture_target)
        self.assertEqual(state["platforms"]["el9test"], {"chrony": "4.11"})

    def test_rpm_receipt_checks_hash_and_spec_version_field(self):
        receipt = self.write_rpm_receipt("el7", "sudo", "1.9.17p2", "1.el7")
        state = self.record([receipt])
        self.assertEqual(state["platforms"]["el7"]["sudo"], "1.9.17p2")
        self.assertEqual(state["platforms"]["el7"]["openssh"], "10.5p1")
        # spec 内容被改动 → 哈希不符，不得回写。
        spec = self.published / "spec" / "el7" / "sudo.spec"
        original = spec.read_text()
        spec.write_text(original + "# tampered\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.record([receipt])

    def test_receipt_tag_must_match_its_own_fields(self):
        receipt = self.write_rpm_receipt("el7", "sudo", "1.9.17p2", "1.el7")
        row = json.loads(receipt.read_text())
        row["tag"] = "el7-sudo-1.9.17p1-1.el7"
        receipt.write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError, "tag does not match"):
            self.record([receipt])

    def test_unknown_target_is_rejected(self):
        self.version_file.write_text(json.dumps(self.state))
        receipt = self.write_rpm_receipt("el9", "chrony", "4.10", "1.el9")
        with self.assertRaisesRegex(ValueError, "unknown platform"):
            record_versions.record(self.version_file, [receipt], get_target=rejecting_target)

    def test_old_state_format_is_rejected(self):
        self.version_file.write_text(json.dumps({"openssh": "10.5p1"}))
        receipt = self.write_rpm_receipt("el7", "sudo", "1.9.17p2", "1.el7")
        with self.assertRaisesRegex(ValueError, "unsupported version.json"):
            record_versions.record(self.version_file, [receipt], get_target=fake_target)

    def test_delimited_package_names_roundtrip(self):
        receipt = self.write_rpm_receipt("el7", "demo_tool", "1.0", "2.el7")
        state = self.record([receipt])
        self.assertEqual(state["platforms"]["el7"]["demo_tool"], "1.0")

    def test_new_platform_bootstrap_creates_its_baseline_entry(self):
        # fixture 状态本就没有 el8 平台条目；首个成功发布创建它。
        receipt = self.write_rpm_receipt("el8", "chrony", "4.10", "1.el8")
        state = self.record([receipt])
        self.assertEqual(state["platforms"]["el8"], {"chrony": "4.10"})

    def test_multiple_receipts_never_cross_downgrade(self):
        receipts = [self.write_rpm_receipt("el7", "sudo", "1.9.16", "1.el7"),
                    self.write_rpm_receipt("el7", "sudo", "1.9.17p2", "1.el7"),
                    self.write_deb_receipt("10.5p1")]
        state = self.record(receipts)
        self.assertEqual(state["platforms"]["el7"]["sudo"], "1.9.17p2")
        self.assertEqual(state["platforms"]["ubuntu2204"]["openssh"], "10.5p1")

    def test_repo_source_spec_is_never_written_back(self):
        receipt = self.write_rpm_receipt("el7", "sudo", "1.9.17p2", "1.el7")
        self.record([receipt])
        # 凭据树之外的仓库目录完全不被触碰（源 spec 版本只是默认值）。
        self.assertFalse((self.root / "spec").exists())
        written = json.loads(self.version_file.read_text())
        self.assertEqual(set(written), {"platforms"})

    def test_cli_maps_failures_to_exit_one(self):
        self.version_file.write_text(json.dumps({"openssh": "10.5p1"}))
        receipt = self.write_rpm_receipt("el7", "sudo", "1.9.17p2", "1.el7")
        self.assertEqual(
            record_versions.main([str(self.version_file), str(receipt)]), 1)


if __name__ == "__main__":
    unittest.main()
