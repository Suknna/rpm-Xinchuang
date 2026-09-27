# 七组件上游测试与 Fedora/RHEL 打包测试实践调研

调研日期：2026-09-27。所有"上游/发行版现状"结论均来自当日实际抓取的一手来源
（上游仓库文件、GNU 官方文档、src.fedoraproject.org / gitlab.com/redhat 的真实
spec 与 gating 仓库内容）；凡未能核实的均明确标注为**缺口**，不作推断。

> 下表的「本仓库现状」指调研开始时的状态。此后已追加 OpenSSH 密码登录及上游
> regress、Vim 指定上游用例、NTP `make check`、chrony/telnet 回环检查；以仓库
> `spec/` 和 `scripts/` 的最新内容为准。Vim 的完整 suite 在无 tty 的 UBI
> 构建容器内仍不稳定，当前仅对已验证的上游目标执行硬门禁。

## 0. 先澄清两类测试的边界

| | 上游测试套件（upstream suite） | 发行版包验证（distro install/functional） |
| --- | --- | --- |
| 验证对象 | **构建树里的二进制**（刚编译完、未安装） | **安装后的系统二进制 + 打包元数据** |
| 运行位置 | `rpmbuild` 的 `%check` 段（Fedora 用 mock：非 root、无 systemd 服务管理） | RHEL gating 用 [tmt](https://tmt.readthedocs.io/) 在 Testing Farm（有 systemd）驱动 beakerlib/shell 测试 |
| 典型内容 | `make check` / `make tests`（单元 + 回归） | 安装/升级/卸载、文件布局、服务启停、配置保留（本仓库 `scripts/test-install.sh`、`scripts/test-upstream-install.sh` 即此类） |
| 局限 | 测不到打包层问题（scriptlet、%files、配置策略） | 测不到上游代码回归，只能抽查命令行为 |

本仓库现状已经同时覆盖两层：spec 的 `%check`（构建期上游套件）+ 干净 UBI 容器
安装冒烟/行为矩阵（`spec/`、`scripts/`、workflow 第 151/242/263 行）。

## 1. 对比总表

| 组件 | 上游测试入口（一手来源） | 关键前置 | Fedora rawhide `%check`（实测抓取） | RHEL 系公开 gating（实测抓取） | 本仓库现状 | EL7/EL8 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| OpenSSH portable | `./configure && make tests`（[regress/README.regress](https://github.com/openssh/openssh-portable/blob/master/regress/README.regress)；[regress/Makefile](https://github.com/openssh/openssh-portable/blob/master/regress/Makefile)：`tests: prep file-tests t-exec unit`） | 自建 loopback sshd（默认端口 4242，`TEST_SSH_PORT` 可改）；系统 `$PATH` 里要有 `scp`；PAM 系统部分测试要 `SUDO=`；putty/conch/dropbear 互操作测试**默认不跑** | 有 `%check`，但跑的是发行版自带 `parallel_tests.sh`+`parallel_tests.Makefile`（SOURCE22/23），`OPENSSL_CONF=/dev/null`；直接 `make tests` 一行被注释掉 | [c9s dist-git tests/tests.yml](https://gitlab.com/redhat/centos-stream/rpms/openssh/-/blob/c9s/tests/tests.yml)：STI beakerlib（`port-forwarding`、`pam_ssh_agent_auth`，需 iproute/procps-ng/initscripts/net-tools/expect 等） | **无 %check**；靠完整行为矩阵（fresh/upgrade/reinstall/uninstall/symlink-guard） | regress 自带 sshd、不依赖 systemd，容器可跑；`regress/README.regress` 已知问题：新版 coreutils 弃用 `head -[n]` 时需 `export _POSIX2_VERSION=199209`（视容器 coreutils 版本而定，未实测） |
| sudo | `make check`（[Makefile.in](https://github.com/sudo-project/sudo/blob/main/Makefile.in)：`check check-verbose check-fuzzer fuzz …` 递归 SUBDIRS；regress 目录遍布 `src/`、`plugins/sudoers/`、`logsrvd/`） | 需先 configure+build；`make check-verbose` 看详细输出；fuzz 走 oss-fuzz（[CONTRIBUTING.md](https://github.com/sudo-project/sudo/blob/main/docs/CONTRIBUTING.md)） | `%check` → `%make_build check` | 无公开仓库（`redhat/centos-stream/tests/sudo` 404） | el7/el8 spec 均已 `%check make check` + 安装后 PAM 真实认证冒烟（`pam-ci` 用户密码 sudo） | 本仓库 CI 已实证可用（spec changelog 记录过 make check 的构建修复） |
| bash | `make tests`（[上游 INSTALL](https://git.savannah.gnu.org/cgit/bash.git/plain/INSTALL)："Optionally, type 'make tests'"） | 无外部依赖；以 root / 无 tty 运行的失败行为**未获上游文档证实**（缺口） | `%bcond_without tests`（默认开）+ `%check make check`（mock 非 root 构建） | 无公开仓库（404） | el7/el8 spec 已 `%check LC_ALL=C make check` | 已在 UBI 容器 root 下实际运行（发布流程在用）；root 场景通过率未单独留档（缺口） |
| vim | `cd src && make test`（或 `src/testdir` 下 `make` 全量；[src/testdir/README.txt](https://github.com/vim/vim/blob/master/src/testdir/README.txt)：`TEST_FILTER`/`TEST_MAY_FAIL`/`TEST_SKIP_PAT`/`TEST_NO_RETRY` 环境变量、`GUI_FLAG=-g`、失败看 `test.log`） | 测的是 `src/vim` 构建产物；部分测试无 GUI/终端时以 `throw "Skipped:"` 自跳过（README 描述的机制） | **无 `%check`、无 make test**（rawhide spec 抓取确认） | [gitlab.com/redhat/centos-stream/tests/vim](https://gitlab.com/redhat/centos-stream/tests/vim)：tmt/FMF，`Sanity/upstream-unittests`、`Sanity/upstream-scripttests`、`vim-aliases`、`bz2011389-Loading-etc-vimrc-virc` | **无 %check**（el8 spec 注释显示 CVE 补丁曾"适配到测试套件可过"，但 CI 不跑） | 全量套件耗时较长；建议先 `TEST_MAY_FAIL` 白名单起步（见 §3） |
| chrony | `make check` = unit + simulation + system（[Makefile.in](https://gitlab.com/chrony/chrony/-/blob/master/Makefile.in)：`check : chronyd chronyc` → `make -C test/unit check` + `cd test/simulation && ./run -i 20 -m 2` + `cd test/system && ./run`）；unit 用自带框架（`test/unit/test.c`） | simulation 需 [clknetsim](https://gitlab.com/chrony/clknetsim)（Linux-only，`CLKNETSIM_PATH` 指向编译产物；[test/simulation/README](https://gitlab.com/chrony/chrony/-/blob/master/test/simulation/README)） | `%check`：`CLKNETSIM_RANDOM_SEED=24508` + 构建 bundled clknetsim + `make quickcheck`（unit+simulation+system 全跑） | [redhat/centos-stream/tests/chrony](https://gitlab.com/redhat/centos-stream/tests/chrony)：tmt，`Sanity/CI-upstream-tests`、`basic-sanity`、`default-configuration`、`ntpstat-chrony-cooperation`、`sanity-nts-selftest` | el7/el8 spec 已 `%check make -C test/unit check`（注释说明：发行版旧 clknetsim 与 chrony 4.9 不兼容，故只跑 unit） | unit 部分 EL7/EL8 已实证可用；simulation/system 未在 EL7 验证（缺口） |
| ntp | `make check`（标准 automake；[GitHub 镜像 ntp-project/ntp `stable` 分支](https://github.com/ntp-project/ntp/tree/stable)：顶层 `Makefile.am` SUBDIRS 含 `tests`（bug-2803/libntp/ntpd/ntpq/sandbox/sec-2853），`sntp/` 自带 Unity 框架，`NTP_PROBLEM_TESTS` 默认启用 test-ntp_restrict/scanner/signd） | 无外部依赖（Unity 打包在内）；测试随 `make` 一起构建 | 无 `%check`（[epel8 spec](https://src.fedoraproject.org/rpms/ntp/raw/epel8/f/ntp.spec) 抓取确认；rawhide 已无 ntp 包） | 无公开仓库（404） | **无 %check**；安装冒烟仅 `ntpd --version` + unit 文件存在 | 最新版 [4.2.8p18](https://downloads.nwtime.org/ntp/)；check 未在 UBI7/8 实测（缺口）；注意 `version.json` 当前 ntp el8 为 null |
| telnet（GNU inetutils） | `make check`（[上游 README.md "Testing" 节](https://git.savannah.gnu.org/cgit/inetutils.git/plain/README.md)：`ftp-localhost`/`ping`/`traceroute` 需 root；`TEST_IPV4`/`TEST_IPV6` 取 yes/no/auto；`--disable-ipv4` 只影响 check 目标；chroot 构建时注意 `/etc` 依赖） | 无 DejaGnu 等外部框架的结论**未能核实**（savannah 持续 502，缺口）；本项目 telnet-only 配置下绝大多数测试被 `--disable-*` 排除，check 很轻 | Fedora `telnet` 是 **netkit-telnet 0.17**（spec 抓取：Source0 为 netkit-telnet，Epoch 1）——与本项目的 inetutils telnet **不是同一上游**；该 spec 无 `%check`；Fedora 也没有 `inetutils` 包（404） | [redhat/centos-stream/tests/telnet](https://gitlab.com/redhat/centos-stream/tests/telnet)：tmt，`Sanity/basic-sanity`、`Sanity/basic`——针对的是发行版 netkit telnet，**不能直接搬用** | el7/el8 spec 已 `%check make check`；安装冒烟 `telnet --version` + `rpm -q telnet-server` | inetutils 2.8（[ftp.gnu.org/gnu/inetutils](https://ftp.gnu.org/gnu/inetutils/) 最新，与项目 Version 一致）；client↔server 回环功能测试尚无（见 §3） |

补充：Fedora `src.fedoraproject.org/tests/{vim,chrony,telnet}` 三个仓库的
README 只有一句 "Public tests have been moved to: https://gitlab.com/redhat/centos-stream/tests/"，
即 RHEL 系 gating 测试现集中在后者；`openssh/sudo/bash/ntp` 在该组内**无**对应仓库
（API 404 实测）。Fedora CI 机制文档：[Fedora CI / Gating Tests](https://docs.fedoraproject.org/en-US/ci/)、[gating](https://docs.fedoraproject.org/en-US/ci/gating/)。
CentOS Stream 8（c8s）dist-git 在 gitlab 与 git.centos.org 均未能公开获取（404/403 实测），
EL8 当年 gating 配置无法引用一手来源，列为缺口。

## 2. 各组件可直接照抄的命令

```sh
# OpenSSH portable（构建完成后，在源码树顶层）
make tests                       # 全量（file-tests + t-exec + unit）
make tests LTESTS=agent-timeout  # 单个测试
# 常用环境变量：TEST_SSH_PORT=4242  SKIP_UNIT=1  SUDO=$(command -v sudo)
# 新 coreutils 报 yes-head 失败时：export _POSIX2_VERSION=199209

# sudo（configure && make 之后）
make check            # 或 make check-verbose

# bash（configure && make 之后）
make tests            # Fedora spec 用的是 make check

# vim（源码树）
cd src && make test            # 全量
cd src/testdir && make test_channel.res   # 单个文件
#   TEST_FILTER=Test_channel TEST_MAY_FAIL=Test_xxx TEST_NO_RETRY=yes

# chrony
make -C test/unit check        # 仅单元（本仓库 spec 现用）
make check                     # unit + simulation(clknetsim) + system
make quickcheck                # 同上，simulation 参数不同

# ntp（configure && make 之后）
make check                     # Unity 单元测试（tests/、sntp/tests）

# GNU inetutils（configure && make 之后）
make check                     # telnet-only 配置下大部分测试已被禁用
```

## 3. 对本仓库 CI 的安全复用建议

原则：**新增测试先以独立 job + 允许失败（观察期）运行，稳定后再转为必需**；
不把依赖 Testing Farm/systemd 的发行版 gating 整体搬入无 systemd 的 UBI 容器。

1. **保持现有两层不动**：spec `%check`（bash/sudo/chrony-unit/telnet）与
   安装冒烟/行为矩阵是本项目最有价值的部分，已覆盖发行版验证层。
2. **OpenSSH 上游 regress（最大补强点）**：本项目 OpenSSH 没有 `%check`，
   而 regress 是上游唯一的正式套件且明确不依赖 systemd。建议加可选 workflow job：
   构建后 `make tests`（给足 timeout，30–60 min 量级），固定 `TEST_SSH_PORT`，
   `LTESTS`/`SKIP_LTESTS` 控制范围；观察期 allow-fail。注意容器内需有系统 `scp`。
3. **vim 上游测试（第二大补强点）**：RHEL gating 自己都在跑
   `Sanity/upstream-unittests`。建议 `cd src && make test` 起步时配
   `TEST_MAY_FAIL` 白名单 + `TEST_NO_RETRY=yes` 缩短时长，独立 allow-fail job；
   稳定后再考虑进 `%check`。
4. **ntp 补 `%check make check`**：测试自带、无外部依赖，成本低；
   先在 UBI7/UBI8 手动试运行记录通过率，再决定是否阻塞发布。
5. **chrony 暂不引入 clknetsim**：Fedora 能跑 quickcheck 是因为 SRPM 捆绑了
   clknetsim 源码并固定随机种子；EL7 上 clknetsim 兼容性未验证，维持
   `make -C test/unit check` 即可（仓库注释已说明原因）。
6. **telnet 补一个 client↔server 回环功能测试**：发行版 gating 的 telnet 测试
   属于 netkit 系，不可复用。建议在 `test-upstream-install.sh` 的 telnet 分支加：
   容器内直接拉起 `telnetd`（无 systemd 时绕过 socket unit），`telnet 127.0.0.1`
   验证握手/回显后退出——把"装上了"升级为"能用"。
7. **EL7 差异**：EL7 已 EOL，UBI7 依赖 vault 补源（`scripts/repos-common.sh`
   已处理）；上游套件里凡依赖新 coreutils 行为的用例（OpenSSH yes-head）按
   上游 README 的 `_POSIX2_VERSION` 方法规避；gcc 版本问题仅影响构建
   （devtoolset-9），不影响测试运行。

## 4. 剩余缺口（未验证，勿当作结论引用）

- 上游套件在 **UBI7/UBI8 root 容器**内的实际通过率未逐一实测：
  bash（root/无 tty 是否产生失败）、OpenSSH regress 全量时长与 flaky、
  ntp `make check`、vim 全量时长。
- inetutils 测试框架细节（是否依赖 DejaGnu）未能核实：savannah cgit 持续 502，
  仅核实了 README 的 Testing 节与 GNU ftp 的 2.8 tarball。
- EL8（c8s）dist-git 的 gating 配置不可公开获取；EL7 dist-gating 更无公开对应物。
- sudo/bash/ntp/openssh 在 `gitlab.com/redhat/centos-stream/tests/` 无公开仓库，
  RHEL 内部使用的测试不可见。
- chrony simulation/system 测试在 EL7 的兼容性、clknetsim 在 devtoolset-9 下的
  可编译性未验证。
- RHEL vim gating 中 `upstream-unittests` 的 allowlist/环境细节未逐文件抓取
  （仅核实了目录与测试名）。
- Fedora rawhide 的 spec 内容逐日变动，本文引用以 2026-09-27 抓取为准；
  本项目 `version.json` 中 ntp el8 为 null（该平台当前无发布基线）。

## 5. 本仓库试跑结果（2026-09-27）

- OpenSSH：EL8 完整上游 `make tests` 已通过；EL7 本机缺少该版本现成的构建树，
  新增 CI 构建期 regress 门禁后须在 CI 验证。独立 UBI7/8 容器中实际 SSH 密码登录已通过。
- NTP：EL8 上游 `make check` 通过；EL7 原始代码使用旧摘要收尾 API，静态 OpenSSL
  3.5 下 SHAKE128 失败。已用 XOF 收尾 API 修正 SNTP 与 ntpd 两处路径，EL7 完整
  `make check` 及 SHAKE128 明确 PASS 均通过；该构建是修复验证，不等同于此前
  发布的旧 EL7 RPM 已获修复。
- Vim：EL7/8 `test_normal.res test_vim9_script.res` 在构建树通过；EL8 全量
  `make test` 在先前打包步骤移动 `runtime/doc` 后因缺文件终止，故未以全量测试
  冒充绿灯；未来可在专门的干净构建树和具备终端条件的环境继续扩展。
- chrony：EL7/8 已安装的 daemon 用 `-x`（不调系统时钟）及本地 `chronyc
  tracking` 通过；telnet：EL7/8 已安装的 telnetd 在本地 TCP 连接完成协议选项协商。
