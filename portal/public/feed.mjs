// The push feed and polling snapshot are independent atomic files. Merge them
// here so a slow download/poll can never overwrite a newer pushed job result.
const time = (value) => Date.parse(value || "") || 0;
const newerDate = (a, b) => time(a) >= time(b) ? a : b;

export function mergeRun(polled, pushed) {
  if (!polled) return pushed;
  if (!pushed) return polled;
  if (polled.run_attempt !== pushed.run_attempt) return polled.run_attempt > pushed.run_attempt ? polled : pushed;
  const terminal = polled.status === "completed" && pushed.status !== "completed" ? polled :
    pushed.status === "completed" && polled.status !== "completed" ? pushed :
      time(polled.updated_at) > time(pushed.updated_at) ? polled : pushed;
  const jobs = new Map((polled.jobs || []).map((j) => [j.name, j]));
  for (const job of pushed.jobs || []) {
    const old = jobs.get(job.name);
    const keepOld = old && ((old.status === "completed" && job.status !== "completed") ||
      (polled.status === "completed" && time(polled.updated_at) > time(pushed.updated_at)));
    jobs.set(job.name, { ...old, ...job, ...(keepOld ? { status: old.status, conclusion: old.conclusion } : {}),
      html_url: old?.html_url || job.html_url });
  }
  return { ...polled, ...pushed, status: terminal.status, conclusion: terminal.conclusion,
    created_at: polled.created_at || pushed.created_at, jobs: [...jobs.values()] };
}

function mergeRuns(polled, pushed) {
  const runs = new Map(polled.map((r) => [r.id, r]));
  for (const run of pushed) runs.set(run.id, mergeRun(runs.get(run.id), run));
  return [...runs.values()].sort((a, b) => b.id - a.id).slice(0, 30);
}

export function mergeFeed(index, feed) {
  if (!feed || feed.repository !== index.repository) return index;
  const result = structuredClone(index);
  const builds = result.builds || {};
  const pushedRuns = feed.runs || [];
  builds.runs = mergeRuns(builds.runs || [], pushedRuns);
  builds.scheduled_runs = mergeRuns(builds.scheduled_runs || [], pushedRuns.filter((r) => r.event === "schedule"));
  for (const run of pushedRuns) {
    if (time(run.received_at) > time(builds.checked_at)) {
      builds.checked_at = run.received_at;
      builds.workflow_state = "active";
    }
  }
  result.builds = builds;
  result.push_received_at = feed.last_received_at;
  result.updated_at = newerDate(result.updated_at, feed.last_received_at);
  for (const release of feed.releases || []) {
    const pkg = result.packages.find((p) => p.id === release.package);
    if (!pkg) continue;
    const position = pkg.releases.findIndex((r) => r.platform === release.platform);
    const old = pkg.releases[position];
    if (old && time(old.published_at) > time(release.published_at)) continue;
    const next = { ...release };
    if (old?.tag === release.tag && old.summary?.status === "ready") next.summary = old.summary;
    if (position < 0) pkg.releases.push(next); else pkg.releases[position] = next;
  }
  return result;
}
