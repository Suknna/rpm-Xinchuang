# rpm-Xinchuang

基于软件官方上游源码及 RHEL 生态的 RPM 打包规则，在 **Red Hat UBI7 / UBI8 / CentOS 7.9.2009**
容器中构建适用于 **RHEL 7 / RHEL 8 / CentOS 7 及兼容发行版的 x86_64 RPM**。
另提供 **Ubuntu 22.04 amd64 的 OpenSSH 原生 DEB 升级包**。
项目通过依赖适配、上游测试和安装验证，尽可能提高软件包在 RHEL 生产环境中的兼容性与可用性。

## 源码与 spec 来源

发行版打包基线主要来自 **CentOS 7 和 AlmaLinux 8 的 SRPM**，维护后的 spec 位于
[`spec/`](spec/)，复用的配置和服务文件位于 [`source-assets/`](source-assets/)。
构建时使用对应软件的官方上游源码，并针对新版本和 EL7 / EL8 调整打包规则。

| 软件 | 源码上游 | 本项目 spec 基础 |
| --- | --- | --- |
| OpenSSH | [OpenSSH portable](https://www.openssh.com/portable.html) | 项目维护的专用 spec，复用上游 Red Hat 服务模板并适配 PAM |
| chrony | [chrony](https://chrony-project.org/) | CentOS 7 / AlmaLinux 8 的 chrony spec |
| Vim（构建已暂停） | [Vim](https://github.com/vim/vim) | CentOS 7 / AlmaLinux 8 的 vim spec |
| Bash | [GNU Bash](https://www.gnu.org/software/bash/) | 项目维护的精简 spec，复用发行版默认配置 |
| sudo | [sudo](https://www.sudo.ws/) | CentOS 7 / AlmaLinux 8 的 sudo spec |
| NTP | [NTP Project](https://www.ntp.org/) | CentOS 7 的 ntp 打包规则，适配 EL7 / EL8 |
| Telnet | [GNU inetutils](https://www.gnu.org/software/inetutils/) | 针对 inetutils 维护的 spec，复用发行版服务文件；不是原来的 netkit-telnet |

## 兼容性与验证

- 使用固定 digest 的官方 UBI / CentOS / Ubuntu 镜像，统一维护在 [`scripts/platforms.sh`](scripts/platforms.sh)；
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
已发布版本记录在 [`version.json`](version.json) 中，失败的平台不会推进版本基线。

每次成功发布后，Releases 对**同一组件、同一平台（EL7 / EL8 / CentOS 7）只保留版本号最高的一套 RPM**，
配套子包一并保留；先比较软件版本，再按 RPM 规则比较修订号。OpenSSH 的 EL7 / EL8
共用一个 Release，两平台均通过构建与验证后一起更新。确认保留版本的 RPM 与校验清单完整一致后，
自动删除该组的其他 Release 及附件，保留 Git tag。手动补发较低版本不会替换高版本，也不会回退版本记录；
`skip_release` 不触发清理。
Ubuntu 22.04 的 OpenSSH DEB 按同样的独立平台保留策略处理，版本排序使用 dpkg 规则。

CentOS 7 是独立构建路径，覆盖 OpenSSH、Bash、chrony、sudo、NTP、Telnet：

- 使用原生 CentOS 7.9.2009 镜像，复用 `spec/*/el7.spec`、`source-assets/*/el7/` 和公共 OpenSSH spec。
- RPM 后缀为 `.centos7`，例如 `openssh-10.6p1-2.centos7.x86_64.rpm`；Release tag 为
  `组件-centos7-版本-修订号`，与 UBI7 的 `.el7` 产物独立。
- 普通组件产物位于 `dist/组件/centos7/`，OpenSSH 本地产物位于 `dist/centos7/`；
  Actions 中统一上传为 `built-组件-centos7`。
- 各组件使用独立的 `centos7` 版本记录，OpenSSH 使用 `openssh_centos7`。
  初始值 `null` 会触发首次构建；只有构建、安装验证、发布和 Release 清理成功后才推进记录。
  CentOS 7 的发布不会修改 UBI7 / UBI8 的版本记录或共享 spec。

**Vim 构建与发布暂时停用**：自动检测、强制重建、手动补发和直接调用构建脚本均已屏蔽。
保留 `spec/vim/` 与 `source-assets/vim/`，便于后续恢复。

也可在 Actions 中选择 **rpm-Xinchuang → Run workflow** 手动运行：

- `version`：指定 OpenSSH 版本，覆盖 UBI7 / UBI8 / CentOS 7 / Ubuntu 22.04。
- `force`：强制重建其他已启用组件。
- `retry_component`：指定已启用组件和版本，例如 `chrony:4.9`，补发全部三个平台。
- `skip_release`：仅构建和验证，产物保留在 Actions artifacts 中。

本地构建、验证 CentOS 7 OpenSSH：

```bash
bash scripts/local-build.sh centos7
source scripts/platforms.sh
sudo docker run --rm -v "$PWD":/src:ro -e SRC_DIR=/src "$(image_for centos7)" \
  bash /src/scripts/verify-rpms.sh centos7
bash scripts/local-test.sh centos7
```

两个脚本均支持 `el7`、`el8`、`centos7` 和 `all`。其他组件可使用相同镜像与构建脚本，例如：

```bash
source scripts/platforms.sh
docker run --rm -v "$PWD":/src -e SRC_DIR=/src "$(image_for centos7)" \
  bash /src/scripts/build-upstream.sh chrony centos7 4.9 https://chrony-project.org/releases/chrony-4.9.tar.gz
docker run --rm -v "$PWD":/src:ro -e SRC_DIR=/src "$(image_for centos7)" \
  bash /src/scripts/test-upstream-install.sh chrony centos7 4.9
```

NTP 的 EL7 / CentOS 7 构建需先运行 `bash scripts/fetch-ntp-openssl.sh "$PWD" centos7`
准备固定版本的 OpenSSL 源码（EL7 使用参数 `el7`）；Actions 已自动执行。

## Ubuntu 22.04 OpenSSH 升级包

Ubuntu 分支只构建 OpenSSH，目标为 **Ubuntu 22.04 (jammy) / amd64**，产物包括
`openssh-client`、`openssh-server`、`openssh-sftp-server` 三个原生 `.deb` 包。
保留发行版的 epoch `1:`，例如 `1:10.6p1-2ubuntu22.04`，可以通过 apt 升级系统自带的 OpenSSH。
构建规则在 [`packaging/openssh/ubuntu2204/`](packaging/openssh/ubuntu2204/)，版本和修订号默认读取
`spec/openssh.spec`，也可由 Actions 的 `version` 或本地入口参数指定上游版本。

- 使用 `scripts/platforms.sh` 固定 digest 的官方 Ubuntu 22.04 镜像，显式选择 `linux/amd64`。
- 源码使用仓库内固定 OpenSSH release key 验签；构建执行上游 `make tests`。
- 动态链接 Ubuntu 的 OpenSSL、zlib、PAM、Kerberos 和 libedit，运行依赖由 debhelper 自动生成。
- 产物门禁校验三包版本/架构、SHA256、ELF、PAM 和服务配置；干净容器测试覆盖首次安装、
  从 Ubuntu 官方包升级、重装、卸载和悬空配置软链，并验证 SSH/PAM 登录、SFTP、SCP。
- `/etc` 不随包分发配置 payload，仅对真正缺失的路径补默认模板。保留既有配置和 host key；
  安装与升级不主动启动、停止或重启 SSH。服务使用 Ubuntu 的 `ssh.service` 名称，
  首次显式启动时生成缺失的 host key；同时保留 `ssh.socket` / `ssh@.service` 的按连接激活入口，
  新安装默认启用常规服务，不自动启用 socket。
- `version.json.openssh_ubuntu2204` 独立记录发布基线，`null` 触发首次构建。
  发布 tag 为 `openssh-ubuntu2204-<版本>-<修订号>ubuntu22.04`，资产含三包、`SHA256SUMS`、
  `SOURCE-SHA256SUM`、`build.json` 和 `changelog`。使用 `dpkg --compare-versions` 保留 Ubuntu
  最高版本，资产校验和清理成功后才回写，较低版本补发不会回退基线。

本地构建并验证（需要 Docker；构建和系统安装操作均在临时容器内）：

```bash
bash scripts/local-openssh-ubuntu.sh all
# 可单独执行，或指定上游版本
bash scripts/local-openssh-ubuntu.sh build 10.6p1
bash scripts/local-openssh-ubuntu.sh test 10.6p1
```

产物位于 `dist/openssh/ubuntu2204/`，构建目录为 `.debbuild/ubuntu2204/`。
每日 Actions 自动检测、构建验证并发布；`skip_release` 仅保存 `built-openssh-ubuntu2204`
artifact。`repair_pam` 保持现有 RPM 修复范围，不选择 Ubuntu；Ubuntu 手动重建使用 `version`。

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
