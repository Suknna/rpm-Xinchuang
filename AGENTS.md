# 仓库工作约定

## 构建边界

- OpenSSH 走 `scripts/build-in-container.sh`，版本取自 `spec/openssh.spec` 的宏，产物在 `dist/<platform>/`。其他组件走 `scripts/build-upstream.sh`，在 `.rpmbuild/` 内复制并调整 `spec/<package>/<el>.spec`，复用 `source-assets/<package>/<el>/`，产物在 `dist/<package>/<platform>/`；维护源 spec/素材，而非构建副本。
- `scripts/platforms.sh` 统一固定镜像 digest 和平台映射。`centos7` 复用 EL7 spec/素材，但必须保留独立构建目录、`.centos7` RPM 后缀和发布状态；修改 EL7 打包规则也会影响 CentOS 7。
- 底层构建、RPM 门禁和安装测试脚本会修改系统仓库、安装软件包，应在临时目标容器内执行。补源逻辑集中在 `scripts/repos-common.sh`：EL7/CentOS 7 用 Vault，EL8 补 AlmaLinux，保留本地固定公钥与 `gpgcheck=1`。
- `scripts/check_versions.py` 的 `PROJECTS` 固定 Anitya 项目 ID，避免 sudo/ntp 同名项目误匹配。Telnet 的源码是 GNU inetutils；Vim 已暂停检测与构建，保留的 spec、素材和测试分支不代表已启用。

## 快速验证

以下命令从仓库根目录执行。

- Python 测试需要系统 `rpm` 绑定；Ubuntu CI 使用 `python3-rpm` 和 `/usr/bin/python3`。GitHub 请求在单元测试中已 mock，无需凭据或 Docker。现有工作流未运行 `tests/`，修改发布逻辑后需手动执行：

  ```bash
  /usr/bin/python3 -m unittest discover -s tests -v
  # 单个用例；去掉 Class.method 参数即可运行整个文件
  /usr/bin/python3 tests/test_prune_releases.py ReleaseRetentionTest.test_dry_run_verifies_without_deletion -v
  ```

- `local-build.sh` / `local-test.sh` 仅针对 OpenSSH。完整验证顺序为构建（含上游 regress）→ RPM 门禁 → 安装测试；本地构建入口不会自动运行 `verify-rpms.sh`：

  ```bash
  platform=el7  # 可换为 el8 或 centos7
  bash scripts/local-build.sh "$platform"
  source scripts/platforms.sh
  sudo docker run --rm -v "$PWD":/src:ro -e SRC_DIR=/src "$(image_for "$platform")" \
    bash /src/scripts/verify-rpms.sh "$platform"
  bash scripts/local-test.sh "$platform"
  ```

- 聚焦安装场景：`bash scripts/local-test.sh el7 upgrade`。省略场景会运行 `fresh upgrade reinstall uninstall symlink-guard`，每个场景使用独立干净容器。
- 其他组件的构建和安装验证命令见 `README.md`「构建与下载」。NTP 在 `el7`/`centos7` 构建前，先在宿主机执行 `bash scripts/fetch-ntp-openssl.sh "$PWD" "$platform"`；EL8 不需要。
- 调整上游测试时以 spec 的 `%check` 和 `scripts/test-openssh-upstream.sh` 为准；`docs/package-test-research.md` 含历史状态和待办，不能视为当前门禁。chrony 当前仅运行上游 unit 测试。

## OpenSSH 打包约束

- 改配置或 scriptlet 前先读 `spec/openssh.spec` 顶部约定与 `scripts/test-install.sh`：`/etc` 配置仅以 `%config(noreplace) %ghost` 登记，默认模板放 `/usr/share/openssh/`，只补真正缺失的路径（悬空软链也算已有路径）。保留已有配置和 host key；安装/升级脚本不主动重启、停止或重载 sshd，缺失密钥由 init 脚本首次启动时生成。
- OpenSSL/zlib 静态链接，glibc/PAM/Kerberos 动态链接。检查静态链接用 `readelf` 的直接 `NEEDED`，`ldd` 的传递依赖会误报；复用 `scripts/verify-rpms.sh`。
- 更新 OpenSSL/zlib 版本宏时同步维护 `certs/checksums.yaml`；NTP EL7 的 OpenSSL 版本另由 `spec/ntp/el7.spec` 的 `ntp_ssl_ver` 控制。OpenSSH tarball 使用固定 release key 验签，OpenSSL/zlib 与辅助源码使用固定 SHA256。

## 发布状态

- 修改发布流程时联读 `.github/workflows/rpm-xinchuang.yml`、`scripts/prune_releases.py` 和 `scripts/record_versions.py`：构建/安装验证 → 发布及资产校验 → 保留最高 RPM 版本 → 回写。`version.json` 是成功发布基线，不是待构建版本清单；`null` 会触发首次构建，较低版本补发不能回退基线。
- OpenSSH EL7/EL8 共用 `v<version>-<revision>` Release 和 `version.json.openssh`，两平台一起成功才更新；CentOS 7 走组件矩阵，使用 `openssh_centos7`。其他组件按平台记录；CentOS 7 发布不回写共享 EL7/OpenSSH spec。
- 组件回写依赖 `published/receipts/*.json` 及匹配 SHA256 的构建 spec；`skip_release` 跳过发布、清理和版本回写。
- 手动检查 Release 清理时给 `prune_releases.py` 传 `--dry-run`；默认会实际删除同组件/平台除选中保留项外的 Release 及附件，保留 Git tag。版本排序使用 `rpm.labelCompare`。
