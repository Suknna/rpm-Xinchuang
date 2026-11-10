"""平台独立发布：prune/record 平台 scope、merged 维护拆分与并发回写契约。

覆盖新 CI 调度（各平台独立检测构建发布）所需的最小显式接口：

* prune --platform 严格限定凭据平台：跨平台/前缀相似（el7x）凭据在任何远程
  调用或删除之前拒绝（artifact 下载 pattern el7-* 可能匹配 el7-extra）。
* --skip-merged 平台普通清理：不触碰跨平台 merged v*，也不为他平台替代做
  完整性校验；本平台普通组合照常先校验后删除。
* --merged-only 父维护：只处理 merged v*，不接 receipt、不删普通组合；
  双平台完整替代门槛、真实资产校验、tag 保留与 dry-run 全部保持。
* record --platform：预检全部凭据后才写盘，坏凭据/他平台凭据零写入。
* 本地临时 bare git + 双 clone 模拟两平台并发回写：non-fast-forward 失败后
  fetch 最新重放，两边基线都保留且防降级（全程本地，不触 GitHub）。

不传任何 flag 的默认行为与既有语义保持不变（由 test_prune_releases /
test_record_versions 继续守护）。
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
import prune_releases  # noqa: E402
import record_versions  # noqa: E402

PLATFORMS = ("el7", "el8", "centos7", "ubuntu2204")
RPM_PACKAGES = ("openssh", "chrony", "bash", "sudo", "ntp", "telnet")
UPSTREAMS = {package: {"version_pattern": r"\d+"} for package in RPM_PACKAGES}
COMBOS = {(platform, package) for platform in ("el7", "el8", "centos7")
          for package in RPM_PACKAGES} | {("ubuntu2204", "openssh")}
FAMILIES = {"el7": "rpm", "el8": "rpm", "centos7": "rpm", "ubuntu2204": "deb"}


def fake_target(platform, package):
    """宽松 fixture 目标解析：组合合法性由 prune 的 combos 校验自行把关。"""
    return {"family": "deb" if platform == "ubuntu2204" else "rpm"}


def temp_dir():
    pathlib.Path("/tmp/opencode").mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir="/tmp/opencode")


class PruneFixture(unittest.TestCase):
    """内存远端 + 本地凭据树的 prune 夹具（记录每一次 gh 调用与删除）。"""

    def setUp(self):
        self.temp = temp_dir()
        self.addCleanup(self.temp.cleanup)
        self.published = pathlib.Path(self.temp.name) / "published"
        self.pages = [[]]
        self.downloads = {}
        self.deleted = []
        self.next_id = 1
        self.remote_calls = []
        self.api = mock.patch.object(prune_releases, "github",
                                     side_effect=self.github).start()
        self.addCleanup(mock.patch.stopall)

    # ---- receipt fixtures（自带可预检的凭据树） ----

    def receipt(self, platform, package, version, release):
        if platform == "ubuntu2204":
            metadata = {"package": package, "platform": platform, "architecture": "amd64",
                        "version": version, "release": release,
                        "deb_version": "1:" + version + "-" + release}
            built = self.published / "metadata" / (platform + "-" + package + ".json")
            built.parent.mkdir(parents=True, exist_ok=True)
            built.write_text(json.dumps(metadata))
            anchor = "metadata_sha256"
        else:
            built = self.published / "spec" / platform / (package + ".spec")
            built.parent.mkdir(parents=True, exist_ok=True)
            built.write_text("Name: %s\nVersion: %s\nRelease: %s\nSummary: t\n"
                             "License: MIT\n\n%%description\nt\n" % (package, version, release))
            anchor = "spec_sha256"
        receipt = self.published / "receipts" / (platform + "-" + package + ".json")
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({
            "platform": platform, "package": package, "version": version,
            "release": release, "tag": "%s-%s-%s-%s" % (platform, package, version, release),
            anchor: hashlib.sha256(built.read_bytes()).hexdigest()}))
        return receipt

    def prune(self, receipts, dry_run=False, combos=COMBOS, **kwargs):
        return prune_releases.prune("owner/repo", [str(path) for path in receipts],
                                    PLATFORMS, UPSTREAMS, combos, FAMILIES,
                                    dry_run=dry_run, get_target=fake_target, **kwargs)

    # ---- remote fixtures ----

    def release(self, tag):
        key = prune_releases.parse_tag(tag, PLATFORMS, set(UPSTREAMS), FAMILIES)
        release = {"id": self.next_id, "tag_name": tag, "draft": False,
                   "prerelease": False, "assets": []}
        self.next_id += 1
        self.pages[-1].append(release)
        if key is None:
            return release
        if key.family == "deb":
            names = ["%s_%s-%s_amd64.deb" % (package, key.version, key.release)
                     for package in prune_releases.UBI_DEB_PACKAGES]
            checksums = []
            for name in names:
                data = name.encode()
                checksum = hashlib.sha256(data).hexdigest()
                release["assets"].append({"name": name, "size": len(data),
                                          "state": "uploaded", "digest": "sha256:" + checksum})
                self.downloads[tag, name] = data
                checksums.append(checksum + "  ./" + name)
            self.downloads[tag, "SHA256SUMS"] = "\n".join(checksums) + "\n"
            release["assets"].append({"name": "SHA256SUMS", "size": 100, "state": "uploaded"})
            return release
        platforms = ("el7", "el8") if key.platform == "all" else (key.platform,)
        for platform in platforms:
            revision = key.release + "." + platform if key.platform == "all" else key.release
            packages = (("openssh", "openssh-clients", "openssh-server")
                        if key.package == "openssh" else (key.package,))
            checksums = []
            for package in packages:
                name = "%s-%s-%s.x86_64.rpm" % (package, key.version, revision)
                data = name.encode()
                checksum = hashlib.sha256(data).hexdigest()
                release["assets"].append({"name": name, "size": len(data),
                                          "state": "uploaded", "digest": "sha256:" + checksum})
                self.downloads[tag, name] = data
                checksums.append(checksum + "  ./" + name)
            manifest = "SHA256SUMS-" + platform if key.platform == "all" else "SHA256SUMS"
            self.downloads[tag, manifest] = "\n".join(checksums) + "\n"
            release["assets"].append({"name": manifest, "size": 100, "state": "uploaded"})
        return release

    def github(self, *args, text=True):
        self.remote_calls.append(args)
        if args == ("api", "--paginate", "--slurp", "repos/owner/repo/releases?per_page=100"):
            return json.dumps(self.pages)
        if args[:2] == ("release", "download"):
            data = self.downloads[args[2], args[6]]
            self.assertEqual(text, isinstance(data, str))
            return data
        self.assertEqual(args[:3], ("api", "--method", "DELETE"))
        self.deleted.append(int(args[3].rsplit("/", 1)[1]))
        return ""


class PlatformScopedPruneTest(PruneFixture):
    """--platform 限定凭据目标：scope 在任何远程调用之前精确把关。"""

    def test_foreign_receipt_is_rejected_before_any_remote_call(self):
        self.release("el7-chrony-4.10-1.el7")
        self.release("el8-bash-5.3-1.el8")
        receipts = [self.receipt("el7", "chrony", "4.10", "1.el7"),
                    self.receipt("el8", "bash", "5.3", "1.el8")]
        with self.assertRaisesRegex(ValueError, "outside platform scope 'el7'"):
            self.prune(receipts, platform="el7")
        self.assertEqual(self.remote_calls, [], "scope 拒绝时不得发起任何远程调用")
        self.assertEqual(self.deleted, [])

    def test_similar_prefix_platform_receipt_is_rejected_before_remote(self):
        # artifact 下载 pattern el7-* 可能带入 el7-extra 凭据：el7x 与 el7
        # 前缀相似但字段必须精确相等，否则在任何远程调用前拒绝。
        self.release("el7-chrony-4.10-1.el7")
        foreign = self.receipt("el7x", "chrony", "4.10", "1.el7x")
        with self.assertRaisesRegex(ValueError, "outside platform scope 'el7'"):
            self.prune([foreign], platform="el7")
        self.assertEqual(self.remote_calls, [])
        self.assertEqual(self.deleted, [])

    def test_unknown_platform_scope_is_rejected_locally(self):
        receipt = self.receipt("el7", "chrony", "4.10", "1.el7")
        with self.assertRaisesRegex(ValueError, "unknown platform scope"):
            self.prune([receipt], platform="el9x")
        self.assertEqual(self.remote_calls, [])
        self.assertEqual(self.deleted, [])

    def test_platform_scope_prunes_only_its_own_combinations(self):
        old = self.release("el7-chrony-4.9-1.el7")
        keeper = self.release("el7-chrony-4.10-1.el7")
        el8_old = self.release("el8-chrony-4.9-1.el8")
        el8_new = self.release("el8-chrony-4.10-1.el8")
        self.prune([self.receipt("el7", "chrony", "4.10", "1.el7")], platform="el7")
        self.assertEqual(self.deleted, [old["id"]])
        for release in (keeper, el8_old, el8_new):
            self.assertNotIn(release["id"], self.deleted)


class SkipMergedPruneTest(PruneFixture):
    """--skip-merged 平台普通清理：merged v* 完全不触碰。"""

    def test_skip_merged_keeps_merged_and_skips_foreign_replacement_verification(self):
        # el8 替代资产不完整：默认路径必须报错（既有门槛），skip_merged 后
        # 平台普通清理不为他平台替代做完整性校验，v* 也绝不删除。
        merged = self.release("v10.5p1-2")
        self.release("el7-openssh-10.6p2-2.el7")
        el8 = self.release("el8-openssh-10.6p2-2.el8")
        el8["assets"] = [a for a in el8["assets"] if "openssh-server" not in a["name"]]
        old = self.release("el7-chrony-4.9-1.el7")
        keeper = self.release("el7-chrony-4.10-1.el7")
        receipt = self.receipt("el7", "chrony", "4.10", "1.el7")
        with self.assertRaisesRegex(ValueError, "primary RPM"):
            self.prune([receipt], platform="el7")
        self.assertEqual(self.deleted, [])
        self.prune([receipt], platform="el7", skip_merged=True)
        self.assertEqual(self.deleted, [old["id"]], "本平台普通清理照常进行")
        self.assertNotIn(merged["id"], self.deleted, "merged v* 绝不因 skip_merged 被触碰")

    def test_skip_merged_without_platform_scope_still_prunes_own_combos(self):
        merged = self.release("v10.5p1-2")
        old = self.release("el7-bash-5.2-1.el7")
        keeper = self.release("el7-bash-5.3-1.el7")
        self.prune([self.receipt("el7", "bash", "5.3", "1.el7")], skip_merged=True)
        self.assertEqual(self.deleted, [old["id"]])
        self.assertNotIn(keeper["id"], self.deleted)
        self.assertNotIn(merged["id"], self.deleted)


class MergedOnlyPruneTest(PruneFixture):
    """--merged-only 父维护：只处理 v*，普通组合绝不删除，安全验证不复制。"""

    def test_merged_only_deletes_only_safely_replaced_merged_releases(self):
        v_first = self.release("v10.5p1")
        v_second = self.release("v10.5p1-2")
        v_higher = self.release("v10.7p1-2")
        el7 = self.release("el7-openssh-10.6p2-2.el7")
        el8 = self.release("el8-openssh-10.6p2-2.el8")
        combo_old = self.release("el7-chrony-4.9-1.el7")
        combo_new = self.release("el7-chrony-4.10-1.el7")
        self.prune([], merged_only=True)
        self.assertCountEqual(self.deleted, [v_first["id"], v_second["id"]])
        for release in (v_higher, el7, el8, combo_old, combo_new):
            self.assertNotIn(release["id"], self.deleted, "父维护绝不删除普通组合")

    def test_merged_only_dry_run_verifies_without_deletion(self):
        self.release("v10.5p1")
        self.release("el7-openssh-10.6p2-2.el7")
        self.release("el8-openssh-10.6p2-2.el8")
        self.prune([], dry_run=True, merged_only=True)
        self.assertEqual(self.deleted, [])
        self.assertTrue(any(call[:2] == ("release", "download") for call in self.remote_calls),
                        "dry-run 仍必须真实校验替代资产")

    def test_merged_only_keeps_merged_when_replacement_is_incomplete(self):
        self.release("v10.5p1-2")
        self.release("el7-openssh-10.6p2-2.el7")
        el8 = self.release("el8-openssh-10.6p2-2.el8")
        el8["assets"] = [a for a in el8["assets"] if "openssh-server" not in a["name"]]
        with self.assertRaisesRegex(ValueError, "primary RPM"):
            self.prune([], merged_only=True)
        self.assertEqual(self.deleted, [])

    def test_merged_only_rejects_corrupt_replacement_before_any_deletion(self):
        self.release("v10.5p1-2")
        el7 = self.release("el7-openssh-10.6p2-2.el7")
        self.release("el8-openssh-10.6p2-2.el8")
        el7["assets"][0]["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.prune([], merged_only=True)
        self.assertEqual(self.deleted, [])

    def test_merged_only_respects_enabled_combo_registry(self):
        # enabled combos 是事实源：任一平台未配置/禁用即绝不删除 merged。
        merged = self.release("v10.5p1-2")
        self.release("el7-openssh-10.6p2-2.el7")
        self.release("el8-openssh-10.6p2-2.el8")
        self.prune([], merged_only=True, combos=COMBOS - {("el8", "openssh")})
        self.assertEqual(self.deleted, [])
        self.assertNotIn(merged["id"], self.deleted)

    def test_merged_only_rejects_receipts_and_conflicting_flags(self):
        receipt = self.receipt("el7", "chrony", "4.10", "1.el7")
        with self.assertRaisesRegex(ValueError, "receipt"):
            self.prune([receipt], merged_only=True)
        with self.assertRaisesRegex(ValueError, "互相冲突"):
            self.prune([], merged_only=True, skip_merged=True)
        with self.assertRaisesRegex(ValueError, "platform"):
            self.prune([], merged_only=True, platform="el7")
        self.assertEqual(self.remote_calls, [], "模式冲突必须在任何远程调用前拒绝")


class PruneCliTest(unittest.TestCase):
    """CLI 标志接线与互斥校验（不依赖真实远端）。"""

    def test_cli_rejects_merged_only_with_receipts(self):
        with self.assertRaises(SystemExit) as ctx:
            prune_releases.main(["--repo", "owner/repo", "--merged-only", "receipt.json"])
        self.assertEqual(ctx.exception.code, 2)

    def test_cli_rejects_merged_only_with_skip_merged(self):
        with self.assertRaises(SystemExit) as ctx:
            prune_releases.main(["--repo", "owner/repo", "--merged-only", "--skip-merged"])
        self.assertEqual(ctx.exception.code, 2)

    def test_cli_rejects_merged_only_with_platform(self):
        with self.assertRaises(SystemExit) as ctx:
            prune_releases.main(["--repo", "owner/repo", "--merged-only", "--platform", "el7"])
        self.assertEqual(ctx.exception.code, 2)

    def test_cli_requires_receipts_unless_merged_only(self):
        with self.assertRaises(SystemExit) as ctx:
            prune_releases.main(["--repo", "owner/repo"])
        self.assertEqual(ctx.exception.code, 2)

    def test_cli_wires_platform_flags_into_prune(self):
        with mock.patch.object(prune_releases, "prune") as prune:
            prune_releases.main(["--repo", "owner/repo", "--platform", "el7",
                                 "--skip-merged", "receipt.json"])
        prune.assert_called_once()
        self.assertEqual(prune.call_args.args[6], False, "dry_run")
        self.assertEqual(prune.call_args.kwargs,
                         {"platform": "el7", "skip_merged": True, "merged_only": False})

    def test_cli_wires_merged_only_without_receipts(self):
        with mock.patch.object(prune_releases, "prune") as prune:
            prune_releases.main(["--repo", "owner/repo", "--merged-only", "--dry-run"])
        prune.assert_called_once()
        self.assertEqual(prune.call_args.args[6], True, "dry_run")
        self.assertEqual(prune.call_args.args[1], [], "merged-only 不接 receipt")
        self.assertEqual(prune.call_args.kwargs,
                         {"platform": None, "skip_merged": False, "merged_only": True})


class RecordPlatformScopeTest(unittest.TestCase):
    """record --platform：预检全部凭据后才写盘，他平台凭据零写入。"""

    def setUp(self):
        self.temp = temp_dir()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.published = self.root / "published"
        self.version_file = self.root / "version.json"
        self.state = {"platforms": {"el7": {"sudo": "1.9.16"},
                                    "ubuntu2204": {"openssh": "10.7p1"}}}
        self.write_version_file(self.state)

    def write_version_file(self, state):
        self.version_file.write_text(json.dumps(state) + "\n", encoding="utf-8")

    def write_rpm_receipt(self, platform, package, version, release):
        spec = self.published / "spec" / platform / (package + ".spec")
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text("Name: %s\nVersion: %s\nRelease: %s\nSummary: t\n"
                        "License: MIT\n\n%%description\nt\n" % (package, version, release))
        receipt = self.published / "receipts" / (platform + "-" + package + ".json")
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({
            "platform": platform, "package": package, "version": version,
            "release": release, "tag": "%s-%s-%s-%s" % (platform, package, version, release),
            "spec_sha256": hashlib.sha256(spec.read_bytes()).hexdigest()}))
        return receipt

    def write_deb_receipt(self, version, release="2ubuntu22.04"):
        metadata = {"package": "openssh", "platform": "ubuntu2204", "architecture": "amd64",
                    "version": version, "release": release,
                    "deb_version": "1:" + version + "-" + release}
        meta = self.published / "metadata" / "ubuntu2204-openssh.json"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps(metadata))
        receipt = self.published / "receipts" / "ubuntu2204-openssh.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({
            "platform": "ubuntu2204", "package": "openssh", "version": version,
            "release": release, "tag": "ubuntu2204-openssh-%s-%s" % (version, release),
            "metadata_sha256": hashlib.sha256(meta.read_bytes()).hexdigest()}))
        return receipt

    def record(self, receipts, platform=None):
        return record_versions.record(self.version_file, receipts,
                                      get_target=fake_target, platform=platform)

    def test_foreign_receipt_is_rejected_without_any_write(self):
        el7 = self.write_rpm_receipt("el7", "sudo", "1.9.17p2", "1.el7")
        deb = self.write_deb_receipt("10.8p1")
        before = self.version_file.read_bytes()
        with self.assertRaisesRegex(ValueError, "outside platform scope 'el7'"):
            self.record([el7, deb], platform="el7")
        self.assertEqual(self.version_file.read_bytes(), before, "零写入")

    def test_similar_prefix_platform_receipt_is_rejected_without_write(self):
        foreign = self.write_rpm_receipt("el7x", "sudo", "1.9.17p2", "1.el7x")
        before = self.version_file.read_bytes()
        with self.assertRaisesRegex(ValueError, "outside platform scope 'el7'"):
            self.record([foreign], platform="el7")
        self.assertEqual(self.version_file.read_bytes(), before)

    def test_all_receipts_are_prechecked_before_any_write(self):
        good = self.write_rpm_receipt("el7", "sudo", "1.9.17p2", "1.el7")
        self.record([good])
        applied = json.loads(self.version_file.read_text())
        other = self.write_rpm_receipt("el7", "bash", "5.3", "1.el7")
        spec = self.published / "spec" / "el7" / "bash.spec"
        spec.write_text(spec.read_text() + "# tampered\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.record([other, good], platform="el7")
        self.assertEqual(json.loads(self.version_file.read_text()), applied,
                         "一张坏凭据 = 整批零写入")

    def test_platform_scope_applies_only_own_rows(self):
        deb = self.write_deb_receipt("10.8p1")
        state = self.record([deb], platform="ubuntu2204")
        self.assertEqual(state["platforms"]["ubuntu2204"]["openssh"], "10.8p1")
        self.assertEqual(state["platforms"]["el7"], {"sudo": "1.9.16"})

    def test_cli_platform_flag_records_own_platform(self):
        receipt = self.write_rpm_receipt("el7", "sudo", "1.9.17p2", "1.el7")
        with mock.patch.object(record_versions.project_config, "get_target", fake_target):
            code = record_versions.main(["--platform", "el7",
                                         str(self.version_file), str(receipt)])
        self.assertEqual(code, 0)
        state = json.loads(self.version_file.read_text())
        self.assertEqual(state["platforms"]["el7"]["sudo"], "1.9.17p2")
        self.assertEqual(state["platforms"]["ubuntu2204"]["openssh"], "10.7p1")

    def test_cli_foreign_receipt_fails_without_write(self):
        deb = self.write_deb_receipt("10.8p1")
        el7 = self.write_rpm_receipt("el7", "sudo", "1.9.17p2", "1.el7")
        before = self.version_file.read_bytes()
        with mock.patch.object(record_versions.project_config, "get_target", fake_target):
            code = record_versions.main(["--platform", "el7",
                                         str(self.version_file), str(deb), str(el7)])
        self.assertEqual(code, 1)
        self.assertEqual(self.version_file.read_bytes(), before)


class ConcurrentWritebackTest(unittest.TestCase):
    """本地 bare git + 双 clone 模拟两平台并发回写（不触 GitHub）。"""

    def setUp(self):
        self.temp = temp_dir()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.published = self.root / "published"
        seed = self.root / "seed"
        seed.mkdir()
        self.git(seed, "init", "-b", "main")
        (seed / "version.json").write_text(json.dumps(
            {"platforms": {"el7": {"sudo": "1.9.16"},
                           "ubuntu2204": {"openssh": "10.7p1"}}},
            indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.git(seed, "add", "version.json")
        self.git(seed, "commit", "-m", "seed baselines")
        self.git(self.root, "clone", "--bare", "seed", "origin.git")
        self.clone_a = self.root / "clone-el7"
        self.clone_b = self.root / "clone-ubuntu"
        self.git(self.root, "clone", "origin.git", "clone-el7")
        self.git(self.root, "clone", "origin.git", "clone-ubuntu")

    def git(self, workdir, *args, check=True):
        result = subprocess.run(
            ["git", "-C", str(workdir), *args], check=False,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env=dict(os.environ, GIT_AUTHOR_NAME="platform-ci",
                     GIT_AUTHOR_EMAIL="ci@example.test",
                     GIT_COMMITTER_NAME="platform-ci",
                     GIT_COMMITTER_EMAIL="ci@example.test"))
        if check and result.returncode != 0:
            raise AssertionError("git %s failed: %s" % (" ".join(args), result.stdout))
        return result

    def rpm_receipt(self, platform, package, version, release):
        spec = self.published / "spec" / platform / (package + ".spec")
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text("Name: %s\nVersion: %s\nRelease: %s\nSummary: t\n"
                        "License: MIT\n\n%%description\nt\n" % (package, version, release))
        receipt = self.published / "receipts" / (platform + "-" + package + ".json")
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({
            "platform": platform, "package": package, "version": version,
            "release": release, "tag": "%s-%s-%s-%s" % (platform, package, version, release),
            "spec_sha256": hashlib.sha256(spec.read_bytes()).hexdigest()}))
        return receipt

    def deb_receipt(self, version, release="2ubuntu22.04"):
        metadata = {"package": "openssh", "platform": "ubuntu2204", "architecture": "amd64",
                    "version": version, "release": release,
                    "deb_version": "1:" + version + "-" + release}
        meta = self.published / "metadata" / "ubuntu2204-openssh.json"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps(metadata))
        receipt = self.published / "receipts" / "ubuntu2204-openssh.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({
            "platform": "ubuntu2204", "package": "openssh", "version": version,
            "release": release, "tag": "ubuntu2204-openssh-%s-%s" % (version, release),
            "metadata_sha256": hashlib.sha256(meta.read_bytes()).hexdigest()}))
        return receipt

    def record(self, clone, receipt, platform):
        return record_versions.record(clone / "version.json", [receipt],
                                      get_target=fake_target, platform=platform)

    def test_concurrent_platform_writeback_replays_after_nonfastforward(self):
        # 平台 A（el7）：基于基线回写并抢先推送成功。
        self.record(self.clone_a, self.rpm_receipt("el7", "sudo", "1.9.17p2", "1.el7"), "el7")
        self.git(self.clone_a, "add", "version.json")
        self.git(self.clone_a, "commit", "-m", "record el7/sudo")
        self.git(self.clone_a, "push", "origin", "main")
        # 平台 B（ubuntu2204）：基于过期基线回写提交，推送被 non-fast-forward 拒绝；
        # 若强推成功，A 的 el7 基线更新将被过期内容覆盖（降级/丢失）。
        self.record(self.clone_b, self.deb_receipt("10.8p1"), "ubuntu2204")
        self.git(self.clone_b, "add", "version.json")
        self.git(self.clone_b, "commit", "-m", "record ubuntu2204/openssh")
        failed = self.git(self.clone_b, "push", "origin", "main", check=False)
        self.assertNotEqual(failed.returncode, 0, "并发推送必须被 non-fast-forward 拒绝")
        # 工作流同款重试：每轮取最新远端分支重放，无 rebase 状态残留。
        self.git(self.clone_b, "fetch", "origin")
        self.git(self.clone_b, "checkout", "-f", "-B", "main", "origin/main")
        self.record(self.clone_b, self.deb_receipt("10.8p1"), "ubuntu2204")
        self.git(self.clone_b, "add", "version.json")
        self.git(self.clone_b, "commit", "-m", "replay record ubuntu2204/openssh")
        self.git(self.clone_b, "push", "origin", "main")
        # 两边基线都保留：A 的更新未被 B 的过期回写覆盖。
        final = json.loads((self.clone_b / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(final["platforms"]["el7"]["sudo"], "1.9.17p2")
        self.assertEqual(final["platforms"]["ubuntu2204"]["openssh"], "10.8p1")
        self.git(self.clone_a, "fetch", "origin")
        replayed = json.loads(
            self.git(self.clone_a, "show", "origin/main:version.json").stdout)
        self.assertEqual(replayed["platforms"]["ubuntu2204"]["openssh"], "10.8p1")
        # 防降级：较低版本补发重放不得回退基线。
        self.record(self.clone_a, self.rpm_receipt("el7", "sudo", "1.9.16", "9.el7"), "el7")
        state = json.loads((self.clone_a / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(state["platforms"]["el7"]["sudo"], "1.9.17p2")


if __name__ == "__main__":
    unittest.main()
