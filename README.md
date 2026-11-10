# rpm-Xinchuang

基于软件官方上游源码及 RHEL 生态的 RPM 打包规则，在 **Red Hat UBI7 / UBI8 / CentOS 7.9.2009**
容器中构建适用于 **RHEL 7 / RHEL 8 / CentOS 7 及兼容发行版的 x86_64 RPM**。
另提供 **Ubuntu 22.04 amd64 的 OpenSSH 原生 DEB 升级包**。
项目通过依赖适配、上游测试和安装验证，尽可能提高软件包在 RHEL 生产环境中的兼容性与可用性。

## 源码与 spec 来源

发行版打包基线主要来自 **CentOS 7 和 AlmaLinux 8 的 SRPM**。仓库按平台优先组织打包资产：
每个平台一个 [`platforms/<platform>/`](platforms/) 目录，内含 `platform.yaml`（声明 digest 固定的
`image`、`family: rpm|deb`、`el` 和 `packages` 映射），每个包位于
`platforms/<platform>/packages/<package>/`（`<package>.spec` 与 `assets/`）。每个启用组合解析为一个
构建目标，kind 按 `包名 + family` 确定（缺省推导，显式声明必须一致）为 `openssh-rpm` /
`upstream-rpm` / `openssh-deb`，产物目录固定
`dist/<platform>/<package>/`；当前启用 19 个组合（三个 RPM 平台各 6 包 + Ubuntu 的 openssh）。
OpenSSH 的 RPM spec 与素材为各 RPM 平台共享，维护在 [`packaging/common/openssh/`](packaging/common/openssh/)；
CentOS 7 平台的 packages 直接引用 `platforms/el7/` 下的打包。Ubuntu 22.04 的 debhelper 规则位于
`platforms/ubuntu2204/packages/openssh/debian/`。上游版本声明统一维护在
[`packaging/upstreams.yaml`](packaging/upstreams.yaml)。全部配置由 [`scripts/project_config.py`](scripts/project_config.py)
统一解析并校验（路径必须仓库相对、镜像禁止浮动 tag），宿主机解析后经环境变量契约传给容器；
构建时使用对应软件的官方上游源码，并针对新版本和各平台调整打包规则。

#### 新增平台或包（最小示例）

`rpm` 平台必须声明 `el` 与 `spec`；`deb` 平台必须声明 `packaging` 且仅支持 `openssh`；
`assets` 缺省取 spec 同目录的 `assets/`（目录存在即生效）；`pre_build` 是宿主机构建前置钩子名
（如 NTP 的 `ntp-openssl`）。平台目录名、包名等标识必须是 `[a-z0-9][a-z0-9_-]*`，未知顶层键
直接报错；`kind` 缺省按 `包名 + family` 推导，显式声明必须与之一致——新增同类 RPM 目标仅凭
配置即可，新构建类型需扩展构建脚本适配，不存在"加配置即构建新 DEB 包"的通用扩展。
新增上游组件需同时在 `packaging/upstreams.yaml` 登记
（`anitya_id` 固定 release-monitoring.org 项目 ID，`source_url` 模板必须含 `{version}`）。

在现有平台追加一个包（`platform.yaml` 的 `packages` 段）：

```yaml
  demo:
    spec: platforms/el8/packages/demo/demo.spec   # 无 assets/ 目录即视为无素材
```

新增一个 RPM 平台（`platforms/<id>/platform.yaml` 最小骨架；image 换成实际固定 digest 后即可解析）：

```yaml
image: registry.example.com/<image>@sha256:<64位十六进制digest>
family: rpm
el: el9
packages:
  openssh:                     # 复用共享 OpenSSH 打包
    spec: packaging/common/openssh/openssh.spec
    packaging: packaging/common/openssh
    assets: packaging/common/openssh
```

用解析器自检（宿主机需 `python3-yaml`；未知字段、越界路径、浮动镜像都会报错）：

```bash
python3 scripts/project_config.py target <platform> <package>
```

