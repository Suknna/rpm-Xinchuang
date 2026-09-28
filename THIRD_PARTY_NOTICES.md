# 第三方来源与许可

根目录的 [MIT License](LICENSE) 适用于本项目原创的构建脚本、工作流和文档。
第三方 spec、配置、服务文件、辅助代码及其衍生内容仍受原许可证约束，原作者的版权和
许可声明继续有效。本项目不以 MIT 对所有 RPM 或第三方代码进行统一重新许可。

## 打包来源

- chrony、Vim、sudo 的 spec 基于 CentOS 7 / AlmaLinux 8 的发行版打包文件调整。
- NTP 使用 CentOS 7 的打包规则，并维护 EL7 / EL8 适配。
- Bash、Telnet 使用本项目维护的 spec，默认配置或服务文件来自相应发行版；Telnet 的
  软件上游为 GNU inetutils，不再使用发行版原有的 netkit-telnet 源码。
- OpenSSH 使用项目维护的专用 spec，复用 OpenSSH portable 随附的 Red Hat 服务模板，
  并维护适用于 EL7 / EL8 的 PAM 配置。

## 软件与依赖

以下为许可概览，不代替各版本源码中的完整声明；RPM spec 的 `License` 字段描述的是
所打包软件的许可，不应直接当作 spec 文件自身的许可声明。

| 软件 / 依赖 | 许可概览 |
| --- | --- |
| OpenSSH portable | BSD 等宽松许可证的组合，详见上游 `LICENCE` |
| chrony | GPLv2，详见对应源码的 `COPYING` |
| GNU Bash | GPLv3 或更新版本 |
| Vim | Vim License；EL8 spec 同时标注 MIT |
| sudo | 主要为 ISC，其他组成部分以其文件声明为准 |
| NTP | MIT / BSD 等许可的组合，含带广告条款的 BSD 变体；附带的 ntpstat 使用 GPLv2 |
| GNU inetutils（Telnet） | GPLv3 或更新版本 |
| OpenSSL 3.x（静态链接依赖） | Apache License 2.0 |
| zlib（静态链接依赖） | zlib License |

仓库内也包含保留独立许可证的辅助文件，例如
[`ntp.dhclient`](source-assets/ntp/el7/ntp.dhclient) 使用 GPLv2 或更新版本，
[`ntp2chrony.py`](source-assets/chrony/el8/ntp2chrony.py) 保留 Miroslav Lichvar 的 MIT 声明。

再分发源码或 RPM 时，应保留对应的版权、许可证及必要声明，并按相关许可证履行
源码提供等义务。打包脚本采用 MIT 不会免除所分发软件及其依赖的许可要求。
