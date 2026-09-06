#!/usr/bin/env python3
"""Publish only the allowlisted public dashboard after all release gates pass."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Shanghai")
QUALITY_REPORT = ROOT / "data" / "research" / "research_quality_report.json"
UPDATE_REPORT = ROOT / "data" / "processed" / "daily_update_report.json"
PUBLICATION_REPORT = ROOT / "data" / "processed" / "public_publication_report.json"
GPT_IMPORT_REPORT = ROOT / "data" / "processed" / "gpt_brief_import_report.json"
DAILY_BRIEF = ROOT / "data" / "processed" / "daily_ai_brief.json"

# This is intentionally narrow. Add another path only after confirming that it
# contains browser-safe, redistribution-safe data.
PUBLIC_ALLOWLIST = ("web/public/data/dashboard.json",)
FORBIDDEN_PUBLIC_MARKERS = (
    "/Users/",
    "\\Users\\",
    ".duckdb",
    "data/raw/",
    "data/research/",
    "data/standardized/",
)


class PublishBlocked(RuntimeError):
    pass


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishBlocked(f"invalid_or_missing_report:{path.relative_to(ROOT)}") from exc


def local_date(timestamp: str) -> date:
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(TZ).date()
    except (TypeError, ValueError) as exc:
        raise PublishBlocked("invalid_quality_timestamp") from exc


def secret_values() -> list[str]:
    path = ROOT / ".env"
    if not path.exists():
        return []
    values = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        value = line.split("=", 1)[1].strip().strip('"').strip("'")
        if len(value) >= 8:
            values.append(value)
    return values


def verify_release_gates(run_date: date) -> None:
    update = load_json(UPDATE_REPORT)
    if update.get("runDate") != run_date.isoformat():
        raise PublishBlocked("daily_update_report_not_current")
    if not update.get("tasks"):
        raise PublishBlocked("no_update_tasks_ran")
    failed = update.get("failed") or []
    blocking_failed = update.get("blockingFailed")
    if blocking_failed is None:
        # Backward-compatible interpretation of older update reports.
        blocking_failed = [name for name in failed if name != "ai_events"]
    if blocking_failed:
        raise PublishBlocked("data_update_failed")
    task_status = {row.get("task"): row.get("status") for row in update.get("tasks", [])}
    if task_status.get("research_pipeline") != "ok":
        raise PublishBlocked("research_pipeline_not_successful")

    quality = load_json(QUALITY_REPORT)
    if quality.get("status") != "pass":
        raise PublishBlocked("data_quality_not_pass")
    if local_date(quality.get("generated_at")) != run_date:
        raise PublishBlocked("data_quality_report_not_current")

    manual_import_ran = task_status.get("gpt_brief_import") == "ok"
    if manual_import_ran:
        brief = load_json(DAILY_BRIEF)
        if brief.get("importMethod") != "manual_chatgpt_copy":
            raise PublishBlocked("manual_gpt_import_brief_missing")
        imported = load_json(GPT_IMPORT_REPORT)
        if imported.get("status") not in {"validated", "ok", "saved_not_published"}:
            raise PublishBlocked("manual_gpt_import_not_validated")
        if imported.get("runDate") != run_date.isoformat():
            raise PublishBlocked("manual_gpt_import_report_not_current")
        if not isinstance(imported.get("importedEvents"), int) or imported["importedEvents"] < 1:
            raise PublishBlocked("manual_gpt_import_has_no_events")
        allowed_statuses = {"official_feed", "primary_source_link_supplied", "attributed_secondary_report"}
        if any(event.get("verificationStatus") not in allowed_statuses for event in brief.get("events", [])):
            raise PublishBlocked("manual_gpt_event_missing_source_classification")


def verify_public_files() -> None:
    secrets = secret_values()
    for relative in PUBLIC_ALLOWLIST:
        path = ROOT / relative
        if not path.is_file():
            raise PublishBlocked(f"missing_public_file:{relative}")
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                raise PublishBlocked(f"invalid_public_json:{relative}") from exc
        if any(marker in text for marker in FORBIDDEN_PUBLIC_MARKERS):
            raise PublishBlocked(f"internal_path_in_public_file:{relative}")
        if any(secret in text for secret in secrets):
            raise PublishBlocked(f"secret_value_in_public_file:{relative}")


def write_report(payload: dict) -> None:
    PUBLICATION_REPORT.parent.mkdir(parents=True, exist_ok=True)
    PUBLICATION_REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Commit and push allowlisted public dashboard data only.")
    parser.add_argument("--date", type=date.fromisoformat, default=datetime.now(TZ).date())
    args = parser.parse_args()
    report = {
        "runDate": args.date.isoformat(),
        "status": "blocked",
        "allowlist": list(PUBLIC_ALLOWLIST),
        "commitHash": None,
        "pushResult": "not_attempted",
        "vercelTrigger": "not_attempted",
    }
    try:
        if git("branch", "--show-current").stdout.strip() != "main":
            raise PublishBlocked("branch_is_not_main")
        if not git("remote", "get-url", "origin", check=False).returncode == 0:
            raise PublishBlocked("origin_remote_missing")
        staged_before = [line for line in git("diff", "--cached", "--name-only").stdout.splitlines() if line]
        if staged_before:
            raise PublishBlocked("preexisting_staged_changes")

        verify_release_gates(args.date)
        verify_public_files()

        previous = load_json(PUBLICATION_REPORT) if PUBLICATION_REPORT.exists() else {}
        current_head = git("rev-parse", "HEAD").stdout.strip()
        if previous.get("status") == "push_failed" and previous.get("commitHash") == current_head:
            pending_paths = [
                line
                for line in git("diff-tree", "--no-commit-id", "--name-only", "-r", current_head).stdout.splitlines()
                if line
            ]
            if pending_paths and set(pending_paths).issubset(PUBLIC_ALLOWLIST):
                push = git("push", "origin", "main", check=False)
                report["commitHash"] = current_head
                if push.returncode != 0:
                    report.update({"status": "push_failed", "pushResult": (push.stderr or push.stdout).strip()})
                    write_report(report)
                    return 1
                report.update(
                    {
                        "status": "pushed",
                        "pushResult": (push.stderr or push.stdout).strip() or "ok",
                        "vercelTrigger": "requested_by_git_push",
                        "reason": "retried_previous_allowlisted_commit",
                    }
                )
                write_report(report)
                return 0

        for relative in PUBLIC_ALLOWLIST:
            tracked = git("ls-files", "--error-unmatch", "--", relative, check=False)
            if tracked.returncode != 0:
                raise PublishBlocked(f"public_file_not_tracked:{relative}")
            git("add", "--", relative)

        staged = [line for line in git("diff", "--cached", "--name-only").stdout.splitlines() if line]
        unexpected = sorted(set(staged) - set(PUBLIC_ALLOWLIST))
        if unexpected:
            raise PublishBlocked("non_allowlisted_file_staged")
        if not staged:
            report.update({"status": "skipped", "reason": "no_public_changes", "pushResult": "skipped"})
            write_report(report)
            return 0

        message = f"Daily data update {args.date.isoformat()}"
        commit = git("commit", "-m", message)
        commit_hash = git("rev-parse", "HEAD").stdout.strip()
        committed_paths = [
            line
            for line in git("diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash).stdout.splitlines()
            if line
        ]
        if sorted(committed_paths) != sorted(staged):
            raise PublishBlocked("committed_paths_do_not_match_allowlist")
        report.update({"status": "committed", "commitHash": commit_hash, "commitResult": commit.stdout.strip()})
        push = git("push", "origin", "main", check=False)
        if push.returncode != 0:
            report.update({"status": "push_failed", "pushResult": (push.stderr or push.stdout).strip()})
            write_report(report)
            return 1
        report.update(
            {
                "status": "pushed",
                "pushResult": (push.stderr or push.stdout).strip() or "ok",
                "vercelTrigger": "requested_by_git_push",
            }
        )
        write_report(report)
        return 0
    except (PublishBlocked, subprocess.CalledProcessError) as exc:
        # The index was verified empty before this process started, so it is
        # safe to unstage only the paths this publisher may have added.
        git("restore", "--staged", "--", *PUBLIC_ALLOWLIST, check=False)
        reason = str(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            reason = (exc.stderr or exc.stdout or f"git_exit_{exc.returncode}").strip()
        report.update({"reason": reason})
        write_report(report)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
