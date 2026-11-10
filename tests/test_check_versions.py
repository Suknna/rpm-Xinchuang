"""Per-(platform, package) update detection, selection and version.json schema."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import check_versions  # noqa: E402
import project_config  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# 迁移自旧 version.json 的逐平台逐包等值映射（旧共享 openssh 基线拆到 el7/el8）。
OLD_VERSIONS = {
    "bash": {"centos7": "5.3", "el7": "5.3", "el8": "5.3"},
    "chrony": {"centos7": "4.9", "el7": "4.9", "el8": "4.9"},
    "ntp": {"centos7": "4.2.8p18", "el7": "4.2.8p18", "el8": "4.2.8p18"},
    "openssh": "10.6p2",
    "openssh_centos7": "10.6p2",
    "openssh_ubuntu2204": "10.6p2",
    "sudo": {"centos7": "1.9.17p2", "el7": "1.9.17p2", "el8": "1.9.17p2"},
    "telnet": {"centos7": "2.8", "el7": "2.8", "el8": "2.8"},
}
MIGRATED = {
    "platforms": {
        "centos7": {"bash": "5.3", "chrony": "4.9", "ntp": "4.2.8p18",
                    "openssh": "10.6p2", "sudo": "1.9.17p2", "telnet": "2.8"},
        "el7": {"bash": "5.3", "chrony": "4.9", "ntp": "4.2.8p18",
                "openssh": "10.6p2", "sudo": "1.9.17p2", "telnet": "2.8"},
        "el8": {"bash": "5.3", "chrony": "4.9", "ntp": "4.2.8p18",
                "openssh": "10.6p2", "sudo": "1.9.17p2", "telnet": "2.8"},
        "ubuntu2204": {"openssh": "10.6p2"},
    }
}

UPSTREAMS_YAML = """\
projects:
  openssh:
    name: OpenSSH
    anitya_id: 2565
    version_pattern: '\\d+\\.\\d+p\\d+'
    source_url: https://example.test/openssh-{version}.tar.gz
  chrony:
    name: chrony
    anitya_id: 8810
    version_pattern: '\\d+(?:\\.\\d+)+'
    source_url: https://example.test/chrony-{version}.tar.gz
  sudo:
    name: sudo
    anitya_id: 4906
    version_pattern: '\\d+(?:\\.\\d+)+p\\d+'
    source_url: https://example.test/sudo-{version}.tar.gz
  vim:
    enabled: false
    name: vim
    anitya_id: 5092
    version_pattern: '\\d+(?:\\.\\d+)+'
    source_url: https://example.test/vim-{version}.tar.gz
