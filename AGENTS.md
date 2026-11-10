# 仓库工作约定

## 构建边界

- 打包配置单一来源：`platforms/<id>/platform.yaml` 声明平台（`image` 必须 digest 固定、`family: rpm|deb`、`el`、`packages`）与包条目（`enabled`/`kind`/`spec`/`assets`/`packaging`/`aux_source`/`pre_build`）；路径一律仓库相对 POSIX，禁绝对路径与 `..`，不适用的字段留空；平台目录名、packages/upstreams 键、`el`/`repos`/`pre_build` 必须匹配安全标识 `[a-z0-9][a-z0-9_-]*`，未知顶层键直接报错。宿主机用 `scripts/project_config.py` 统一解析（`load_config`/`get_target`/`iter_targets`/`load_upstreams`/`platform_ids`；CLI `target|shell PLATFORM PACKAGE`、`image PLATFORM`、`platforms`），产物目录固定 `dist/<platform>/<package>/`；维护源 spec/素材，而非构建副本。
- `kind` 缺省按 `包名+family` 派生，可显式声明但必须与之一致：openssh 仅 `openssh-rpm`/`openssh-deb`，其余包仅 `upstream-rpm`；别名或第四种组合一律拒绝。共享 OpenSSH 打包在 `packaging/common/openssh/{openssh.spec,sshd.pam}`；`centos7` 的 packages 引用 `platforms/el7/` 下的 spec/assets，但保留独立构建目录、`.centos7` RPM 后缀和发布状态；修改 EL7 打包规则会同步影响 CentOS 7。YAML 仅宿主解析；EL7/CentOS7 调度不新增 Python3/PyYAML 依赖，容器消费已解析环境变量（`target_env`/`shell` 输出经 `docker -e` 传入）。
- 底层构建、RPM 门禁和安装测试脚本会修改系统仓库、安装软件包，应在临时目标容器内执行。补源逻辑集中在 `scripts/repos-common.sh`：EL7/CentOS 7 用 Vault，EL8 补 AlmaLinux，保留本地固定公钥与 `gpgcheck=1`。
- 上游注册唯一来源 `packaging/upstreams.yaml`（`projects.<pkg>`: `name`/`anitya_id`/`version_pattern`/`source_url`（含 `{version}`）/`enabled`）；`anitya_id` 固定项目 ID，不能按名字匹配（Anitya 存在与 sudo/ntp 同名的无关项目）；检测只认 `enabled` 项。Telnet 的源码是 GNU inetutils；Vim 暂停：upstreams.yaml 与三个 RPM 平台的 platform.yaml 均 `enabled: false`。

## 快速验证

以下命令从仓库根目录执行。

- Python 测试需要系统 `rpm` 绑定与 `python3-yaml`；CI 统一 `/usr/bin/python3` 并安装 `python3-rpm` / `python3-yaml`。GitHub 请求在单元测试中已 mock，无需凭据或 Docker。CI 会运行 `tests/`；改动发布逻辑后仍建议提交前本地跑一遍：

  ```bash
  /usr/bin/python3 -m unittest discover -s tests -v
  # 单个用例；去掉 Class.method 参数即可运行整个文件
  /usr/bin/python3 tests/test_prune_releases.py ReleaseRetentionTest.test_dry_run_verifies_without_deletion -v
  ```

- 统一入口 `scripts/package.sh`（本地与 CI 共用同一实现）：`build PLATFORM PACKAGE [VERSION] [URL]` 含产物门禁（openssh-rpm 另含上游 regress；DEB 门禁内置于构建脚本）；`test PLATFORM PACKAGE [SCENARIO...]` 在独立干净容器做安装测试。`test` 从 `dist/<platform>/<package>/` 的构建元数据读实际版本（RPM `build.spec`、DEB `build.json`），必须先 `build`；openssh 构建可省版本（取共享 spec 宏）且不接 URL；upstream-rpm 必须提供版本与 https URL，test 只跑单容器 smoke、不接场景参数（已知组件专用 smoke，未注册用例的包回退通用安装一致性验证）：

  ```bash
  bash scripts/package.sh build el7 openssh
  bash scripts/package.sh test el7 openssh   # 5 场景缺省全跑：fresh upgrade reinstall uninstall symlink-guard
  bash scripts/package.sh build el8 chrony 4.9 https://chrony-project.org/releases/chrony-4.9.tar.gz
  bash scripts/package.sh test el8 chrony
  ```

- `local-build.sh` / `local-test.sh` 为纯转发（`<platform|all> [package] [版本|场景...]`），`all` 按 platform.yaml 动态筛选启用该包的平台；聚焦安装场景：`bash scripts/local-test.sh el7 upgrade`，每个场景使用独立干净容器。产物在 `dist/<platform>/<package>/`（RPM 含 build.spec、DEB 含 build.json/changelog），缓存 `.rpmbuild/<platform>/<package>/` 与 `.debbuild/<platform>/<package>/`。
- NTP 构建前的 OpenSSL 源码准备由 `pre_build: ntp-openssl` 钩子自动执行（宿主侧 `scripts/prebuild/`），无需手动 fetch。
- 调整上游测试时以 spec 的 `%check` 和 `scripts/test-openssh-upstream.sh` 为准；`docs/package-test-research.md` 含历史状态和待办，不能视为当前门禁。chrony 当前仅运行上游 unit 测试。

