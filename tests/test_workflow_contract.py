"""Workflow scheduling contract: unified matrix, artifact gating, serial finalize.

验证的是工作流真实调度行为契约：job DAG（tests 是发布链一等门禁）、每 job 独立
依赖安装、宿主 Python 显式 /usr/bin/python3、无 rebase 的回写重放循环、
skip_release/dry_run 门禁与统一矩阵入口。
"""

import os
import pathlib
import re
import sys
import unittest

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import publish_release  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/rpm-xinchuang.yml"


def load_workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def step_script(job, step_name):
    for step in load_workflow()["jobs"][job]["steps"]:
        if step.get("name") == step_name:
            return step.get("run", "")
    raise AssertionError("step %r not found in job %r" % (step_name, job))


class WorkflowContractTest(unittest.TestCase):
    def setUp(self):
        self.doc = load_workflow()
        self.jobs = self.doc["jobs"]

    def needs(self, job):
        value = self.jobs[job]["needs"]
        return [value] if isinstance(value, str) else value

    def triggers(self):
        # PyYAML 会把裸键 on 解析成 True，两种形态都要兼容。
        return self.doc.get("on") or self.doc.get(True)

    def test_triggers_and_concurrency(self):
        triggers = self.triggers()
        self.assertEqual(sorted(triggers), ["schedule", "workflow_dispatch"])
        self.assertNotIn("pull_request", triggers, "外部 PR 绝不能拿到仓库 token")
        concurrency = self.doc["concurrency"]
        self.assertEqual(concurrency["group"], "rpm-xinchuang")
        self.assertFalse(concurrency["cancel-in-progress"])

    def test_job_dependency_chain_gates_everything_on_local_tests(self):
        # 本地行为测试是一等门禁：任何构建/发布/收口 job 都不得绕过 tests。
        self.assertEqual(self.needs("build"), ["check", "tests"])
        self.assertEqual(self.needs("test"), ["check", "tests", "build"])
        self.assertEqual(self.needs("publish"), ["check", "tests", "build", "test"])
        self.assertEqual(self.needs("finalize"), ["check", "tests", "build", "test", "publish"])
        self.assertEqual(self.needs("scheduled-time"),
                         ["check", "tests", "build", "test", "publish", "finalize"])
        for job in ("build", "test", "publish", "finalize"):
            condition = self.jobs[job]["if"]
            self.assertIn("always()", condition, job)
            self.assertIn("needs.tests.result == 'success'", condition, job)
        # 旧专用 OpenSSH build/test/release job 必须消失。
        for legacy in ("build-el7", "build-el8", "test-el7", "test-el8",
                       "release", "component-build", "component-install",
                       "component-release", "component-record"):
            self.assertNotIn(legacy, self.jobs)

    def test_matrix_jobs_use_fail_fast_false_and_the_platform_field(self):
        for job in ("build", "test", "publish"):
            strategy = self.jobs[job]["strategy"]
            self.assertFalse(strategy["fail-fast"], job)
            self.assertIn("fromJSON(needs.check.outputs.matrix)", strategy["matrix"])
        script = step_script("build", "统一构建入口（含产物门禁）")
        self.assertIn('bash scripts/package.sh build "$PLATFORM" "$PACKAGE" "$VERSION"', script)
        # OpenSSH 构建只接受 VERSION（固定官方源），URL 仅对 upstream 组件追加。
        self.assertIn('case "$PACKAGE_KIND"', script)
        self.assertIn("openssh-*) ;;", script)
        self.assertIn('cmd+=("$URL")', script)
        install = step_script("test", "干净目标系统安装行为测试（SSH 五场景 / 组件 smoke）")
        self.assertIn('bash scripts/package.sh test "$PLATFORM" "$PACKAGE"', install)
        self.assertNotIn("$URL", install)
        self.assertNotIn("test \"$PLATFORM\" \"$PACKAGE\" \"$VERSION\"", install)

    def test_artifacts_associate_combinations_exactly(self):
        upload = next(step for step in self.jobs["build"]["steps"]
                      if step.get("name") == "上传构建产物")
        self.assertEqual(upload["with"]["name"], "built-${{ matrix.platform }}-${{ matrix.package }}")
        verified = next(step for step in self.jobs["test"]["steps"]
                        if step.get("name") == "上传安装验证凭据")
        self.assertEqual(verified["with"]["name"],
                         "verified-${{ matrix.platform }}-${{ matrix.package }}")
        receipt = next(step for step in self.jobs["publish"]["steps"]
                       if step.get("name", "").startswith("上传发布凭据"))
        self.assertEqual(receipt["with"]["name"],
                         "receipt-${{ matrix.platform }}-${{ matrix.package }}")

    def test_publish_and_finalize_are_gated_by_verified_marker_and_skip_release(self):
        publish_if = self.jobs["publish"]["if"]
        self.assertIn("inputs.skip_release != true", publish_if)
        for step in self.jobs["publish"]["steps"]:
            if step.get("name", "").startswith("幂等发布"):
                self.assertIn("hashFiles(format('verified/{0}-{1}', matrix.platform, "
                              "matrix.package)) != ''", step["if"])
        self.assertIn("inputs.skip_release != true", self.jobs["finalize"]["if"])

    def test_finalize_is_the_serial_cleanup_and_writeback_point(self):
        cleanup = step_script("finalize", "集中串行清理历史 Release（先校验后删除，保留 Git tag）")
        self.assertIn("prune_releases.py --repo \"$GITHUB_REPOSITORY\"", cleanup)
        self.assertIn("--dry-run", cleanup)
        writeback = step_script("finalize",
                                "回写成功基线（每轮取最新分支重放 receipt + 防降级，无 rebase 状态残留）")
        # 重放循环：每轮强制回到最新远端分支，无 rebase；record 在循环内重放。
        self.assertIn("git checkout -f -B \"$BRANCH\" \"origin/$BRANCH\"", writeback)
        self.assertNotIn("git rebase", writeback)
        self.assertIn("/usr/bin/python3 scripts/record_versions.py version.json", writeback)
        self.assertIn("git add version.json", writeback)
        self.assertNotRegex(writeback, r"git add [^\n]*spec")
        self.assertLess(writeback.index("record_versions.py"), writeback.index("git add version.json"))
        self.assertIn("push 冲突，重试", writeback)

    def test_workflow_never_leaves_a_rebase_in_progress(self):
        text = WORKFLOW.read_text()
        self.assertNotIn("git rebase", text, "重试路径必须无 rebase 状态残留")

    def test_dry_run_skips_the_writeback(self):
        for step in self.jobs["finalize"]["steps"]:
            if step.get("name", "").startswith("回写成功基线"):
                self.assertIn("env.DRY_RUN != 'true'", step["if"])

    def test_check_uses_the_new_detection_interface(self):
        script = step_script("check", "检测启用上游相对各平台基线的更新")
        self.assertIn("/usr/bin/python3 scripts/check_versions.py", script)
        self.assertIn("--targets", script)
        self.assertIn("--openssh-version", script)
        text = WORKFLOW.read_text()
        self.assertNotIn("--repair-pam", text)
        self.assertNotIn("--retry-component", text)
        self.assertNotIn("select-release-rpm.sh", text, "选择器已删除，发布走 rpm header")
        self.assertNotIn("publish-openssh-deb.sh", text, "DEB 发布并入 publish_release.py")
        self.assertNotIn("build-openssh-deb.sh", text, "构建统一走 package.sh")
        self.assertNotIn("build-in-container.sh", text, "CI 不得绕过统一入口")
        self.assertNotIn("sed -i", text, "CI 不得手动改写源 spec")

    def test_every_host_job_installs_its_own_python_dependencies(self):
        # job 隔离：使用宿主 Python 的 job 必须自带依赖安装，不依赖其他 job。
        for job, packages in (("check", ("python3-yaml",)),
                              ("build", ("python3-yaml",)),
                              ("test", ("python3-yaml",)),
                              ("publish", ("python3-rpm", "python3-yaml")),
                              ("finalize", ("python3-rpm", "python3-yaml")),
                              ("tests", ("rpm", "python3-rpm", "python3-yaml"))):
            runs = [step.get("run", "") for step in self.jobs[job]["steps"]]
            joined = "\n".join(runs)
            for package in packages:
                self.assertIn(package, joined, "%s 缺少 %s 安装" % (job, package))

    def test_host_python_is_explicit_and_publish_justifies_its_rpm_binding(self):
        text = WORKFLOW.read_text()
        self.assertIn("/usr/bin/python3 scripts/publish_release.py", text)
        self.assertIn("/usr/bin/python3 scripts/project_config.py", text)
        self.assertNotRegex(text, r"(?m)^\s*python3 scripts/", "宿主 Python 必须显式 /usr/bin/python3")
        # package.sh 的宿主 Python 由 PYTHON 环境变量显式指定（build/test 注入）。
        for job in ("build", "test"):
            self.assertEqual(self.jobs[job]["env"].get("PYTHON"), "/usr/bin/python3", job)
        # publish 读取 rpm header / spec 包集合，python3-rpm 安装不是冗余。
        self.assertTrue(hasattr(publish_release, "read_rpm_header"))
        self.assertTrue(hasattr(publish_release, "spec_package_names"))

    def test_local_tests_job_runs_the_suite(self):
        job = self.jobs["tests"]
        runs = [step.get("run", "") for step in job["steps"]]
        self.assertTrue(any("unittest discover -s tests" in run for run in runs))

    def test_permissions_follow_least_privilege(self):
        self.assertEqual(self.doc["permissions"], {"contents": "read"})
        for job in ("publish", "finalize", "scheduled-time"):
            self.assertEqual(self.jobs[job]["permissions"], {"contents": "write"}, job)
        for job in ("check", "build", "test"):
            self.assertNotIn("permissions", self.jobs[job], job)

    def test_scheduled_time_records_even_without_updates(self):
        condition = self.jobs["scheduled-time"]["if"]
        # 无更新时上游 job 全部 skip：必须 always() + 显式放行 no-update 分支。
        self.assertIn("always()", condition)
        self.assertIn("github.event_name == 'schedule'", condition)
        self.assertIn("needs.tests.result == 'success'", condition)
        self.assertIn("needs.check.outputs.has_updates != 'true'", condition)
        for job in ("build", "test", "publish", "finalize"):
            self.assertIn("needs.%s.result == 'success'" % job, condition)


class WorkflowScriptContractTest(unittest.TestCase):
    """发布/清理/回写脚本与工作流命令保持契约一致（防止单方面改名）。"""

    def test_finalize_calls_match_script_interfaces(self):
        text = WORKFLOW.read_text()
        self.assertIn("scripts/publish_release.py", text)
        self.assertRegex(text, r"prune_releases\.py --repo \"\$GITHUB_REPOSITORY\" \$dry")
        self.assertRegex(text, r"record_versions\.py version\.json \"\$\{receipts\[@\]\}\"")

    def test_workflow_is_valid_yaml_with_expected_entry_names(self):
        doc = load_workflow()
        self.assertEqual(doc["name"], "rpm-Xinchuang")
        steps = [step.get("run", "") for step in doc["jobs"]["check"]["steps"]]
        self.assertTrue(any("check_versions.py" in run for run in steps))


if __name__ == "__main__":
    unittest.main()
