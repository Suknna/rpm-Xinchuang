# RPM 下载站

静态中文页面 + Python 同步/接收程序 + Caddy。没有前端打包步骤、数据库或常驻应用服务器。
CI 通过受限 SSH 主动推送每个任务分支的开始和结果，发布成功后直接推送 RPM。
服务器每 10 分钟只读 GitHub Releases / Actions，补齐丢失状态或文件；浏览器每 15 秒
读取本站 JSON，展示最近构建、任务日志入口与每日调度健康。

## 安装

目标服务器需要 Python **3.9+**（含 venv / ensurepip）、curl、systemd 和 Caddy。
上传本目录，在目标服务器执行 `bash portal/install.sh`。
安装器保留当前 Caddy 站点地址、TLS 和认证配置，只将原先的
`root * /data` + `file_server browse` 替换为路由片段的 import。
如果站点结构不匹配，安装器停止，由管理员把下面一行放进现有认证站点块后重跑：

```caddyfile
import /data/dist/app/Caddy.routes
```

首次切换时，旧 Caddyfile 和 /data 旧文件移到 `/var/backups/rpm-portal-<时间>/`，
不再对外暴露。大文件在同一文件系统中移动；若 `/data` 独立挂载，先自行移走旧文件。

```text
/data/dist/app/             同步程序与 Caddy 路由（不公开）
/data/dist/venv/            Python 环境（不公开）
/data/dist/private/         config.yaml、摘要缓存、文件回执、锁（0700，不公开）
/data/dist/public/          前端资源，Caddy 的站点根目录
/data/dist/public/data/     只含公开构建/下载信息的 JSON
/data/download/<tag>/       RPM 与 SHA256SUMS，映射 /download/<tag>/...
```

Caddy 不开启目录浏览，不以 `/data` 或 `/data/dist` 为根目录。
现有账号密码认证覆盖页面、JSON 和下载。同步程序以 `rpm-portal` 系统账号运行。

## CI 推送配置

生成一把**专用** ed25519 密钥（不能复用服务器 root 登录密钥），将公钥上传到服务器：

```bash
ssh-keygen -t ed25519 -N '' -C rpm-portal-ci -f ./portal-ci
# 在服务器执行，传入上传的公钥：
bash portal/enable-ci.sh /path/to/portal-ci.pub
```

在仓库 Actions Secrets 配置：

| Secret | 内容 |
| --- | --- |
| `PORTAL_SSH_HOST` | 服务器域名或地址 |
| `PORTAL_SSH_KEY` | 专用私钥完整内容 |
| `PORTAL_SSH_KNOWN_HOSTS` | 已核验的 SSH host key 对应 known_hosts 行 |

客户端固定使用 `rpm-portal` 用户与标准 SSH 端口。公钥安装项强制执行 `receive.py`，
只允许 `event`、`summary`、`upload` 三种请求，禁止任意命令、交互终端和端口转发。
主机身份严格校验；私钥、地址、模型参数均不写入仓库、公开 JSON 或 CI 错误正文。

- 主工作流每个 job 在 checkout 后上报开始，在 `always()` 末尾上报成功/失败/取消。
- 版本检查成功还会上报“无更新”或待构建的软件/版本/平台；矩阵分支分别跟踪。
- `portal-status.yml` 在整次构建结束后推送 GitHub 的实际结果及全部 job 状态，
  补齐因 checkout 失败、取消或 runner 终止而未执行的末尾通知，以及跳过的任务。
- 推送接收按 run ID、attempt 和任务名合并，重复事件幂等；迟到事件不会把已完成任务改回执行中。
- 所有通知、摘要与镜像传输均是 best-effort，失败只在 Actions 中提示，不改变原构建/测试/发布结果。
- 定时成功时间的 job 使用 `always()` 后再核对实际门禁，允许“没有更新、构建被跳过”的正常调度记录心跳。

`index.json` 保存轮询快照，`events.json` 保存主动推送，两者独立原子写入。
页面按运行 attempt、终态及时间合并，避免慢速轮询覆盖刚到达的推送。

手动补推已有 Release：GitHub Actions → **RPM portal status and delivery** → Run workflow，
填写 `release_tag`。留空则只推送最近一次构建的真实状态，不执行编译或测试。

## 私密配置

服务器上的 `/data/dist/private/config.yaml` 是唯一人工配置文件。
`config.example.yaml` 为无密钥模板。不要提交实际配置、IP、模型地址、密钥或 Caddy 密码哈希。

