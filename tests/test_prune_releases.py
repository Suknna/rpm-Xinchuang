"""Centralized retention: highest verified EVR per combination, legacy fallbacks honored.

receipt fixture 自带可被 record_versions.read_receipt 预检的凭据树（构建 spec /
DEB 元数据 + 哈希），保证「先本地预检、后远程校验、再删除」的真实语义。
"""

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

PLATFORMS = ("el7", "el8", "centos7", "ubuntu2204")
RPM_PACKAGES = ("openssh", "chrony", "bash", "sudo", "ntp", "telnet", "demo-tool", "demo_tool")
UPSTREAMS = {package: {"version_pattern": pattern} for package, pattern in (
    ("openssh", r"\d+\.\d+p\d+"), ("chrony", r"\d+(?:\.\d+)+"), ("bash", r"\d+(?:\.\d+)+"),
    ("sudo", r"\d+(?:\.\d+)+p\d+"), ("ntp", r"\d+(?:\.\d+)+p\d+"),
    ("telnet", r"\d+(?:\.\d+)+"), ("demo-tool", r"\d+(?:\.\d+)+"),
    ("demo_tool", r"\d+(?:\.\d+)+"))}
COMBOS = {(platform, package) for platform in ("el7", "el8", "centos7")
          for package in RPM_PACKAGES} | {("ubuntu2204", "openssh")}
FAMILIES = {"el7": "rpm", "el8": "rpm", "centos7": "rpm", "ubuntu2204": "deb"}


def fake_target(platform, package):
    """宽松 fixture 目标解析：注入 read_receipt，让组合合法性由 prune 自行把关。"""
    return {"family": "deb" if platform == "ubuntu2204" else "rpm"}


