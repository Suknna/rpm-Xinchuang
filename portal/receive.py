#!/usr/bin/env python3
"""Restricted SSH receiver: events, upstream summaries and verified release files.

The dedicated CI key can execute only these three commands. No shell commands,
client paths, configuration values or model credentials are accepted/returned.
"""

import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tarfile
import tempfile

import yaml

if __package__:
    from .sync import PACKAGES, atomic_json, now, read_json, release_identity, safe_name, summarize
else:
    from sync import PACKAGES, atomic_json, now, read_json, release_identity, safe_name, summarize

CONCLUSIONS = {"success", "failure", "cancelled", "skipped", "timed_out", "neutral", "action_required", "startup_failure", "stale"}


def text(value, limit=200):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError("invalid text")
    return value


def number(value):
    if type(value) is not int or value < 1:
        raise ValueError("invalid positive integer")
    return value


def timestamp(value):
    text(value, 40)
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp needs a timezone")
    return parsed.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def status_fields(payload):
    status = payload.get("status")
    conclusion = payload.get("conclusion")
    if status not in ("queued", "waiting", "in_progress", "completed"):
        raise ValueError("invalid status")
    if status == "completed" and conclusion not in CONCLUSIONS:
        raise ValueError("invalid conclusion")
    return {"status": status, "conclusion": conclusion if status == "completed" else None}


