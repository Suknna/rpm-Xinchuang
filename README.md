# rpm-Xinchuang

基于软件官方上游源码及 RHEL 生态的 RPM 打包规则，在 **Red Hat UBI7 / UBI8**
容器中构建适用于 **RHEL 7 / RHEL 8 及兼容发行版的 x86_64 RPM**。
项目通过依赖适配、上游测试和安装验证，尽可能提高软件包在 RHEL 生产环境中的兼容性与可用性。

## 源码与 spec 来源

发行版打包基线主要来自 **CentOS 7 和 AlmaLinux 8 的 SRPM**，维护后的 spec 位于
[`spec/`](spec/)，复用的配置和服务文件位于 [`source-assets/`](source-assets/)。
构建时使用对应软件的官方上游源码，并针对新版本和 EL7 / EL8 调整打包规则。

| 软件 | 源码上游 | 本项目 spec 基础 |
| --- | --- | --- |
| OpenSSH | [OpenSSH portable](https://www.openssh.com/portable.html) | 项目维护的专用 spec，复用上游 Red Hat 服务模板并适配 PAM |
| chrony | [chrony](https://chrony-project.org/) | CentOS 7 / AlmaLinux 8 的 chrony spec |
| Vim | [Vim](https://github.com/vim/vim) | CentOS 7 / AlmaLinux 8 的 vim spec |
| Bash | [GNU Bash](https://www.gnu.org/software/bash/) | 项目维护的精简 spec，复用发行版默认配置 |
| sudo | [sudo](https://www.sudo.ws/) | CentOS 7 / AlmaLinux 8 的 sudo spec |
| NTP | [NTP Project](https://www.ntp.org/) | CentOS 7 的 ntp 打包规则，适配 EL7 / EL8 |
| Telnet | [GNU inetutils](https://www.gnu.org/software/inetutils/) | 针对 inetutils 维护的 spec，复用发行版服务文件；不是原来的 netkit-telnet |

## 兼容性与验证

- 使用固定 digest 的官方 UBI 镜像；EL7 通过 CentOS Vault、EL8 通过 AlmaLinux 仓库补充构建依赖。
- 执行上游测试，并在干净 UBI 容器中安装、运行构建出的 RPM；构建和验证通过后才发布。
  测试覆盖因组件而异，例如 chrony 运行单元测试、Vim 运行已验证的核心用例，详见
  [测试说明](docs/package-test-research.md)。
- OpenSSH 静态链接 OpenSSL / zlib，动态链接系统 glibc / PAM / Kerberos5；保留既有配置和
  host key，本包的安装、升级脚本不主动重启 sshd。替换发行版包时，旧包卸载脚本仍可能触发重启。
- Release 附带 RPM 和 SHA256 校验文件，方便下载后核验。

生产部署仍需在目标系统上验证配置、依赖和业务行为；UBI 容器测试不等同于完整的 RHEL
生产环境验收。EL7 构建使用 CentOS 7 归档源，部署时需结合目标系统的支持周期评估。

## 构建与下载

[GitHub Actions](.github/workflows/rpm-xinchuang.yml) 每天北京时间 **09:17** 检查上游版本，
发现更新后自动构建、测试并发布到 [Releases](https://github.com/Suknna/rpm-Xinchuang/releases)。
已发布版本记录在 [`version.json`](version.json) 中，失败的平台不会推进版本基线。

也可在 Actions 中选择 **rpm-Xinchuang → Run workflow** 手动运行：

- `version`：指定 OpenSSH 版本。
- `force`：强制重建其他六个组件。
- `retry_component`：指定组件和版本，例如 `vim:9.2.1135`。
- `skip_release`：仅构建和验证，产物保留在 Actions artifacts 中。

## 开源许可

本项目原创的构建脚本、工作流和文档采用 [MIT License](LICENSE)。
来自上游或发行版的 spec、配置、辅助代码及其衍生内容，以及构建出的 RPM 和所含依赖，
保留各自的版权和许可证；MIT 许可不替代这些上游条款。详见 [第三方许可说明](THIRD_PARTY_NOTICES.md)。
