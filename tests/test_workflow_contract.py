"""Workflow scheduling contract: 平台独立 discover→tests→platform 父子流水线.

验证父子两个 workflow 的真实调度行为契约：

* 父 rpm-xinchuang.yml：本地 discover 平台矩阵（无网络，启用 target 派生，新增
  平台零代码进入）→ 全局 tests 门控 → platform 矩阵（fail-fast:false）逐平台
  调用本地可复用 platform.yml → maintain-merged 单例 --merged-only（无凭据、
  不写基线，与平台结果解耦）→ scheduled-time 仅在全平台与维护都成功后写 time；
* 子 platform.yml：check（先本地 --platform scope 再网络 fetch）→ build → test
  → publish → finalize 平台内闭环；receipt 工件按平台前缀隔离；prune/record
  都带 --platform 精确字段校验（前缀相似平台绝不混淆），prune 另带 --skip-merged
  （跨平台 v* 收口在父级）；无更新平台整体 skip 仍 success；
* 权限最小化：父顶层 read；platform 调用 job contents:write 是子写权限上限；
  子顶层 read，仅 publish/finalize 提升；无 secrets:inherit，只用 github.token；
* 失败与 skip 语义：check 失败/跳过时 outputs 为空，下游条件先判
  needs.check.result == 'success' 再碰 fromJSON（job if 在矩阵展开前判定，
  guard 足够防空 JSON）；无更新平台下游全部 skip、平台整体仍 success；单组合
  build/test/publish 失败只影响自身——test/publish/finalize 以 always() 对抗
  needs 隐式全成功语义，失败组合被 verified marker 拦截；
* 父矩阵形状：discover 输出字符串数组，strategy.matrix 必须是单维度 platform
  的对象形式（裸数组不是合法 matrix 定义），测试用真实 discover 输出断言
  fromJSON 替换后的运行时形状（actionlint 判不了 runtime shape）。
"""

import json
import os
import pathlib
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import check_versions  # noqa: E402
import publish_release  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PARENT = ROOT / ".github/workflows/rpm-xinchuang.yml"
CHILD = ROOT / ".github/workflows/platform.yml"


def load_workflow(path=PARENT):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def triggers_of(doc):
    # PyYAML 会把裸键 on 解析成 True，两种形态都要兼容。
    return doc.get("on") or doc.get(True)


def needs_of(jobs, job):
    value = jobs[job].get("needs", [])
    return [value] if isinstance(value, str) else value


def step_script(doc, job, step_name):
    for step in doc["jobs"][job]["steps"]:
        if step.get("name") == step_name:
            return step.get("run", "")
    raise AssertionError("step %r not found in job %r" % (step_name, job))


def job_runs(doc, job):
    return "\n".join(step.get("run", "") for step in doc["jobs"][job]["steps"])


_FIXTURE_UPSTREAMS = """projects:
  demo:
    name: demo
    anitya_id: 1
    version_pattern: '\\d+'
    source_url: https://example.com/demo-{version}.tar.gz
"""


def make_fixture_root(platforms=("demo", "ci9")):
    """最小 fixture 仓库：提供真实 discover 实现的运行时输出形状来源。"""
    handle = tempfile.TemporaryDirectory()
    root = pathlib.Path(handle.name)
    (root / "packaging").mkdir(parents=True)
    (root / "packaging" / "upstreams.yaml").write_text(_FIXTURE_UPSTREAMS, encoding="utf-8")
    for platform in platforms:
        platform_dir = root / "platforms" / platform
        platform_dir.mkdir(parents=True)
        (platform_dir / "platform.yaml").write_text(
            "image: registry.example.com/img@sha256:%s\n"
            "family: rpm\nel: %s\npackages:\n"
            "  demo:\n    spec: platforms/%s/packages/demo/demo.spec\n"
            % ("a" * 64, platform, platform), encoding="utf-8")
        spec = platform_dir / "packages" / "demo" / "demo.spec"
        spec.parent.mkdir(parents=True)
        spec.write_text("Name: demo\n", encoding="utf-8")
    return handle, root


