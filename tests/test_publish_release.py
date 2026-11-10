"""Per-combination idempotent publish: assets, receipts, and re-entry integrity.

发布身份以真实 rpm header 为权威（rpmbuild 生成真实包，无 rpmbuild 环境时退回
filename-seam 单元测试）；创建成功不等于完整成功：远程资产逐字节校验通过才写
发布凭据。旧 select-release-rpm.sh 的关键行为（唯一主 RPM、错误平台隔离、
vim→vim-enhanced）在此以真实 header 测试继承。
"""

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import publish_release  # noqa: E402

HAS_RPMBUILD = shutil.which("rpmbuild") is not None


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class StatefulGh:
    """有状态 gh 假件：create 落库存，view/download 从库存读取，可注入损坏。"""

    def __init__(self):
        self.created = []
        self.store = {}      # tag -> {asset_name: bytes}
        self.drops = {}      # tag -> set(missing asset names)
        self.corruptions = {}  # tag -> {asset_name: bytes}

    def create(self, tag, assets):
        self.created.append(tag)
        self.store[tag] = {pathlib.Path(a).name: pathlib.Path(a).read_bytes() for a in assets}

    def __call__(self, *args, text=True):
        if args[:2] == ("release", "create"):
            tag = args[2]
            extra = list(args[3:])
            assets = extra[:extra.index("--repo")]
            self.create(tag, assets)
            return ""
        if args[:2] == ("release", "view"):
            tag = args[2]
            drops = self.drops.get(tag, set())
            assets = [{"name": name, "size": len(data), "state": "uploaded"}
                      for name, data in sorted((self.store.get(tag) or {}).items())
                      if name not in drops]
            return json.dumps({"assets": assets})
        if args[:2] == ("release", "download"):
            tag, pattern = args[2], args[6]
            data = dict(self.store.get(tag) or {})
            data.update(self.corruptions.get(tag, {}))
            if pattern in self.drops.get(tag, set()) or pattern not in data:
                raise KeyError(pattern)
            assert text is False, "package downloads must request binary bytes"
            return data[pattern]
        raise AssertionError("unexpected gh call: %r" % (args,))


class PublishReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.published = self.root / "published"
        self.gh = StatefulGh()
        patcher = mock.patch.object(publish_release, "github", side_effect=self.gh)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.exists = mock.patch.object(publish_release.check_update, "release_exists",
                                        return_value=False).start()
        self.addCleanup(mock.patch.stopall)

    def build_rpm_dist(self, platform="el7", package="openssh", version="10.6p2",
                       release="2.el7", header_release=None):
        """假字节 fixture：包文件名合法但内容非 RPM，read_rpm_header 由 seam 提供。"""
        dist = self.root / "dist" / platform / package
        if dist.exists():
            shutil.rmtree(dist)
        dist.mkdir(parents=True)
        names = ["%s-%s-%s.x86_64.rpm" % (name, version, release)
                 for name in (package, package + "-clients", package + "-server")]
        for name in names:
            (dist / name).write_bytes(name.encode())
        (dist / "SOURCE-SHA256SUM").write_text("source\n")
        # build.spec 需可被 rpm.spec 解析且声明全部子包（validate_rpm_set 锚定用）。
        (dist / "build.spec").write_text(
            "Name: %s\nVersion: %s\nRelease: %s\nSummary: t\nLicense: MIT\n"
            "%%package clients\nSummary: t\n%%package server\nSummary: t\n"
            "%%description\nt\n%%description clients\nt\n%%description server\nt\n"
            % (package, version, header_release or release))
        manifest = "".join(sha256((dist / n).read_bytes()) + "  ./" + n + "\n"
                           for n in names)
        (dist / "SHA256SUMS").write_text(manifest)
        return dist, names

    def fake_header(self, path):
        # filename-seam：N-V-R.arch.rpm → header 四元组（仅用于假字节 fixture）。
        stem = path.name[:-len(".x86_64.rpm")]
        name, version, release = stem.rsplit("-", 2)
        return name, version, release, "x86_64"

    def patch_fake_headers(self):
        patcher = mock.patch.object(publish_release, "read_rpm_header",
                                    side_effect=self.fake_header)
        patcher.start()
        self.addCleanup(patcher.stop)

    def build_deb_dist(self, platform="ubuntu2204", package="openssh",
                       version="10.6p2", release="2ubuntu22.04"):
        dist = self.root / "dist" / platform / package
        if dist.exists():
            shutil.rmtree(dist)
        dist.mkdir(parents=True)
        names = ["%s_%s-%s_amd64.deb" % (name, version, release)
                 for name in ("openssh-client", "openssh-server", "openssh-sftp-server")]
        for name in names:
            (dist / name).write_bytes(name.encode())
        (dist / "changelog").write_text("changelog\n")
        (dist / "build.json").write_text(json.dumps(
            {"package": package, "platform": platform, "architecture": "amd64",
             "version": version, "release": release, "deb_version": "1:" + version + "-" + release}))
        manifest = "".join(sha256((dist / n).read_bytes()) + "  ./" + n + "\n"
                           for n in names)
        (dist / "SHA256SUMS").write_text(manifest)
        return dist, names

    def publish(self, dist, platform, package, version, **kwargs):
        return publish_release.publish(
            dist, platform, package, version, "owner/repo",
            published_root=self.published, source_url="https://example.test/src.tar.gz",
            output=None, **kwargs)

    def receipt_path(self, platform, package):
        return self.published / "receipts" / ("%s-%s.json" % (platform, package))

    def prime_existing(self, tag, dist, names):
        self.exists.return_value = True
        self.gh.store[tag] = {name: (dist / name).read_bytes()
                              for name in names + ["SHA256SUMS"]}

    def test_rpm_release_carries_only_packages_and_manifest(self):
        self.patch_fake_headers()
        dist, names = self.build_rpm_dist()
        tag = self.publish(dist, "el7", "openssh", "10.6p2")
        self.assertEqual(tag, "el7-openssh-10.6p2-2.el7")
        self.assertEqual(self.gh.created, [tag])
        assets = sorted(self.gh.store[tag])
        self.assertCountEqual(assets, names + ["SHA256SUMS"])
        self.assertNotIn("build.spec", assets)
        self.assertNotIn("SOURCE-SHA256SUM", assets)
        receipt = json.loads(self.receipt_path("el7", "openssh").read_text())
        self.assertEqual(receipt, {
            "platform": "el7", "package": "openssh", "version": "10.6p2",
            "release": "2.el7", "tag": tag,
            "spec_sha256": sha256((dist / "build.spec").read_bytes())})
        self.assertEqual((self.published / "spec" / "el7" / "openssh.spec").read_bytes(),
                         (dist / "build.spec").read_bytes())

    def test_deb_release_derives_release_from_build_json(self):
        dist, names = self.build_deb_dist()
        tag = self.publish(dist, "ubuntu2204", "openssh", "10.6p2")
        self.assertEqual(tag, "ubuntu2204-openssh-10.6p2-2ubuntu22.04")
        assets = sorted(self.gh.store[tag])
        self.assertCountEqual(assets, names + ["SHA256SUMS"])
        receipt = json.loads(self.receipt_path("ubuntu2204", "openssh").read_text())
        self.assertEqual(receipt["tag"], tag)
        self.assertEqual(receipt["metadata_sha256"], sha256((dist / "build.json").read_bytes()))

    def test_reentry_with_identical_assets_is_idempotent_and_still_writes_receipt(self):
        self.patch_fake_headers()
        dist, names = self.build_rpm_dist()
        self.prime_existing("el7-openssh-10.6p2-2.el7", dist, names)
        tag = self.publish(dist, "el7", "openssh", "10.6p2")
        self.assertEqual(tag, "el7-openssh-10.6p2-2.el7")
        self.assertEqual(self.gh.created, [])
        self.assertTrue(self.receipt_path("el7", "openssh").is_file())

    def test_reentry_with_divergent_asset_fails_without_receipt_or_recreate(self):
        self.patch_fake_headers()
        dist, names = self.build_rpm_dist()
        self.prime_existing("el7-openssh-10.6p2-2.el7", dist, names)
        self.gh.store["el7-openssh-10.6p2-2.el7"]["openssh-10.6p2-2.el7.x86_64.rpm"] = b"tampered"
        with self.assertRaisesRegex(ValueError, "byte mismatch"):
            self.publish(dist, "el7", "openssh", "10.6p2")
        self.assertEqual(self.gh.created, [])
        self.assertFalse(self.receipt_path("el7", "openssh").exists())

    def test_reentry_with_unexpected_extra_asset_fails(self):
        self.patch_fake_headers()
        dist, names = self.build_rpm_dist()
        self.prime_existing("el7-openssh-10.6p2-2.el7", dist, names)
        self.gh.store["el7-openssh-10.6p2-2.el7"]["build.spec"] = b"should not be an asset"
        with self.assertRaisesRegex(ValueError, "asset set mismatch"):
            self.publish(dist, "el7", "openssh", "10.6p2")
        self.assertEqual(self.gh.created, [])

    def test_created_release_is_reverified_before_the_receipt_is_written(self):
        self.patch_fake_headers()
        dist, names = self.build_rpm_dist()
        # 情形一：create 后远程缺资产 → 无凭据（也绝不二次 create）。
        self.gh.drops["el7-openssh-10.6p2-2.el7"] = {"openssh-server-10.6p2-2.el7.x86_64.rpm"}
        with self.assertRaisesRegex(ValueError, "asset set mismatch"):
            self.publish(dist, "el7", "openssh", "10.6p2")
        self.assertEqual(self.gh.created, ["el7-openssh-10.6p2-2.el7"])
        self.assertFalse(self.receipt_path("el7", "openssh").exists())
        # 情形二：create 后远程字节损坏 → 无凭据。
        self.gh.drops.clear()
        dist, _ = self.build_rpm_dist()
        self.gh.corruptions["el7-openssh-10.6p2-2.el7"] = {
            "openssh-10.6p2-2.el7.x86_64.rpm": b"corrupt"}
        with self.assertRaisesRegex(ValueError, "byte mismatch"):
            self.publish(dist, "el7", "openssh", "10.6p2")
        # 每次 publish 至多一次 create：损坏在 create 之后的远程校验被拦下，
        # 绝不进入重试/重建路径。
        self.assertEqual(len(self.gh.created), 2)
        self.assertFalse(self.receipt_path("el7", "openssh").exists())

    def test_manifest_must_cover_exactly_the_package_files(self):
        self.patch_fake_headers()
        dist, _ = self.build_rpm_dist()
        (dist / "extra-10.6p2-2.el7.x86_64.rpm").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "cover exactly"):
            self.publish(dist, "el7", "openssh", "10.6p2")
        dist, _ = self.build_rpm_dist()
        manifest = (dist / "SHA256SUMS").read_text()
        (dist / "SHA256SUMS").write_text(manifest + sha256(b"x") + "  ./fake.rpm\n")
        with self.assertRaisesRegex(ValueError, "cover exactly"):
            self.publish(dist, "el7", "openssh", "10.6p2")
        dist, _ = self.build_rpm_dist()
        manifest = (dist / "SHA256SUMS").read_text()
        lines = manifest.splitlines()
        lines[0] = sha256(b"corrupt") + lines[0][64:]
        (dist / "SHA256SUMS").write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.publish(dist, "el7", "openssh", "10.6p2")

    def test_exactly_one_build_metadata_file_is_required(self):
        self.patch_fake_headers()
        dist, _ = self.build_rpm_dist()
        (dist / "build.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.publish(dist, "el7", "openssh", "10.6p2")
        dist, _ = self.build_rpm_dist()
        (dist / "build.spec").unlink()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.publish(dist, "el7", "openssh", "10.6p2")

    def test_bad_deb_release_metadata_fails(self):
        dist, _ = self.build_deb_dist(release="wrong")
        with self.assertRaisesRegex(ValueError, "unexpected DEB release"):
            self.publish(dist, "ubuntu2204", "openssh", "10.6p2")

    def test_build_metadata_kind_must_match_configured_family(self):
        dist, _ = self.build_deb_dist()
        with self.assertRaisesRegex(ValueError, "does not match configured family"):
            self.publish(dist, "ubuntu2204", "openssh", "10.6p2",
                         get_target=lambda platform, package: {"family": "rpm"})

    def test_new_rpm_platform_publishes_through_config_target(self):
        # 新同族平台（如 el9test）只要配置声明即可发布，无需代码枚举。
        self.patch_fake_headers()
        dist, names = self.build_rpm_dist(platform="el9test", package="chrony",
                                          version="4.11", release="1.el9test")
        tag = publish_release.publish(
            dist, "el9test", "chrony", "4.11", "owner/repo",
            published_root=self.published, get_target=lambda platform, package: {"family": "rpm"})
        self.assertEqual(tag, "el9test-chrony-4.11-1.el9test")
        self.assertCountEqual(sorted(self.gh.store[tag]), names + ["SHA256SUMS"])

    def test_main_maps_gh_failures_to_exit_one(self):
        self.patch_fake_headers()
        dist, _ = self.build_rpm_dist()
        with mock.patch.object(publish_release, "github",
                               side_effect=subprocess.CalledProcessError(1, "gh")):
            result = publish_release.main([
                "--dir", str(dist), "--platform", "el7", "--package", "openssh",
                "--version", "10.6p2", "--repo", "owner/repo",
                "--published-root", str(self.published)])
        self.assertEqual(result, 1)


@unittest.skipUnless(HAS_RPMBUILD, "rpmbuild is required for real-header tests")
class RealHeaderSelectionTest(unittest.TestCase):
    """旧选择器行为的真实 header 继承：唯一主 RPM、平台隔离、vim-enhanced、
    header 权威 release、分隔符包名。"""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.top = pathlib.Path(cls.temp.name)
        for directory in ("BUILD", "SOURCES", "RPMS", "SRPMS", "SPECS"):
            (cls.top / directory).mkdir()
        (cls.top / "SOURCES" / "payload.txt").write_text("payload\n")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def build_rpm(cls, name, version, release, arch="x86_64"):
        spec = cls.top / "SPECS" / ("%s.spec" % name)
        spec.write_text(
            "Name: %s\nVersion: %s\nRelease: %s\nSummary: t\nLicense: MIT\n"
            "Source1: payload.txt\n\n%%description\nt\n\n%%install\n"
            "cp %%{SOURCE1} %%{buildroot}/p.txt\n\n%%files\n/p.txt\n" % (name, version, release))
        subprocess.run(
            ["rpmbuild", "-bb", "--target", arch,
             "--define", "_topdir %s" % cls.top, str(spec)],
            capture_output=True, text=True, check=True)
        built = (cls.top / "RPMS" / arch) / ("%s-%s-%s.%s.rpm" % (name, version, release, arch))
        if not built.is_file():
            raise AssertionError("rpmbuild did not produce " + built.name)
        return built

    def dist_dir(self, platform, package, files):
        dist = self.top / "dist" / platform / package
        if dist.exists():
            shutil.rmtree(dist)
        dist.mkdir(parents=True, exist_ok=True)
        for source in files:
            shutil.copyfile(source, dist / source.name)
        (dist / "build.spec").write_text("Name: %s\n" % package)
        names = sorted(path.name for path in dist.glob("*.rpm"))
        manifest = "".join(sha256((dist / n).read_bytes()) + "  ./" + n + "\n" for n in names)
        (dist / "SHA256SUMS").write_text(manifest)
        return dist

    def select(self, dist, package, version):
        return publish_release.select_main_rpm(dist, package, version)

    def test_header_release_is_authoritative_over_filename(self):
        # 文件名 release 段被故意写错；tag 必须来自 header 权威元数据。
        real = self.build_rpm("chrony", "4.9", "1.el8")
        spoofed_name = "chrony-4.9-99.el8.x86_64.rpm"
        dist = self.dist_dir("el8", "chrony", [real])
        (dist / real.name).rename(dist / spoofed_name)
        manifest = sha256((dist / spoofed_name).read_bytes()) + "  ./" + spoofed_name + "\n"
        (dist / "SHA256SUMS").write_text(manifest)
        with self.assertRaisesRegex(ValueError, "filename does not match RPM header"):
            self.select(dist, "chrony", "4.9")

    def test_main_rpm_without_dist_suffix_cannot_disguise_its_filename(self):
        # header release 无发行后缀（"1"）却伪装成带 .el8 的文件名 → 拒绝。
        bare = self.build_rpm("chrony", "4.9", "1")
        dist = self.dist_dir("el8", "chrony", [bare])
        (dist / bare.name).rename(dist / "chrony-4.9-1.el8.x86_64.rpm")
        with self.assertRaisesRegex(ValueError, "filename does not match RPM header"):
            self.select(dist, "chrony", "4.9")

    def test_primary_must_be_exactly_one_across_revisions(self):
        first = self.build_rpm("chrony", "4.9", "1.el8")
        second = self.build_rpm("chrony", "4.9", "2.el8")
        dist = self.dist_dir("el8", "chrony", [first, second])
        with self.assertRaisesRegex(ValueError, "需要且仅需一个主 RPM"):
            self.select(dist, "chrony", "4.9")

    def test_wrong_platform_rpm_is_isolated_by_spec_expansion(self):
        # 平台归属不拼文件名双后缀，而由 spec 宏展开（dist = .<platform>）独立验证。
        el8 = self.build_rpm("chrony", "4.9", "1.el8")
        for platform, dist_release in (("el7", "2.el7"), ("centos7", "2.centos7")):
            dist = self.dist_dir(platform, "chrony", [el8])
            (dist / "build.spec").write_text(
                "Name: chrony\nVersion: 4.9\nRelease: 2%{?dist}\nSummary: t\nLicense: MIT\n\n"
                "%description\nt\n")
            _, release = self.select(dist, "chrony", "4.9")
            self.assertEqual(release, "1.el8")
            with self.assertRaisesRegex(ValueError, "expanded identity mismatch"):
                publish_release.validate_rpm_set(dist, "chrony", "4.9", release,
                                                 dist / "build.spec", platform)

    def test_renamed_subpackage_is_rejected(self):
        main = self.build_rpm("chrony", "4.9", "1.el8")
        sub = self.build_rpm("chrony-debuginfo", "4.9", "1.el8")
        dist = self.dist_dir("el8", "chrony", [main, sub])
        (dist / "build.spec").write_text(
            "Name: chrony\nVersion: 4.9\nRelease: 1%{?dist}\nSummary: t\nLicense: MIT\n\n"
            "%description\nt\n")
        publish_release.validate_rpm_set(dist, "chrony", "4.9", "1.el8", dist / "build.spec", "el8")
        (dist / sub.name).rename(dist / "chrony-dbg-4.9-1.el8.x86_64.rpm")
        with self.assertRaisesRegex(ValueError, "filename does not match RPM header"):
            publish_release.validate_rpm_set(dist, "chrony", "4.9", "1.el8", dist / "build.spec", "el8")

    def test_vim_primary_falls_back_to_enhanced_package(self):
        enhanced = self.build_rpm("vim-enhanced", "9.2.1000", "1.el8")
        dist = self.dist_dir("el8", "vim", [enhanced])
        _, release = self.select(dist, "vim", "9.2.1000")
        self.assertEqual(release, "1.el8")

    def test_hyphenated_and_underscored_package_names_select_cleanly(self):
        hyphen = self.build_rpm("demo-tool", "1.0", "2.el7")
        underscore = self.build_rpm("demo_tool", "1.0", "2.el7")
        for package, rpm_path in (("demo-tool", hyphen), ("demo_tool", underscore)):
            dist = self.dist_dir("el7", package, [rpm_path])
            path, release = self.select(dist, package, "1.0")
            self.assertEqual(release, "2.el7")
            self.assertEqual(path.name, rpm_path.name)

    def test_unrelated_same_evr_package_is_rejected_by_spec_set(self):
        chrony = self.build_rpm("chrony", "4.9", "1.el8")
        intruder = self.build_rpm("intruder", "4.9", "1.el8")
        dist = self.dist_dir("el8", "chrony", [chrony, intruder])
        (dist / "build.spec").write_text(
            "Name: chrony\nVersion: 4.9\nRelease: 1%{?dist}\nSummary: t\nLicense: MIT\n\n"
            "%description\nt\n")
        with self.assertRaisesRegex(ValueError, "unrelated RPM not declared by build.spec"):
            publish_release.validate_rpm_set(dist, "chrony", "4.9", "1.el8",
                                             dist / "build.spec", "el8")
        (dist / intruder.name).unlink()
        publish_release.validate_rpm_set(dist, "chrony", "4.9", "1.el8",
                                         dist / "build.spec", "el8")

    def test_spec_declared_subpackages_and_debug_are_allowed(self):
        # 非前缀子包（ntpdate/sntp 形态）与自动生成的 debuginfo 合法；
        # 子包 V/R 与主包不一致仍然拒绝。
        main = self.build_rpm("ntp", "4.2.8", "1.el8")
        sub = self.build_rpm("ntpdate", "4.2.8", "1.el8")
        debug = self.build_rpm("ntp-debuginfo", "4.2.8", "1.el8")
        stray = self.build_rpm("ntpdate", "4.2.8", "2.el8")
        dist = self.dist_dir("el8", "ntp", [main, sub, debug])
        (dist / "build.spec").write_text(
            "Name: ntp\nVersion: 4.2.8\nRelease: 1%{?dist}\nSummary: t\nLicense: MIT\n"
            "%package -n ntpdate\nSummary: t\n%description -n ntpdate\nt\n"
            "%description\nt\n")
        publish_release.validate_rpm_set(dist, "ntp", "4.2.8", "1.el8",
                                         dist / "build.spec", "el8")
        shutil.copyfile(stray, dist / stray.name)
        with self.assertRaisesRegex(ValueError, "V/R differs from primary header"):
            publish_release.validate_rpm_set(dist, "ntp", "4.2.8", "1.el8",
                                             dist / "build.spec", "el8")


if __name__ == "__main__":
    unittest.main()