| 软件 | 源码上游 | 本项目 spec 基础 |
| --- | --- | --- |
| OpenSSH | [OpenSSH portable](https://www.openssh.com/portable.html) | 项目维护的共享 spec（`packaging/common/openssh/`），复用上游 Red Hat 服务模板并适配 PAM |
| chrony | [chrony](https://chrony-project.org/) | CentOS 7 / AlmaLinux 8 的 chrony spec |
| Vim（构建已暂停） | [Vim](https://github.com/vim/vim) | CentOS 7 / AlmaLinux 8 的 vim spec |
| Bash | [GNU Bash](https://www.gnu.org/software/bash/) | 项目维护的精简 spec，复用发行版默认配置 |
| sudo | [sudo](https://www.sudo.ws/) | CentOS 7 / AlmaLinux 8 的 sudo spec |
| NTP | [NTP Project](https://www.ntp.org/) | CentOS 7 的 ntp 打包规则，适配 EL7 / EL8 |
| Telnet | [GNU inetutils](https://www.gnu.org/software/inetutils/) | 针对 inetutils 维护的 spec，复用发行版服务文件；不是原来的 netkit-telnet |

## 兼容性与验证

- 使用固定 digest 的官方 UBI / CentOS / Ubuntu 镜像，登记在各平台 `platform.yaml` 的 `image` 字段，
  由 [`scripts/project_config.py`](scripts/project_config.py) 校验（禁止浮动 tag）；
  EL7 与 CentOS 7 使用 CentOS Vault，EL8 通过 AlmaLinux 仓库补充构建依赖。
- 执行上游测试，并在对应平台的干净容器中安装、运行构建出的 RPM；构建和验证通过后才发布。
  测试覆盖因组件而异，例如 chrony 运行单元测试、Vim 运行已验证的核心用例，详见
  [测试说明](docs/package-test-research.md)。
- OpenSSH RPM 静态链接 OpenSSL / zlib，动态链接系统 glibc / PAM / Kerberos5；保留既有配置和
  host key，本包的安装、升级脚本不主动重启 sshd。替换发行版包时，旧包卸载脚本仍可能触发重启。
- Release 附带 RPM 和 SHA256 校验文件，方便下载后核验。
- Vim EL7 保留系统 GTK2 依赖，通过源码兼容补丁修复新版本的图像缩放编译问题；
  安装验证同时运行命令行 Vim 和 Xvfb 下的 gVim，不要求额外升级 GTK 或 glibc。

生产部署仍需在目标系统上验证配置、依赖和业务行为；容器测试不等同于完整的目标系统
生产环境验收。EL7 / CentOS 7 构建使用 CentOS 7 归档源，部署时需结合目标系统的支持周期评估。

## 构建与下载

[GitHub Actions](.github/workflows/rpm-xinchuang.yml) 每天北京时间 **09:17** 检查上游版本，
发现更新后自动构建、测试并发布到 [Releases](https://github.com/Suknna/rpm-Xinchuang/releases)。
已发布版本记录在 [`version.json`](version.json) 的 `platforms.<platform>.<package>` 中，失败的平台不会推进版本基线。

每个 (platform, package) 组合独立 Release，tag 为 `<platform>-<package>-<version>-<release>`，
release 段取自实际构建产物（RPM 以 rpm header 为权威且文件名须一致，DEB 取 `build.json` 的
原生修订串）；Release 资产严格限定包文件与 `SHA256SUMS`（RPM 集合锚定构建 spec 声明的
二进制包），`build.spec` / `build.json` / `changelog` 只作为发布凭据工件保存、不对外公开。
新建 Release 后必须远程逐字节校验通过才写凭据，创建成功不等于完整成功。全部凭据经本地预检
后由 finalize 集中收口：先校验后清理同组合的其余 Release（保留 Git tag），最后只回写
[`version.json`](version.json) 成功基线（源 spec 永不因发布改写）；一张坏凭据即中止，零删除、
零回写。保留组合内版本最高的一套（RPM 用 rpm 规则、Ubuntu 用 dpkg 规则，绝不按创建时间），
较低版本补发不替换高版本、不回退基线。历史上 OpenSSH EL7 / EL8 共用 `v<版本>-<修订号>`
Release，按还原的平台修订串比较，仅在 EL7 与 EL8 都存在不低于它的完整且校验通过的新格式
替代时才清理；凭据所指 Release 已被保留策略删除时，同组合存在更高且校验通过的替代按
superseded 重入，否则硬失败。`dry_run` 发布照常执行，清理只演练列出、不删除、不回写；
`skip_release` 跳过发布、清理与回写。

CentOS 7 是独立构建路径，覆盖 OpenSSH、Bash、chrony、sudo、NTP、Telnet：

- 使用原生 CentOS 7.9.2009 镜像，复用 EL7 的打包规则与素材；RPM 后缀为 `.centos7`，
  例如 `openssh-10.6p1-2.centos7.x86_64.rpm`，与 UBI7 的 `.el7` 产物独立。
- 产物统一输出到 `dist/centos7/<package>/`；发布 tag 为 `centos7-<package>-<版本>-<修订号>`。
- 版本基线记录在 `version.json` 的 `platforms.centos7.<package>`；初始值 `null` 会触发首次构建；
  只有构建、安装验证、发布和清理成功后才推进记录。CentOS 7 的发布不影响其他平台的版本记录。

**Vim 构建与发布暂时停用**：以 `enabled: false` 保留其打包配置与素材，便于后续恢复。

也可在 Actions 中选择 **rpm-Xinchuang → Run workflow** 手动运行：

- `version`：指定 OpenSSH 版本，统一 pin 所有 OpenSSH 平台（格式 X.YpZ）。
- `targets`：仅构建指定组合，`pkg`、`pkg/平台`、`pkg@版本`、`pkg/平台@版本` 逗号分隔；
  版本优先级为显式 pin > 已发布基线 > 上游最新。
- `force`：强制重建其他已启用组件的当前上游最新版。
- `skip_release`：仅构建验证，不发布、不清理、不回写。
- `dry_run`：发布照常执行，清理只演练（列出将删除项）、不回写基线。

本地构建与验证（统一入口 `scripts/package.sh`，本地与 CI 共用同一实现；`build` 含产物门禁，
openssh 另含上游 regress）：

```bash
bash scripts/package.sh build centos7 openssh      # openssh 可省版本（取共享 spec 宏），不接 URL（源码固定）
bash scripts/package.sh test centos7 openssh       # 5 场景（fresh upgrade reinstall uninstall symlink-guard）缺省全跑
bash scripts/package.sh build centos7 chrony 4.9 https://chrony-project.org/releases/chrony-4.9.tar.gz
bash scripts/package.sh test centos7 chrony        # upstream 组件为单容器 smoke，不接场景参数
```

`test` 从 `dist/<platform>/<package>/` 的构建元数据读取实际版本（RPM `build.spec`、DEB
`build.json`），需先完成 `build`；upstream 组件为单容器 smoke（已知组件有专用检查，未注册
用例的包回退通用安装一致性验证）。`scripts/local-build.sh` / `scripts/local-test.sh` 保留为
纯转发（`<platform|all> [package] [版本|场景...]`），`all` 按 platform.yaml 动态筛选启用该包的
平台；例如 `bash scripts/local-test.sh el7 upgrade` 聚焦单个安装场景。NTP 构建前的 OpenSSL
源码准备由 `platform.yaml` 的 `pre_build: ntp-openssl` 钩子自动执行，无需手动 fetch。产物位于
`dist/<platform>/<package>/`（RPM 含 build.spec 副本，DEB 另含 build.json / changelog），
构建缓存位于 `.rpmbuild/<platform>/<package>/` 与 `.debbuild/<platform>/<package>/`；源 spec
不被修改。

## Ubuntu 22.04 OpenSSH 升级包

Ubuntu 分支只构建 OpenSSH，目标为 **Ubuntu 22.04 (jammy) / amd64**，产物包括
`openssh-client`、`openssh-server`、`openssh-sftp-server` 三个原生 `.deb` 包。
保留发行版的 epoch `1:`，例如 `1:10.6p1-2ubuntu22.04`，可以通过 apt 升级系统自带的 OpenSSH。
构建规则在 [`platforms/ubuntu2204/packages/openssh/debian/`](platforms/ubuntu2204/packages/openssh/debian/)，
上游版本也可由构建入口参数指定。

- 使用 `platform.yaml` 声明的固定 digest 官方 Ubuntu 22.04 镜像，显式选择 `linux/amd64`。
- 源码使用仓库内固定 OpenSSH release key 验签；构建执行上游 `make tests`。
- 动态链接 Ubuntu 的 OpenSSL、zlib、PAM、Kerberos 和 libedit，运行依赖由 debhelper 自动生成。
- 产物门禁校验三包版本/架构、SHA256、ELF、PAM 和服务配置；干净容器测试覆盖首次安装、
  从 Ubuntu 官方包升级、重装、卸载和悬空配置软链，并验证 SSH/PAM 登录、SFTP、SCP。
- `/etc` 不随包分发配置 payload，仅对真正缺失的路径补默认模板。保留既有配置和 host key；
  安装与升级不主动启动、停止或重启 SSH。服务使用 Ubuntu 的 `ssh.service` 名称，
  首次显式启动时生成缺失的 host key；同时保留 `ssh.socket` / `ssh@.service` 的按连接激活入口，
  新安装默认启用常规服务，不自动启用 socket。
- `platforms.ubuntu2204.openssh` 独立记录发布基线，`null` 触发首次构建。
  发布 tag 为 `ubuntu2204-openssh-<版本>-<修订串>`，修订串取自 `build.json`
  （dpkg 原生格式，如 `2ubuntu22.04`）；Release 资产仅三个 `.deb` 与 `SHA256SUMS`，
  `build.json` / `changelog` 只作发布凭据工件。使用 `dpkg --compare-versions` 保留 Ubuntu
  最高成功版本，资产校验通过才参与清理与回写，较低版本补发不会替换或回退基线。

本地构建并验证（需要 Docker；构建和系统安装操作均在临时容器内）：

```bash
bash scripts/package.sh build ubuntu2204 openssh   # 可选第二参数指定上游版本，如 10.6p1
bash scripts/package.sh test ubuntu2204 openssh    # 5 场景缺省全跑，可传场景子集
```

产物位于 `dist/ubuntu2204/openssh/`，构建缓存为 `.debbuild/ubuntu2204/openssh/`。
每日 Actions 自动检测、构建验证并发布；workflow artifact 名为 `built-ubuntu2204-openssh` /
`verified-ubuntu2204-openssh` / `receipt-ubuntu2204-openssh`。Ubuntu 手动重建用 `version`
（统一 pin 所有 OpenSSH 平台）或 `targets openssh/ubuntu2204[@版本]`。

在 Ubuntu 22.04 上下载同一 Release 的全部 DEB 和 `SHA256SUMS` 后执行：

```bash
sha256sum -c SHA256SUMS
sudo apt install ./openssh-*.deb
# 升级已有服务：确认保留的配置可被新版本接受，再激活新进程
sudo /usr/sbin/sshd -t
sudo systemctl restart ssh
```

全新安装的 host key 由 `ssh.service` 在首次 `sudo systemctl start ssh` 时生成。
本项目保留管理员配置，因此上游已移除的指令仍需由管理员调整。
Ubuntu 下游专有补丁不包含在 portable 构建中；升级不承诺保留这些额外功能。
容器内验证服务文件和真实 SSH 会话，完整 systemd 引导、socket 激活及目标机自定义配置需在目标环境验收。
卸载使用 `apt remove` 会保留配置与密钥；若要重新使用 Ubuntu 仓库的旧版本，需要显式选择降级。

## 开源许可

本项目原创的构建脚本、工作流和文档采用 [MIT License](LICENSE)。
来自上游或发行版的 spec、配置、辅助代码及其衍生内容，以及构建出的 RPM 和所含依赖，
保留各自的版权和许可证；MIT 许可不替代这些上游条款。详见 [第三方许可说明](THIRD_PARTY_NOTICES.md)。