## OpenSSH 打包约束

- 改配置或 scriptlet 前先读 `packaging/common/openssh/` 共享 spec 的顶部约定与 `scripts/test-install.sh`：`/etc` 配置仅以 `%config(noreplace) %ghost` 登记，默认模板放 `/usr/share/openssh/`，只补真正缺失的路径（悬空软链也算已有路径）。保留已有配置和 host key；安装/升级脚本不主动重启、停止或重载 sshd，缺失密钥由 init 脚本首次启动时生成。
- OpenSSL/zlib 静态链接，glibc/PAM/Kerberos 动态链接。检查静态链接用 `readelf` 的直接 `NEEDED`，`ldd` 的传递依赖会误报；复用 `scripts/verify-rpms.sh`。
- 更新 OpenSSL/zlib 版本宏时同步维护 `certs/checksums.yaml`；NTP EL7 的 OpenSSL 版本另由 `platforms/el7/packages/ntp/ntp.spec` 的 `ntp_ssl_ver` 控制。OpenSSH tarball 使用固定 release key 验签，OpenSSL/zlib 与辅助源码使用固定 SHA256。
- Ubuntu DEB：`/etc` 不随包分发配置 payload，仅补真正缺失的路径；保留既有配置与 host key，安装/升级不主动启动/停止/重启 SSH，服务名 `ssh.service`、首次启动生成缺失密钥；保留 epoch `1:`（`1:<版本>-<修订>`）。门禁校验三包版本/架构、SHA256、ELF、PAM 与服务配置，安装测试覆盖 fresh/upgrade/reinstall/uninstall/symlink-guard 五场景并验证 SSH/PAM 登录、SFTP、SCP。

## 发布状态

- 修改发布流程时联读 `.github/workflows/rpm-xinchuang.yml`（父编排）、`.github/workflows/platform.yml`（单平台可复用链）、`scripts/publish_release.py`、`scripts/prune_releases.py` 和 `scripts/record_versions.py`：父 discover 本地无网络发现启用平台（清单派生自启用 target，不硬编码平台）并预检全局输入 → 共享 tests 为代码质量门控（父级一次）→ platform 矩阵逐平台调用子链 check（先 `--platform` 本地 scope 再网络 fetch，上游检测故障按平台隔离）→ build（含门禁）→ test → 每组合幂等 publish → finalize（prune `--platform --skip-merged` 清理、record `--platform` 回写）；矩阵 fail-fast:false，单平台失败不阻断其他平台；顶层 concurrency 跨运行串行、同运行平台并行。
- `version.json` 是唯一回写对象（源 spec 永不因发布改写），是成功发布基线而非待构建清单；缺失条目以上游最新版首建。tag `<platform>-<package>-<version>-<release>`，release 取自实际构建产物：RPM 以 rpm header 为权威（文件名须一致），DEB 取 `build.json`。
- Release 资产严格限定包文件 + `SHA256SUMS`（RPM 集合必须锚定 build.spec 声明的二进制包，含子包/noarch/debuginfo，拒绝混入无关包）；`build.spec`/`build.json`/`changelog` 只作 `published/` 凭据工件。新建 Release 后必须远程逐字节校验通过才写 receipt；重入时资产不一致同样失败不写。
- 清理前置预检：`record_versions.read_receipt` 先全批校验凭据（身份/哈希/构建 spec 或元数据一致性），一张坏凭据即中止、零删除；其后只保留组合内 EVR 最高项（RPM `rpm.labelCompare`、Ubuntu `dpkg --compare-versions`，绝不按时间），较低版本补发不替换高版本、不回退基线；按不可变 Release ID 删除，Git tag 保留。旧合并 `v<版本>[-<修订号>]` 按还原的 `R.<平台>` 比较，仅当 EL7 与 EL8 都存在不低于它的完整且校验通过的新格式替代才删除——该维护已拆出平台批：平台 finalize 带 `--skip-merged` 不触碰跨平台 v*，父 maintain-merged 在全平台结束后以 `--merged-only` 单例维护（不接凭据、不回写，失败不影响已完成回写）；receipt 所指 Release 已被保留策略删除时，同组合存在更高且校验通过的替代按 superseded 重入，否则硬失败。
- 手动检查清理给 `prune_releases.py` 传 `--dry-run`（校验并列出将删除项；平台批可加 `--platform`，旧合并维护单独跑 `--merged-only`）；workflow `dry_run` 发布照常、清理只演练且不回写；`skip_release` 跳过 publish/finalize 全部写操作。回写重试时每轮取最新远端分支重放 receipt（无 rebase 残留），record 自带防降级。
