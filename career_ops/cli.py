"""Career operations CLI for a job-search tracker and application log.

This script is the controlled state layer around:
- data/sample_job_search_log.csv
- data/sample_application_tracker.csv

It keeps the visible CSV workflow intact while enforcing schemas, sorting,
status transitions, and review/application bookkeeping.

Examples:
    python3 -B career_ops/cli.py validate-state
    python3 -B career_ops/cli.py sort
    python3 -B career_ops/cli.py promote-role --company "Northstar CRM" --role "Product Analytics Lead" --output-file Ashish_Product_Analytics_Northstar.docx --tier1 88 --tier2 81 --legacy-no-queue
    python3 -B career_ops/cli.py mark-review-needed --output-file Ashish_Product_Analytics_Northstar.docx
    python3 -B career_ops/cli.py mark-ready --output-file Ashish_Product_Analytics_Northstar.docx --review-status "Passed"
    python3 -B career_ops/cli.py mark-applied --output-file Ashish_Product_Analytics_Northstar.docx --applied-date 2026-04-30
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback for local demos.
    fcntl = None


BASE = Path(__file__).resolve().parents[1]
DEFAULT_JOB_LOG = BASE / "data" / "sample_job_search_log.csv"
DEFAULT_TRACKER = BASE / "data" / "sample_application_tracker.csv"
DEFAULT_RESUME_QUEUE = BASE / "data" / "sample_resume_queue"
JOB_LOG = DEFAULT_JOB_LOG
TRACKER = DEFAULT_TRACKER
RESUME_QUEUE = DEFAULT_RESUME_QUEUE

JOB_LOG_FIELDS = [
    "search_date",
    "company",
    "role",
    "jd_url",
    "location_type",
    "location_city",
    "track",
    "agent_score",
    "status",
    "decision_reason",
    "resume_file",
    "applied",
    "notes",
]

TRACKER_FIELDS = [
    "date",
    "company",
    "role",
    "track",
    "fitment_score",
    "location_type",
    "location_exception",
    "output_file",
    "tier1_coverage_pct",
    "tier2_coverage_pct",
    "applied",
    "status",
    "review_status",
    "last_reviewed_at",
    "review_notes",
    "notes",
    "application_deadline",
    "follow_up_due",
    "follow_up_count",
    "last_follow_up_date",
    "job_url",
]

JOB_STATUSES = {"Pursued", "Excluded", "Monitoring", "Applied", "Skipped"}
TRACKER_STATUSES = {"Draft Built", "Review Needed", "Resume Ready", "Applied", "Cold"}
REVIEW_STATUSES = {"", "Pending", "Passed", "Warning Accepted", "Failed", "Legacy Unreviewed"}
YES_NO = {"", "Yes", "No"}
TRACKS = {"A", "P", "B", ""}
DECISION_REASONS = {
    "",
    "Very strong fit",
    "Very strong fit - location exception",
    "Below build threshold",
    "Closed listing",
    "Closed or stale listing",
    "Hard tool gap",
    "Domain stretch",
    "Location hard stop",
    "Excluded below fit bar",
    "Built before strict gate",
    "Needs verification",
}
QUEUE_STATUSES = {
    "pending_gate",
    "master_recommended",
    "gate_checked",
    "proposed",
    "approved",
    "building",
    "ready",
    "failed",
    "archived",
}
GATE_DECISIONS = {"use_master_as_is", "customization_needed"}
BUILD_STAGES = {"mechanical_qa", "final_critic", "docx_build", "state_update"}
RETRY_TARGETS = {"master_check", "evidence_map", "build_resume", "human_approval"}
MASTER_BY_TRACK = {
    "A": "01_master_resumes/Ashish_Gupta_Silla_Analytics_Leader.docx",
    "B": "01_master_resumes/Ashish_Gupta_Silla_Analytics_Leader.docx",
    "P": "01_master_resumes/Ashish_Product_Specialist.docx",
}


@dataclass
class Finding:
    severity: str
    path: Path
    message: str


def normalize(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "role"


def role_id(company: str, role: str) -> str:
    return f"{slugify(company)}__{slugify(role)}"


def queue_path(role_id_value: str) -> Path:
    return RESUME_QUEUE / f"{role_id_value}.json"


def ensure_queue_dir() -> None:
    RESUME_QUEUE.mkdir(parents=True, exist_ok=True)


@contextmanager
def state_lock():
    lock_path = BASE / ".career_ops_state.lock"
    with lock_path.open("w", encoding="utf-8") as lock_handle:
        if fcntl is not None:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def queue_lock():
    ensure_queue_dir()
    lock_path = RESUME_QUEUE / ".queue.lock"
    with lock_path.open("w", encoding="utf-8") as lock_handle:
        if fcntl is not None:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def load_packet(role_id_value: str) -> dict:
    path = queue_path(role_id_value)
    if not path.exists():
        raise SystemExit(f"No queue packet found for role_id {role_id_value!r}")
    try:
        packet = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Queue packet {display_path(path)} is not valid JSON: {exc}") from exc
    packet["_path"] = path
    return packet


def write_packet(packet: dict) -> None:
    ensure_queue_dir()
    packet["updated_at"] = today()
    path = queue_path(packet["role_id"])
    payload = {key: value for key, value in packet.items() if key != "_path"}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=RESUME_QUEUE, delete=False) as tmp:
        tmp.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def append_feedback_log(feedback_row: dict) -> None:
    ensure_queue_dir()
    path = RESUME_QUEUE / ".feedback_log.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(feedback_row, sort_keys=True) + "\n")


def queue_packets() -> list[dict]:
    ensure_queue_dir()
    packets: list[dict] = []
    for path in sorted(RESUME_QUEUE.glob("*.json")):
        try:
            packet = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            packets.append({"_path": path, "_invalid_json": str(exc)})
            continue
        packet["_path"] = path
        packets.append(packet)
    return packets


def assert_status(packet: dict, allowed: set[str]) -> None:
    if packet.get("status") not in allowed:
        raise SystemExit(
            f"Role {packet.get('role_id')} is {packet.get('status')!r}; expected one of {', '.join(sorted(allowed))}"
        )


def today() -> str:
    return date.today().isoformat()


def display_path(path: Path) -> Path:
    if not path.is_absolute():
        return path
    try:
        return path.relative_to(BASE)
    except ValueError:
        return path


def parse_date(value: str, field: str, path: Path, findings: list[Finding], *, required: bool = False) -> None:
    if not value:
        if required:
            findings.append(Finding("ERROR", path, f"{field} is required"))
        return
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        findings.append(Finding("ERROR", path, f"{field} must use YYYY-MM-DD; found {value!r}"))


def normalize_score(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    return value if "/" in value else f"{value}/10"


def read_csv(path: Path, expected_fields: list[str]) -> tuple[list[dict[str, str]], list[Finding]]:
    findings: list[Finding] = []
    if not path.exists():
        return [], [Finding("ERROR", path, "file does not exist")]

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected_fields:
            findings.append(
                Finding(
                    "ERROR",
                    path,
                    "header mismatch; expected "
                    + ",".join(expected_fields)
                    + " but found "
                    + ",".join(reader.fieldnames or []),
                )
            )
        rows: list[dict[str, str]] = []
        for index, row in enumerate(reader, start=2):
            if None in row:
                findings.append(Finding("ERROR", path, f"row {index} has extra CSV fields: {row[None]!r}"))
                row.pop(None, None)
            rows.append({field: row.get(field, "") or "" for field in expected_fields})
    return rows, findings


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", dir=path.parent, delete=False) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])
        tmp_path = Path(handle.name)
    os.replace(tmp_path, path)


def validate_job_log(rows: list[dict[str, str]]) -> list[Finding]:
    findings: list[Finding] = []
    seen_urls: dict[str, int] = {}
    seen_pairs: dict[tuple[str, str], int] = {}
    for index, row in enumerate(rows, start=2):
        row_id = f"row {index} ({row.get('company')} - {row.get('role')})"
        parse_date(row.get("search_date", ""), "search_date", JOB_LOG, findings, required=True)
        if row.get("track") not in TRACKS:
            findings.append(Finding("ERROR", JOB_LOG, f"{row_id}: invalid track {row.get('track')!r}"))
        if row.get("status") not in JOB_STATUSES:
            findings.append(Finding("ERROR", JOB_LOG, f"{row_id}: invalid status {row.get('status')!r}"))
        if row.get("decision_reason") not in DECISION_REASONS:
            findings.append(Finding("WARN", JOB_LOG, f"{row_id}: non-standard decision_reason {row.get('decision_reason')!r}"))
        if row.get("applied") not in YES_NO:
            findings.append(Finding("ERROR", JOB_LOG, f"{row_id}: applied must be Yes/No/blank"))
        if row.get("status") in {"Pursued", "Excluded", "Monitoring"} and not row.get("decision_reason"):
            findings.append(Finding("WARN", JOB_LOG, f"{row_id}: decision_reason should be filled"))

        url = row.get("jd_url", "")
        if url:
            if url in seen_urls:
                findings.append(Finding("WARN", JOB_LOG, f"{row_id}: duplicate jd_url also on row {seen_urls[url]}"))
            seen_urls[url] = index

        pair = (normalize(row.get("company")), normalize(row.get("role")))
        if all(pair):
            if pair in seen_pairs and row.get("status") != "Pursued":
                findings.append(Finding("WARN", JOB_LOG, f"{row_id}: duplicate company+role also on row {seen_pairs[pair]}"))
            seen_pairs[pair] = index
    return findings


def validate_tracker(rows: list[dict[str, str]], job_rows: list[dict[str, str]]) -> list[Finding]:
    findings: list[Finding] = []
    dates = [row.get("date", "") for row in rows]
    if dates != sorted(dates, reverse=True):
        findings.append(Finding("WARN", TRACKER, "rows are not sorted by descending date"))

    job_by_file = {row.get("resume_file", ""): row for row in job_rows if row.get("resume_file")}
    for index, row in enumerate(rows, start=2):
        row_id = f"row {index} ({row.get('company')} - {row.get('role')})"
        parse_date(row.get("date", ""), "date", TRACKER, findings, required=True)
        parse_date(row.get("last_reviewed_at", ""), "last_reviewed_at", TRACKER, findings)
        parse_date(row.get("application_deadline", ""), "application_deadline", TRACKER, findings)
        parse_date(row.get("follow_up_due", ""), "follow_up_due", TRACKER, findings)
        parse_date(row.get("last_follow_up_date", ""), "last_follow_up_date", TRACKER, findings)
        if row.get("track") not in TRACKS:
            findings.append(Finding("ERROR", TRACKER, f"{row_id}: invalid track {row.get('track')!r}"))
        if row.get("status") not in TRACKER_STATUSES:
            findings.append(Finding("ERROR", TRACKER, f"{row_id}: invalid status {row.get('status')!r}"))
        if row.get("review_status") not in REVIEW_STATUSES:
            findings.append(Finding("ERROR", TRACKER, f"{row_id}: invalid review_status {row.get('review_status')!r}"))
        if row.get("applied") not in YES_NO:
            findings.append(Finding("ERROR", TRACKER, f"{row_id}: applied must be Yes/No/blank"))
        if row.get("location_exception") not in YES_NO:
            findings.append(Finding("ERROR", TRACKER, f"{row_id}: location_exception must be Yes/No/blank"))
        if row.get("status") == "Resume Ready" and row.get("review_status") not in {
            "Passed",
            "Warning Accepted",
            "Legacy Unreviewed",
        }:
            findings.append(
                Finding(
                    "ERROR",
                    TRACKER,
                    f"{row_id}: Resume Ready requires Passed, Warning Accepted, or Legacy Unreviewed review_status",
                )
            )
        if row.get("status") == "Resume Ready" and row.get("review_status") == "Legacy Unreviewed":
            findings.append(Finding("WARN", TRACKER, f"{row_id}: legacy ready row predates the formal review gate"))
        if row.get("status") == "Applied" and row.get("applied") != "Yes":
            findings.append(Finding("ERROR", TRACKER, f"{row_id}: Applied status requires applied=Yes"))
        if row.get("review_status") in {"Passed", "Warning Accepted", "Failed"} and not row.get("last_reviewed_at"):
            findings.append(Finding("WARN", TRACKER, f"{row_id}: review_status is set but last_reviewed_at is blank"))
        if row.get("review_status") == "Warning Accepted" and not row.get("review_notes"):
            findings.append(Finding("WARN", TRACKER, f"{row_id}: Warning Accepted should name the accepted warning"))
        if row.get("location_exception") == "Yes" and not row.get("fitment_score", "").startswith(("9", "10")):
            findings.append(Finding("WARN", TRACKER, f"{row_id}: location_exception=Yes should be reserved for >8/10 fits"))

        job_row = job_by_file.get(row.get("output_file", ""))
        if job_row:
            expected_score = normalize_score(job_row.get("agent_score"))
            if expected_score and row.get("fitment_score") and row.get("fitment_score") != expected_score:
                findings.append(
                    Finding(
                        "WARN",
                        TRACKER,
                        f"{row_id}: fitment_score {row.get('fitment_score')!r} differs from job log {expected_score!r}",
                    )
                )
            if job_row.get("jd_url") and row.get("job_url") and row.get("job_url") != job_row.get("jd_url"):
                findings.append(Finding("WARN", TRACKER, f"{row_id}: job_url differs from job log jd_url"))
    return findings


def matching_queue_packets(company: str, role: str, output_file: str = "") -> list[dict]:
    matches: list[dict] = []
    for packet in queue_packets():
        if packet.get("_invalid_json"):
            continue
        output_matches = output_file and packet.get("build", {}).get("output_file") == output_file
        role_matches = normalize(packet.get("company")) == normalize(company) and normalize(packet.get("role")) == normalize(role)
        if output_matches or role_matches:
            matches.append(packet)
    return matches


def enforce_ready_queue_packet(company: str, role: str, output_file: str, *, legacy_no_queue: bool = False) -> None:
    matches = matching_queue_packets(company, role, output_file)
    if not matches:
        if legacy_no_queue:
            return
        raise SystemExit(
            "Tracker update is blocked because no matching ready queue packet exists. "
            "Run the queue workflow first, or pass --legacy-no-queue for an older/manual artifact."
        )
    if legacy_no_queue:
        return
    ready_matches = [
        packet
        for packet in matches
        if packet.get("status") == "ready" and packet.get("build", {}).get("output_file") == output_file
    ]
    if not ready_matches:
        statuses = ", ".join(f"{packet.get('role_id')}={packet.get('status')}" for packet in matches)
        raise SystemExit(
            "Tracker update is blocked because matching queue packet(s) are not ready "
            f"for {output_file!r}: {statuses}"
        )


def validate_queue(packets: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    building = [packet for packet in packets if packet.get("status") == "building"]
    if len(building) > 1:
        active = ", ".join(packet.get("role_id", "<missing>") for packet in building)
        findings.append(Finding("ERROR", RESUME_QUEUE, f"multiple packets occupy the serialized build slot: {active}"))

    seen_role_ids: set[str] = set()
    for packet in packets:
        path = packet.get("_path", RESUME_QUEUE)
        if packet.get("_invalid_json"):
            findings.append(Finding("ERROR", path, f"invalid queue JSON: {packet['_invalid_json']}"))
            continue
        role_id_value = packet.get("role_id", "")
        status = packet.get("status", "")
        if not role_id_value:
            findings.append(Finding("ERROR", path, "role_id is required"))
        elif role_id_value in seen_role_ids:
            findings.append(Finding("ERROR", path, f"duplicate queue role_id {role_id_value!r}"))
        seen_role_ids.add(role_id_value)

        if status not in QUEUE_STATUSES:
            findings.append(Finding("ERROR", path, f"{role_id_value}: invalid queue status {status!r}"))
            continue
        if not packet.get("company") or not packet.get("role"):
            findings.append(Finding("ERROR", path, f"{role_id_value}: company and role are required"))
        if packet.get("track") not in MASTER_BY_TRACK:
            findings.append(Finding("ERROR", path, f"{role_id_value}: invalid track {packet.get('track')!r}"))

        gate = packet.get("gate", {})
        proposal = packet.get("proposal", {})
        approval = packet.get("approval", {})
        build = packet.get("build", {})
        failure = packet.get("failure")

        if status in {"master_recommended", "gate_checked", "proposed", "approved", "building", "ready"}:
            if not gate.get("master_resume_checked") or gate.get("gate_decision") not in GATE_DECISIONS:
                findings.append(Finding("ERROR", path, f"{role_id_value}: status {status} requires a completed master gate"))
        if status in {"proposed", "approved", "building", "ready"}:
            if not proposal.get("proposal_ready_for_user") or not proposal.get("evidence_map"):
                findings.append(Finding("ERROR", path, f"{role_id_value}: status {status} requires an evidence-map proposal"))
        if status in {"approved", "building", "ready"}:
            if not approval.get("approval_after_evidence_map"):
                findings.append(Finding("ERROR", path, f"{role_id_value}: status {status} requires approval after evidence map"))
        if status in {"building", "ready"} and not build.get("output_file"):
            findings.append(Finding("WARN", path, f"{role_id_value}: {status} packet should record output_file"))
        if status == "ready":
            if build.get("mechanical_qa") not in {"Passed", "Warning Accepted"}:
                findings.append(Finding("ERROR", path, f"{role_id_value}: ready requires mechanical_qa Passed/Warning Accepted"))
            if build.get("final_critic") not in {"Passed", "Warning Accepted"}:
                findings.append(Finding("ERROR", path, f"{role_id_value}: ready requires final_critic Passed/Warning Accepted"))
            if "Warning Accepted" in {build.get("mechanical_qa"), build.get("final_critic")} and not build.get("notes"):
                findings.append(Finding("ERROR", path, f"{role_id_value}: accepted QA/critic warnings require notes"))
        if status == "failed":
            if not failure:
                findings.append(Finding("ERROR", path, f"{role_id_value}: failed packet requires failure metadata"))
            elif failure.get("retry_target") not in RETRY_TARGETS:
                findings.append(Finding("ERROR", path, f"{role_id_value}: invalid retry_target {failure.get('retry_target')!r}"))
        elif failure:
            findings.append(Finding("WARN", path, f"{role_id_value}: stale failure metadata should be moved to failure_history"))

        if packet.get("feedback", {}).get("captured") and not packet.get("feedback", {}).get("signal_type"):
            findings.append(Finding("ERROR", path, f"{role_id_value}: captured feedback requires signal_type"))

    if RESUME_QUEUE == DEFAULT_RESUME_QUEUE and list(RESUME_QUEUE.glob("*.json")):
        findings.append(
            Finding(
                "WARN",
                RESUME_QUEUE,
                "sample queue contains JSON packets; keep real queue packets outside the public repo",
            )
        )
    return findings


def load_state() -> tuple[list[dict[str, str]], list[dict[str, str]], list[Finding]]:
    job_rows, job_findings = read_csv(JOB_LOG, JOB_LOG_FIELDS)
    tracker_rows, tracker_findings = read_csv(TRACKER, TRACKER_FIELDS)
    return job_rows, tracker_rows, job_findings + tracker_findings


def validate_state(args: argparse.Namespace) -> int:
    job_rows, tracker_rows, findings = load_state()
    findings.extend(validate_job_log(job_rows))
    findings.extend(validate_tracker(tracker_rows, job_rows))
    packets = queue_packets()
    findings.extend(validate_queue(packets))
    print_findings(findings)
    print(f"\nJob log rows: {len(job_rows)}")
    print(f"Tracker rows: {len(tracker_rows)}")
    print(f"Queue packets: {len(packets)}")
    errors = sum(1 for finding in findings if finding.severity == "ERROR")
    warnings = sum(1 for finding in findings if finding.severity == "WARN")
    print(f"Summary: {errors} error(s), {warnings} warning(s)")
    if args.strict:
        return 1 if findings else 0
    return 1 if errors else 0


def validate_queue_command(args: argparse.Namespace) -> int:
    packets = queue_packets()
    findings = validate_queue(packets)
    print_findings(findings)
    print(f"\nQueue packets: {len(packets)}")
    errors = sum(1 for finding in findings if finding.severity == "ERROR")
    warnings = sum(1 for finding in findings if finding.severity == "WARN")
    print(f"Summary: {errors} error(s), {warnings} warning(s)")
    if args.strict:
        return 1 if findings else 0
    return 1 if errors else 0


def sort_state(args: argparse.Namespace) -> int:
    with state_lock():
        job_rows, tracker_rows, findings = load_state()
        if any(finding.severity == "ERROR" for finding in findings):
            print_findings(findings)
            return 1
        tracker_rows.sort(key=lambda row: (row.get("date", ""), row.get("company", ""), row.get("role", "")), reverse=True)
        job_rows.sort(key=lambda row: (row.get("search_date", ""), row.get("company", ""), row.get("role", "")))
        write_csv(TRACKER, TRACKER_FIELDS, tracker_rows)
        write_csv(JOB_LOG, JOB_LOG_FIELDS, job_rows)
    print(f"Sorted {display_path(TRACKER)} and {display_path(JOB_LOG)}")
    return 0


def find_tracker_row(rows: list[dict[str, str]], *, output_file: str = "", company: str = "", role: str = "") -> dict[str, str]:
    if output_file:
        matches = [row for row in rows if row.get("output_file") == output_file]
    else:
        matches = [
            row
            for row in rows
            if normalize(row.get("company")) == normalize(company) and normalize(row.get("role")) == normalize(role)
        ]
    if not matches:
        raise SystemExit("No matching tracker row found")
    if len(matches) > 1:
        raise SystemExit("Multiple matching tracker rows found; use --output-file")
    return matches[0]


def find_job_row(rows: list[dict[str, str]], company: str, role: str) -> dict[str, str]:
    matches = [
        row
        for row in rows
        if normalize(row.get("company")) == normalize(company) and normalize(row.get("role")) == normalize(role)
    ]
    if not matches:
        raise SystemExit("No matching job log row found")
    pursued = [row for row in matches if row.get("status") == "Pursued"]
    if len(pursued) == 1:
        return pursued[0]
    if len(matches) == 1:
        return matches[0]
    raise SystemExit("Multiple matching job log rows found; make the role title more exact")


def promote_role(args: argparse.Namespace) -> int:
    with state_lock():
        job_rows, tracker_rows, findings = load_state()
        if any(finding.severity == "ERROR" for finding in findings):
            print_findings(findings)
            return 1
        job_row = find_job_row(job_rows, args.company, args.role)
        if job_row.get("status") not in {"Pursued", "Monitoring"}:
            raise SystemExit(f"Job log status is {job_row.get('status')!r}; only Pursued/Monitoring roles can be promoted")
        if any(row.get("output_file") == args.output_file for row in tracker_rows):
            raise SystemExit(f"Tracker already has output_file {args.output_file!r}")
        enforce_ready_queue_packet(
            job_row.get("company", ""),
            job_row.get("role", ""),
            args.output_file,
            legacy_no_queue=args.legacy_no_queue,
        )

        tracker_rows.append(
            {
                "date": args.date or today(),
                "company": job_row.get("company", ""),
                "role": job_row.get("role", ""),
                "track": job_row.get("track", ""),
                "fitment_score": normalize_score(job_row.get("agent_score")),
                "location_type": job_row.get("location_type", ""),
                "location_exception": args.location_exception,
                "output_file": args.output_file,
                "tier1_coverage_pct": str(args.tier1),
                "tier2_coverage_pct": str(args.tier2),
                "applied": "No",
                "status": "Draft Built",
                "review_status": "",
                "last_reviewed_at": "",
                "review_notes": "",
                "notes": job_row.get("notes", ""),
                "application_deadline": args.application_deadline or "",
                "follow_up_due": "",
                "follow_up_count": "0",
                "last_follow_up_date": "",
                "job_url": job_row.get("jd_url", ""),
            }
        )
        job_row["resume_file"] = args.output_file
        if args.legacy_no_queue:
            job_row["decision_reason"] = "Built before strict gate"
        if job_row.get("status") == "Monitoring":
            job_row["status"] = "Pursued"
        tracker_rows.sort(key=lambda row: (row.get("date", ""), row.get("company", ""), row.get("role", "")), reverse=True)
        write_csv(TRACKER, TRACKER_FIELDS, tracker_rows)
        write_csv(JOB_LOG, JOB_LOG_FIELDS, job_rows)
    print(f"Promoted {job_row.get('company')} - {job_row.get('role')} to Draft Built")
    return 0


def mark_review_needed(args: argparse.Namespace) -> int:
    with state_lock():
        _, tracker_rows, findings = load_state()
        if any(finding.severity == "ERROR" for finding in findings):
            print_findings(findings)
            return 1
        row = find_tracker_row(tracker_rows, output_file=args.output_file, company=args.company, role=args.role)
        if row.get("status") not in {"Draft Built", "Review Needed"}:
            raise SystemExit(f"Cannot mark review needed from status {row.get('status')!r}")
        row["status"] = "Review Needed"
        row["review_status"] = "Pending"
        write_csv(TRACKER, TRACKER_FIELDS, tracker_rows)
    print(f"Marked Review Needed: {row.get('company')} - {row.get('role')}")
    return 0


def mark_ready(args: argparse.Namespace) -> int:
    with state_lock():
        _, tracker_rows, findings = load_state()
        if any(finding.severity == "ERROR" for finding in findings):
            print_findings(findings)
            return 1
        if args.review_status not in {"Passed", "Warning Accepted"}:
            raise SystemExit("--review-status must be Passed or Warning Accepted")
        if args.review_status == "Warning Accepted" and not args.review_notes:
            raise SystemExit("--review-notes is required when accepting warnings")
        row = find_tracker_row(tracker_rows, output_file=args.output_file, company=args.company, role=args.role)
        if row.get("status") not in {"Draft Built", "Review Needed", "Resume Ready"}:
            raise SystemExit(f"Cannot mark ready from status {row.get('status')!r}")
        enforce_ready_queue_packet(
            row.get("company", ""),
            row.get("role", ""),
            row.get("output_file", ""),
            legacy_no_queue=args.legacy_no_queue,
        )
        row["status"] = "Resume Ready"
        row["review_status"] = args.review_status
        row["last_reviewed_at"] = args.reviewed_at or today()
        row["review_notes"] = args.review_notes or "Validation and whole-resume review passed."
        if args.legacy_no_queue:
            row["notes"] = (row.get("notes", "") + " Legacy no-queue readiness override.").strip()
        write_csv(TRACKER, TRACKER_FIELDS, tracker_rows)
    print(f"Marked Resume Ready: {row.get('company')} - {row.get('role')}")
    return 0


def mark_applied(args: argparse.Namespace) -> int:
    with state_lock():
        job_rows, tracker_rows, findings = load_state()
        if any(finding.severity == "ERROR" for finding in findings):
            print_findings(findings)
            return 1
        row = find_tracker_row(tracker_rows, output_file=args.output_file, company=args.company, role=args.role)
        if row.get("status") not in {"Resume Ready", "Applied"}:
            raise SystemExit(f"Cannot mark applied from status {row.get('status')!r}; mark Resume Ready first")
        applied_date = args.applied_date or today()
        parse_check: list[Finding] = []
        parse_date(applied_date, "applied_date", TRACKER, parse_check, required=True)
        if parse_check:
            print_findings(parse_check)
            return 1
        due_date = datetime.strptime(applied_date, "%Y-%m-%d").date() + timedelta(days=args.follow_up_days)
        row["date"] = applied_date
        row["applied"] = "Yes"
        row["status"] = "Applied"
        row["follow_up_due"] = due_date.isoformat()
        row["follow_up_count"] = row.get("follow_up_count") or "0"
        for job_row in job_rows:
            if job_row.get("resume_file") == row.get("output_file"):
                job_row["applied"] = "Yes"
                job_row["status"] = "Applied"
        tracker_rows.sort(key=lambda item: (item.get("date", ""), item.get("company", ""), item.get("role", "")), reverse=True)
        write_csv(TRACKER, TRACKER_FIELDS, tracker_rows)
        write_csv(JOB_LOG, JOB_LOG_FIELDS, job_rows)
    print(f"Marked Applied: {row.get('company')} - {row.get('role')} (follow-up due {row['follow_up_due']})")
    return 0


def queue_add(args: argparse.Namespace) -> int:
    with queue_lock():
        new_role_id = args.role_id or role_id(args.company, args.role)
        path = queue_path(new_role_id)
        if path.exists():
            raise SystemExit(f"Queue packet already exists: {display_path(path)}")
        if args.track not in MASTER_BY_TRACK:
            raise SystemExit(f"Unsupported track {args.track!r}")
        packet = {
            "role_id": new_role_id,
            "company": args.company,
            "role": args.role,
            "jd_url": args.jd_url or "",
            "track": args.track,
            "location_type": args.location_type or "",
            "location_city": args.location_city or "",
            "status": "pending_gate",
            "created_at": today(),
            "updated_at": today(),
            "master_resume_path": MASTER_BY_TRACK[args.track],
            "gate": {},
            "proposal": {},
            "approval": {},
            "build": {},
            "feedback": {},
            "history": [
                {
                    "date": today(),
                    "event": "queued",
                    "note": "Role queued for master-resume gate.",
                }
            ],
        }
        write_packet(packet)
    print(f"Queued role {new_role_id}: {args.company} - {args.role}")
    print(f"Next: career-ops --resume-queue {display_path(RESUME_QUEUE)} queue-gate --role-id {new_role_id} ...")
    return 0


def queue_gate(args: argparse.Namespace) -> int:
    with queue_lock():
        packet = load_packet(args.role_id)
        assert_status(packet, {"pending_gate", "master_recommended", "gate_checked"})
        if args.requirement_intensity > 7 and args.gate_decision == "use_master_as_is":
            raise SystemExit("use_master_as_is is inconsistent with requirement intensity above 7")
        if args.requirement_intensity <= 7 and args.gate_decision == "customization_needed" and not args.user_approved_tailoring:
            raise SystemExit(
                "customization_needed with intensity <= 7 requires --user-approved-tailoring after recommending the master"
            )
        if len(args.reason.split()) < 8:
            raise SystemExit("--reason must explain the gate decision with at least 8 words")

        packet["gate"] = {
            "master_resume_checked": True,
            "master_resume_path": packet.get("master_resume_path", ""),
            "requirement_intensity": args.requirement_intensity,
            "gate_decision": args.gate_decision,
            "reason": args.reason,
            "next_action": args.next_action,
        }
        packet["proposal"] = {}
        packet["approval"] = {}
        packet["build"] = {}
        packet["status"] = "master_recommended" if args.gate_decision == "use_master_as_is" else "gate_checked"
        packet.setdefault("history", []).append({"date": today(), "event": "gate_checked", "note": args.reason})
        write_packet(packet)
    print(f"Gate recorded for {args.role_id}: {args.gate_decision}")
    if packet["status"] == "master_recommended":
        print("Stop before tailoring unless the user explicitly approves customization anyway.")
    else:
        print("Next: run achievement-bank scan and record proposal with queue-propose.")
    return 0


def queue_propose(args: argparse.Namespace) -> int:
    with queue_lock():
        packet = load_packet(args.role_id)
        assert_status(packet, {"gate_checked", "proposed"})
        gate = packet.get("gate", {})
        if gate.get("gate_decision") != "customization_needed":
            raise SystemExit("queue-propose requires gate_decision=customization_needed")
        if len(args.evidence_map.split()) < 8:
            raise SystemExit("--evidence-map must summarize JD-to-achievement mapping")
        if len(args.proposed_changes.split()) < 8:
            raise SystemExit("--proposed-changes must describe concrete master-vs-tailored changes")

        packet["proposal"] = {
            "evidence_map": args.evidence_map,
            "proposed_changes": args.proposed_changes,
            "honest_gaps": args.honest_gaps or "",
            "claims_to_avoid": args.claims_to_avoid or "",
            "proposal_ready_for_user": True,
        }
        packet["approval"] = {}
        packet["build"] = {}
        packet["status"] = "proposed"
        packet.setdefault("history", []).append({"date": today(), "event": "proposal_recorded", "note": args.proposed_changes})
        write_packet(packet)
    print(f"Proposal recorded for {args.role_id}. Next: queue-approve after user approval.")
    return 0


def queue_approve(args: argparse.Namespace) -> int:
    with queue_lock():
        packet = load_packet(args.role_id)
        assert_status(packet, {"proposed", "approved"})
        if len(args.approval_note.split()) < 8:
            raise SystemExit("--approval-note must capture user approval or mapping direction")
        packet["approval"] = {
            "approved_by": args.approved_by,
            "approved_at": args.approved_at or today(),
            "evidence_map_presented_to_user": True,
            "approval_after_evidence_map": True,
            "approval_note": args.approval_note,
        }
        packet["build"] = {}
        packet["status"] = "approved"
        packet.setdefault("history", []).append({"date": today(), "event": "approved", "note": args.approval_note})
        write_packet(packet)
    print(f"Approved {args.role_id}. Next: queue-start-build when the serialized build slot is free.")
    return 0


def queue_start_build(args: argparse.Namespace) -> int:
    with queue_lock():
        packet = load_packet(args.role_id)
        assert_status(packet, {"approved"})
        active = [item for item in queue_packets() if item.get("status") == "building" and item.get("role_id") != args.role_id]
        if active:
            active_ids = ", ".join(item.get("role_id", "") for item in active)
            raise SystemExit(f"Build slot is already occupied by: {active_ids}")
        if packet.get("failure"):
            raise SystemExit("Cannot build while failure metadata is present; run queue-retry and repair the target step first")
        if not packet.get("approval", {}).get("approval_after_evidence_map"):
            raise SystemExit("Cannot build before approval_after_evidence_map=true")
        packet["status"] = "building"
        packet["build"] = {
            "started_at": args.started_at or today(),
            "output_file": args.output_file or "",
            "build_owner": args.build_owner,
            "serialized_build_slot": True,
        }
        packet.setdefault("history", []).append({"date": today(), "event": "build_started", "note": args.output_file or ""})
        write_packet(packet)
    print(f"Build started for {args.role_id}. No other packet can enter building until this completes or fails.")
    return 0


def queue_complete_build(args: argparse.Namespace) -> int:
    with queue_lock():
        packet = load_packet(args.role_id)
        assert_status(packet, {"building", "ready"})
        if "Warning Accepted" in {args.mechanical_qa, args.final_critic} and not args.notes:
            raise SystemExit("--notes is required when accepting mechanical QA or final critic warnings")
        packet["status"] = "ready"
        packet.setdefault("build", {}).update(
            {
                "completed_at": args.completed_at or today(),
                "output_file": args.output_file,
                "mechanical_qa": args.mechanical_qa,
                "final_critic": args.final_critic,
                "notes": args.notes or "",
            }
        )
        packet.setdefault("history", []).append(
            {"date": today(), "event": "build_completed", "note": f"{args.output_file}; {args.final_critic}"}
        )
        write_packet(packet)
    print(f"Build completed for {args.role_id}: {args.output_file}")
    print("Next: promote/mark tracker state with the normal career-ops lifecycle commands.")
    return 0


def queue_fail(args: argparse.Namespace) -> int:
    with queue_lock():
        packet = load_packet(args.role_id)
        assert_status(packet, {"building", "proposed", "approved", "failed"})
        if len(args.reason.split()) < 6:
            raise SystemExit("--reason must explain the failure")
        packet["status"] = "failed"
        packet["failure"] = {
            "failed_at": args.failed_at or today(),
            "stage": args.stage,
            "reason": args.reason,
            "retry_target": args.retry_target,
        }
        packet.setdefault("history", []).append(
            {"date": today(), "event": "failed", "note": f"{args.stage}: {args.reason}; retry {args.retry_target}"}
        )
        write_packet(packet)
    print(f"Marked failed: {args.role_id}. Retry target: {args.retry_target}")
    return 0


def queue_retry(args: argparse.Namespace) -> int:
    with queue_lock():
        packet = load_packet(args.role_id)
        assert_status(packet, {"failed"})
        failure = packet.get("failure") or {}
        retry_target = failure.get("retry_target")
        if retry_target not in RETRY_TARGETS:
            raise SystemExit("Failed packet has no valid retry_target")
        if args.retry_target and args.retry_target != retry_target:
            raise SystemExit(f"Failure retry_target is {retry_target!r}; cannot retry as {args.retry_target!r}")

        packet.setdefault("failure_history", []).append(failure)
        packet.pop("failure", None)
        if retry_target == "master_check":
            packet["status"] = "pending_gate"
            packet["gate"] = {}
            packet["proposal"] = {}
            packet["approval"] = {}
            packet["build"] = {}
            next_step = "queue-gate"
        elif retry_target == "evidence_map":
            packet["status"] = "gate_checked"
            packet["proposal"] = {}
            packet["approval"] = {}
            packet["build"] = {}
            next_step = "queue-propose"
        elif retry_target == "human_approval":
            packet["status"] = "proposed"
            packet["approval"] = {}
            packet["build"] = {}
            next_step = "queue-approve"
        else:
            packet["status"] = "approved"
            packet["build"] = {}
            next_step = "queue-start-build"

        packet.setdefault("history", []).append(
            {"date": today(), "event": "retry_opened", "note": f"Returned to {retry_target}: {args.note or ''}".strip()}
        )
        write_packet(packet)
    print(f"Retry opened for {args.role_id}: {retry_target}. Next: {next_step}.")
    return 0


def queue_feedback(args: argparse.Namespace) -> int:
    with queue_lock():
        packet = load_packet(args.role_id)
        assert_status(packet, {"master_recommended", "approved", "ready", "failed", "archived"})
        if len(args.note.split()) < 6:
            raise SystemExit("--note must capture the feedback signal with at least 6 words")
        feedback = {
            "captured": True,
            "captured_at": args.captured_at or today(),
            "signal_type": args.signal_type,
            "note": args.note,
            "manual_edits": args.manual_edits or "",
            "rejected_items": args.rejected_items or "",
            "accepted_warnings": args.accepted_warnings or "",
            "applied_signal": args.applied_signal or "",
            "feeds_future_evidence_selection": True,
        }
        packet["feedback"] = feedback
        packet.setdefault("learning_memory", []).append(
            {
                "date": feedback["captured_at"],
                "signal_type": args.signal_type,
                "note": args.note,
            }
        )
        packet.setdefault("history", []).append({"date": today(), "event": "feedback_captured", "note": args.note})
        write_packet(packet)
        append_feedback_log(
            {
                "role_id": args.role_id,
                "company": packet.get("company", ""),
                "role": packet.get("role", ""),
                "captured_at": feedback["captured_at"],
                "signal_type": args.signal_type,
                "note": args.note,
            }
        )
    print(f"Feedback captured for {args.role_id}; future evidence maps should use this signal.")
    return 0


def queue_archive(args: argparse.Namespace) -> int:
    with queue_lock():
        packet = load_packet(args.role_id)
        assert_status(packet, {"master_recommended", "ready", "failed", "archived"})
        if len(args.reason.split()) < 6:
            raise SystemExit("--reason must explain why this packet is being archived")
        packet["status"] = "archived"
        if packet.get("failure"):
            packet.setdefault("failure_history", []).append(packet["failure"])
            packet.pop("failure", None)
        packet.setdefault("archive", {}).update(
            {
                "archived_at": args.archived_at or today(),
                "reason": args.reason,
            }
        )
        packet.setdefault("history", []).append({"date": today(), "event": "archived", "note": args.reason})
        write_packet(packet)
    print(f"Archived queue packet: {args.role_id}")
    return 0


def queue_status(args: argparse.Namespace) -> int:
    packets = queue_packets()
    if args.role_id:
        packets = [packet for packet in packets if packet.get("role_id") == args.role_id]
    if not packets:
        print("No queue packets found.")
        return 0
    for packet in packets:
        if packet.get("_invalid_json"):
            print(f"{display_path(packet.get('_path', RESUME_QUEUE))} | invalid_json | {packet.get('_invalid_json')}")
            continue
        print(
            f"{packet.get('role_id')} | {packet.get('status')} | "
            f"{packet.get('company')} - {packet.get('role')} | updated {packet.get('updated_at')}"
        )
    active = [packet.get("role_id") for packet in packets if packet.get("status") == "building"]
    if active:
        print(f"\nSerialized build slot occupied by: {', '.join(active)}")
    return 0


def print_findings(findings: list[Finding]) -> None:
    if not findings:
        print("[PASS] career ops state is valid")
        return
    for finding in findings:
        print(f"{finding.severity}: {display_path(finding.path)}: {finding.message}")


def add_common_match_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output-file")
    group.add_argument("--company")
    parser.add_argument("--role", help="Required when matching by --company")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--job-log",
        type=Path,
        default=DEFAULT_JOB_LOG,
        help="Path to the job-search log CSV",
    )
    parser.add_argument(
        "--tracker",
        type=Path,
        default=DEFAULT_TRACKER,
        help="Path to the application tracker CSV",
    )
    parser.add_argument(
        "--resume-queue",
        type=Path,
        default=DEFAULT_RESUME_QUEUE,
        help="Directory for resume orchestration queue packets",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-state", help="Validate tracker/log schemas and lifecycle invariants")
    validate.add_argument("--strict", action="store_true", help="Treat warnings as a non-zero exit")
    validate.set_defaults(func=validate_state)

    validate_queue_parser = subparsers.add_parser("validate-queue", help="Validate resume orchestration queue packets")
    validate_queue_parser.add_argument("--strict", action="store_true", help="Treat warnings as a non-zero exit")
    validate_queue_parser.set_defaults(func=validate_queue_command)

    sort = subparsers.add_parser("sort", help="Sort tracker descending by date and job log ascending by search date")
    sort.set_defaults(func=sort_state)

    promote = subparsers.add_parser("promote-role", help="Create a Draft Built tracker row from a job log row")
    promote.add_argument("--company", required=True)
    promote.add_argument("--role", required=True)
    promote.add_argument("--output-file", required=True)
    promote.add_argument("--tier1", required=True, type=int)
    promote.add_argument("--tier2", required=True, type=int)
    promote.add_argument("--date")
    promote.add_argument("--location-exception", choices=["", "Yes", "No"], default="No")
    promote.add_argument("--application-deadline")
    promote.add_argument(
        "--legacy-no-queue",
        action="store_true",
        help="Bypass the ready queue-packet requirement for older/manual artifacts",
    )
    promote.set_defaults(func=promote_role)

    review_needed = subparsers.add_parser("mark-review-needed", help="Move a tracker row to Review Needed")
    add_common_match_args(review_needed)
    review_needed.set_defaults(func=mark_review_needed)

    ready = subparsers.add_parser("mark-ready", help="Move a tracker row to Resume Ready after review")
    add_common_match_args(ready)
    ready.add_argument("--review-status", required=True, choices=["Passed", "Warning Accepted"])
    ready.add_argument("--review-notes", default="")
    ready.add_argument("--reviewed-at")
    ready.add_argument(
        "--legacy-no-queue",
        action="store_true",
        help="Bypass the ready queue-packet requirement for older/manual artifacts",
    )
    ready.set_defaults(func=mark_ready)

    applied = subparsers.add_parser("mark-applied", help="Mark tracker and job log rows as applied")
    add_common_match_args(applied)
    applied.add_argument("--applied-date")
    applied.add_argument("--follow-up-days", type=int, default=7)
    applied.set_defaults(func=mark_applied)

    queue_add_parser = subparsers.add_parser("queue-add", help="Add a role to the resume orchestration queue")
    queue_add_parser.add_argument("--company", required=True)
    queue_add_parser.add_argument("--role", required=True)
    queue_add_parser.add_argument("--track", required=True, choices=sorted(MASTER_BY_TRACK))
    queue_add_parser.add_argument("--jd-url", default="")
    queue_add_parser.add_argument("--location-type", default="")
    queue_add_parser.add_argument("--location-city", default="")
    queue_add_parser.add_argument("--role-id")
    queue_add_parser.set_defaults(func=queue_add)

    queue_gate_parser = subparsers.add_parser("queue-gate", help="Record the master-resume customization gate")
    queue_gate_parser.add_argument("--role-id", required=True)
    queue_gate_parser.add_argument("--requirement-intensity", required=True, type=int, choices=range(1, 11))
    queue_gate_parser.add_argument("--gate-decision", required=True, choices=sorted(GATE_DECISIONS))
    queue_gate_parser.add_argument("--reason", required=True)
    queue_gate_parser.add_argument("--next-action", required=True)
    queue_gate_parser.add_argument(
        "--user-approved-tailoring",
        action="store_true",
        help="Allow tailoring after a low-intensity gate only when the user explicitly asked to customize anyway",
    )
    queue_gate_parser.set_defaults(func=queue_gate)

    queue_propose_parser = subparsers.add_parser("queue-propose", help="Record the evidence map and proposed customization")
    queue_propose_parser.add_argument("--role-id", required=True)
    queue_propose_parser.add_argument("--evidence-map", required=True)
    queue_propose_parser.add_argument("--proposed-changes", required=True)
    queue_propose_parser.add_argument("--honest-gaps", default="")
    queue_propose_parser.add_argument("--claims-to-avoid", default="")
    queue_propose_parser.set_defaults(func=queue_propose)

    queue_approve_parser = subparsers.add_parser("queue-approve", help="Record user approval after evidence mapping")
    queue_approve_parser.add_argument("--role-id", required=True)
    queue_approve_parser.add_argument("--approval-note", required=True)
    queue_approve_parser.add_argument("--approved-by", default="Ashish")
    queue_approve_parser.add_argument("--approved-at")
    queue_approve_parser.set_defaults(func=queue_approve)

    queue_start_parser = subparsers.add_parser("queue-start-build", help="Enter the serialized build slot")
    queue_start_parser.add_argument("--role-id", required=True)
    queue_start_parser.add_argument("--output-file", default="")
    queue_start_parser.add_argument("--build-owner", default="build-agent")
    queue_start_parser.add_argument("--started-at")
    queue_start_parser.set_defaults(func=queue_start_build)

    queue_complete_parser = subparsers.add_parser("queue-complete-build", help="Mark a queued build as ready")
    queue_complete_parser.add_argument("--role-id", required=True)
    queue_complete_parser.add_argument("--output-file", required=True)
    queue_complete_parser.add_argument("--mechanical-qa", required=True, choices=["Passed", "Warning Accepted"])
    queue_complete_parser.add_argument("--final-critic", required=True, choices=["Passed", "Warning Accepted"])
    queue_complete_parser.add_argument("--notes", default="")
    queue_complete_parser.add_argument("--completed-at")
    queue_complete_parser.set_defaults(func=queue_complete_build)

    queue_fail_parser = subparsers.add_parser("queue-fail", help="Mark a queued role as failed with a retry target")
    queue_fail_parser.add_argument("--role-id", required=True)
    queue_fail_parser.add_argument("--stage", required=True, choices=sorted(BUILD_STAGES))
    queue_fail_parser.add_argument("--reason", required=True)
    queue_fail_parser.add_argument("--retry-target", required=True, choices=sorted(RETRY_TARGETS))
    queue_fail_parser.add_argument("--failed-at")
    queue_fail_parser.set_defaults(func=queue_fail)

    queue_retry_parser = subparsers.add_parser("queue-retry", help="Open the required retry path after a queue failure")
    queue_retry_parser.add_argument("--role-id", required=True)
    queue_retry_parser.add_argument("--retry-target", choices=sorted(RETRY_TARGETS))
    queue_retry_parser.add_argument("--note", default="")
    queue_retry_parser.set_defaults(func=queue_retry)

    queue_feedback_parser = subparsers.add_parser("queue-feedback", help="Capture review/application feedback for future evidence selection")
    queue_feedback_parser.add_argument("--role-id", required=True)
    queue_feedback_parser.add_argument(
        "--signal-type",
        required=True,
        choices=["approval", "manual_edit", "rejected_item", "accepted_warning", "applied", "rejected_application"],
    )
    queue_feedback_parser.add_argument("--note", required=True)
    queue_feedback_parser.add_argument("--manual-edits", default="")
    queue_feedback_parser.add_argument("--rejected-items", default="")
    queue_feedback_parser.add_argument("--accepted-warnings", default="")
    queue_feedback_parser.add_argument("--applied-signal", default="")
    queue_feedback_parser.add_argument("--captured-at")
    queue_feedback_parser.set_defaults(func=queue_feedback)

    queue_archive_parser = subparsers.add_parser("queue-archive", help="Archive a terminal queue packet")
    queue_archive_parser.add_argument("--role-id", required=True)
    queue_archive_parser.add_argument("--reason", required=True)
    queue_archive_parser.add_argument("--archived-at")
    queue_archive_parser.set_defaults(func=queue_archive)

    queue_status_parser = subparsers.add_parser("queue-status", help="List resume orchestration queue packets")
    queue_status_parser.add_argument("--role-id")
    queue_status_parser.set_defaults(func=queue_status)

    args = parser.parse_args()
    if getattr(args, "company", None) and not getattr(args, "role", None) and args.command != "promote-role":
        parser.error("--role is required when matching by --company")
    return args


def main() -> int:
    global JOB_LOG, TRACKER, RESUME_QUEUE
    args = parse_args()
    JOB_LOG = args.job_log
    TRACKER = args.tracker
    RESUME_QUEUE = args.resume_queue
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
