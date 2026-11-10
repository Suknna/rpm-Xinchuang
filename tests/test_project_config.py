"""platforms/<id>/platform.yaml 与 packaging/upstreams.yaml 的配置契约测试。"""

import json
import os
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import project_config  # noqa: E402


ROOT = project_config.ROOT

# 从 scripts/platforms.sh 原样迁移的固定镜像，测试钉住防止漂移。
IMAGES = {
    "el7": "registry.access.redhat.com/ubi7/ubi@sha256:046e525722f14702c360dc6092324af7c21656e76b0c254b067871f1d4d3df68",
    "el8": "registry.access.redhat.com/ubi8/ubi@sha256:ed721ca811f29fa0fd8a4666aec2fb6771f3defbecc708a973d0b711d6f09293",
    "centos7": "docker.io/library/centos@sha256:dead07b4d8ed7e29e98de0f4504d87e8880d4347859d839686a31da35a3b532f",
    "ubuntu2204": "docker.io/library/ubuntu@sha256:076e7bf82319619f28dd0aa9c02ab34b055ad37100395b4f49a2ffba04fb5e11",
}

SIX_PACKAGES = {"openssh", "bash", "chrony", "sudo", "ntp", "telnet"}

UPSTREAMS_YAML = textwrap.dedent("""\
    projects:
      demo:
        name: demo
        anitya_id: 1
        version_pattern: '\\d+'
        source_url: https://example.com/demo-{version}.tar.gz
    """)