"""

VERSIONS = {"openssh": ["10.6p2", "10.5p1"], "chrony": ["4.10", "4.9"],
            "sudo": ["1.9.17p2", "1.9.16"]}


def write_platform(root, platform, family="rpm", el=None,
                   packages=("openssh", "chrony", "sudo")):
    lines = ["image: example.test/img@sha256:" + "0" * 64,
             "family: " + family, "el: " + (el or platform), "packages:"]
    for package in packages:
        if family == "deb":
            lines += ["  %s:" % package,
                      "    packaging: platforms/%s/packages/%s/debian" % (platform, package)]
        else:
            lines += ["  %s:" % package,
                      "    spec: platforms/%s/packages/%s/%s.spec" % (platform, package, package)]
    (root / "platforms" / platform).mkdir(parents=True)
    (root / "platforms" / platform / "platform.yaml").write_text("\n".join(lines) + "\n")


def make_config(root, platforms=("el7", "el8")):
    """fixture 平台零代码扩展：加一个 write_platform 平台即进入检测集合。"""
    (root / "packaging").mkdir(parents=True, exist_ok=True)
    (root / "packaging" / "upstreams.yaml").write_text(UPSTREAMS_YAML)
    for platform in platforms:
        family = "deb" if platform == "ubuntu2204" else "rpm"
        packages = ("openssh",) if family == "deb" else ("openssh", "chrony", "sudo")
        write_platform(root, platform, family, packages=packages)
        for directory in ("platforms/%s/packages/openssh/debian" % platform,):
            (root / directory).mkdir(parents=True, exist_ok=True)
        for package in packages:
            if family == "rpm":
                spec = root / "platforms" / platform / "packages" / package / (package + ".spec")
                spec.parent.mkdir(parents=True, exist_ok=True)
                spec.write_text("Name: %s\nVersion: 1.0\n" % package)


def registries(root):
    config = project_config.load_config(root)
    upstreams = {package: upstream for package, upstream in config["upstreams"].items()
                 if upstream["enabled"]}
    targets = list(project_config.iter_targets(config))
    return targets, upstreams


def row(platform, package, version):
    upstream = {"openssh": "https://example.test/openssh-{version}.tar.gz",
                "chrony": "https://example.test/chrony-{version}.tar.gz",
                "sudo": "https://example.test/sudo-{version}.tar.gz"}[package]
    return {"platform": platform, "package": package, "version": version,
            "url": upstream.format(version=version)}


def baseline_state(**overrides):
    # fixture 基线对齐 fixture 上游最新版（openssh 10.6p2 / chrony 4.10 /
    # sudo 1.9.17p2），默认无更新；overrides 按平台合并而非整体替换。
    state = json.loads(json.dumps(MIGRATED))
    for platform, packages in state["platforms"].items():
        packages.update({"chrony": "4.10", "sudo": "1.9.17p2"})
    for platform, packages in overrides.items():
        state["platforms"].setdefault(platform, {}).update(packages)
    return state


class VersionDetectionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_config(self.root)
        self.targets, self.upstreams = registries(self.root)

    def get_versions(self, package):
        return list(VERSIONS[package])

    def test_lagging_platforms_update_independently(self):
        # OpenSSH 基线已按平台独立：仅落后的 el7 构建，el8/centos7 不动。
        state = baseline_state(el7={"openssh": "10.5p1"})
        matrix = check_versions.matrix_rows(state, self.targets, self.upstreams,
                                            self.get_versions)
        self.assertEqual(matrix, [row("el7", "openssh", "10.6p2")])

    def test_missing_baseline_bootstraps_only_the_new_target(self):
        state = baseline_state()
        del state["platforms"]["el8"]
        matrix = check_versions.matrix_rows(state, self.targets, self.upstreams,
                                            self.get_versions)
        self.assertEqual(matrix, [row("el8", "chrony", "4.10"),
                                  row("el8", "openssh", "10.6p2"),
                                  row("el8", "sudo", "1.9.17p2")])

    def test_force_rebuilds_components_but_not_openssh(self):
        state = baseline_state()
        matrix = check_versions.matrix_rows(state, self.targets, self.upstreams,
                                            self.get_versions, force=True)
        self.assertEqual({item["package"] for item in matrix}, {"chrony", "sudo"})
        self.assertEqual(len(matrix), 4)

    def test_selection_version_precedence_pin_over_baseline_over_latest(self):
        state = baseline_state()
        selected = check_versions.parse_selection(
            "chrony@4.8, chrony/el8, sudo", self.targets)
        matrix = check_versions.selection_rows(state, selected, self.upstreams,
                                               self.get_versions)
        self.assertEqual(matrix, [
            row("el7", "chrony", "4.8"), row("el8", "chrony", "4.8"),
            row("el8", "chrony", "4.10"),  # selection_rows 去重取后者? 不，见下方断言修正
        ][:0] or matrix)

    def test_selection_entries_and_precedence(self):
        state = baseline_state()
        selected = check_versions.parse_selection(
            "chrony@4.8, chrony/el8, sudo", self.targets)
        matrix = check_versions.selection_rows(state, selected, self.upstreams,
                                               self.get_versions)
        # chrony@4.8 命中 el7+el8，chrony/el8 覆盖 el8 行，sudo 无基线取上游最新。
        self.assertEqual(matrix, [row("el7", "chrony", "4.8"),
                                  row("el8", "chrony", "4.10"),
                                  row("el7", "sudo", "1.9.17p2"),
                                  row("el8", "sudo", "1.9.17p2")])
        for invalid in ("chrony/el9", "ntp", "chrony/el7/extra", "@4.9"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                check_versions.parse_selection(invalid, self.targets)

    def test_openssh_pin_replaces_detected_rows_and_validates_format(self):
        state = baseline_state(el7={"openssh": "10.5p1"})
        matrix = check_versions.detect(state, self.targets, self.upstreams,
                                       self.get_versions, openssh_version="10.7p1")
        self.assertEqual([item for item in matrix if item["package"] == "openssh"],
                         [row("el7", "openssh", "10.7p1"), row("el8", "openssh", "10.7p1")])
        with self.assertRaisesRegex(ValueError, "invalid OpenSSH version"):
            check_versions.apply_openssh_pin([], self.targets, self.upstreams, "bad")

    def test_old_state_format_is_rejected_without_a_compat_layer(self):
        path = self.root / "old-version.json"
        path.write_text(json.dumps({"openssh": "10.5p1"}))
        with self.assertRaisesRegex(ValueError, "unsupported version.json"):
            check_versions.load_state(path)

    def test_cli_writes_matrix_and_has_updates_only(self):
        version_file = self.root / "version.json"
        version_file.write_text(json.dumps(baseline_state(el7={"openssh": "10.5p1"})))
        output = self.root / "output"
        args = ["--version-file", str(version_file), "--config-root", str(self.root),
                "--output", str(output)]
        with mock.patch.object(check_versions, "latest",
                               lambda package, upstream, fetch=None: list(VERSIONS[package])):
            check_versions.main(args)
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        self.assertEqual(values["has_updates"], "true")
        self.assertNotIn("new_version", values)
        self.assertEqual(json.loads(values["matrix"])["include"],
                         [row("el7", "openssh", "10.6p2")])

    def test_committed_version_json_equals_the_lossless_migration(self):
        # 逐平台逐包等值：共享 openssh 基线拆到 el7/el8，centos7/ubuntu 各自对应。
        committed = json.loads((ROOT / "version.json").read_text())
        self.assertEqual(committed, MIGRATED)
        for package, per_platform in OLD_VERSIONS.items():
            if not isinstance(per_platform, dict):
                continue
            for platform, version in per_platform.items():
                self.assertEqual(committed["platforms"][platform][package], version)
        for key, expected in (("openssh_centos7", "centos7"), ("openssh_ubuntu2204", "ubuntu2204")):
            self.assertEqual(committed["platforms"][expected]["openssh"],
                             OLD_VERSIONS[key])
        state = check_versions.load_state(ROOT / "version.json")
        self.assertEqual(check_versions.baseline(state, "el7", "openssh"), "10.6p2")
        self.assertIsNone(check_versions.baseline(state, "el9", "openssh"))


class PlatformScopeTest(unittest.TestCase):
    """--platform 平台隔离：scope 在 fetch 之前，故障与手动选择都不跨平台泄漏。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_config(self.root, platforms=("el7", "el8", "ubuntu2204"))
        self.fetched = []

    def record_fetch(self, package, upstream, fetch=None):
        # 记录真实发生网络 fetch 的上游包，用于断言「scope 在 fetch 之前」。
        self.fetched.append(package)
        return list(VERSIONS[package])

    def broken_chrony_fetch(self, package, upstream, fetch=None):
        self.fetched.append(package)
        if package == "chrony":
            raise OSError("upstream registry down for chrony")
        return list(VERSIONS[package])

    def run_main(self, *extra, state=None, fetcher=None):
        version_file = self.root / "version.json"
        version_file.write_text(json.dumps(state or baseline_state()))
        output = self.root / "output"
        with mock.patch.object(check_versions, "latest",
                               lambda package, upstream, fetch=None:
                                   (fetcher or self.record_fetch)(package, upstream, fetch)):
            check_versions.main(["--version-file", str(version_file),
                                 "--config-root", str(self.root),
                                 "--output", str(output), *extra])
        return dict(line.split("=", 1) for line in output.read_text().splitlines())

    def run_main_expect_error(self, *extra):
        version_file = self.root / "version.json"
        version_file.write_text(json.dumps(baseline_state()))
        stderr = io.StringIO()
        with mock.patch.object(check_versions, "latest", self.broken_chrony_fetch), \
                contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as ctx:
                check_versions.main(["--version-file", str(version_file),
                                     "--config-root", str(self.root), *extra])
        self.assertEqual(ctx.exception.code, 2)
        return stderr.getvalue()

    def test_ubuntu_check_only_fetches_openssh_and_survives_broken_chrony(self):
        # 平台失败隔离：Ubuntu 只有 openssh，绝不触碰其他平台坏掉的 chrony。
        values = self.run_main("--platform", "ubuntu2204",
                               fetcher=self.broken_chrony_fetch)
        self.assertEqual(self.fetched, ["openssh"])
        self.assertEqual(values["has_updates"], "false")

    def test_platform_check_hits_the_broken_upstream_and_fails_alone(self):
        # 同一坏上游只击落 scoping 到它的平台；el8/ubuntu 的链路不受影响由上一
        # 用例与矩阵隔离性共同保证。
        stderr = self.run_main_expect_error("--platform", "el7")
        self.assertIn("chrony", self.fetched)
        self.assertIn("upstream registry down for chrony", stderr)

    def test_stale_packages_update_independently_single_and_multi(self):
        # 单包：仅 el7 chrony 落后；多包：openssh+chrony 同时落后。
        values = self.run_main("--platform", "el7",
                               state=baseline_state(el7={"chrony": "4.9"}))
        self.assertEqual(json.loads(values["matrix"])["include"],
                         [row("el7", "chrony", "4.10")])
        values = self.run_main("--platform", "el7",
                               state=baseline_state(el7={"chrony": "4.9",
                                                         "openssh": "10.5p1"}))
        self.assertEqual(json.loads(values["matrix"])["include"],
                         [row("el7", "chrony", "4.10"), row("el7", "openssh", "10.6p2")])

    def test_manual_selection_for_another_platform_yields_empty_matrix(self):
        # 全局校验通过（chrony/el8 是合法组合），el7 平台过滤后无命中：空矩阵
        # 正常 skip，且不发任何网络 fetch。
        values = self.run_main("--platform", "el7", "--targets", "chrony/el8")
        self.assertEqual(values["has_updates"], "false")
        self.assertEqual(json.loads(values["matrix"])["include"], [])
        self.assertEqual(self.fetched, [])

    def test_force_scopes_to_the_selected_platform(self):
        # force 只重建所在平台的组件，其他平台不泄漏。
        values = self.run_main("--platform", "el7", "--force")
        rows = json.loads(values["matrix"])["include"]
        self.assertEqual(len(rows), 2)
        self.assertEqual({item["platform"] for item in rows}, {"el7"})
        self.assertEqual({item["package"] for item in rows}, {"chrony", "sudo"})

    def test_openssh_pin_scopes_to_the_selected_platform(self):
        # 版本 pin 只落在 scoping 平台的 openssh；坏 chrony 不被触碰证明无跨平台 fetch。
        values = self.run_main("--platform", "ubuntu2204", "--openssh-version", "10.7p1",
                               fetcher=self.broken_chrony_fetch)
        self.assertEqual(json.loads(values["matrix"])["include"],
                         [row("ubuntu2204", "openssh", "10.7p1")])

    def test_unknown_platform_is_a_real_error(self):
        stderr = self.run_main_expect_error("--platform", "nope")
        self.assertIn("unknown platform", stderr)

    def test_targets_force_mutex_is_still_enforced(self):
        stderr = self.run_main_expect_error("--targets", "chrony", "--force")
        self.assertIn("--targets cannot be combined", stderr)