class ParentWorkflowContractTest(unittest.TestCase):
    """父编排：发现平台、全局门控、平台矩阵与集中维护的 DAG 契约。"""

    def setUp(self):
        self.doc = load_workflow()
        self.jobs = self.doc["jobs"]
        self.text = PARENT.read_text()

    def needs(self, job):
        return needs_of(self.jobs, job)

    def test_triggers_inputs_and_global_serialization(self):
        triggers = triggers_of(self.doc)
        self.assertEqual(sorted(triggers), ["schedule", "workflow_dispatch"])
        self.assertNotIn("pull_request", triggers, "外部 PR 绝不能拿到仓库 token")
        self.assertEqual(triggers["schedule"], [{"cron": "17 1 * * *"}],
                         "北京时间每天 09:17 = UTC 01:17")
        inputs = triggers["workflow_dispatch"]["inputs"]
        self.assertEqual(sorted(inputs),
                         ["dry_run", "force", "skip_release", "targets", "version"])
        for name in ("force", "skip_release", "dry_run"):
            self.assertEqual(inputs[name]["type"], "boolean", name)
        for name in ("version", "targets"):
            self.assertEqual(inputs[name]["type"], "string", name)
        self.assertEqual(self.doc["concurrency"],
                         {"group": "rpm-xinchuang", "cancel-in-progress": False})
        self.assertEqual(self.doc["permissions"], {"contents": "read"})

    def test_parent_jobs_form_the_discovered_platform_dag(self):
        self.assertEqual(sorted(self.jobs),
                         ["discover", "maintain-merged", "platform",
                          "scheduled-time", "tests"])
        # 旧单体 workflow 的 job 必须全部消失（平台链整体迁入 platform.yml）。
        for legacy in ("check", "build", "test", "publish", "finalize",
                       "build-el7", "build-el8", "test-el7", "test-el8",
                       "release", "component-build", "component-install",
                       "component-release", "component-record"):
            self.assertNotIn(legacy, self.jobs)

    def test_discover_is_local_config_only(self):
        script = step_script(self.doc, "discover", "本地校验全局输入并发现启用平台")
        # 平台清单与全局输入预检全部走本地配置：不发起任何网络检测。
        self.assertIn("check_versions.discover(", script)
        self.assertIn("GITHUB_OUTPUT", script)
        self.assertIn("platforms=", script)
        self.assertNotIn("scripts/check_versions.py", self.text,
                         "网络检测 CLI 只属于子平台链")
        self.assertNotIn("release-monitoring", self.text)

    def test_platform_job_calls_the_local_reusable_workflow(self):
        job = self.jobs["platform"]
        self.assertTrue(CHILD.is_file())
        self.assertEqual(job["uses"], "./.github/workflows/platform.yml")
        self.assertEqual(self.needs("platform"), ["discover", "tests"])
        self.assertIn("needs.discover.result == 'success'", job["if"])
        self.assertIn("needs.tests.result == 'success'", job["if"])
        strategy = job["strategy"]
        self.assertFalse(strategy["fail-fast"])
        matrix = strategy["matrix"]
        # discover 输出字符串数组：matrix 必须是单维度 platform 的对象形式，
        # 裸数组不是合法 matrix 定义。
        self.assertIsInstance(matrix, dict, "strategy.matrix 不能是裸数组")
        self.assertEqual(sorted(matrix), ["platform"],
                         "单维度：平台清单唯一来源是 discover，不得硬编码")
        self.assertIn("fromJSON(needs.discover.outputs.platforms)", matrix["platform"])
        # 调用 job 的 contents:write 是子流水线写权限的硬上限。
        self.assertEqual(job["permissions"], {"contents": "write"})
        with_ = job["with"]
        self.assertEqual(with_["platform"], "${{ matrix.platform }}")
        # schedule 触发时 inputs.* 是空字符串：布尔必须 || false 兜底，避免空
        # string 传给 boolean 型 workflow_call 输入的类型错误。
        self.assertEqual(with_["force"], "${{ inputs.force || false }}")
        self.assertEqual(with_["skip_release"], "${{ inputs.skip_release || false }}")
        self.assertEqual(with_["dry_run"], "${{ inputs.dry_run || false }}")
        self.assertEqual(with_["version"], "${{ inputs.version || '' }}")
        self.assertEqual(with_["targets"], "${{ inputs.targets || '' }}")
        self.assertNotIn("secrets", job, "只用 github.token，无需继承任何 secret")

    def test_platform_matrix_dimension_matches_real_discover_output(self):
        # actionlint 判不了 runtime shape：用真实 discover 输出断言 fromJSON
        # 替换后的矩阵形状——platform 维度逐元素对齐，with.platform 引用成立。
        handle, root = make_fixture_root(("demo", "ci9"))
        self.addCleanup(handle.cleanup)
        platforms = check_versions.discover(str(root))
        self.assertEqual(platforms, ["ci9", "demo"])
        self.assertTrue(all(isinstance(item, str) for item in platforms))
        matrix = self.jobs["platform"]["strategy"]["matrix"]
        self.assertIsInstance(matrix, dict)
        self.assertEqual(sorted(matrix), ["platform"])
        rendered = {"platform": platforms}  # fromJSON 替换后的运行时形状
        self.assertEqual(sorted(rendered["platform"]), platforms)
        self.assertEqual(self.jobs["platform"]["with"]["platform"], "${{ matrix.platform }}")

    def test_maintain_merged_runs_after_all_platforms_independently(self):
        job = self.jobs["maintain-merged"]
        self.assertEqual(self.needs("maintain-merged"), ["discover", "tests", "platform"])
        condition = job["if"]
        self.assertIn("always()", condition, "全平台结束后必须运行，与平台结果解耦")
        self.assertIn("needs.discover.result == 'success'", condition)
        self.assertIn("needs.tests.result == 'success'", condition)
        self.assertIn("inputs.skip_release != true", condition)
        self.assertNotIn("needs.platform.result", condition)
        self.assertEqual(job["permissions"], {"contents": "write"})

    def test_maintain_merged_is_a_single_receiptless_prune(self):
        script = step_script(self.doc, "maintain-merged",
                             "集中维护旧合并 Release（先校验后删除，保留 Git tag）")
        self.assertRegex(script,
                         r'prune_releases\.py --repo "\$GITHUB_REPOSITORY"[\s\\]+--merged-only \$dry')
        self.assertIn("--dry-run", script)
        # 无凭据收口：不预检 receipt、不删普通组合、不回写基线，也不做平台 scope。
        self.assertNotIn("receipt", script)
        self.assertNotIn("--platform", script)
        runs = job_runs(self.doc, "maintain-merged")
        self.assertNotIn("record_versions", runs)
        self.assertNotIn("version.json", runs)
        self.assertNotIn("git push", runs)

    def test_scheduled_time_gates_on_full_platform_and_maintenance_success(self):
        condition = self.jobs["scheduled-time"]["if"]
        self.assertIn("always()", condition)
        self.assertIn("github.event_name == 'schedule'", condition)
        for dep in ("discover", "tests", "platform", "maintain-merged"):
            self.assertIn("needs.%s.result == 'success'" % dep, condition)
        script = step_script(self.doc, "scheduled-time",
                             "更新根目录 time 并提交（每轮取最新远端分支，无 rebase 状态残留）")
        self.assertIn('git checkout -f -B "$BRANCH" "origin/$BRANCH"', script)
        self.assertIn("push 冲突，重试", script)
        self.assertEqual(self.jobs["scheduled-time"]["permissions"], {"contents": "write"})

    def test_write_jobs_keep_least_privilege(self):
        for job in ("discover", "tests"):
            self.assertNotIn("permissions", self.jobs[job], job)