def store(config, mutate):
    root = Path(config["data_dir"])
    with (root / "dist/private/push.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        target = root / "dist/public/data/events.json"
        feed = read_json(target, {"repository": config["repository"], "runs": [], "releases": []})
        mutate(feed)
        feed["last_received_at"] = now()
        atomic_json(target, feed)
        index = target.with_name("index.json")
        if not index.exists():
            atomic_json(index, {"repository": config["repository"], "builds": {}, "packages": [
                {"id": key, "name": value[0], "description": value[1], "icon": value[2], "releases": []}
                for key, value in PACKAGES.items()]})


def receive_event(payload, config):
    if payload.get("repository") != config["repository"] or payload.get("workflow") != config["workflow"]:
        raise ValueError("repository or workflow mismatch")
    run_id, attempt = number(payload["id"]), number(payload["run_attempt"])
    sent_at = timestamp(payload["sent_at"])
    run_url = "https://github.com/%s/actions/runs/%s" % (config["repository"], run_id)
    kind = payload.get("kind")
    if kind not in ("job", "run"):
        raise ValueError("invalid event kind")
    common = {"id": run_id, "run_attempt": attempt, "run_number": number(payload["run_number"]),
              "event": text(payload["event"], 40), "head_branch": text(payload["head_branch"]),
              "created_at": timestamp(payload["created_at"]), "html_url": run_url,
              "display_title": text(payload.get("display_title", "rpm-Xinchuang"))}
    fields = status_fields(payload)

    def clean_job(job):
        url = job.get("html_url") or run_url
        if url != run_url and not re.fullmatch(re.escape(run_url) + r"/job/\d+", url):
            raise ValueError("invalid job URL")
        return {"name": text(job["name"]), "detail": text(job.get("detail", ""), 2000),
                "html_url": url, "updated_at": sent_at, **status_fields(job)}

    jobs = payload.get("jobs", []) if kind == "run" else [payload]
    if not isinstance(jobs, list) or len(jobs) > 200:
        raise ValueError("invalid jobs")
    jobs = [clean_job(job) for job in jobs]

    def apply(feed):
        previous = next((r for r in feed["runs"] if r["id"] == run_id), None)
        if previous and previous["run_attempt"] > attempt:
            return
        run = previous if previous and previous["run_attempt"] == attempt else {
            **common, "status": "in_progress", "conclusion": None, "jobs": [], "updated_at": sent_at}
        # A delayed job-start/end can never reopen a terminal workflow attempt.
        terminal = run["status"] == "completed"
        if terminal and kind == "run" and fields["status"] != "completed":
            return
        if kind == "run" and sent_at >= run["updated_at"]:
            run.update(common)
            run.update(fields)
        by_name = {j["name"]: j for j in run["jobs"]}
        for job in jobs:
            old = by_name.get(job["name"])
            if kind == "job" and terminal:
                continue
            if old and (old["updated_at"] > sent_at or (old["status"] == "completed" and job["status"] != "completed")):
                continue
            # The final GitHub snapshot supplies real job URLs while retaining
            # the version-check decision already pushed by that job.
            if old and not job["detail"]:
                job["detail"] = old.get("detail", "")
            by_name[job["name"]] = job
        run["jobs"] = list(by_name.values())
        run["updated_at"] = max(run["updated_at"], sent_at)
        run["received_at"] = now()
        feed["runs"] = sorted([r for r in feed["runs"] if r["id"] != run_id] + [run],
                              key=lambda r: r["id"], reverse=True)[:30]

    store(config, apply)
    return {"ok": True}


def summary_for(package, version, config):
    if package not in PACKAGES or not re.fullmatch(r"\d+(?:\.\d+)+(?:p\d+)?", version):
        raise ValueError("invalid source version")
    directory = Path(config["data_dir"]) / "dist/private/summaries"
    return summarize(package, version, config, directory)


def receive_upload(header, stream, config):
    if header.get("repository") != config["repository"]:
        raise ValueError("repository mismatch")
    tag = safe_name(header["tag"])
    identity = release_identity(tag)
    if not identity:
        raise ValueError("unrecognized release tag")
    package, version, platform = identity
    published = timestamp(header["published_at"])
    assets = header.get("assets")
    if not isinstance(assets, list) or not 1 <= len(assets) <= 200:
        raise ValueError("invalid manifest")
    manifest = {}
    for asset in assets:
        name = safe_name(asset["name"])
        if not (name.endswith(".rpm") or re.fullmatch(r"SHA256SUMS(?:-el[78])?", name)):
            raise ValueError("unsupported asset")
        if name in manifest or number(asset["size"]) > 1024 * 1024 * 1024:
            raise ValueError("invalid asset size or duplicate name")
        number(asset["id"])
        if not re.fullmatch(r"[a-f0-9]{64}", asset["sha256"]):
            raise ValueError("invalid checksum")
        if asset.get("digest") not in (None, "sha256:" + asset["sha256"]):
            raise ValueError("official checksum mismatch")
        manifest[name] = {k: asset.get(k) for k in ("id", "name", "size", "sha256", "updated_at", "digest")}
    if sum(a["size"] for a in manifest.values()) > 2 * 1024 * 1024 * 1024:
        raise ValueError("release exceeds upload limit")
    root = Path(config["data_dir"])
    incoming = root / "dist/private/incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=incoming) as staging:
        received = set()
        # Never extract archive paths, links, permissions, owners or devices.
        with tarfile.open(fileobj=stream, mode="r|") as archive:
            for member in archive:
                expected = manifest.get(member.name)
                if not member.isfile() or not expected or member.name in received or member.size != expected["size"]:
                    raise ValueError("archive does not match manifest")
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("missing archive member")
                digest = hashlib.sha256()
                with source, (Path(staging) / member.name).open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        digest.update(chunk)
                        output.write(chunk)
                if digest.hexdigest() != expected["sha256"]:
                    raise ValueError("uploaded checksum mismatch")
                received.add(member.name)
        if received != set(manifest):
            raise ValueError("incomplete upload")
        directory = root / "download" / tag
        directory.mkdir(parents=True, exist_ok=True)
        for name, asset in manifest.items():
            path = Path(staging) / name
            path.chmod(0o644)
            os.replace(path, directory / name)
            atomic_json(root / "dist/private/receipts" / (str(asset["id"]) + ".json"), {
                "asset": {k: asset[k] for k in ("id", "size", "updated_at", "digest")}, "sha256": asset["sha256"]})

    summary = read_json(root / "dist/private/summaries" / (package + "-" + version + ".json"),
                        {"status": "unavailable", "text": "摘要暂不可用，等待服务器补充。"})
    releases = []
    for el in ([platform] if platform else ["el7", "el8"]):
        public_assets = [{"name": a["name"], "size": a["size"], "sha256": a["sha256"],
                          "url": "/download/" + tag + "/" + a["name"],
                          "debug": "-debuginfo-" in a["name"] or "-debugsource-" in a["name"]}
                         for a in manifest.values() if (a["name"].endswith(".rpm") and "." + el + "." in a["name"])
                         or a["name"] in ("SHA256SUMS", "SHA256SUMS-" + el)]
        if not any(a["name"].endswith(".rpm") for a in public_assets):
            continue
        releases.append({"package": package, "platform": el, "version": version, "tag": tag,
                         "published_at": published, "release_url": "https://github.com/%s/releases/tag/%s" % (config["repository"], tag),
                         "assets": public_assets, "mirror_ok": True, "summary": summary})

    def apply(feed):
        feed["releases"] = sorted([r for r in feed["releases"] if r["tag"] != tag] + releases,
                                  key=lambda r: r["published_at"], reverse=True)[:50]
    store(config, apply)
    return {"ok": True, "files": len(manifest)}


def main():
    with open("/data/dist/private/config.yaml") as stream:
        config = yaml.safe_load(stream)
    command = os.environ.get("SSH_ORIGINAL_COMMAND", "")
    if command == "upload":
        line = sys.stdin.buffer.readline(65537)
        if len(line) > 65536 or not line.endswith(b"\n"):
            raise ValueError("invalid upload header")
        result = receive_upload(json.loads(line), sys.stdin.buffer, config)
    elif command in ("event", "summary"):
        data = sys.stdin.buffer.read(262145)
        if len(data) > 262144:
            raise ValueError("request too large")
        payload = json.loads(data)
        result = receive_event(payload, config) if command == "event" else summary_for(payload["package"], payload["version"], config)
    else:
        raise ValueError("unsupported SSH command")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # The CI log must never receive private provider URLs or connection data.
        print(json.dumps({"ok": False, "error": type(error).__name__}))
        sys.exit(1)
