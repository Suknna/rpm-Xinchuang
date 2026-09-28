import test from "node:test";
import assert from "node:assert/strict";
import { dailySchedule, scheduleHealth } from "../public/health.mjs";

const timestamp = Date.parse("2026-09-28T05:00:00Z");
const builds = (overrides = {}) => ({
  workflow_state: "active", cron: ["17 1 * * *"], checked_at: new Date(timestamp).toISOString(),
  scheduled_runs: [{ created_at: "2026-09-28T01:20:00Z", status: "completed", conclusion: "success" }],
  ...overrides,
});

test("manual success never hides the scheduled failure", () => {
  const value = builds({ runs: [{ conclusion: "success" }], scheduled_runs: [{ created_at: "2026-09-28T01:20:00Z", status: "completed", conclusion: "failure" }] });
  assert.equal(scheduleHealth(value, timestamp)[0], "运行异常");
});

test("missing trigger is detected even when yesterday succeeded", () => {
  const value = builds({ scheduled_runs: [{ created_at: "2026-09-27T01:20:00Z", status: "completed", conclusion: "success" }] });
  assert.equal(scheduleHealth(value, timestamp)[0], "调度缺失");
});

test("late trigger inside the grace period is pending, not healthy", () => {
  const time = Date.parse("2026-09-28T02:00:00Z");
  assert.equal(scheduleHealth(builds({ checked_at: new Date(time).toISOString(), scheduled_runs: [] }), time)[0], "等待触发");
});

test("stale data and disabled workflows cannot show green", () => {
  assert.equal(scheduleHealth(builds({ checked_at: "2026-09-28T04:00:00Z" }), timestamp)[0], "状态未知");
  assert.equal(scheduleHealth(builds({ workflow_state: "disabled_inactivity" }), timestamp)[0], "已停用");
});

test("before today's trigger the expected run is yesterday's", () => {
  const schedule = dailySchedule(builds(), Date.parse("2026-09-28T00:10:00Z"));
  assert.equal(new Date(schedule.expected).toISOString(), "2026-09-27T01:17:00.000Z");
  assert.equal(new Date(schedule.next).toISOString(), "2026-09-28T01:17:00.000Z");
  assert.equal(schedule.label, "每天 09:17");
});

test("unsupported schedules are explicit and running is not success", () => {
  assert.equal(scheduleHealth(builds({ cron: ["*/5 * * * *"] }), timestamp)[0], "待确认");
  assert.equal(scheduleHealth(builds({ scheduled_runs: [{ created_at: "2026-09-28T01:20:00Z", status: "in_progress" }] }), timestamp)[0], "执行中");
  assert.equal(scheduleHealth(builds(), timestamp)[0], "运行正常");
});