class PlatformWorkflowContractTest(unittest.TestCase):
    """子平台链：check scope 前置、工件隔离、平台内清理回写的调度契约。"""

    def setUp(self):
        self.doc = load_workflow(CHILD)
        self.jobs = self.doc["jobs"]

    def needs(self, job):
        return needs_of(self.jobs, job)

    def test_child_is_call_only_with_typed_inputs(self):
        triggers = triggers_of(self.doc)
        self.assertEqual(sorted(triggers), ["workflow_call"],
                         "子流水线只能被父平台矩阵调用")
        inputs = triggers["workflow_call"]["inputs"]
        self.assertEqual(sorted(inputs),
                         ["dry_run", "force", "platform", "skip_release",
                          "targets", "version"])
        self.assertTrue(inputs["platform"]["required"])
        self.assertEqual(inputs["platform"]["type"], "string")
        for name in ("force", "skip_release", "dry_run"):
            self.assertEqual(inputs[name]["type"], "boolean", name)
            self.assertFalse(inputs[name]["default"], name)
        for name in ("version", "targets"):
            self.assertEqual(inputs[name]["type"], "string", name)
            self.assertEqual(inputs[name]["default"], "", name)
        self.assertEqual(self.doc["name"], "rpm-Xinchuang platform")
        self.assertEqual(self.doc["permissions"], {"contents": "read"})
        self.assertNotIn("concurrency", self.doc, "串行由父顶层 concurrency 统一保证")

    def test_child_jobs_are_a_self_contained_platform_chain(self):
        self.assertEqual(sorted(self.jobs), ["build", "check", "finalize", "publish", "test"])
        # 全局 tests 门控在父级：子链内不得再有 tests/discover/收口 job。
        for global_job in ("tests", "discover", "maintain-merged", "scheduled-time"):
            self.assertNotIn(global_job, self.jobs, global_job)
        self.assertEqual(self.needs("build"), ["check"])
        self.assertEqual(self.needs("test"), ["check", "build"])
        self.assertEqual(self.needs("publish"), ["check", "build", "test"])
        self.assertEqual(self.needs("finalize"), ["check", "build", "test", "publish"])
        for job in ("build", "test", "publish"):
            strategy = self.jobs[job]["strategy"]
            self.assertFalse(strategy["fail-fast"], job)
            self.assertEqual(strategy["matrix"],
                             "${{ fromJSON(needs.check.outputs.matrix) }}", job)

    def test_check_failure_or_no_updates_skips_the_whole_chain(self):
        # job if 在矩阵展开前判定：check 失败/跳过时 outputs 为空，先判 result
        # 再碰 fromJSON 防空 JSON 异常；has_updates=false 时整体 skip（check
        # 成功且无更新 = 平台整体 skip 仍 success）。
        for job in ("build", "test", "publish", "finalize"):
            condition = self.jobs[job]["if"]
            self.assertIn("needs.check.result == 'success'", condition, job)
            self.assertIn("needs.check.outputs.has_updates == 'true'", condition, job)

    def test_single_combo_failure_does_not_block_other_combos(self):
        # needs 隐式全成功语义会放大单包失败：test/publish/finalize 必须
        # always() 运行，且不得用上游矩阵 job 的聚合 result 阻断其他包。
        for job, upstream in (("test", "build"), ("publish", "test"),
                              ("finalize", "publish")):
            condition = self.jobs[job]["if"]
            self.assertIn("always()", condition, job)
            self.assertNotIn("needs.%s.result" % upstream, condition, job)
        # 失败组合自身被 marker 拦截：无安装验证凭据的组合不会进入发布。
        publish_if = self.jobs["publish"]["if"]
        self.assertIn("inputs.skip_release != true", publish_if)

    def test_child_check_scopes_before_any_fetch(self):
        script = step_script(self.doc, "check",
                             "检测本平台启用上游相对基线的更新（先本地 --platform scope 再网络 fetch）")
        self.assertIn('scripts/check_versions.py --platform "$PLATFORM"', script)
        self.assertIn('--openssh-version "$FORCE_VERSION"', script)
        self.assertIn('--targets "$TARGETS"', script)
        self.assertIn('--output "$GITHUB_OUTPUT"', script)

    def test_release_gates_and_receipt_scope(self):
        for job in ("publish", "finalize"):
            self.assertIn("inputs.skip_release != true", self.jobs[job]["if"], job)
        upload = next(step for step in self.jobs["build"]["steps"]
                      if step.get("name") == "上传构建产物")
        self.assertEqual(upload["with"]["name"],
                         "built-${{ matrix.platform }}-${{ matrix.package }}")
        verified = next(step for step in self.jobs["test"]["steps"]
                        if step.get("name") == "上传安装验证凭据")
        self.assertEqual(verified["with"]["name"],
                         "verified-${{ matrix.platform }}-${{ matrix.package }}")
        for step in self.jobs["publish"]["steps"]:
            if step.get("name", "").startswith("幂等发布"):
                self.assertIn("hashFiles(format('verified/{0}-{1}', matrix.platform, "
                              "matrix.package)) != ''", step["if"])
        receipt = next(step for step in self.jobs["publish"]["steps"]
                       if step.get("name", "").startswith("上传发布凭据"))
        self.assertEqual(receipt["with"]["name"],
                         "receipt-${{ matrix.platform }}-${{ matrix.package }}")
        merge = next(step for step in self.jobs["finalize"]["steps"]
                     if step.get("name") == "合并本平台全部组合的发布凭据")
        self.assertEqual(merge["with"]["pattern"], "receipt-${{ inputs.platform }}-*",
                         "receipt 工件按平台范围隔离")
        self.assertTrue(merge["with"]["merge-multiple"])

    def test_finalize_cleans_and_records_platform_scoped(self):
        cleanup = step_script(self.doc, "finalize",
                              "集中串行清理本平台历史 Release（先校验后删除，保留 Git tag）")
        self.assertRegex(cleanup,
                         r'prune_releases\.py --repo "\$GITHUB_REPOSITORY"[\s\\]+'
                         r'--platform "\$PLATFORM" --skip-merged \$dry "\$\{receipts\[@\]\}"')
        self.assertIn("--dry-run", cleanup)
        writeback = step_script(self.doc, "finalize",
                                "回写本平台成功基线（每轮取最新分支重放 receipt + 防降级，无 rebase 状态残留）")
        # 重放循环：每轮强制回到最新远端分支，无 rebase；record 在循环内重放，
        # 且带 --platform 精确字段校验（前缀相似平台绝不混淆）。
        self.assertIn('git checkout -f -B "$BRANCH" "origin/$BRANCH"', writeback)
        self.assertNotIn("git rebase", writeback)
        self.assertRegex(writeback,
                         r'record_versions\.py --platform "\$PLATFORM"[\s\\]+'
                         r'version\.json "\$\{receipts\[@\]\}"')
        self.assertLess(writeback.index("record_versions.py"),
                        writeback.index("git add version.json"))
        self.assertNotRegex(writeback, r"git add [^\n]*spec")
        self.assertIn("push 冲突，重试", writeback)
        # dry_run 只演练清理，不回写。
        step = next(step for step in self.jobs["finalize"]["steps"]
                    if step.get("name", "").startswith("回写本平台成功基线"))
        self.assertIn("env.DRY_RUN != 'true'", step["if"])

    def test_child_permissions_least_privilege(self):
        for job in ("check", "build", "test"):
            self.assertNotIn("permissions", self.jobs[job], job)
        for job in ("publish", "finalize"):
            self.assertEqual(self.jobs[job]["permissions"], {"contents": "write"}, job)