```yaml
repository: owner/repo
workflow: rpm-xinchuang.yml
data_dir: /data
github_token: "" # 公共仓库可不填；如填，只需 contents/actions 只读权限
model:
  endpoint: "" # 完整的 OpenAI-compatible /chat/completions URL
  name: ""
  api_key: ""
```

配置模型后，`systemctl start rpm-portal-sync.service` 触发重试。
上游原文取自对应版本官方发布说明或源码归档内 NEWS / ChangeLog，按软件/源码版本缓存，
不将 RPM 打包说明当作上游更新。输出为纯文本，并展示官方来源链接。
发布前 CI 请求服务器摘要，最多等待 60 秒；未配置模型、无对应版本原文或请求失败时，
Release 正文只保留“上游更新摘要暂不可用”，仍继续发布。页面会在后续同步中补充摘要。
失败一小时后重试，按软件/版本加锁避免 EL7/EL8 重复调用模型。
删除单个 `private/summaries/<组件>-<版本>.json` 可强制重新生成。
已发布的 Release 正文不由服务器回写；后续补充的摘要首先显示在下载页面。

## 运行与故障排查

```bash
systemctl status rpm-portal-sync.timer
journalctl -u rpm-portal-sync.service -n 60 --no-pager
systemctl start rpm-portal-sync.service
```

- 公开仓库无需服务器 GitHub 凭证，正常轮询约 30 次 API 请求/小时；大量历史 Release、
  初始任务缓存、连续构建可能触及匿名限额，可填只读 token 提高额度。
- RPM 先写隐藏临时文件，校验大小及 GitHub 提供的 SHA256 后原子发布；不完整文件不出现下载链接。
  所有完成下载的文件都记录实际 SHA256。GitHub 未提供摘要的旧资产只能校验大小并记录本地摘要。
- 下载使用系统 curl 的断点续传，最多 4 路并发、每个文件每轮最多 120 秒；网络中断保留隐藏片段，
  下轮接着下载。普通 RPM 优先于调试文件；文件完成一个便发布一个下载入口。
  首次从 GitHub 下载较慢时也可通过 SSH 预置资产；同步器会核对官方摘要后再接纳。
- CI 在 GitHub Release 发布/重入校验成功后，将实际发布的 RPM 与校验文件打包推送。
  接收器只接受清单中的普通文件，校验全部文件大小与 SHA256 后发布，拒绝路径穿越和符号链接。
- 状态/API 获取失败时保留上次成功数据并显示错误；超过 30 分钟的旧数据不视为当前健康状态。
- 从默认分支实际工作流读取 cron。当前健康判断支持单个每日固定时刻 cron；其他表达式明确标记待确认。
  超过计划 2 小时未触发标记调度缺失，失败、停用、数据过期分别展示。
- 文件按 Release tag 留存，当前页面只显示各平台最新 Release；旧下载链接继续有效，不自动删除历史 RPM。
- GitHub Release 被删除不会自动删除服务器历史资产；需要撤销坏包时应同时移除对应下载目录。

## 迁移

1. 新服务器安装 Python 3.9+、venv 和 Caddy，复制本目录。
2. 停止旧服务器 `rpm-portal-sync.timer`，等待 `rpm-portal-sync.service` 结束。
3. 复制 `/data/download`、`/data/dist/private`、`/data/dist/public/data` 到新服务器相同路径。
   **不要复制 venv**（解释器路径和系统相关），由安装器重建。
4. 将原 Caddy 站点认证配置带到新服务器，按新域名/IP 配置 TLS；不用修改代码。
5. 运行安装器，并 `chown -R rpm-portal:rpm-portal /data/dist/private /data/dist/public/data /data/download`
   修正迁移后的 UID/GID；`chmod 700 /data/dist/private`。
6. 运行 `bash portal/enable-ci.sh /data/dist/private/ci-key.pub` 恢复受限登录，更新
   GitHub `PORTAL_SSH_HOST` 与 `PORTAL_SSH_KNOWN_HOSTS`；迁移公钥后可沿用原 CI 私钥。
7. 手动运行辅助工作流验证主动推送，再验证认证、RPM 下载、定时器，切换访问地址。

## 验证

```bash
python3 -m unittest discover -s portal/tests -v
node --test portal/tests/test_health.mjs portal/tests/test_feed.mjs
node --check portal/public/app.js
```
