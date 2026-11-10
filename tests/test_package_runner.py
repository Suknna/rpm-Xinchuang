"""scripts/package.sh 统一入口的调度测试（mock docker，不触网、不跑容器）。

沙箱内放入真实的 scripts/package.sh 与 scripts/project_config.py，配以最小
platform.yaml/spec 夹具；docker 由 PATH 上的 Python shim 替代，按 JSON 行记录
完整 argv（保真含空格路径/查询参数 URL 的传参）。验证：构建/测试对容器脚本的
调度与参数、环境变量契约透传、dist/<platform>/<package> 路径、test 版本来自
构建元数据（build.spec/build.json，绝不回退源 spec）、新平台无需硬编码、
pre_build 钩子触发、local-* all 按配置动态筛选启用平台、旧签名转发。
"""

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

SHA1 = "1" * 64
SHA2 = "2" * 64
SHA3 = "3" * 64
SHA4 = "4" * 64

PLATFORM_YAMLS = {
    "el7": textwrap.dedent("""\
        image: registry.test/ubi7@sha256:{sha1}
        family: rpm
        el: el7
        packages:
          openssh:
            spec: packaging/common/openssh/openssh.spec
            packaging: packaging/common/openssh
            assets: packaging/common/openssh
          chrony:
            spec: platforms/el7/packages/chrony/chrony.spec
            aux_source: 10
          ntp:
            spec: platforms/el7/packages/ntp/ntp.spec
            aux_source: 5
            pre_build: ntp-openssl
          vim:
            enabled: false   # 暂停包：all 筛选必须排除
            spec: platforms/el7/packages/vim/vim.spec
        """).format(sha1=SHA1),
    "centos7": textwrap.dedent("""\
        image: registry.test/centos7@sha256:{sha2}
        family: rpm
        el: el7
        packages:
          openssh:
            spec: packaging/common/openssh/openssh.spec
            packaging: packaging/common/openssh
            assets: packaging/common/openssh
        """).format(sha2=SHA2),
    # 新平台：沿用 el7 打包家族（el/repos 复用），无需在脚本侧新增任何映射。
    "el9test": textwrap.dedent("""\
        image: registry.test/el9@sha256:{sha3}
        family: rpm
        el: el7
        packages:
          demo:
            spec: platforms/el9test/packages/demo/demo.spec
        """).format(sha3=SHA3),
    "ubuntu2204": textwrap.dedent("""\
        image: registry.test/ubuntu@sha256:{sha4}
        family: deb
        packages:
          openssh:
            spec: packaging/common/openssh/openssh.spec
            packaging: platforms/ubuntu2204/packages/openssh/debian
        """).format(sha4=SHA4),
}

SPEC_FILES = {
    "packaging/common/openssh/openssh.spec": "%global ver 10.1p1\n%global rel 1\n",
    "platforms/el7/packages/chrony/chrony.spec": "Version: 4.5\n",
    "platforms/el7/packages/chrony/assets/asset.txt": "asset\n",
    "platforms/el7/packages/ntp/ntp.spec": "Version: 4.2.8p15\n%global ntp_ssl_ver 3.0.9\n",
    "platforms/el9test/packages/demo/demo.spec": "Version: 1.0\n",
    "platforms/ubuntu2204/packages/openssh/debian/control": "Source: openssh\n",
}

UPSTREAMS_YAML = textwrap.dedent("""\
    projects:
      openssh:
        name: OpenSSH
        anitya_id: 2565
        version_pattern: '\\d+\\.\\d+p\\d+'
        source_url: https://cdn.openbsd.test/pub/openssh-{version}.tar.gz
      chrony:
        name: chrony
        anitya_id: 8810
        version_pattern: '\d+(?:\.\d+)+'
        source_url: https://chrony.test/releases/chrony-{version}.tar.gz
      ntp:
        name: ntp
        anitya_id: 9999
        version_pattern: '\d+(?:\.\d+)+'
        source_url: https://ntp.test/ntp-{version}.tar.gz
      demo:
        name: demo
        anitya_id: 1234
        version_pattern: '\d+(?:\.\d+)+'
        source_url: https://demo.test/demo-{version}.tar.gz
    """)

