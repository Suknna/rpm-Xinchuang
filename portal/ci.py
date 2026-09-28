#!/usr/bin/env python3
"""Best-effort CI push client. Uses only runner Python, OpenSSH and GitHub CLI."""

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

WORKFLOW = "rpm-xinchuang.yml"
NAMES = {
    "check": "check", "build-el7": "build-el7", "build-el8": "build-el8",
    "test-el7": "test-el7", "test-el8": "test-el8", "release": "release",
    "component-build": "构建 {package} ({el})",
    "component-install": "安装验证 {package} ({el})",
    "component-release": "发布 {package} ({el})",
    "component-record": "回写已发布版本与 spec", "scheduled-time": "记录最近一次成功调度时间",
}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def gh(path):
    return json.loads(subprocess.check_output(["gh", "api", path], stderr=subprocess.PIPE, timeout=45))


def ssh(command, payload=None, stream=None, timeout=25):
    host, key, known = (os.environ.get(k, "") for k in ("PORTAL_SSH_HOST", "PORTAL_SSH_KEY", "PORTAL_SSH_KNOWN_HOSTS"))
    if not all((host, key, known)) or not re.fullmatch(r"[A-Za-z0-9.:-]+", host):
        raise ValueError("SSH settings unavailable")
    with tempfile.TemporaryDirectory(prefix="rpm-portal-") as directory:
        key_path, hosts_path = Path(directory) / "key", Path(directory) / "known_hosts"
        key_path.write_text(key.rstrip() + "\n")
        key_path.chmod(0o600)
        hosts_path.write_text(known.rstrip() + "\n")
        args = ["ssh", "-T", "-i", str(key_path), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + str(hosts_path),
                "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
                "-o", "LogLevel=ERROR", "rpm-portal@" + host, command]
        if stream is None:
            result = subprocess.run(args, input=json.dumps(payload).encode(), stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=timeout, check=True)
        else:
            result = subprocess.run(args, stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=timeout, check=True)
        response = json.loads(result.stdout)
        if response.get("ok") is False:
            raise RuntimeError("receiver rejected request")
        return response


def check_detail(plan):
    entries = json.loads(plan.get("matrix", '{"include":[]}') or '{"include":[]}').get("include", [])
    versions = sorted({p["package"] + " " + p["version"] + " / " + p["el"].upper() for p in entries})
    if plan.get("new_version"):
        versions.insert(0, "OpenSSH " + plan["new_version"] + " / EL7 + EL8")
    return "发现待构建版本：" + "；".join(versions) if versions else "检查完成，没有需要构建的新版本。"


def job_event(environ):
    matrix = json.loads(environ.get("PORTAL_MATRIX", "{}") or "{}") or {}
    job = environ["GITHUB_JOB"]
    status = environ.get("PORTAL_STATUS", "in_progress")
    terminal = status in ("success", "failure", "cancelled", "skipped")
    detail = ""
    if matrix.get("version"):
        detail = "源码版本 " + matrix["version"]
    if job == "check" and status == "success":
        detail = check_detail(json.loads(environ.get("PORTAL_PLAN", "{}") or "{}"))
    return {"kind": "job", "repository": environ["GITHUB_REPOSITORY"], "workflow": WORKFLOW,
            "id": int(environ["GITHUB_RUN_ID"]), "run_attempt": int(environ["GITHUB_RUN_ATTEMPT"]),
            "run_number": int(environ["GITHUB_RUN_NUMBER"]), "event": environ["GITHUB_EVENT_NAME"],
            "head_branch": environ["GITHUB_REF_NAME"], "created_at": now(), "sent_at": now(),
            "name": NAMES[job].format(**matrix), "detail": detail,
            "status": "completed" if terminal else status, "conclusion": status if terminal else None}


def run_event(repository, run, jobs):
    return {"kind": "run", "repository": repository, "workflow": WORKFLOW,
            **{k: run[k] for k in ("id", "run_attempt", "run_number", "event", "head_branch", "created_at", "status", "conclusion")},
            "display_title": run.get("display_title", "rpm-Xinchuang"), "sent_at": now(),
            "jobs": [{k: job.get(k) for k in ("name", "status", "conclusion", "html_url")} for job in jobs]}