class PlatformConfigTest(unittest.TestCase):
    """真实仓库配置：平台、启用组合与迁移后的固定值。"""

    @classmethod
    def setUpClass(cls):
        cls.config = project_config.load_config()

    def test_four_platforms_with_expected_enabled_packages(self):
        platforms = self.config["platforms"]
        self.assertEqual(sorted(platforms), ["centos7", "el7", "el8", "ubuntu2204"])
        enabled = {platform: {name for name, entry in cfg["packages"].items()
                              if entry["enabled"]}
                   for platform, cfg in platforms.items()}
        self.assertEqual(enabled["el7"], SIX_PACKAGES)
        self.assertEqual(enabled["el8"], SIX_PACKAGES)
        self.assertEqual(enabled["centos7"], SIX_PACKAGES)
        self.assertEqual(enabled["ubuntu2204"], {"openssh"})

    def test_vim_is_registered_but_paused(self):
        for platform in ("el7", "el8", "centos7"):
            self.assertFalse(self.config["platforms"][platform]["packages"]["vim"]["enabled"])
        self.assertNotIn("vim", self.config["platforms"]["ubuntu2204"]["packages"])
        # 暂停目标仍可解析（供手动强制构建），只是不出现在启用组合里。
        target = project_config.get_target("el7", "vim")
        self.assertEqual(target["kind"], "upstream-rpm")
        self.assertEqual(target["spec"], "platforms/el7/packages/vim/vim.spec")

    def test_images_keep_the_pinned_digests(self):
        for platform, image in IMAGES.items():
            self.assertEqual(self.config["platforms"][platform]["image"], image)

    def test_rpm_upstream_target_flat_dict(self):
        target = project_config.get_target("el7", "bash")
        self.assertEqual(target, {
            "platform": "el7", "package": "bash",
            "kind": "upstream-rpm", "family": "rpm", "el": "el7", "repos": "el7",
            "image": IMAGES["el7"],
            "spec": "platforms/el7/packages/bash/bash.spec",
            "assets": "platforms/el7/packages/bash/assets",
            "packaging": "", "aux_source": "", "pre_build": "",
            "dist_dir": "dist/el7/bash",
        })
        self.assertTrue((ROOT / target["spec"]).is_file())
        self.assertTrue((ROOT / target["assets"]).is_dir())

    def test_centos7_reuses_el7_packaging_with_own_dist_dir(self):
        target = project_config.get_target("centos7", "chrony")
        self.assertEqual(target["spec"], "platforms/el7/packages/chrony/chrony.spec")
        self.assertEqual(target["assets"], "platforms/el7/packages/chrony/assets")
        self.assertEqual(target["el"], "el7")
        self.assertEqual(target["repos"], "el7")
        self.assertEqual(target["dist_dir"], "dist/centos7/chrony")
        self.assertEqual(target["aux_source"], "10")

    def test_openssh_targets_share_common_packaging(self):
        for platform in ("el7", "el8", "centos7"):
            target = project_config.get_target(platform, "openssh")
            self.assertEqual(target["kind"], "openssh-rpm")
            self.assertEqual(target["spec"], "packaging/common/openssh/openssh.spec")
            self.assertEqual(target["assets"], "packaging/common/openssh")
            self.assertEqual(target["packaging"], "packaging/common/openssh")
            self.assertEqual(target["dist_dir"], f"dist/{platform}/openssh")

    def test_ubuntu2204_openssh_is_the_only_deb_target(self):
        target = project_config.get_target("ubuntu2204", "openssh")
        self.assertEqual(target, {
            "platform": "ubuntu2204", "package": "openssh",
            "kind": "openssh-deb", "family": "deb", "el": "", "repos": "",
            "image": IMAGES["ubuntu2204"],
            "spec": "packaging/common/openssh/openssh.spec",
            "assets": "",
            "packaging": "platforms/ubuntu2204/packages/openssh/debian",
            "aux_source": "", "pre_build": "",
            "dist_dir": "dist/ubuntu2204/openssh",
        })
        self.assertTrue((ROOT / target["packaging"] / "control").is_file())

    def test_aux_source_and_pre_build_hooks(self):
        self.assertEqual(project_config.get_target("el7", "ntp")["aux_source"], "5")
        self.assertEqual(project_config.get_target("el7", "ntp")["pre_build"], "ntp-openssl")
        self.assertEqual(project_config.get_target("centos7", "ntp")["pre_build"], "ntp-openssl")
        self.assertEqual(project_config.get_target("el8", "ntp")["pre_build"], "")
        self.assertEqual(project_config.get_target("el8", "chrony")["aux_source"], "10")
        self.assertEqual(project_config.get_target("el8", "bash")["pre_build"], "")

    def test_iter_targets_yields_only_enabled_flat_dicts(self):
        targets = list(project_config.iter_targets(self.config))
        self.assertEqual(len(targets), 19)  # 6 包 × 3 RPM 平台 + 1 个 DEB
        self.assertTrue(all(isinstance(target, dict) for target in targets))
        self.assertEqual({target["platform"] for target in targets}, set(IMAGES))
        self.assertNotIn("vim", {target["package"] for target in targets})
        kinds = {}
        for target in targets:
            kinds[target["kind"]] = kinds.get(target["kind"], 0) + 1
        self.assertEqual(kinds, {"upstream-rpm": 15, "openssh-rpm": 3, "openssh-deb": 1})

    def test_upstream_registry_pins_fixed_anitya_ids(self):
        upstreams = self.config["upstreams"]
        self.assertEqual(
            {name: item["anitya_id"] for name, item in upstreams.items()}, {
                "openssh": 2565, "chrony": 8810, "vim": 5092,
                "bash": 166, "sudo": 4906, "ntp": 9025, "telnet": 13805,
            })
        # 固定名字避免同名项目误匹配；telnet 的上游是 GNU inetutils。
        self.assertEqual(upstreams["openssh"]["name"], "OpenSSH")
        self.assertEqual(upstreams["telnet"]["name"], "inetutils")
        self.assertEqual(upstreams["ntp"]["version_pattern"], r"\d+(?:\.\d+)+p\d+")
        self.assertTrue(upstreams["openssh"]["source_url"].endswith("openssh-{version}.tar.gz"))
        self.assertFalse(upstreams["vim"]["enabled"])
        self.assertTrue(all(item["enabled"] for name, item in upstreams.items()
                            if name != "vim"))

    def test_target_env_contract(self):
        env = project_config.target_env(project_config.get_target("ubuntu2204", "openssh"))
        self.assertEqual(env, {
            "BUILD_PLATFORM": "ubuntu2204", "PACKAGE": "openssh",
            "PACKAGE_KIND": "openssh-deb", "PACKAGE_FAMILY": "deb",
            "BUILD_IMAGE": IMAGES["ubuntu2204"], "PACKAGING_EL": "",
            "SPEC_PATH": "packaging/common/openssh/openssh.spec",
            "ASSETS_PATH": "",
            "PACKAGING_PATH": "platforms/ubuntu2204/packages/openssh/debian",
            "AUX_SOURCE": "", "PRE_BUILD": "",
            "DIST_DIR": "dist/ubuntu2204/openssh",
        })

    def test_target_env_roundtrips_through_shlex_for_every_target(self):
        # KEY=shlex.quote(value) 必须能无损分词回原值，宿主 eval/docker -e 才安全。
        for target in project_config.iter_targets(self.config):
            for key, value in project_config.target_env(target).items():
                with self.subTest(platform=target["platform"],
                                  package=target["package"], key=key):
                    self.assertEqual(shlex.split(f"{key}={shlex.quote(value)}"),
                                     [f"{key}={value}"])

    def test_target_env_special_characters_survive_shlex_roundtrip(self):
        weird = {
            "platform": "el7", "package": "bash", "kind": "upstream-rpm",
            "family": "rpm", "el": "el7", "repos": "el7",
            "image": "reg:5000/img@sha256:" + "a" * 64,
            "spec": "a b/spec'x.spec", "assets": 'as"sets$dir',
            "packaging": "pkg`x\\dir", "aux_source": "10", "pre_build": "",
            "dist_dir": "dist/a b/c'd",
        }
        for key, value in project_config.target_env(weird).items():
            self.assertEqual(shlex.split(f"{key}={shlex.quote(value)}"),
                             [f"{key}={value}"])