class ReleaseRetentionTest(unittest.TestCase):
    def setUp(self):
        self.pages = [[]]
        self.downloads = {}
        self.deleted = []
        self.next_id = 1
        self.remote_calls = []
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.published = pathlib.Path(self.temp.name) / "published"
        self.api = mock.patch.object(prune_releases, "github",
                                     side_effect=self.github).start()
        self.addCleanup(mock.patch.stopall)

    # ---- receipt fixtures（自带可预检的凭据树） ----

    def receipt(self, platform, package, version, release, tag=None):
        tag = tag or "%s-%s-%s-%s" % (platform, package, version, release)
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
        row = {"platform": platform, "package": package, "version": version,
               "release": release, "tag": tag,
               anchor: hashlib.sha256(built.read_bytes()).hexdigest()}
        receipt.write_text(json.dumps(row))
        return receipt

    def tampered_receipt(self, platform, package):
        receipt = self.published / "receipts" / (platform + "-" + package + ".json")
        row = json.loads(receipt.read_text())
        key = "spec_sha256" if "spec_sha256" in row else "metadata_sha256"
        row[key] = "0" * 64
        receipt.write_text(json.dumps(row))
        return receipt

    def prune(self, receipts, dry_run=False, combos=COMBOS):
        return prune_releases.prune("owner/repo", [str(path) for path in receipts],
                                    PLATFORMS, UPSTREAMS, combos, FAMILIES,
                                    dry_run=dry_run, get_target=fake_target)

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
            extras = ["build.json", "SOURCE-SHA256SUM", "changelog"] if key.fmt != "new" else []
            checksums = []
            for name in names:
                data = name.encode()
                checksum = hashlib.sha256(data).hexdigest()
                release["assets"].append({"name": name, "size": len(data),
                                          "state": "uploaded", "digest": "sha256:" + checksum})
                self.downloads[tag, name] = data
                checksums.append(checksum + "  ./" + name)
            self.downloads[tag, "SHA256SUMS"] = "\n".join(checksums) + "\n"
            for name in ["SHA256SUMS"] + extras:
                release["assets"].append({"name": name, "size": 100, "state": "uploaded"})
            return release
        platforms = ("el7", "el8") if key.platform == "all" else (key.platform,)
        for platform in platforms:
            # 真实 RPM 文件名是 N-V-R.x86_64.rpm：release 段自带发行后缀；
            # 旧合并 Release 的 R 是纯数字，此时按旧约定补 .<platform>。
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
            if key.fmt == "legacy_component":
                release["assets"] += [{"name": "SOURCE-SHA256SUM", "size": 10, "state": "uploaded"},
                                      {"name": "%s-%s.spec" % (key.package, platform),
                                       "size": 10, "state": "uploaded"}]
        return release

    def github(self, *args, text=True):
        self.remote_calls.append(args)
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

    # ---- retention ----

    def test_numeric_order_and_pagination_preserve_other_combinations(self):
        old = self.release("el7-chrony-4.9-9.el7")
        other_platform = self.release("el8-chrony-4.9-1.el8")
        other_package = self.release("el7-bash-5.3-1.el7")
        unrelated = self.release("backup-el7-999-1.el7")
        self.pages.append([])
        current = self.release("el7-chrony-4.10-2.el7")
        keeper = self.release("el7-chrony-4.10-10.el7")
        self.prune([self.receipt("el7", "chrony", "4.10", "2.el7")])
        self.assertCountEqual(self.deleted, [old["id"], current["id"]])
        for release in (other_platform, other_package, unrelated, keeper):
            self.assertNotIn(release["id"], self.deleted)

    def test_legacy_component_fallback_is_replaced_by_new_format_keeper(self):
        legacy = self.release("sudo-el7-1.8.23-10.el7_9.3")
        current = self.release("el7-sudo-1.9.17p2-1.el7")
        self.prune([self.receipt("el7", "sudo", "1.9.17p2", "1.el7")])
        self.assertEqual(self.deleted, [legacy["id"]])
        self.assertNotIn(current["id"], self.deleted)

    def test_sudo_patchlevel_and_distro_revisions_compare_numerically(self):
        for old_tag, new_tag in (
            ("el7-sudo-1.9.17p2-10.el7", "el7-sudo-1.9.17p10-1.el7"),
            ("el8-sudo-1.9.5p2-1.el8_9.9", "el8-sudo-1.9.5p2-1.el8_10.5"),
        ):
            with self.subTest(old=old_tag):
                self.pages = [[]]
                self.deleted.clear()
                old = self.release(old_tag)
                keeper = self.release(new_tag)
                platform, package = new_tag.split("-")[:2]
                version = "1.9.17p10" if "p10" in new_tag else "1.9.5p2"
                self.prune([self.receipt(platform, package, version,
                                         new_tag.rsplit("-", 1)[1])])
                self.assertEqual(self.deleted, [old["id"]])
                self.assertNotIn(keeper["id"], self.deleted)

    def test_merged_release_needs_both_platforms_new_format_not_older(self):
        v_first = self.release("v10.5p1")
        v_second = self.release("v10.5p1-2")
        v_higher = self.release("v10.7p1-2")
        el7 = self.release("el7-openssh-10.6p2-2.el7")
        el8 = self.release("el8-openssh-10.6p2-2.el8")
        receipts = [self.receipt("el7", "openssh", "10.6p2", "2.el7"),
                    self.receipt("el8", "openssh", "10.6p2", "2.el8")]
        self.prune(receipts)
        self.assertCountEqual(self.deleted, [v_first["id"], v_second["id"]])
        for release in (v_higher, el7, el8):
            self.assertNotIn(release["id"], self.deleted)

    def test_merged_release_survives_a_single_platform_replacement(self):
        self.release("v10.5p1-2")
        self.release("el7-openssh-10.6p2-2.el7")
        self.prune([self.receipt("el7", "openssh", "10.6p2", "2.el7")])
        self.assertEqual(self.deleted, [])

    def test_merged_release_survives_older_replacements(self):
        self.release("v10.7p1-2")
        self.release("el7-openssh-10.6p2-2.el7")
        self.release("el8-openssh-10.6p2-2.el8")
        receipts = [self.receipt("el7", "openssh", "10.6p2", "2.el7"),
                    self.receipt("el8", "openssh", "10.6p2", "2.el8")]
        self.prune(receipts)
        self.assertEqual(self.deleted, [])

    def test_merged_release_survives_tilde_rc_replacements(self):
        # 合并项按旧约定还原 R.<platform> 比较：2.el7~rc1 < 2.el7，绝不误删。
        self.release("v10.6p2-2")
        self.release("el7-openssh-10.6p2-2.el7~rc1")
        self.release("el8-openssh-10.6p2-2.el8~rc1")
        receipts = [self.receipt("el7", "openssh", "10.6p2", "2.el7~rc1"),
                    self.receipt("el8", "openssh", "10.6p2", "2.el8~rc1")]
        self.prune(receipts)
        self.assertEqual(self.deleted, [])

    def test_merged_release_survives_a_disabled_platform(self):
        combos = COMBOS - {("el8", "openssh")}
        self.release("v10.5p1-2")
        self.release("el7-openssh-10.6p2-2.el7")
        receipt = self.receipt("el7", "openssh", "10.6p2", "2.el7")
        prune_releases.prune("owner/repo", [str(receipt)], PLATFORMS, UPSTREAMS, combos,
                             FAMILIES)
        self.assertEqual(self.deleted, [])

    def test_merged_release_survives_incomplete_replacement_and_aborts_nothing_else(self):
        self.release("v10.5p1-2")
        el7 = self.release("el7-openssh-10.6p2-2.el7")
        el8 = self.release("el8-openssh-10.6p2-2.el8")
        el8["assets"] = [asset for asset in el8["assets"] if "openssh-server" not in asset["name"]]
        receipts = [self.receipt("el7", "openssh", "10.6p2", "2.el7"),
                    self.receipt("el8", "openssh", "10.6p2", "2.el8")]
        with self.assertRaisesRegex(ValueError, "primary RPM"):
            self.prune(receipts)
        self.assertEqual(self.deleted, [])
        self.assertNotIn(el7["id"], self.deleted)

    def test_asset_release_segment_must_match_the_tag_exactly(self):
        # tag 宣称 99.el7（EVR 最高，会成为保留项），资产实际是 1.el7：
        # 严格比对必须拒绝该保留项，绝不据此删除真实发布。
        fake = self.release("el7-chrony-4.10-99.el7")
        for asset in fake["assets"]:
            if asset["name"].endswith(".rpm"):
                asset["name"] = asset["name"].replace("4.10-99.el7", "4.10-1.el7")
        self.downloads["el7-chrony-4.10-99.el7", "SHA256SUMS"] = "".join(
            hashlib.sha256(asset["name"].encode()).hexdigest() + "  ./" + asset["name"] + "\n"
            for asset in fake["assets"] if asset["name"].endswith(".rpm"))
        current = self.release("el7-chrony-4.10-2.el7")
        with self.assertRaisesRegex(ValueError, "does not match tag"):
            self.prune([self.receipt("el7", "chrony", "4.10", "2.el7")])
        self.assertEqual(self.deleted, [])
        self.assertNotIn(current["id"], self.deleted)

    def test_centos_retention_never_deletes_merged_releases(self):
        merged = self.release("v10.6p2-2")
        old = self.release("openssh-centos7-10.6p2-1.centos7")
        keeper = self.release("centos7-openssh-10.6p2-2.centos7")
        self.prune([self.receipt("centos7", "openssh", "10.6p2", "2.centos7")])
        self.assertEqual(self.deleted, [old["id"]])
        self.assertNotIn(merged["id"], self.deleted)
        self.assertNotIn(keeper["id"], self.deleted)

    def test_legacy_ubuntu_release_is_replaced_by_new_format(self):
        legacy = self.release("openssh-ubuntu2204-10.5p1-2ubuntu22.04")
        keeper = self.release("ubuntu2204-openssh-10.6p2-10ubuntu22.04")
        current = self.release("ubuntu2204-openssh-10.6p2-2ubuntu22.04")
        self.prune([self.receipt("ubuntu2204", "openssh", "10.6p2", "2ubuntu22.04")])
        self.assertEqual(self.deleted, [legacy["id"], current["id"]])
        self.assertNotIn(keeper["id"], self.deleted)

    def test_incomplete_current_release_aborts_all_deletions(self):
        self.release("el7-chrony-4.9-1.el7")
        current = self.release("el7-chrony-4.10-1.el7")
        current["assets"][0]["state"] = "new"
        other = self.release("el8-bash-5.2-1.el8")
        other_keeper = self.release("el8-bash-5.3-1.el8")
        receipts = [self.receipt("el7", "chrony", "4.10", "1.el7"),
                    self.receipt("el8", "bash", "5.3", "1.el8")]
        with self.assertRaisesRegex(ValueError, "incomplete asset"):
            self.prune(receipts)
        self.assertEqual(self.deleted, [])
        self.assertNotIn(other["id"], self.deleted)
        self.assertNotIn(other_keeper["id"], self.deleted)

    def test_lower_republish_cannot_replace_higher_keeper(self):
        old = self.release("el7-chrony-4.9-9.el7")
        keeper = self.release("el7-chrony-4.10-1.el7")
        self.prune([self.receipt("el7", "chrony", "4.9", "9.el7")])
        self.assertEqual(self.deleted, [old["id"]])
        self.assertNotIn(keeper["id"], self.deleted)

    def test_drafts_prereleases_and_unrecognized_tags_are_not_candidates(self):
        current = self.release("el7-bash-5.3-1.el7")
        draft = self.release("el7-bash-5.4-1.el7")
        draft["draft"] = True
        preview = self.release("el7-bash-5.5-1.el7")
        preview["prerelease"] = True
        for tag in ("el7-bash-6.1-custom", "v99.0", "vim-el7-9.2-1.el7",
                    "ntp-el7-6.0-1.el8", "openssh-el7-10.6p1-2.el7"):
            self.release(tag)
        self.prune([self.receipt("el7", "bash", "5.3", "1.el7")])
        self.assertEqual(self.deleted, [])

    def test_missing_current_release_cannot_trigger_deletion(self):
        self.release("el7-ntp-4.2.8p17-1.el7")
        self.release("el7-ntp-4.2.8p18-1.el7")
        with self.assertRaisesRegex(ValueError, "not found without a newer verified"):
            self.prune([self.receipt("el7", "ntp", "4.2.8p18", "2.el7")])
        self.assertEqual(self.deleted, [])

    def test_receipt_for_unconfigured_target_is_rejected(self):
        self.release("el7-chrony-4.10-1.el7")
        with self.assertRaisesRegex(ValueError, "not configured"):
            self.prune([self.receipt("el7", "chrony", "4.10", "1.el7")],
                       combos=COMBOS - {("el7", "chrony")})
        self.assertEqual(self.deleted, [])

    def test_superseded_lower_republish_allows_rerun_of_the_same_batch(self):
        # 低版本补发已被保留策略删除：凭据仍指向已删 tag，重入按 superseded 处理。
        keeper = self.release("el7-chrony-4.10-1.el7")
        self.prune([self.receipt("el7", "chrony", "4.9", "9.el7")])
        self.assertEqual(self.deleted, [])
        self.assertNotIn(keeper["id"], self.deleted)
        # 幂等：再次运行同一批次结果一致。
        self.remote_calls.clear()
        self.prune([self.receipt("el7", "chrony", "4.9", "9.el7")])
        self.assertEqual(self.deleted, [])

    def test_missing_current_without_provable_replacement_is_an_error(self):
        # 组合为空 → 不放行。
        with self.assertRaisesRegex(ValueError, "not found without a newer verified"):
            self.prune([self.receipt("el7", "chrony", "4.9", "9.el7")])
        # 替代存在但不是更高 EVR → 不放行。
        self.release("el7-chrony-4.8-1.el7")
        with self.assertRaisesRegex(ValueError, "not found without a newer verified"):
            self.prune([self.receipt("el7", "chrony", "4.9", "9.el7")])
        # 替代更高但清单缺失 → 校验失败，不放行。
        broken = self.release("el7-chrony-4.10-1.el7")
        broken["assets"] = [a for a in broken["assets"] if a["name"] != "SHA256SUMS"]
        with self.assertRaisesRegex(ValueError, "missing or incomplete asset"):
            self.prune([self.receipt("el7", "chrony", "4.9", "9.el7")])
        self.assertEqual(self.deleted, [])

    def test_bad_receipt_aborts_before_any_remote_call(self):
        self.release("el7-chrony-4.10-1.el7")
        self.release("el8-bash-5.3-1.el8")
        receipts = [self.receipt("el7", "chrony", "4.10", "1.el7"),
                    self.receipt("el8", "bash", "5.3", "1.el8")]
        self.tampered_receipt("el8", "bash")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.prune(receipts)
        self.assertEqual(self.deleted, [])
        self.assertEqual(self.remote_calls, [], "本地预检失败时不得发起任何远程调用")

    def test_dry_run_verifies_without_deletion(self):
        old = self.release("el7-chrony-4.9-1.el7")
        keeper = self.release("el7-chrony-4.10-1.el7")
        self.prune([self.receipt("el7", "chrony", "4.10", "1.el7")], dry_run=True)
        self.assertEqual(self.deleted, [])
        self.assertNotIn(old["id"], self.deleted)
        self.assertNotIn(keeper["id"], self.deleted)

    def test_corrupt_replacement_checksums_preserve_everything(self):
        old = self.release("el8-chrony-4.9-1.el8")
        keeper = self.release("el8-chrony-4.10-1.el8")
        keeper["assets"][0]["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.prune([self.receipt("el8", "chrony", "4.10", "1.el8")])
        self.assertEqual(self.deleted, [])
        self.assertNotIn(old["id"], self.deleted)

    def test_legacy_assets_without_digest_are_downloaded_and_verified(self):
        old = self.release("telnet-el7-2.7-1.el7")
        keeper = self.release("el7-telnet-2.8-1.el7")
        for asset in keeper["assets"]:
            asset.pop("digest", None)
        self.prune([self.receipt("el7", "telnet", "2.8", "1.el7")])
        self.assertEqual(self.deleted, [old["id"]])
        self.api.assert_any_call("release", "download", keeper["tag_name"], "--repo",
                                 "owner/repo", "--pattern", "telnet-2.8-1.el7.x86_64.rpm",
                                 "--output", "-", text=False)

    def test_cleanup_is_idempotent_after_completion(self):
        self.release("el7-chrony-4.9-1.el7")
        current = self.release("el7-chrony-4.10-1.el7")
        self.prune([self.receipt("el7", "chrony", "4.10", "1.el7")])
        self.assertEqual(self.deleted, [self.pages[0][0]["id"]])
        self.pages = [[current]]
        self.deleted.clear()
        self.prune([self.receipt("el7", "chrony", "4.10", "1.el7")])
        self.assertEqual(self.deleted, [])

    def test_superseded_combo_completes_remaining_history_deletions_on_rerun(self):
        # 上一轮删 current 成功、删另一个 history 失败：重跑时 superseded 组合
        # 纳入统一保留/删除计划，剩余历史被清理，唯一 keeper 保留。
        history = self.release("el7-chrony-4.9-1.el7")
        keeper = self.release("el7-chrony-4.10-1.el7")
        receipt = self.receipt("el7", "chrony", "4.9", "9.el7")

        def fail_first_delete(*args, **kwargs):
            if args[:3] == ("api", "--method", "DELETE"):
                raise subprocess.CalledProcessError(1, "gh")
            return self.github(*args, **kwargs)

        self.api.side_effect = fail_first_delete
        with self.assertRaises(subprocess.CalledProcessError):
            self.prune([receipt])
        self.assertEqual(self.deleted, [])
        self.api.side_effect = self.github
        self.prune([receipt])
        self.assertEqual(self.deleted, [history["id"]])
        self.assertNotIn(keeper["id"], self.deleted)
        # 幂等：模拟远端状态（已删项消失）后重跑，零删除。
        self.pages = [[keeper]]
        self.deleted.clear()
        self.prune([receipt])
        self.assertEqual(self.deleted, [])

    def test_delimited_package_names_parse_and_retain_end_to_end(self):
        for name in ("demo-tool", "demo_tool"):
            key = prune_releases.parse_tag("el7-%s-1.0-2.el7" % name, PLATFORMS,
                                           set(UPSTREAMS), FAMILIES)
            self.assertEqual((key.platform, key.package, key.release), ("el7", name, "2.el7"),
                             name)
            legacy = prune_releases.parse_tag("%s-el7-1.0-1.el7" % name, PLATFORMS,
                                              set(UPSTREAMS), FAMILIES)
            self.assertEqual((legacy.platform, legacy.package), ("el7", name), name)
        # 全链：demo_tool 新 keeper 替换旧组件格式回退。
        legacy = self.release("demo_tool-el7-1.0-1.el7")
        current = self.release("el7-demo_tool-1.0-2.el7")
        self.prune([self.receipt("el7", "demo_tool", "1.0", "2.el7")])
        self.assertEqual(self.deleted, [legacy["id"]])
        self.assertNotIn(current["id"], self.deleted)

    def test_failed_deletion_reports_failure(self):
        self.release("el7-bash-5.2-1.el7")
        current = self.release("el7-bash-5.3-1.el7")

        def fail_delete(*args, **kwargs):
            if args[:3] == ("api", "--method", "DELETE"):
                raise subprocess.CalledProcessError(1, "gh")
            return self.github(*args, **kwargs)

        self.api.side_effect = fail_delete
        receipt = self.receipt("el7", "bash", "5.3", "1.el7")
        with self.assertRaises(subprocess.CalledProcessError):
            self.prune([receipt])
        result = prune_releases.main(["--repo", "owner/repo", str(receipt)])
        self.assertEqual(result, 1)
        self.assertNotIn(current["id"], self.deleted)


if __name__ == "__main__":
    unittest.main()