# Python shim：逐条 docker 调用记录完整 argv 为 JSON 行（保真空格/特殊字符）。
DOCKER_SHIM = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json
    import os
    import pathlib
    import sys

    log = pathlib.Path(os.environ["DOCKER_LOG"])
    if sys.argv[1:] != ["info"]:  # 宿主探测 docker 可用性，不算容器调用
        with log.open("a") as fh:
            fh.write(json.dumps(sys.argv[1:]) + "\\n")
    fail = os.environ.get("FAKE_FAIL_SUBSTRING")
    if fail and fail in " ".join(sys.argv[1:]):
        raise SystemExit(1)
    """)

PREBUILD_STUB = textwrap.dedent("""\
    #!/usr/bin/env bash
    {
        printf 'arg:%s\\n' "$@"
        printf 'SPEC_PATH:%s\\nPACKAGE:%s\\nBUILD_PLATFORM:%s\\n' \\
            "${SPEC_PATH:-}" "${PACKAGE:-}" "${BUILD_PLATFORM:-}"
    } >> "${PREBUILD_LOG:?PREBUILD_LOG missing}"
    """)


def parse_invocation(line):
    """解析 shim 记录的一行 JSON docker 调用：{env, opts, image, cmd, argv}。"""
    argv = json.loads(line)
    env, opts, rest = {}, [], []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token in ("-e", "-v", "--platform"):
            value = argv[i + 1]
            if token == "-e":
                key, _, val = value.partition("=")
                env[key] = val
            else:
                opts.append((token, value))
            i += 2
        elif token in ("run", "--rm"):
            i += 1
        else:
            rest = argv[i:]
            break
    return {"env": env, "opts": opts, "image": rest[0], "cmd": rest[1:], "argv": argv}


def mount_of(call):
    return next(value for flag, value in call["opts"] if flag == "-v")


def is_readonly(call):
    return mount_of(call).endswith(":/src:ro")


class PackageSandbox:
    """构造沙箱仓库：真实脚本 + 最小配置夹具 + docker shim。

    沙箱根路径刻意包含空格，验证挂载与容器命令的传参保真。
    """

    def __init__(self, root):
        self.root = root
        (root / "bin").mkdir(parents=True)
        self._copy_script("package.sh")
        self._copy_script("project_config.py")
        self._copy_script("local-build.sh")
        self._copy_script("local-test.sh")
        prebuild = root / "scripts" / "prebuild"
        prebuild.mkdir(parents=True)
        (prebuild / "ntp-openssl.sh").write_text(PREBUILD_STUB)
        (root / "bin" / "docker").write_text(DOCKER_SHIM)
        (root / "bin" / "docker").chmod(0o755)
        for platform, text in PLATFORM_YAMLS.items():
            source = root / "platforms" / platform
            source.mkdir(parents=True)
            (source / "platform.yaml").write_text(text)
        upstreams = root / "packaging"
        upstreams.mkdir(parents=True)
        (upstreams / "upstreams.yaml").write_text(UPSTREAMS_YAML)
        (upstreams / "common" / "openssh").mkdir(parents=True, exist_ok=True)
        for relpath, content in SPEC_FILES.items():
            target = root / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)

    def _copy_script(self, name):
        target = self.root / "scripts" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "scripts" / name, target)

    def write_dist_file(self, dist_rel, name, content):
        path = self.root / dist_rel / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def stage_build_spec(self, dist_rel, version):
        # 夹具同时含 openssh（%global ver）与 upstream（Version:）两套解析所需行。
        package = dist_rel.rstrip("/").split("/")[-1]
        self.write_dist_file(dist_rel, "build.spec",
                             f"Name: {package}\nVersion: {version}\n"
                             f"Release: 1%{{?dist}}\n"
                             f"%global ver {version}\n%global rel 1\n")

    def stage_build_json(self, dist_rel, version, package="openssh", platform="ubuntu2204"):
        self.write_dist_file(dist_rel, "build.json", json.dumps({
            "package": package, "platform": platform, "architecture": "amd64",
            "version": version, "release": "1ubuntu22.04",
            "deb_version": f"1:{version}-1ubuntu22.04",
        }))

    def run(self, *args, script="package.sh", fail_substring=None, extra_env=None):
        env = dict(os.environ)
        env["PATH"] = str(self.root / "bin") + os.pathsep + env["PATH"]
        env["DOCKER_LOG"] = str(self.root / "docker.log")
        env["PREBUILD_LOG"] = str(self.root / "prebuild.log")
        env.pop("BUILD_SOURCE_CACHE", None)
        env.pop("FAKE_FAIL_SUBSTRING", None)
        env.pop("PYTHON", None)
        if fail_substring:
            env["FAKE_FAIL_SUBSTRING"] = fail_substring
        env.update(extra_env or {})
        return subprocess.run(
            ["bash", str(self.root / "scripts" / script), *args],
            env=env, capture_output=True, text=True, cwd=str(self.root),
        )

    def invocations(self):
        log = self.root / "docker.log"
        if not log.exists():
            return []
        return [parse_invocation(line) for line in log.read_text().splitlines()
                if line.strip()]

    def prebuild_log(self):
        log = self.root / "prebuild.log"
        return log.read_text().splitlines() if log.exists() else []


class PackageRunnerTest(unittest.TestCase):
    """build/test 调度、参数与环境变量契约。"""

    def setUp(self):
        # 路径带空格：任何 $* 拼接式传参都会在此暴露。
        self._tmp = tempfile.TemporaryDirectory(prefix="pkg runner ")
        self.addCleanup(self._tmp.cleanup)
        self.sandbox = PackageSandbox(pathlib.Path(self._tmp.name))

    def test_build_openssh_rpm_builds_then_verifies(self):
        result = self.sandbox.run("build", "el7", "openssh")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.sandbox.invocations()
        self.assertEqual(len(calls), 2, result.stderr)
        build, verify = calls
        # 版本缺省自共享 spec 解析（build 阶段语义）；构建容器可写、门禁容器只读。
        self.assertEqual(build["env"]["VERSION"], "10.1p1")
        self.assertEqual(build["env"]["DIST_DIR"], "dist/el7/openssh")
        self.assertEqual(build["env"]["SPEC_PATH"], "packaging/common/openssh/openssh.spec")
        self.assertEqual(build["env"]["PACKAGING_EL"], "el7")
        self.assertEqual(build["env"]["PACKAGE_KIND"], "openssh-rpm")
        self.assertEqual(build["env"]["AUX_SOURCE"], "")
        self.assertEqual(build["image"], f"registry.test/ubi7@sha256:{SHA1}")
        self.assertEqual(build["cmd"], ["bash", "/src/scripts/build-in-container.sh"])
        self.assertFalse(is_readonly(build))
        self.assertTrue(is_readonly(verify))
        self.assertEqual(verify["cmd"], ["bash", "/src/scripts/verify-rpms.sh", "el7"])
        self.assertEqual(mount_of(build), f"{self.sandbox.root}:/src")
        self.assertEqual(mount_of(verify), f"{self.sandbox.root}:/src:ro")
        # 产物目录必须由宿主预先创建（runner-owned，避免容器以 root 创建）。
        self.assertTrue((self.sandbox.root / "dist/el7/openssh").is_dir())
        self.assertEqual(self.sandbox.prebuild_log(), [])

    def test_build_centos7_keeps_own_dist_and_suffix(self):
        result = self.sandbox.run("build", "centos7", "openssh")
        self.assertEqual(result.returncode, 0, result.stderr)
        build, verify = self.sandbox.invocations()
        self.assertEqual(build["env"]["BUILD_PLATFORM"], "centos7")
        self.assertEqual(build["env"]["PACKAGING_EL"], "el7")  # centos7 复用 EL7 打包家族
        self.assertEqual(build["env"]["DIST_DIR"], "dist/centos7/openssh")
        self.assertEqual(build["image"], f"registry.test/centos7@sha256:{SHA2}")
        self.assertEqual(verify["cmd"], ["bash", "/src/scripts/verify-rpms.sh", "centos7"])

    def test_build_upstream_requires_version_and_url(self):
        for args in (("build", "el7", "chrony"),
                     ("build", "el7", "chrony", "4.5"),
                     ("build", "el7", "chrony", "", "https://x.test/a.tar.gz")):
            result = self.sandbox.run(*args)
            self.assertEqual(result.returncode, 2, f"args={args}: {result.stderr}")
        self.assertEqual(self.sandbox.invocations(), [])

    def test_build_upstream_rejects_non_https_or_dotdot_url(self):
        for url in ("http://x.test/a.tar.gz", "https://x.test/../a.tar.gz"):
            result = self.sandbox.run("build", "el7", "chrony", "4.5", url)
            self.assertEqual(result.returncode, 2, f"url={url}: {result.stderr}")
        self.assertEqual(self.sandbox.invocations(), [])

    def test_build_upstream_passes_url_with_query_params_verbatim(self):
        url = "https://chrony.test/releases/chrony-4.5.tar.gz?sig=ab12&mirror=1"
        result = self.sandbox.run("build", "el7", "chrony", "4.5", url)
        self.assertEqual(result.returncode, 0, result.stderr)
        call = self.sandbox.invocations()[0]
        # JSON 记录的 argv 保真：URL 原样到达容器命令末位。
        self.assertEqual(call["cmd"], [
            "bash", "/src/scripts/build-upstream.sh", "chrony", "el7", "4.5", url])

    def test_build_upstream_passes_config_through(self):
        url = "https://chrony.test/releases/chrony-4.5.tar.gz"
        result = self.sandbox.run("build", "el7", "chrony", "4.5", url)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.sandbox.invocations()
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(call["cmd"], [
            "bash", "/src/scripts/build-upstream.sh", "chrony", "el7", "4.5", url])
        self.assertEqual(call["env"]["AUX_SOURCE"], "10")
        self.assertEqual(call["env"]["ASSETS_PATH"], "platforms/el7/packages/chrony/assets")
        self.assertEqual(call["env"]["DIST_DIR"], "dist/el7/chrony")
        self.assertEqual(call["env"]["PACKAGING_EL"], "el7")

    def test_build_ntp_triggers_prebuild_hook_by_token(self):
        url = "https://ntp.test/ntp-4.2.8p15.tar.gz"
        result = self.sandbox.run("build", "el7", "ntp", "4.2.8p15", url)
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.sandbox.prebuild_log()
        self.assertEqual(len(log), 5, log)
        self.assertEqual(log[0], f"arg:{self.sandbox.root}")  # 带空格路径保真
        self.assertEqual(log[1], "arg:el7")
        self.assertIn("SPEC_PATH:platforms/el7/packages/ntp/ntp.spec", log)
        self.assertIn("PACKAGE:ntp", log)
        self.assertIn("BUILD_PLATFORM:el7", log)
        call = self.sandbox.invocations()[0]
        self.assertEqual(call["env"]["AUX_SOURCE"], "5")
        self.assertEqual(call["env"]["PRE_BUILD"], "ntp-openssl")
        self.assertEqual(call["cmd"][1], "/src/scripts/build-upstream.sh")

    def test_new_platform_runs_without_hardcoded_mapping(self):
        result = self.sandbox.run("build", "el9test", "demo", "1.0",
                                  "https://demo.test/demo-1.0.tar.gz")
        self.assertEqual(result.returncode, 0, result.stderr)
        call = self.sandbox.invocations()[0]
        self.assertEqual(call["image"], f"registry.test/el9@sha256:{SHA3}")
        self.assertEqual(call["env"]["PACKAGING_EL"], "el7")  # 新平台复用已有 repos 家族
        self.assertEqual(call["env"]["DIST_DIR"], "dist/el9test/demo")
        self.assertEqual(call["cmd"][3], "el9test")  # build-upstream.sh <pkg> <platform> ...

    def test_build_openssh_rejects_malformed_version_before_side_effects(self):
        result = self.sandbox.run("build", "el7", "openssh", "not-a-p-version")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid OpenSSH version", result.stderr)
        self.assertEqual(self.sandbox.invocations(), [])
        self.assertFalse((self.sandbox.root / "dist/el7/openssh").exists())

    def test_build_openssh_deb_uses_amd64_and_deb_scripts(self):
        result = self.sandbox.run("build", "ubuntu2204", "openssh")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.sandbox.invocations()
        self.assertEqual(len(calls), 1)  # DEB 门禁内置于构建脚本末尾
        call = calls[0]
        self.assertEqual(call["cmd"], ["bash", "/src/scripts/build-openssh-deb.sh", "10.1p1"])
        self.assertIn(("--platform", "linux/amd64"), call["opts"])
        self.assertEqual(call["env"]["PACKAGING_EL"], "")
        self.assertEqual(call["env"]["DIST_DIR"], "dist/ubuntu2204/openssh")
        self.assertEqual(call["env"]["PACKAGING_PATH"],
                         "platforms/ubuntu2204/packages/openssh/debian")

    # ---- test 阶段版本来源：一律读构建元数据，不回退源 spec ----

    def test_test_reads_actual_versions_from_dist_metadata(self):
        # 源 spec 停留在 10.1p1/4.5，构建元数据是显式新版本：测试必须用新版本。
        self.sandbox.stage_build_spec("dist/el7/openssh", "10.9p9")
        self.sandbox.stage_build_json("dist/ubuntu2204/openssh", "10.9p9")
        self.sandbox.write_dist_file("dist/el7/chrony", "build.spec",
                                     "Name: chrony\nVersion: 9.9\nRelease: 1%{?dist}\n")

        rpm = self.sandbox.run("test", "el7", "openssh", "upgrade")
        self.assertEqual(rpm.returncode, 0, rpm.stderr)
        rpm_call = self.sandbox.invocations()[0]
        self.assertEqual(rpm_call["cmd"], ["bash", "/src/scripts/test-install.sh", "el7", "upgrade"])
        self.assertEqual(rpm_call["env"]["VERSION"], "10.9p9")  # 来自 build.spec

        deb = self.sandbox.run("test", "ubuntu2204", "openssh", "fresh")
        self.assertEqual(deb.returncode, 0, deb.stderr)
        deb_call = self.sandbox.invocations()[-1]
        self.assertEqual(deb_call["cmd"],
                         ["bash", "/src/scripts/test-openssh-deb.sh", "fresh", "10.9p9"])

        upstream = self.sandbox.run("test", "el7", "chrony")
        self.assertEqual(upstream.returncode, 0, upstream.stderr)
        upstream_call = self.sandbox.invocations()[-1]
        self.assertEqual(upstream_call["cmd"],
                         ["bash", "/src/scripts/test-upstream-install.sh", "chrony", "el7", "9.9"])

    def test_test_rejects_missing_build_metadata(self):
        for args in (("test", "el7", "openssh"),
                     ("test", "ubuntu2204", "openssh"),
                     ("test", "el7", "chrony")):
            result = self.sandbox.run(*args)
            self.assertEqual(result.returncode, 2, f"args={args}: {result.stderr}")
            self.assertIn("missing build metadata", result.stderr)
        self.assertEqual(self.sandbox.invocations(), [])

    def test_test_rejects_mismatched_metadata(self):
        # DEB：build.json 归属与请求目标不符。
        self.sandbox.stage_build_json("dist/ubuntu2204/openssh", "10.1p1",
                                      package="otherpkg", platform="ubuntu2204")
        result = self.sandbox.run("test", "ubuntu2204", "openssh")
        self.assertEqual(result.returncode, 2)
        self.assertIn("does not match target ubuntu2204/openssh", result.stderr)
        (self.sandbox.root / "dist/ubuntu2204/openssh/build.json").unlink()
        self.sandbox.stage_build_json("dist/ubuntu2204/openssh", "10.1p1",
                                      package="openssh", platform="el9bogus")
        result = self.sandbox.run("test", "ubuntu2204", "openssh")
        self.assertEqual(result.returncode, 2)
        self.assertIn("does not match target", result.stderr)
        # RPM：build.spec 版本格式非法。
        self.sandbox.write_dist_file("dist/el7/openssh", "build.spec",
                                     "%global ver broke.format\n")
        result = self.sandbox.run("test", "el7", "openssh")
        self.assertEqual(result.returncode, 2)
        self.assertIn("malformed", result.stderr)
        # upstream：build.spec 缺 Version: 字段。
        self.sandbox.write_dist_file("dist/el7/chrony", "build.spec",
                                     "%global ver 4.5\n")
        result = self.sandbox.run("test", "el7", "chrony")
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot parse version", result.stderr)
        self.assertEqual(self.sandbox.invocations(), [])

    def test_test_rejects_build_spec_name_mismatch(self):
        # 宿主侧 Name 字面量识别：build.spec 与请求包不一致直接拒绝，不进容器。
        self.sandbox.write_dist_file("dist/el7/openssh", "build.spec",
                                     "Name: otherpkg\n%global ver 10.1p1\n%global rel 1\n")
        result = self.sandbox.run("test", "el7", "openssh")
        self.assertEqual(result.returncode, 2)
        self.assertIn("does not match target package 'openssh'", result.stderr)
        self.assertEqual(self.sandbox.invocations(), [])

    # ---- 常规 test 调度 ----

    def test_test_openssh_runs_five_clean_scenarios(self):
        self.sandbox.stage_build_spec("dist/el7/openssh", "10.1p1")
        result = self.sandbox.run("test", "el7", "openssh")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.sandbox.invocations()
        self.assertEqual([call["cmd"][-1] for call in calls],
                         ["fresh", "upgrade", "reinstall", "uninstall", "symlink-guard"])
        for call in calls:
            self.assertEqual(call["cmd"],
                             ["bash", "/src/scripts/test-install.sh", "el7", call["cmd"][-1]])
            self.assertTrue(is_readonly(call))
            self.assertEqual(call["env"]["VERSION"], "10.1p1")

    def test_test_single_scenario_only_runs_that_scenario(self):
        self.sandbox.stage_build_spec("dist/el7/openssh", "10.1p1")
        result = self.sandbox.run("test", "el7", "openssh", "upgrade")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.sandbox.invocations()), 1)

    def test_test_failure_accumulates_across_scenarios(self):
        self.sandbox.stage_build_spec("dist/el7/openssh", "10.1p1")
        result = self.sandbox.run("test", "el7", "openssh", fail_substring="el7 upgrade")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(self.sandbox.invocations()), 5)  # 失败不中断其余场景

    def test_test_openssh_deb_runs_five_scenarios_with_version(self):
        self.sandbox.stage_build_json("dist/ubuntu2204/openssh", "10.1p1")
        result = self.sandbox.run("test", "ubuntu2204", "openssh")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.sandbox.invocations()
        self.assertEqual(len(calls), 5)
        for call, scenario in zip(calls, ["fresh", "upgrade", "reinstall", "uninstall", "symlink-guard"]):
            self.assertEqual(call["cmd"],
                             ["bash", "/src/scripts/test-openssh-deb.sh", scenario, "10.1p1"])
            self.assertIn(("--platform", "linux/amd64"), call["opts"])

    def test_test_upstream_is_single_smoke_with_dist_version(self):
        self.sandbox.write_dist_file("dist/el7/chrony", "build.spec",
                                     "Name: chrony\nVersion: 4.5\nRelease: 1%{?dist}\n")
        result = self.sandbox.run("test", "el7", "chrony")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.sandbox.invocations()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["cmd"],
                         ["bash", "/src/scripts/test-upstream-install.sh", "chrony", "el7", "4.5"])

    def test_test_upstream_rejects_scenario_arguments(self):
        result = self.sandbox.run("test", "el7", "chrony", "fresh")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.sandbox.invocations(), [])

    def test_unknown_package_fails_before_any_container(self):
        result = self.sandbox.run("build", "el7", "nosuchpkg", "1.0", "https://x.test/a.tar.gz")
        self.assertEqual(result.returncode, 2)
        self.assertIn("nosuchpkg", result.stderr)
        self.assertEqual(self.sandbox.invocations(), [])

    # ---- 宿主 Python 解释器注入（PYTHON，默认 /usr/bin/python3）----

    def test_host_python_calls_go_through_injected_interpreter(self):
        # 假 python：记录 argv 后透传真实解释器，证明宿主调用全部走 "$PYTHON"。
        fake = self.sandbox.root / "bin" / "python-fake"
        fake.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            printf 'argv:%s\n' "$*" >> "${PYTHON_LOG:?PYTHON_LOG missing}"
            exec /usr/bin/python3 "$@"
            """))
        fake.chmod(0o755)
        python_log = str(self.sandbox.root / "python.log")
        result = self.sandbox.run("build", "el7", "openssh",
                                  extra_env={"PYTHON": str(fake), "PYTHON_LOG": python_log})
        self.assertEqual(result.returncode, 0, result.stderr)
        log = (self.sandbox.root / "python.log").read_text().splitlines()
        self.assertIn("argv:scripts/project_config.py shell el7 openssh", log)
        self.assertEqual(len(self.sandbox.invocations()), 2)  # 注入后调度不受影响

    def test_missing_python_interpreter_fails_before_anything(self):
        result = self.sandbox.run("build", "el7", "openssh",
                                  extra_env={"PYTHON": "/nonexistent/python-xyz"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("PYTHON interpreter not found", result.stderr)
        self.assertIn("/nonexistent/python-xyz", result.stderr)
        self.assertEqual(self.sandbox.invocations(), [])
        self.assertFalse((self.sandbox.root / "dist/el7/openssh").exists())


class RpmIdentityTest(unittest.TestCase):
    """scripts/rpm-identity.sh 直测：用真实已构建 el8 chrony 产物（只读）+
    宿主只读 rpm。产物或宿主 rpm 缺失时跳过（不新增宿主依赖）。"""

    REAL_DIST = ROOT / "dist/el8/chrony"
    REAL_SPEC = ROOT / "platforms/el8/packages/chrony/chrony.spec"
    NTP_SPEC = ROOT / "platforms/el8/packages/ntp/ntp.spec"

    @classmethod
    def setUpClass(cls):
        cls.have_artifacts = cls.REAL_DIST.is_dir() and cls.REAL_SPEC.is_file() \
            and any(cls.REAL_DIST.glob("chrony-*.rpm"))
        cls.skip_message = "real el8 chrony artifacts or host rpm binary unavailable"

    def verify(self, dist, spec, platform, version):
        return subprocess.run(
            ["bash", "-c",
             'source "$1/scripts/rpm-identity.sh" && '
             'rpm_identity_verify "$2" "$3" "$4" "$5"',
            "bash", str(ROOT), str(dist), str(spec), platform, version],
            capture_output=True, text=True, cwd=str(ROOT),
        )

    def allowed_names(self, spec, platform):
        return subprocess.run(
            ["bash", "-c",
             'source "$1/scripts/rpm-identity.sh" && '
             'rpm_identity_allowed_names "$2" "$3"',
            "bash", str(ROOT), str(spec), platform],
            capture_output=True, text=True, cwd=str(ROOT),
        )

    def _build_unrelated_rpm(self, tmpdir):
        """用宿主 rpmbuild 构造与 chrony 同 EVR 的无关包（Name: unrelated）。"""
        top = tmpdir / "top"
        for sub in ("BUILD", "RPMS", "SOURCES", "SPECS", "SRPMS"):
            (top / sub).mkdir(parents=True)
        spec = top / "SPECS" / "unrelated.spec"
        spec.write_text(textwrap.dedent("""\
            Name:           unrelated
            Version:        4.9
            Release:        1%{?dist}
            Summary:        identity-check fixture
            License:        MIT
            %description
            Fixture for rpm-identity tests.
            %install
            mkdir -p %{buildroot}/etc
            echo fixture > %{buildroot}/etc/unrelated-fixture
            %files
            %defattr(644,root,root,755)
            /etc/unrelated-fixture
            """))
        subprocess.run(
            ["rpmbuild", "-bb", "--define", f"_topdir {top}", "--define", "dist .el8", str(spec)],
            check=True, capture_output=True, text=True,
        )
        return top / "RPMS" / "x86_64" / "unrelated-4.9-1.el8.x86_64.rpm"

    @unittest.skipUnless(__import__("shutil").which("rpm"), "host rpm binary unavailable")
    def test_accepts_real_chrony_el8(self):
        if not self.have_artifacts:
            self.skipTest(self.skip_message)
        result = self.verify(self.REAL_DIST, self.REAL_SPEC, "el8", "4.9")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("matches build.spec (chrony-4.9-1.el8, platform el8)", result.stdout)

    @unittest.skipUnless(__import__("shutil").which("rpm"), "host rpm binary unavailable")
    def test_rejects_renamed_package_same_version(self):
        if not self.have_artifacts:
            self.skipTest(self.skip_message)
        with tempfile.TemporaryDirectory() as folder:
            dist = pathlib.Path(folder)
            for rpm in self.REAL_DIST.glob("chrony-4.9*.rpm"):
                shutil.copyfile(rpm, dist / rpm.name.replace("chrony", "otherpkg", 1))
            result = self.verify(dist, self.REAL_SPEC, "el8", "4.9")
        self.assertNotEqual(result.returncode, 0)
        # 拒绝路径：文件名与自身 header 身份不一致（改名冒充/错放目录）。
        self.assertIn("filename does not match rpm header", result.stderr)
        self.assertIn("header says chrony-4.9-1.el8.x86_64.rpm", result.stderr)

    @unittest.skipUnless(__import__("shutil").which("rpm"), "host rpm binary unavailable")
    def test_rejects_version_mismatch_between_spec_and_rpms(self):
        if not self.have_artifacts:
            self.skipTest(self.skip_message)
        result = self.verify(self.REAL_DIST, self.REAL_SPEC, "el8", "4.10")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("identity mismatch", result.stderr)

    @unittest.skipUnless(__import__("shutil").which("rpm"), "host rpm binary unavailable")
    def test_rejects_wrong_platform_rpms(self):
        if not self.have_artifacts:
            self.skipTest(self.skip_message)
        # el8 包对 centos7 目标：期望 Release 1.centos7 ≠ 实际 1.el8。
        result = self.verify(self.REAL_DIST, self.REAL_SPEC, "centos7", "4.9")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("identity mismatch", result.stderr)

    @unittest.skipUnless(
        __import__("shutil").which("rpmspec") and __import__("shutil").which("rpmbuild"),
        "host rpmspec/rpmbuild unavailable")
    def test_ntp_non_prefix_subpackages_are_declared(self):
        if not self.NTP_SPEC.is_file():
            self.skipTest("ntp spec unavailable")
        result = self.allowed_names(self.NTP_SPEC, "el8")
        self.assertEqual(result.returncode, 0, result.stderr)
        names = set(result.stdout.split())
        # %package -n ntpdate / -n sntp：非主包前缀子包必须进允许集合。
        self.assertIn("ntp", names)
        self.assertIn("ntpdate", names)
        self.assertIn("sntp", names)
        self.assertIn("ntp-perl", names)

    @unittest.skipUnless(
        __import__("shutil").which("rpmspec") and __import__("shutil").which("rpmbuild"),
        "host rpmspec/rpmbuild unavailable")
    def test_rejects_unrelated_package_same_evr(self):
        if not self.have_artifacts:
            self.skipTest(self.skip_message)
        with tempfile.TemporaryDirectory() as folder:
            dist = pathlib.Path(folder)
            for rpm in self.REAL_DIST.glob("chrony-4.9*.rpm"):
                shutil.copyfile(rpm, dist / rpm.name)
            unrelated = self._build_unrelated_rpm(pathlib.Path(folder))
            self.assertTrue(unrelated.is_file())
            shutil.copyfile(unrelated, dist / unrelated.name)
            result = self.verify(dist, self.REAL_SPEC, "el8", "4.9")
        self.assertNotEqual(result.returncode, 0)
        # 同 EVR 但 spec 未声明的包名必须拒绝，不能被安装。
        self.assertIn("is not declared by", result.stderr)
        self.assertIn("'unrelated'", result.stderr)


class LocalForwardTest(unittest.TestCase):
    """旧 local-* 入口转发到 package.sh，all 按配置动态筛选，不保留第二套实现。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="pkg runner ")
        self.addCleanup(self._tmp.cleanup)
        self.sandbox = PackageSandbox(pathlib.Path(self._tmp.name))

    def test_local_build_forwards_to_package_build(self):
        result = self.sandbox.run("centos7", script="local-build.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        build, verify = self.sandbox.invocations()
        self.assertEqual(build["cmd"], ["bash", "/src/scripts/build-in-container.sh"])
        self.assertEqual(verify["cmd"], ["bash", "/src/scripts/verify-rpms.sh", "centos7"])

    def test_local_build_all_follows_enabled_targets(self):
        # el9test/demo 未包含 openssh：all openssh 不得波及；暂停的 vim 同理被排除。
        result = self.sandbox.run("all", "openssh", script="local-build.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        build_scripts = {"/src/scripts/build-in-container.sh", "/src/scripts/build-openssh-deb.sh"}
        builds = [call for call in self.sandbox.invocations() if call["cmd"][1] in build_scripts]
        self.assertEqual(sorted(call["env"]["BUILD_PLATFORM"] for call in builds),
                         ["centos7", "el7", "ubuntu2204"])

    def test_local_build_all_rejects_package_without_enabled_targets(self):
        # vim 在夹具中 enabled: false：无启用平台时明确失败，绝不猜测平台。
        result = self.sandbox.run("all", "vim", script="local-build.sh")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no enabled platform builds 'vim'", result.stderr)
        self.assertEqual(self.sandbox.invocations(), [])

    def test_local_test_all_follows_enabled_targets(self):
        self.sandbox.write_dist_file("dist/el9test/demo", "build.spec",
                                     "Name: demo\nVersion: 1.0\nRelease: 1%{?dist}\n")
        result = self.sandbox.run("all", "demo", script="local-test.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.sandbox.invocations()
        self.assertEqual(len(calls), 1)  # demo 只在 el9test 启用
        self.assertEqual(calls[0]["env"]["BUILD_PLATFORM"], "el9test")
        self.assertEqual(calls[0]["cmd"],
                         ["bash", "/src/scripts/test-upstream-install.sh", "demo", "el9test", "1.0"])

    def test_local_test_legacy_scenario_signature(self):
        # 旧用法：场景直接跟在平台后，包固定 openssh。
        self.sandbox.stage_build_spec("dist/el7/openssh", "10.1p1")
        result = self.sandbox.run("el7", "upgrade", script="local-test.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.sandbox.invocations()
        self.assertEqual(calls[0]["cmd"], ["bash", "/src/scripts/test-install.sh", "el7", "upgrade"])

    def test_local_test_forwards_custom_package(self):
        self.sandbox.write_dist_file("dist/el7/chrony", "build.spec",
                                     "Name: chrony\nVersion: 4.5\nRelease: 1%{?dist}\n")
        result = self.sandbox.run("el7", "chrony", script="local-test.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.sandbox.invocations()[0]["cmd"][1],
                         "/src/scripts/test-upstream-install.sh")

    def test_local_all_routes_python_through_injected_interpreter(self):
        fake = self.sandbox.root / "bin" / "python-fake"
        fake.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            printf 'argv:%s\n' "$*" >> "${PYTHON_LOG:?PYTHON_LOG missing}"
            exec /usr/bin/python3 "$@"
            """))
        fake.chmod(0o755)
        python_log = self.sandbox.root / "python.log"
        self.sandbox.write_dist_file("dist/el9test/demo", "build.spec",
                                     "Name: demo\nVersion: 1.0\nRelease: 1%{?dist}\n")
        result = self.sandbox.run("all", "demo", script="local-test.sh",
                                  extra_env={"PYTHON": str(fake), "PYTHON_LOG": str(python_log)})
        self.assertEqual(result.returncode, 0, result.stderr)
        log = python_log.read_text().splitlines()
        self.assertIn("argv:- demo", log)  # enabled_platforms 的 heredoc 调用走 "$PYTHON"


if __name__ == "__main__":
    unittest.main()
