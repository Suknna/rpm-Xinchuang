// Pure status rules are shared by the dashboard and time-boundary tests.
export function stale(value, timestamp = Date.now()) {
  return !value || !Number.isFinite(Date.parse(value)) || timestamp - Date.parse(value) > 30 * 60000;
}

export function runState(run) {
  if (!run) return ["暂无记录", "neutral", "—"];
  if (run.status !== "completed") return [run.status === "queued" ? "排队中" : "执行中", "running", "◷"];
  if (run.conclusion === "success") return ["成功", "success", "✓"];
  if (["failure", "timed_out", "startup_failure", "action_required"].includes(run.conclusion)) return ["失败", "failure", "×"];
  return [{ cancelled: "已取消", skipped: "已跳过", neutral: "中立", stale: "已过期" }[run.conclusion] || "未知结果", "neutral", "−"];
}

export function dailySchedule(builds, timestamp = Date.now()) {
  const crons = builds.cron || [];
  const match = crons.length === 1 && /^(\d{1,2}) (\d{1,2}) \* \* \*$/.exec(crons[0]);
  if (!match || Number(match[1]) > 59 || Number(match[2]) > 23) return null;
  const hour = Number(match[2]), minute = Number(match[1]);
  const expected = new Date(timestamp);
  expected.setUTCHours(hour, minute, 0, 0);
  if (expected.getTime() > timestamp) expected.setUTCDate(expected.getUTCDate() - 1);
  return { expected: expected.getTime(), next: expected.getTime() + 86400000,
    label: `每天 ${String((hour + 8) % 24).padStart(2, "0")}:${String(minute).padStart(2, "0")}` };
}

export function scheduleHealth(builds, timestamp = Date.now()) {
  const latest = (builds.scheduled_runs || [])[0];
  const schedule = dailySchedule(builds, timestamp);
  if (stale(builds.checked_at, timestamp)) return ["状态未知", "warn", "状态数据已过期，等待同步恢复"];
  if (builds.workflow_state !== "active") return ["已停用", "bad", "GitHub 工作流当前未启用"];
  if (!schedule) return ["待确认", "warn", "未检测到单一每日 cron，请核对工作流"];
  if (!latest || Date.parse(latest.created_at) < schedule.expected) {
    if (timestamp > schedule.expected + 2 * 3600000) return ["调度缺失", "bad", "预期触发时间已超过 2 小时"];
    if (!latest) return ["等待触发", "warn", "处于调度延迟宽限期"];
    if (latest.conclusion !== "success") return ["上次异常", "bad", "今天等待触发，上次定时运行未成功"];
    return ["等待触发", "warn", "今天尚未触发，处于 2 小时宽限期"];
  }
  if (latest.status !== "completed") return ["执行中", "", "已触发，等待本次任务完成"];
  if (latest.conclusion !== "success") return ["运行异常", "bad", "最近定时运行未成功，请查看 CI 日志"];
  return ["运行正常", "good", "最近定时运行已完成且成功"];
}
