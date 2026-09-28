"use strict";

import { runState, stale, dailySchedule, scheduleHealth } from "./health.mjs";
import { mergeFeed } from "./feed.mjs";

const $ = (selector) => document.querySelector(selector);
const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const external = (value) => {
  try { const url = new URL(value); return url.protocol === "https:" ? escapeHTML(url.href) : "#"; }
  catch { return "#"; }
};
const dateFormat = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
const date = (value) => value && Number.isFinite(Date.parse(value)) ? dateFormat.format(new Date(value)) : "暂无记录";
const age = (value) => {
  if (!value || !Number.isFinite(Date.parse(value))) return "尚未同步";
  const minutes = Math.max(0, Math.floor((Date.now() - Date.parse(value)) / 60000));
  return minutes < 1 ? "刚刚" : minutes < 60 ? `${minutes} 分钟前` : minutes < 1440 ? `${Math.floor(minutes / 60)} 小时前` : `${Math.floor(minutes / 1440)} 天前`;
};
const size = (bytes) => bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
const state = { data: null, platform: "all", search: "", loading: false, view: "packages", failed: false };

function badge(run) {
  const [label, color, icon] = runState(run);
  return `<span class="badge ${color}">${icon} ${label}</span>`;
}

function setView() {
  state.view = ["packages", "builds", "schedule"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "packages";
  const titles = {
    packages: ["软件包", "让每一次更新，清晰可见", "从官方源码到可用的 RPM，下载所需版本，了解每一次改变。"],
    builds: ["构建看板", "每一次构建，都有迹可循", "构建、验证、发布。集中查看运行结果，一键定位失败日志。"],
    schedule: ["定时任务", "每天的例行检查，心中有数", "区分调度缺失与执行失败，让成功记录真正代表运行健康。"],
  };
  const [breadcrumb, title, description] = titles[state.view];
  $("#breadcrumb").textContent = breadcrumb;
  $("#page-title").innerHTML = `${title}<span>.</span>`;
  $("#page-description").textContent = description;
  document.title = `${breadcrumb} · RPM Studio`;
  document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== `${state.view}-view`; });
  document.querySelectorAll(".nav-link").forEach((link) => {
    const active = link.dataset.view === state.view;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  });
}

function renderMetrics() {
  const data = state.data, builds = data.builds || {}, runs = builds.runs || [];
  const count = (data.packages || []).filter((p) => p.releases.some((r) => r.assets.some((a) => a.url && a.name.endsWith(".rpm")))).length;
  $("#metric-packages").innerHTML = `${String(count).padStart(2, "0")}<small>/ 07 个组件</small>`;
  const latest = runs[0], [buildLabel, color, icon] = runState(latest);
  $("#metric-build").textContent = `${icon} ${buildLabel}`;
  $("#metric-build").className = `metric-value status-value ${color === "success" ? "good" : color === "failure" ? "bad" : ""}`;
  $("#metric-build-detail").textContent = latest ? `#${latest.run_number} · ${date(latest.created_at)}${stale(builds.checked_at) ? " · 旧数据" : ""}` : "尚未获取到运行记录";
  const [health, healthClass, detail] = scheduleHealth(builds);
  $("#metric-schedule").textContent = health;
  $("#metric-schedule").className = `metric-value status-value ${healthClass}`;
  $("#metric-schedule-detail").textContent = dailySchedule(builds)?.label + " · 北京时间";
  if (!dailySchedule(builds)) $("#metric-schedule-detail").textContent = detail;
  const oldest = [builds.checked_at, data.catalog_checked_at].filter(Boolean).sort()[0];
  $("#metric-sync").textContent = age(oldest);
  const syncBad = state.failed || stale(builds.checked_at) || stale(data.catalog_checked_at) || (data.errors || []).length;
  $("#metric-sync").className = `metric-value status-value ${syncBad ? "warn" : ""}`;
  $("#metric-sync-detail").textContent = syncBad ? "数据同步异常或已过期" : "CI 主动推送 · 定时补偿";
  $("#nav-build-alert").hidden = color !== "failure";
  const messages = [...(data.errors || [])];
  if (state.failed) messages.push("页面数据请求失败，正在展示上次结果。");
  if (stale(builds.checked_at) || stale(data.catalog_checked_at)) messages.push("数据尚未就绪或已超过 30 分钟未更新，当前状态不能代表最新结果。");
  if ((data.packages || []).some((p) => p.releases.some((r) => !r.mirror_ok))) messages.push("部分 Release 文件仍待同步，下载入口将在校验完成后开放。");
  $("#notice").hidden = !messages.length;
  $("#notice").textContent = messages.join(" ");
  $("#footer-update").textContent = `数据更新于 ${date(data.updated_at)} · 北京时间`;
  $("#repo-link").href = `https://github.com/${data.repository}`;
  $("#actions-link").href = `https://github.com/${data.repository}/actions`;
}