def push_run(run=None):
    repository = os.environ["GITHUB_REPOSITORY"]
    if run is None:
        run = gh("repos/%s/actions/workflows/%s/runs?per_page=1" % (repository, WORKFLOW))["workflow_runs"][0]
    jobs = []
    page = 1
    while True:
        try:
            batch = gh("repos/%s/actions/runs/%s/attempts/%s/jobs?per_page=100&page=%s" % (repository, run["id"], run["run_attempt"], page))["jobs"]
        except Exception:
            print("::notice::任务明细暂不可用，仍推送整次运行结果。")
            break
        jobs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    ssh("event", run_event(repository, run, jobs))
    print("已推送整次运行及 %d 个任务的实际状态。" % len(jobs))


def release_data(tag):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", tag):
        raise ValueError("invalid release tag")
    release = gh("repos/%s/releases/tags/%s" % (os.environ["GITHUB_REPOSITORY"], tag))
    if release["draft"] or release["prerelease"]:
        raise ValueError("only published stable releases can be mirrored")
    return release


def publish(tag, paths, release=None):
    release = release or release_data(tag)
    expected = {a["name"]: a for a in release["assets"]
                if a["name"].endswith(".rpm") or re.fullmatch(r"SHA256SUMS(?:-el[78])?", a["name"])}
    files = {path.name: path for path in paths}
    if len(files) != len(paths) or set(files) != set(expected):
        raise ValueError("local files do not match the published release")
    assets = []
    for name, path in files.items():
        source = expected[name]
        if path.stat().st_size != source["size"]:
            raise ValueError("published asset size mismatch")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        sha = digest.hexdigest()
        if source.get("digest") and source["digest"] != "sha256:" + sha:
            raise ValueError("published asset digest mismatch")
        assets.append({**{k: source.get(k) for k in ("id", "name", "size", "updated_at", "digest")}, "sha256": sha})
    with tempfile.TemporaryFile() as stream:
        header = {"repository": os.environ["GITHUB_REPOSITORY"], "tag": tag,
                  "published_at": release["published_at"], "assets": assets}
        stream.write(json.dumps(header).encode() + b"\n")
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for name, path in files.items():
                archive.add(path, arcname=name, recursive=False)
        stream.seek(0)
        result = ssh("upload", stream=stream, timeout=900)
    print("已推送并校验 %d 个 Release 文件。" % result["files"])


def write_summary(package, version, output):
    title = "## %s %s\n\n" % (package, version)
    notes = "上游更新摘要暂不可用。\n"
    try:
        result = ssh("summary", {"package": package, "version": version}, timeout=60)
        if result.get("status") == "ready":
            notes = result["text"] + "\n\n官方更新说明：" + result["source_url"] + "\n"
        else:
            print("::notice::上游摘要暂不可用，Release 将继续发布。")
    finally:
        # Even SSH/model failure leaves a valid notes file for gh release create.
        output.write_text(title + notes, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("event", "complete", "snapshot", "publish", "relay", "summary"))
    parser.add_argument("--tag", default=os.environ.get("PORTAL_TAG", ""))
    parser.add_argument("--package")
    parser.add_argument("--version")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "event":
            payload = job_event(os.environ)
            ssh("event", payload)
            print("已推送：%s · %s" % (payload["name"], payload["conclusion"] or payload["status"]))
        elif args.mode == "complete":
            payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
            push_run(payload["workflow_run"])
        elif args.mode == "snapshot":
            push_run()
        elif args.mode == "publish":
            paths = [Path(p) for pattern in os.environ["PORTAL_FILES"].splitlines() if pattern.strip()
                     for p in glob.glob(pattern.strip())]
            publish(args.tag, paths)
        elif args.mode == "relay":
            release = release_data(args.tag)
            with tempfile.TemporaryDirectory() as directory:
                subprocess.run(["gh", "release", "download", args.tag, "--repo", os.environ["GITHUB_REPOSITORY"],
                                "--pattern", "*.rpm", "--pattern", "SHA256SUMS*", "--dir", directory],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=900)
                publish(args.tag, list(Path(directory).iterdir()), release)
        elif args.mode == "summary":
            if not args.package or not args.version or args.output is None:
                parser.error("summary needs --package, --version and --output")
            write_summary(args.package, args.version, args.output)
    except Exception as error:
        # No command lines, stderr or exception bodies: these can expose server
        # addresses from SSH or private model configuration in public CI logs.
        print("::warning::下载站推送/摘要暂不可用 (%s)；主流水线继续，服务器轮询将补偿。" % type(error).__name__)
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a") as stream:
                stream.write("\n下载站上报未送达，稍后由服务器轮询补偿。\n")


if __name__ == "__main__":
    main()