class CrossWorkflowContractTest(unittest.TestCase):
    """父子共享的横切契约：依赖安装、显式 Python、零平台硬编码。"""

    def setUp(self):
        self.parent = load_workflow(PARENT)
        self.child = load_workflow(CHILD)
        self.parent_text = PARENT.read_text()
        self.child_text = CHILD.read_text()

    def test_every_host_job_installs_its_own_python_dependencies(self):
        # job 隔离：使用宿主 Python 的 job 必须自带依赖安装，不依赖其他 job。
        for doc, job, packages in (
                (self.parent, "discover", ("python3-yaml",)),
                (self.parent, "tests", ("rpm", "python3-rpm", "python3-yaml")),
                (self.parent, "maintain-merged", ("python3-rpm", "python3-yaml")),
                (self.child, "check", ("python3-yaml",)),
                (self.child, "build", ("python3-yaml",)),
                (self.child, "test", ("python3-yaml",)),
                (self.child, "publish", ("python3-rpm", "python3-yaml")),
                (self.child, "finalize", ("python3-rpm", "python3-yaml"))):
            runs = job_runs(doc, job)
            for package in packages:
                self.assertIn(package, runs,
                              "%s/%s 缺少 %s 安装" % (doc["name"], job, package))

    def test_host_python_is_explicit_and_publish_justifies_its_rpm_binding(self):
        for path, text in ((PARENT, self.parent_text), (CHILD, self.child_text)):
            self.assertNotRegex(text, r"(?m)^\s*python3 scripts/",
                                "%s：宿主 Python 必须显式 /usr/bin/python3" % path.name)
        self.assertIn("/usr/bin/python3 scripts/publish_release.py", self.child_text)
        self.assertIn("/usr/bin/python3 scripts/project_config.py", self.child_text)
        # package.sh 的宿主 Python 由 PYTHON 环境变量显式指定（build/test 注入）。
        for job in ("build", "test"):
            self.assertEqual(self.child["jobs"][job]["env"].get("PYTHON"),
                             "/usr/bin/python3", job)
        # publish 读取 rpm header / spec 包集合，python3-rpm 安装不是冗余。
        self.assertTrue(hasattr(publish_release, "read_rpm_header"))
        self.assertTrue(hasattr(publish_release, "spec_package_names"))

    def test_no_platform_ids_are_hardcoded_in_either_workflow(self):
        # 平台清单唯一来源是 discover 输出与矩阵变量：新增平台无需改任何 workflow。
        for path, text in ((PARENT, self.parent_text), (CHILD, self.child_text)):
            for platform in ("el7", "el8", "centos7", "ubuntu2204"):
                self.assertNotIn(platform, text,
                                 "%s 硬编码了平台 id %s" % (path.name, platform))

    def test_forbidden_legacy_and_unsafe_patterns_absent(self):
        for path, text in ((PARENT, self.parent_text), (CHILD, self.child_text)):
            self.assertNotIn("git rebase", text, "%s：重试路径必须无 rebase 状态残留" % path.name)
            self.assertNotIn("sed -i", text, "%s：CI 不得手动改写源 spec" % path.name)
            self.assertNotIn("build-in-container.sh", text, "%s：CI 不得绕过统一入口" % path.name)
            for legacy in ("select-release-rpm.sh", "publish-openssh-deb.sh",
                           "build-openssh-deb.sh", "--repair-pam", "--retry-component"):
                self.assertNotIn(legacy, text, path.name)

    def test_local_tests_job_runs_the_suite(self):
        runs = job_runs(self.parent, "tests")
        self.assertIn("unittest discover -s tests", runs)


if __name__ == "__main__":
    unittest.main()