function assetHTML(asset) {
  const url = typeof asset.url === "string" && /^\/download\/[A-Za-z0-9._+-]+\/[A-Za-z0-9._+-]+$/.test(asset.url) ? asset.url : null;
  const sha = /^[a-f0-9]{64}$/.test(asset.sha256) ? asset.sha256 : null;
  return `<div class="asset"><div class="asset-top"><div class="asset-info"><div class="asset-name">${escapeHTML(asset.name)}</div><div class="asset-size">${size(asset.size)}${url ? " · 已同步" : " · 等待同步"}</div></div>${url ? `<a class="download-button" href="${escapeHTML(url)}" download aria-label="下载 ${escapeHTML(asset.name)}">↓ 下载</a>` : '<span class="chip">同步中</span>'}</div>${sha ? `<button type="button" class="copy-hash" data-sha="${sha}" title="${sha}">SHA256 ${sha.slice(0, 12)}… <span>复制</span></button>` : ""}</div>`;
}

function releaseHTML(release) {
  const summary = release.summary || {}, regular = release.assets.filter((a) => !a.debug), debug = release.assets.filter((a) => a.debug);
  return `<article class="release-panel"><div class="release-heading"><h4>${escapeHTML(release.platform.toUpperCase())}<small>x86_64</small></h4><a href="${external(release.release_url)}" target="_blank" rel="noopener noreferrer">GitHub Release ↗</a></div><div class="release-subtitle"><b>版本 ${escapeHTML(release.version)}</b><span>${date(release.published_at)}</span></div>${summary.status === "ready" ? `<p class="summary-text">${escapeHTML(summary.text)}</p>` : `<p class="summary-empty">${escapeHTML(summary.text || "摘要暂不可用，等待服务器同步。")}</p>`}${summary.source_url ? `<a class="source-link" href="${external(summary.source_url)}" target="_blank" rel="noopener noreferrer">官方更新原文 ↗</a>` : ""}<div class="download-title"><span>下载文件</span><span>${regular.filter((a) => a.name.endsWith(".rpm")).length} 个 RPM</span></div>${regular.map(assetHTML).join("")}${debug.length ? `<details class="debug-files"><summary>调试文件 · ${debug.length} 个</summary>${debug.map(assetHTML).join("")}</details>` : ""}</article>`;
}

function renderPackages() {
  const opened = new Set([...document.querySelectorAll(".package[open]")].map((p) => p.dataset.package));
  const packages = (state.data.packages || []).filter((p) => `${p.name} ${p.id} ${p.description}`.toLowerCase().includes(state.search));
  $("#package-list").innerHTML = packages.length ? packages.map((p) => {
    const releases = p.releases.filter((r) => state.platform === "all" || r.platform === state.platform).sort((a, b) => a.platform.localeCompare(b.platform));
    const latest = [...releases].sort((a, b) => b.published_at.localeCompare(a.published_at))[0];
    const versions = [...new Set(releases.map((r) => r.version))].join(" / ");
    return `<details class="package" data-package="${escapeHTML(p.id)}" ${opened.has(p.id) ? "open" : ""}><summary><span class="package-icon">${escapeHTML(p.icon)}</span><div class="package-name"><h3>${escapeHTML(p.name)}</h3><p>${escapeHTML(p.description)}</p></div><span class="package-version">${versions ? `v${escapeHTML(versions)}` : "待发布"}</span><span class="platforms">${["el7", "el8"].map((el) => `<span class="chip ${p.releases.some((r) => r.platform === el) ? "available" : ""}">${el.toUpperCase()}</span>`).join("")}</span><span class="package-date">${latest ? age(latest.published_at) + "更新" : "暂无 Release"}</span><span class="chevron" aria-hidden="true">›</span></summary><div class="package-content">${releases.length ? `<div class="release-grid">${releases.map(releaseHTML).join("")}</div>` : '<p class="empty-package">该平台暂无已发布的 RPM。可前往构建看板查看最新进展。</p>'}</div></details>`;
  }).join("") : state.search ? '<div class="empty-state"><h3>没有找到匹配的软件包</h3><p>试试组件名称，例如 OpenSSH、Vim 或 chrony。</p></div>' : '<div class="empty-state"><h3>软件目录等待同步</h3><p>首次同步完成后，将展示最新发布的 RPM 文件。</p></div>';
}

