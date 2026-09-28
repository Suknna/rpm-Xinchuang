import test from "node:test";
import assert from "node:assert/strict";
import { mergeRun, mergeFeed } from "../public/feed.mjs";

const run = (extra = {}) => ({ id: 1, run_attempt: 1, event: "schedule", status: "in_progress", conclusion: null,
  updated_at: "2026-09-28T01:20:00Z", jobs: [{ name: "check", status: "in_progress", conclusion: null }], ...extra });

test("polling cannot reopen a pushed completed task", () => {
  const pushed = run({ jobs: [{ name: "check", status: "completed", conclusion: "failure", detail: "版本检查失败" }] });
  assert.equal(mergeRun(run(), pushed).jobs[0].conclusion, "failure");
});

test("a newer authoritative completion overrides an earlier job report", () => {
  const polled = run({ status: "completed", conclusion: "failure", updated_at: "2026-09-28T02:00:00Z",
    jobs: [{ name: "check", status: "completed", conclusion: "failure" }] });
  const pushed = run({ jobs: [{ name: "check", status: "completed", conclusion: "success" }] });
  assert.equal(mergeRun(polled, pushed).conclusion, "failure");
  assert.equal(mergeRun(polled, pushed).jobs[0].conclusion, "failure");
});

test("a rerun is never mixed with the old failed attempt", () => {
  const old = run({ status: "completed", conclusion: "failure" });
  const current = run({ run_attempt: 2 });
  assert.deepEqual(mergeRun(old, current), current);
  assert.deepEqual(mergeRun(current, old), current);
});

test("a pushed schedule is visible before the next GitHub poll", () => {
  const result = mergeFeed({ repository: "owner/repo", packages: [], builds: {} }, {
    repository: "owner/repo", runs: [run({ received_at: "2026-09-28T01:21:00Z" })], releases: [],
  });
  assert.equal(result.builds.scheduled_runs.length, 1);
  assert.equal(result.builds.checked_at, "2026-09-28T01:21:00Z");
});

test("push fills download links immediately and retains a ready upstream summary", () => {
  const release = { tag: "bash-el8-5.3-1.el8", platform: "el8", published_at: "2026-09-28T02:00:00Z",
    summary: { status: "ready", text: "中文更新" }, assets: [] };
  const result = mergeFeed({ repository: "owner/repo", builds: {}, packages: [{ id: "bash", releases: [release] }] }, {
    repository: "owner/repo", runs: [], releases: [{ ...release, package: "bash", summary: { status: "unavailable" },
      assets: [{ url: "/download/bash/file.rpm" }], mirror_ok: true }],
  });
  assert.equal(result.packages[0].releases[0].assets[0].url, "/download/bash/file.rpm");
  assert.equal(result.packages[0].releases[0].summary.text, "中文更新");
});

test("old release pushes do not roll back a newer polled release", () => {
  const current = { platform: "el8", version: "5.3", published_at: "2026-09-28T02:00:00Z" };
  const result = mergeFeed({ repository: "owner/repo", builds: {}, packages: [{ id: "bash", releases: [current] }] }, {
    repository: "owner/repo", runs: [], releases: [{ package: "bash", platform: "el8", version: "5.2", published_at: "2026-09-27T02:00:00Z" }],
  });
  assert.equal(result.packages[0].releases[0].version, "5.3");
});