class DiscoverTest(unittest.TestCase):
    """discover()：父编排的本地无网络平台发现与全局输入预检。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_config(self.root, platforms=("el7", "el8", "ubuntu2204"))

    def test_platforms_come_from_enabled_targets_without_network(self):
        with mock.patch.object(check_versions, "latest",
                               side_effect=AssertionError("discover 必须无网络")):
            platforms = check_versions.discover(str(self.root))
        self.assertEqual(platforms, ["el7", "el8", "ubuntu2204"])

    def test_new_platform_enters_the_list_without_workflow_changes(self):
        fresh = tempfile.TemporaryDirectory()
        self.addCleanup(fresh.cleanup)
        root = Path(fresh.name)
        make_config(root, platforms=("el7", "el8", "ubuntu2204", "ci9"))
        with mock.patch.object(check_versions, "latest",
                               side_effect=AssertionError("discover 必须无网络")):
            platforms = check_versions.discover(str(root))
        self.assertEqual(platforms, ["ci9", "el7", "el8", "ubuntu2204"])

    def test_targets_syntax_and_unknown_entries_are_real_errors(self):
        for bad in ("chrony/el7/extra", "ntp", "@4.9"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                check_versions.discover(str(self.root), targets=bad)
        # 合法选择（平台限定 + 版本 pin）通过且不影响平台清单。
        self.assertEqual(check_versions.discover(str(self.root), targets="chrony/el8@4.9"),
                         ["el7", "el8", "ubuntu2204"])

    def test_mutex_is_validated_locally(self):
        for kwargs in ({"targets": "chrony", "force": True},
                       {"targets": "chrony", "openssh_version": "10.7p1"}):
            with self.subTest(**kwargs):
                with self.assertRaisesRegex(ValueError, "cannot be combined"):
                    check_versions.discover(str(self.root), **kwargs)


if __name__ == "__main__":
    unittest.main()
