# rpm-Xinchuang — EL7/EL8 RPM 自动构建与发布

**定时检测、构建和发布都在 GitHub Actions 运行，不依赖本机。**唯一的
[rpm-Xinchuang 工作流](.github/workflows/rpm-xinchuang.yml) 在北京时间每天 09:17
（UTC 01:17）运行一次。它通过 [Anitya](https://release-monitoring.org/) 固定项目 ID
检查七个组件的最新稳定版，与根目录 [`version.json`](version.json) 按平台对比；
有更新才在官方 UBI7 / UBI8 镜像中构建 x86_64 RPM。

| 组件 | 目标平台 | 更新来源 | Release tag 示例 |
| --- | --- | --- | --- |
| OpenSSH | EL7、EL8 | OpenSSH portable | `v10.5p1` |
| chrony、vim、bash、sudo、ntp | EL7、EL8 | 各组件官方发布的源码包 | `bash-el8-5.3-1.el8` |
| telnet | EL7、EL8 | GNU inetutils 的 telnet/telnetd | `telnet-el8-2.8-1.el8` |

所有 RPM 都使用仓库 [`spec/`](spec/) 中维护的 spec 构建；其余组件的发行版辅助
配置/服务文件存于 [`source-assets/`](source-assets/)。下载的是**上游官方最新版源码**，
并非反复抓取 CentOS/Alma 的旧 SRPM；EL7 NTP 有一处针对静态 OpenSSL 3.5
SHAKE128 XOF 兼容的仓库维护补丁。
OpenSSH 保留静态链接 OpenSSL/zlib 的专用 spec 与完整安装行为测试；其余组件还会
在**干净 UBI 容器中安装并运行**。构建及安装验证均成功后，每个组件/平台独立发布
RPM、`SHA256SUMS`、源码摘要和实际构建 spec，并回写 `version.json` 和对应 spec。
失败的平台不更新版本基线，等待后续修复重试。
测试分层：OpenSSH 构建后运行上游 `make tests`，bash/sudo/NTP/GNU inetutils
在 spec 的 `%check` 运行上游 `make check`，chrony 运行上游单元测试，vim
运行已在 EL7/EL8 验证的上游核心用例。另在独立干净 UBI 容器中测试已安装
RPM：SSH 与 sudo 使用普通用户真实密码认证，chrony/telnet 检查本地服务响应；
详细来源与未覆盖的全量测试见 [`docs/package-test-research.md`](docs/package-test-research.md)。

**手动运行：**GitHub *Actions* →「rpm-Xinchuang」→ *Run workflow*；`version`
可指定 OpenSSH 版本，`force` 可重建六个组件，`skip_release` 只验证不发布。
修复 PAM 时单独勾选 `repair_pam`（不要同时填写 `version` 或勾选 `force`）：
只构建 OpenSSH EL7/EL8 和 sudo EL8，分别执行载荷检查与干净 UBI 安装测试。
默认会发布新版 release（OpenSSH `v10.5p1-2`，sudo `sudo-el8-1.9.17p2-2.el8`）；
勾选 `skip_release` 可以先只运行 CI 验证。构建后的 RPM 可从 workflow artifacts 获取。
根目录 [`time`](time) 记录上一次**完整成功的定时调度**（UTC），无更新时也会更新并
产生提交，取代旧的 45 天空提交保活。EL7 已停止维护；构建仍使用固定 UBI7 镜像
及其补充仓库。telnet 改用 GNU inetutils，包名仍为 `telnet` / `telnet-server`。
升级 bash、sudo 等系统基础包之前，应先在目标环境验证。

## OpenSSH 产物特性

| 项目 | 说明 |
| --- | --- |
| OpenSSH | portable 稳定版（CI 自动跟踪，spec 见 `spec/openssh.spec`，版本见 `version.json`） |
| OpenSSL / zlib | **静态链接**（OpenSSL 当前 3.5.3 含 zlib；zlib 亦静态链接，二进制不依赖系统 libz.so），OpenSSL 版本固定在 spec 内、**仅手动升级** |
| glibc / PAM / Kerberos5 | **动态链接**（不替换系统基础库；sshd 动态链接 libpam） |
| 图形 askpass | **不构建**（x11 / gnome-askpass 均禁用） |
| 目标平台 | 仅 x86_64；EL7（UBI7）与 EL8（UBI8）各一套 |

## OpenSSH 构建分支（.github/workflows/rpm-xinchuang.yml）

 1. 每天 **北京时间 09:17**（cron `17 1 * * *` UTC）运行
    `scripts/check_versions.py`，同时比较七个 Anitya 项目和 `version.json`；
2. 仅当上游更高时：在 UBI7 / UBI8 容器内**并行真实构建** RPM
   （源码包先验证官方 GPG 签名 / 固定 SHA256）；
3. **EL7 与 EL8 都构建成功**才创建 GitHub Release（tag `vX.YpZ`），
   附上全部 RPM 与 SHA256SUMS；任一失败则不发布、不推进；
 4. 发布成功后回写 `spec/openssh.spec` 的 `%global ver` 与 `version.json` 并提交；
5. 手动触发（workflow_dispatch）可强制指定版本或“仅构建不发布”。

幂等与并发：同组运行排队执行（不取消）；Release 按tag查询后创建（重复运行不重复发）；
版本回写基于 git diff（无变化不提交）；push 带重试与 rebase。

## 构建依赖（容器内自动安装）

- 基础镜像固定 digest：`ubi7/ubi@sha256:046e5257…`、`ubi8/ubi@sha256:ed721ca8…`
  （与 `scripts/local-*.sh`、workflow 保持一致；升级 digest 属受控变更）；
- **EL7**：UBI7 自带主源已 404（EOL），补充 CentOS 7.9.2009 vault（base/updates/extras）
  与 SCLo vault（devtoolset-9，系统 gcc 4.8 不满足 OpenSSL 3.5 的 C11 要求）；
- **EL8**：UBI8 自带源缺 `pam-devel`，补充 AlmaLinux 8（BaseOS/AppStream/PowerTools）；
- **EL7 NTP**：系统 OpenSSL 1.0.2 不支持上游 NTP 所需的接口；构建时用
  `certs/checksums.yaml` 固定摘要的 OpenSSL 3.5.3 源码构建私有静态库，
  避免要求目标系统升级 OpenSSL；
- 其余：rpm-build、gnupg2、krb5-devel、perl 模块（IPC::Cmd / Time::Piece /
  Data::Dumper）、cpio 等（见 spec 的 BuildRequires 与 `scripts/repos-common.sh`）；
  zlib 从源码以 -fPIC 静态构建（EL7 系统 libz.a 非 PIC，无法链入 PIE，
  故 openssl 与 openssh 统一链接自建的静态 libz.a）；
- **所有补充源均 `gpgcheck=1`**，且 GPG 公钥**固定在本仓库 `certs/` 下**
  （指纹已对照 centos.org / repo.almalinux.org 官方公布值逐一核验，见
  `scripts/repos-common.sh` 注释），不随源同渠道动态下载。

## 安全边界（重点）

### 配置保留（严格策略：不覆盖、不移动、不删除）

- `/etc` 下的配置（`sshd_config`、`ssh_config`、`/etc/pam.d/sshd`、`moduli`、
  init 脚本）**不随包分发内容**：RPM 中以 `%config(noreplace) %ghost` 登记所有权
  （payload 为空），因此 rpm 在**任何升级路径上都不会改写、移动或删除既有文件**
  ——不会产生 `.rpmnew` / `.rpmsave`，卸载也不会删除配置；
- 默认配置以模板形式安装到 `/usr/share/openssh/`（`sshd_config`、`ssh_config`、
  `moduli`、`sshd.pam`、`sshd.init`）；
- SSH 的 `sshd.pam` 模板采用发行版 `password-auth`/`postlogin` 栈，而非上游
  `contrib/redhat/sshd.pam` 中已失效的 `pam_stack.so`；全新安装的 `sshd_config`
  模板显式设置 `UsePAM yes`，已有配置保持原样；
- `%post` 脚本段**仅在目标文件缺失时**从模板补齐（典型为全新安装）；已存在的
  文件在任何场景下都不会被本包写入；
- 升级时 `%post` 会用新二进制对保留配置执行 `sshd -t` 预检并**透明打印结果**
  （失败仅警告，不阻止安装、不自动修复、不重启服务）；
- **已安装坏包生成的 `/etc/pam.d/sshd` 不会被新包自动覆盖。**更新包只修复全新
  安装/缺失文件场景；对已写入 `pam_stack.so` 的现存机器，需通过控制台或其他安全
  通道备份并人工修复 PAM 配置，验证可登录后再断开现有会话。sudo 同理：现存配置
  应先检查，不能仅凭升级包判断现场认证已经恢复。
- init 脚本同样遵循该策略：升级后 `/etc/rc.d/init.d/sshd` 仍是你现有的脚本
  （旧发行版脚本与新二进制路径兼容，可正常工作）；如需启用新模板，管理员可
  手动比对 `/usr/share/openssh/sshd.init` 后自行替换。

### Host key

- 安装/升级**绝不生成、绝不覆盖** `/etc/ssh/ssh_host_*key`；
- 缺失的密钥由 init 脚本在**首次启动**时用 `ssh-keygen -A` 生成（该命令只补缺失项，
  已有密钥原样保留）——已由行为测试验证（重启前后密钥逐字节一致）。

### 不自动重启 SSH

- 本包的安装、升级、重装**不会**重启、停止或重载正在运行的 sshd；
- 升级后旧进程继续运行，需**管理员择机手动重启**：
  - EL7：`service sshd restart`
  - EL8：`systemctl daemon-reload && systemctl restart sshd`

### 旧发行版包 scriptlet 的重启边界（如实说明，不作虚假保证）

从**发行版自带 openssh-server 升级**到本包时，rpm 会执行**旧包自带的 `%postun`
脚本**，其中包含 `condrestart`（EL7）/ `try-restart`（EL8）逻辑——该重启由旧包
发起，本包**无法阻止**。已做的保护与验证：

- 升级前旧包脚本内容可通过 `rpm -q --scripts openssh-server` 证实含重启逻辑
  （行为测试已自动留证）；
- 本包升级后保证保留配置能通过新版 `sshd -t`，因此**该次重启会以新二进制 +
  旧配置正常拉起**（EL7 行为测试实测：重启后 banner 即为 OpenSSH 10.x）；
- 若管理员曾写入新版本不兼容的指令（如已删除的协议选项），重启会失败——
  `%post` 的 `sshd -t` 预检会提前在安装日志中大声警告，但**不会也无法替你阻止**
  旧包的重启尝试。升级前请自行确认 `sshd -t` 输出。

## 静态 OpenSSL 升级（仅手动）

1. 修改 `spec/openssh.spec`：`%global ssl_ver X.Y.Z`；
2. 下载官方签名的 `openssl-X.Y.Z.tar.gz`，**验证签名后**把 SHA256 更新到
   `certs/checksums.yaml`（构建时强校验，未登记的版本会直接构建失败）；
3. OpenSSH 版本更新**不要求**升级 OpenSSL；OpenSSL 不单独发布 Release。

## 源码校验

- OpenSSH tarball：构建时用 `certs/openssh-release-key.asc` 验签，
  key 指纹固定校验 `7168B983 815A5EEF 59A4ADFD 2A3F414E 736060BA`
  （Damien Miller / OpenSSH release key）；
- OpenSSL tarball：SHA256 必须命中 `certs/checksums.yaml`（初始值已用
  官方签名 `BA5473A2 B0587B07 FB27CF2D 216094DF D0CB81EF` 验证）。

## CI 权限与保活

- workflow 默认 `contents: read`；发布回写及更新 `time` 的 job 才使用 `contents: write`
  （本仓库 GITHUB_TOKEN）；
- **无 `pull_request` 触发**：外部 PR 永远不会拿到任何写权限 token；
  手动运行也只应由仓库所有者发起；
- 所有第三方 action 固定 commit SHA：
  checkout `3d3c42e5…`（v7.0.1）、upload-artifact `043fb46d…`（v7.0.1）、
  download-artifact `3e5f45b2…`（v8.0.1）。

### 定时任务与保活的局限（如实说明）

- GitHub 会在**仓库 60 天无提交**后自动停用 scheduled workflow；
  每次完整成功的调度都会写入 `time` 并提交，避免长期无提交；
- 定时任务**不保证准点**：GitHub schedule 高峰期可能延迟数分钟到数十分钟；
- scheduled workflow **只在默认分支**生效；若工作流被停用或仓库被归档，
  需要手动重新启用；
- fork 仓库默认不运行 scheduled workflow。

## 本地构建与测试

依赖：docker（或兼容工具）+ 能访问 aliyun 镜像的网络。

```bash
# 构建（与 CI 完全相同的容器内脚本）
scripts/local-build.sh el7
scripts/local-build.sh el8     # 或 all

# 行为测试（每场景独立干净容器）
scripts/local-test.sh all       # fresh / upgrade / reinstall / uninstall × el7/el8

# 版本及源码包检测单元测试
python3 -m unittest discover -s tests -v
```

行为测试覆盖：全新安装（不生成密钥、不启动、服务注册开机自启、默认配置与
模板一致）、发行版旧版真实升级（配置/密钥/init脚本逐字节保留、不产生
.rpmnew/.rpmsave、旧包 scriptlet 重启边界留证）、同版本强制重装（运行中
sshd 不被重启）、卸载（停止、注销、配置原位保留不被删除）。

## 仓库结构

```
spec/openssh.spec         OpenSSH 包装、静态链接依赖与配置策略
spec/<组件>/<el>.spec     六组件各平台的仓库维护 spec
source-assets/            从发行版 spec 保留的服务文件及配置模板（不含补丁）
version.json              七组件按平台记录的已发布版本
time                      最近一次完整成功调度的 UTC 时间
.github/workflows/rpm-xinchuang.yml  唯一的 GitHub Actions 工作流
scripts/check_versions.py Anitya 七项目版本检测与构建矩阵生成
scripts/build-upstream.sh UBI 内编译官方上游源码并打 RPM
scripts/test-upstream-install.sh  全新 UBI 中安装及命令测试
scripts/record_versions.py  合并已发布版本和实际构建 spec
scripts/repos-common.sh   EL7/EL8 补充源定义（gpgcheck 全开）
scripts/build-in-container.sh  UBI 容器内构建（验签→rpmbuild）
scripts/test-install.sh        安装/升级行为测试（容器内执行）
certs/                固定的 OpenSSH release 公钥 + OpenSSL SHA256 表
tests/                版本检测单元测试（unittest）
```