class ConfigValidationTest(unittest.TestCase):
    """非法输入必须报 ConfigError；新增平台无需改代码。"""

    def fixture(self, platform_yaml, files=()):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        platform_dir = root / "platforms/demo"
        platform_dir.mkdir(parents=True)
        (platform_dir / "platform.yaml").write_text(
            textwrap.dedent(platform_yaml), encoding="utf-8")
        packaging = root / "packaging"
        packaging.mkdir()
        (packaging / "upstreams.yaml").write_text(UPSTREAMS_YAML, encoding="utf-8")
        for name, content in files:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root

    DEMO_SPEC = "platforms/demo/packages/demo/demo.spec"

    def rpm_yaml(self, packages):
        """packages 是 packages: 下的条目文本，dedent 后统一加两级缩进。"""
        return (
            f"image: registry.example.com/img@sha256:{'a' * 64}\n"
            "family: rpm\n"
            "el: el7\n"
            "packages:\n"
            + textwrap.indent(textwrap.dedent(packages), "  ")
        )

    def test_unknown_platform_or_package_fail(self):
        root = self.fixture(self.rpm_yaml("""\
            demo:
              spec: """ + self.DEMO_SPEC),
                            [(self.DEMO_SPEC, "Name: demo\n")])
        with self.assertRaisesRegex(project_config.ConfigError, "unknown platform"):
            project_config.get_target("nope", "demo", root=root)
        with self.assertRaisesRegex(project_config.ConfigError, "unknown package"):
            project_config.get_target("demo", "nope", root=root)

    def test_path_escape_and_absolute_paths_are_rejected(self):
        root = self.fixture(self.rpm_yaml("""\
            demo:
              spec: """ + self.DEMO_SPEC + "\n              assets: ../../outside"))
        with self.assertRaisesRegex(project_config.ConfigError, "escapes the repository"):
            project_config.load_config(root)
        root = self.fixture(self.rpm_yaml("""\
            demo:
              spec: /etc/passwd"""))
        with self.assertRaisesRegex(project_config.ConfigError, "escapes the repository"):
            project_config.load_config(root)

    def test_duplicate_keys_are_rejected(self):
        root = self.fixture(self.rpm_yaml("""\
            demo:
              spec: a.spec
            demo:
              spec: b.spec
            """))
        with self.assertRaisesRegex(project_config.ConfigError, "duplicate key"):
            project_config.load_config(root)

    def test_floating_image_tag_is_rejected(self):
        root = self.fixture(textwrap.dedent("""\
            image: registry.example.com/img:latest
            family: rpm
            el: el7
            packages:
              demo:
                spec: spec
            """))
        with self.assertRaisesRegex(project_config.ConfigError, "digest-pinned"):
            project_config.load_config(root)

    def test_empty_enabled_set_is_rejected(self):
        root = self.fixture(self.rpm_yaml("""\
            demo:
              enabled: false
              spec: x"""))
        with self.assertRaisesRegex(project_config.ConfigError, "no enabled packages"):
            project_config.load_config(root)

    def test_missing_declared_spec_fails_at_target_time(self):
        root = self.fixture(self.rpm_yaml("""\
            demo:
              spec: missing.spec"""))
        config = project_config.load_config(root)  # 结构合法
        with self.assertRaisesRegex(project_config.ConfigError, "spec not found"):
            project_config.get_target("demo", "demo", root=root)
        with self.assertRaisesRegex(project_config.ConfigError, "spec not found"):
            list(project_config.iter_targets(config))

    def test_rpm_platform_requires_el(self):
        root = self.fixture(textwrap.dedent("""\
            image: registry.example.com/img@sha256:%s
            family: rpm
            packages:
              demo:
                spec: demo.spec
            """ % ("a" * 64)))
        with self.assertRaisesRegex(project_config.ConfigError, "requires 'el'"):
            project_config.load_config(root)

    def test_unknown_keys_are_rejected(self):
        root = self.fixture("kind: rpm\n" + self.rpm_yaml("""\
            demo:
              spec: x"""))
        with self.assertRaisesRegex(project_config.ConfigError, "unknown keys"):
            project_config.load_config(root)

    def test_unsafe_identifiers_are_rejected(self):
        # 包名/平台目录名/el 必须是 [a-z0-9][a-z0-9_-]*，防 tag/shell/dist 越界。
        for bad in ("../evil", "..", "Demo", "a b"):
            with self.subTest(package=bad):
                root = self.fixture(self.rpm_yaml(f"    {bad}:\n      spec: x"))
                with self.assertRaisesRegex(project_config.ConfigError,
                                            "package name must match"):
                    project_config.load_config(root)
        root = self.fixture(self.rpm_yaml("""\
            demo:
              spec: x
            """))
        bad = root / "platforms/Bad_ID"
        bad.mkdir()
        (bad / "platform.yaml").write_text(
            "image: x\nfamily: rpm\nel: el7\npackages: {demo: {spec: x}}\n",
            encoding="utf-8")
        with self.assertRaisesRegex(project_config.ConfigError, "platform id must match"):
            project_config.load_config(root)
        root = self.fixture(self.rpm_yaml("""\
            demo:
              spec: x
            """).replace("el: el7", "el: '../x'"))
        with self.assertRaisesRegex(project_config.ConfigError, "el must match"):
            project_config.load_config(root)

    def test_non_string_keys_are_rejected(self):
        root = self.fixture("123: oops\n" + self.rpm_yaml("""\
            demo:
              spec: x
            """))
        with self.assertRaisesRegex(project_config.ConfigError, "keys must be strings"):
            project_config.load_config(root)
        root = self.fixture(self.rpm_yaml("""\
            demo:
              spec: x
            123:
              spec: y
            """))
        with self.assertRaisesRegex(project_config.ConfigError, "package name must match"):
            project_config.load_config(root)

    def test_upstreams_top_level_and_keys_are_strict(self):
        root = self.fixture(self.rpm_yaml("""\
            demo:
              spec: x
            """))
        upstreams = root / "packaging/upstreams.yaml"
        upstreams.write_text(textwrap.dedent("""\
            projects:
              demo:
                name: demo
                anitya_id: 1
                version_pattern: '\\d+'
                source_url: https://example.com/demo-{version}.tar.gz
            stale: true
            """), encoding="utf-8")
        with self.assertRaisesRegex(project_config.ConfigError, "unknown keys: stale"):
            project_config.load_config(root)
        upstreams.write_text(textwrap.dedent("""\
            projects:
              ../evil:
                name: evil
                anitya_id: 1
                version_pattern: '\\d+'
                source_url: https://example.com/x-{version}.tar.gz
            """), encoding="utf-8")
        with self.assertRaisesRegex(project_config.ConfigError, "upstream name must match"):
            project_config.load_config(root)

    def test_declared_kind_must_match_package_and_family(self):
        def yaml_of(packages):
            return (f"image: registry.example.com/img@sha256:{'a' * 64}\n"
                    "family: deb\n"
                    "packages:\n"
                    + textwrap.indent(textwrap.dedent(packages), "  "))
        # 显式声明正确 kind 被接受（含 deb 缺 spec 时声明 kind 也合法）。
        root = self.fixture(yaml_of("""\
            openssh:
              packaging: platforms/demo/debian
              kind: openssh-deb
            """), [("platforms/demo/debian/control", "Package: openssh\n")])
        self.assertEqual(
            project_config.get_target("demo", "openssh", root=root)["kind"],
            "openssh-deb")
        # 声明与包名/family 不一致 → 拒绝；第四种 kind（upstream-deb）→ 拒绝。
        root = self.fixture(yaml_of("""\
            openssh:
              packaging: platforms/demo/debian
              kind: upstream-rpm
            """))
        with self.assertRaisesRegex(project_config.ConfigError, "does not match"):
            project_config.load_config(root)
        root = self.fixture(yaml_of("""\
            openssh:
              packaging: platforms/demo/debian
              kind: upstream-deb
            """))
        with self.assertRaisesRegex(project_config.ConfigError, "kind must be one of"):
            project_config.load_config(root)
        root = self.fixture(self.rpm_yaml("""\
            openssh:
              spec: packaging/common/openssh/openssh.spec
              kind: openssh-deb
            """))
        with self.assertRaisesRegex(project_config.ConfigError, "does not match"):
            project_config.load_config(root)

    def test_deb_platform_requires_packaging_and_only_openssh(self):
        root = self.fixture(textwrap.dedent("""\
            image: registry.example.com/img@sha256:%s
            family: deb
            packages:
              bash:
                packaging: platforms/demo/packages/bash/debian
            """ % ("a" * 64)))
        with self.assertRaisesRegex(project_config.ConfigError, "only openssh"):
            project_config.load_config(root)
        root = self.fixture(textwrap.dedent("""\
            image: registry.example.com/img@sha256:%s
            family: deb
            packages:
              openssh:
                spec: packaging/common/openssh/openssh.spec
            """ % ("a" * 64)))
        with self.assertRaisesRegex(project_config.ConfigError, "requires 'packaging'"):
            project_config.load_config(root)

    def test_new_platform_needs_no_code_changes(self):
        root = self.fixture(self.rpm_yaml("""\
            demo:
              spec: """ + self.DEMO_SPEC),
                            [(self.DEMO_SPEC, "Name: demo\n")])
        ci9 = textwrap.dedent(f"""\
            image: registry.example.com/other@sha256:{'b' * 64}
            family: rpm
            el: ci9
            packages:
              demo:
                spec: platforms/ci9/packages/demo/demo.spec
            """)
        (root / "platforms/ci9").mkdir()
        (root / "platforms/ci9/platform.yaml").write_text(ci9, encoding="utf-8")
        spec = root / "platforms/ci9/packages/demo/demo.spec"
        spec.parent.mkdir(parents=True)
        spec.write_text("Name: demo\n", encoding="utf-8")
        config = project_config.load_config(root)
        targets = list(project_config.iter_targets(config))
        self.assertEqual({(t["platform"], t["package"]) for t in targets},
                         {("demo", "demo"), ("ci9", "demo")})
        target = project_config.get_target("ci9", "demo", root=root)
        self.assertEqual(target["kind"], "upstream-rpm")
        self.assertEqual(target["dist_dir"], "dist/ci9/demo")