function runHTML(run) {
  const trigger = { schedule: "定时检查", workflow_dispatch: "手动触发", push: "代码推送", workflow_run: "工作流触发" }[run.event] || run.event;
  const jobs = run.jobs || [];
  return `<article class="build-row"><div class="build-row-head"><div class="build-info"><a class="build-title" href="${external(run.html_url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(run.display_title || "rpm-Xinchuang")} ↗</a><div class="build-meta"><b>#${run.run_number}${run.run_attempt > 1 ? ` · 第 ${run.run_attempt} 次尝试` : ""}</b><span>${escapeHTML(trigger)}</span><span>${date(run.created_at)}</span><span>${escapeHTML(run.head_branch)}</span></div></div>${badge(run)}</div>${jobs.length ? `<details class="job-details" data-run="${run.id}"><summary>展开 ${jobs.length} 个任务${jobs.some((j) => runState(j)[1] === "failure") ? " · 包含失败任务" : ""}</summary><div class="jobs">${jobs.map((j) => `<div class="job"><div class="job-main"><a href="${external(j.html_url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(j.name)} ↗</a>${j.detail ? `<p class="job-note">${escapeHTML(j.detail)}</p>` : ""}</div>${badge(j)}</div>`).join("")}</div></details>` : ""}</article>`;
}

function renderBuilds() {
  const opened = new Set([...document.querySelectorAll(".job-details[open]")].map((p) => p.dataset.run));
  const runs = state.data.builds?.runs || [];
  const count = (key) => runs.filter((r) => runState(r)[1] === key).length;
  $("#build-summary").innerHTML = `<span class="badge success">✓ ${count("success")} 次成功</span><span class="badge failure">× ${count("failure")} 次失败</span><span class="badge running">◷ ${count("running")} 次进行中</span><span class="badge neutral">${count("neutral")} 次其他结果</span><span class="badge neutral">最近主动推送：${state.data.push_received_at ? age(state.data.push_received_at) : "尚未收到"}</span>`;
  $("#build-list").innerHTML = runs.length ? runs.map(runHTML).join("") : '<div class="empty-state"><h3>尚无构建数据</h3><p>服务器完成首次同步后将在此展示。</p></div>';
  document.querySelectorAll(".job-details").forEach((detail) => { detail.open = opened.has(detail.dataset.run); });
}

function chinaDay(timestamp) { return new Date(new Date(timestamp).getTime() + 8 * 3600000).toISOString().slice(0, 10); }