class CommandLineTest(unittest.TestCase):
    """CLI 输出供构建脚本与宿主机 shell 消费。"""

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "scripts/project_config.py", *args],
                              cwd=ROOT, capture_output=True, text=True)

    def test_target_prints_json_matching_get_target(self):
        result = self.run_cli("target", "el7", "ntp")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout),
                         project_config.get_target("el7", "ntp"))

    def test_shell_output_is_safe_to_source(self):
        result = self.run_cli("shell", "el7", "ntp")
        self.assertEqual(result.returncode, 0, result.stderr)
        probe = subprocess.run(
            ["bash", "-ec",
             'eval "$(cat)" && printf \'%s\\n\' "$BUILD_PLATFORM" "$PACKAGE" '
             '"$PACKAGE_KIND" "$SPEC_PATH" "$AUX_SOURCE" "$PRE_BUILD" "$DIST_DIR"'],
            input=result.stdout, capture_output=True, text=True)
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(probe.stdout.splitlines(), [
            "el7", "ntp", "upstream-rpm",
            "platforms/el7/packages/ntp/ntp.spec", "5", "ntp-openssl",
            "dist/el7/ntp",
        ])

    def test_shell_quotes_special_characters(self):
        result = self.run_cli("shell", "el7", "bash")
        self.assertEqual(result.returncode, 0, result.stderr)
        probe = subprocess.run(
            ["bash", "-ec", 'eval "$(cat)" && printf \'%s\\n\' "$BUILD_IMAGE" "$PACKAGING_EL"'],
            input=result.stdout, capture_output=True, text=True)
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(probe.stdout.splitlines(), [IMAGES["el7"], "el7"])

    def test_image_prints_pinned_reference(self):
        result = self.run_cli("image", "centos7")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), IMAGES["centos7"])

    def test_platforms_prints_json_enabled_platform_list(self):
        # CI discover 的平台矩阵唯一来源：有启用 target 的平台，JSON 列表。
        result = self.run_cli("platforms")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout),
                         ["centos7", "el7", "el8", "ubuntu2204"])

    def test_platforms_honors_config_root_and_new_platforms(self):
        # fixture 仓库零代码新增平台：平台矩阵随配置自动扩展，无需改 workflow。
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "packaging").mkdir(parents=True)
        (root / "packaging" / "upstreams.yaml").write_text(UPSTREAMS_YAML, encoding="utf-8")
        for platform in ("demo", "ci9"):
            (root / "platforms" / platform).mkdir(parents=True)
            (root / "platforms" / platform / "platform.yaml").write_text(
                f"image: registry.example.com/img@sha256:{'a' * 64}\n"
                "family: rpm\n"
                f"el: {platform}\n"
                "packages:\n"
                "  demo:\n"
                f"    spec: platforms/{platform}/packages/demo/demo.spec\n",
                encoding="utf-8")
            spec = root / "platforms" / platform / "packages" / "demo" / "demo.spec"
            spec.parent.mkdir(parents=True)
            spec.write_text("Name: demo\n", encoding="utf-8")
        result = self.run_cli("platforms", "--config-root", str(root))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["ci9", "demo"])

    def test_platforms_rejects_broken_config(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "packaging").mkdir(parents=True)
        (root / "packaging" / "upstreams.yaml").write_text(UPSTREAMS_YAML, encoding="utf-8")
        (root / "platforms" / "demo").mkdir(parents=True)
        (root / "platforms" / "demo" / "platform.yaml").write_text(
            "image: registry.example.com/img:latest\nfamily: rpm\nel: el7\n"
            "packages: {demo: {spec: x}}\n", encoding="utf-8")
        result = self.run_cli("platforms", "--config-root", str(root))
        self.assertEqual(result.returncode, 2)
        self.assertIn("digest-pinned", result.stderr)

    def test_invalid_target_exits_nonzero_with_message(self):
        result = self.run_cli("target", "el7", "nope")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown package", result.stderr)
        result = self.run_cli("image", "nope")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown platform", result.stderr)


if __name__ == "__main__":
    unittest.main()