function renderSchedule() {
  const builds = state.data.builds || {}, runs = builds.scheduled_runs || [], latest = runs[0];
  const schedule = dailySchedule(builds), [health, color, description] = scheduleHealth(builds);
  $("#schedule-card").innerHTML = `<div><h3 class="schedule-status ${color}">${health}</h3><p>${description}</p><p>GitHub 调度可能延迟，超过预期时间 2 小时仍未触发将标记异常。</p></div><div class="schedule-facts"><div class="schedule-fact"><span>运行计划</span><b>${schedule?.label || "无法识别每日计划"}</b></div><div class="schedule-fact"><span>最近触发</span><b>${date(latest?.created_at)}</b></div><div class="schedule-fact"><span>下次计划</span><b>${schedule ? date(new Date(schedule.next).toISOString()) : "待确认"}</b></div><div class="schedule-fact"><span>工作流</span><b>${builds.workflow_state === "active" ? "已启用" : escapeHTML(builds.workflow_state || "未知")}</b></div></div>`;
  const today = chinaDay(Date.now());
  $("#schedule-calendar").innerHTML = Array.from({ length: 14 }, (_, i) => {
    const day = chinaDay(Date.now() - (13 - i) * 86400000);
    const matches = runs.filter((r) => chinaDay(r.created_at) === day);
    const run = matches[0];
    let label = "未检测到定时运行", color = "missing", symbol = "−";
    if (run) [label, color, symbol] = runState(run);
    else if (day === today && schedule && (chinaDay(schedule.expected) !== today || Date.now() < schedule.expected + 2 * 3600000)) { label = "等待今日调度"; color = "pending"; symbol = "·"; }
    const tile = `<span class="day-square ${color}">${symbol}</span><span>${day.slice(5).replace("-", "/")}</span>`;
    return run ? `<a class="day" href="${external(run.html_url)}" target="_blank" rel="noopener noreferrer" title="${day} · ${label} · ${matches.length} 次运行">${tile}</a>` : `<div class="day" title="${day} · ${label}">${tile}</div>`;
  }).join("");
  $("#schedule-list").innerHTML = runs.length ? runs.slice(0, 14).map(runHTML).join("") : '<div class="empty-state"><h3>尚未检测到定时运行</h3><p>请确认默认分支的工作流已启用 schedule。</p></div>';
}

async function load() {
  if (state.loading) return;
  state.loading = true;
  $("#refresh").disabled = true;
  $("#refresh").setAttribute("aria-busy", "true");
  try {
    const [response, feed] = await Promise.all([
      fetch("/data/index.json", { cache: "no-store", signal: AbortSignal.timeout(15000) }),
      fetch("/data/events.json", { cache: "no-store", signal: AbortSignal.timeout(15000) })
        .then((r) => r.ok ? r.json() : null).catch(() => null),
    ]);
    if (!response.ok) throw new Error("Index unavailable");
    const data = await response.json();
    if (!Array.isArray(data.packages) || !/^[\w.-]+\/[\w.-]+$/.test(data.repository)) throw new Error("Invalid index");
    state.data = mergeFeed(data, feed);
    state.failed = false;
    renderMetrics(); renderPackages(); renderBuilds(); renderSchedule();
  } catch {
    state.failed = true;
    if (state.data) renderMetrics();
    else {
      $("#notice").hidden = false;
      $("#notice").textContent = "无法读取站点数据。首次同步可能仍在进行，请稍后刷新；若持续出现，请检查服务器同步服务。";
      $("#package-list").innerHTML = '<div class="empty-state"><h3>下载目录尚未就绪</h3><p>待同步完成后，此处将展示真实的 RPM 文件与构建状态。</p></div>';
      $("#metric-sync").textContent = "连接异常";
      $("#metric-sync").classList.add("warn");
    }
  } finally {
    state.loading = false;
    $("#refresh").disabled = false;
    $("#refresh").removeAttribute("aria-busy");
  }
}

let toastTimer;
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-platform]");
  if (button) {
    state.platform = button.dataset.platform;
    document.querySelectorAll("[data-platform]").forEach((b) => { b.classList.toggle("selected", b === button); b.setAttribute("aria-pressed", String(b === button)); });
    if (state.data) renderPackages();
  }
  const copy = event.target.closest("[data-sha]");
  if (copy) {
    try { await navigator.clipboard.writeText(copy.dataset.sha); $("#toast").textContent = "SHA256 校验值已复制"; }
    catch { $("#toast").textContent = `请手动复制：${copy.dataset.sha}`; }
    $("#toast").hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { $("#toast").hidden = true; }, 7000);
  }
});
$("#search").addEventListener("input", (event) => { state.search = event.target.value.trim().toLowerCase(); if (state.data) renderPackages(); });
document.addEventListener("keydown", (event) => {
  if (event.key === "/" && !/INPUT|TEXTAREA/.test(document.activeElement.tagName) && state.view === "packages") { event.preventDefault(); $("#search").focus(); }
});
$("#refresh").addEventListener("click", load);
window.addEventListener("hashchange", setView);
setView();
load();
setInterval(() => { if (!document.hidden) load(); }, 15000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
