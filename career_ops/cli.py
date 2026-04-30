"""Career operations CLI for a job-search tracker and application log.

This script is the controlled state layer around:
- data/job_search_log.csv
- data/application_tracker.csv

It keeps the visible CSV workflow intact while enforcing schemas, sorting,
status transitions, and review/application bookkeeping.

Examples:
    python3 -B scripts/career_ops.py validate-state
    python3 -B scripts/career_ops.py sort
    python3 -B scripts/career_ops.py promote-role --company Sweed --role "Product Analytics Lead" --output-file Ashish_Gupta_Silla_Sweed_v1.docx --tier1 93 --tier2 86
    python3 -B scripts/career_ops.py mark-review-needed --output-file Ashish_Gupta_Silla_Sweed_v1.docx
    python3 -B scripts/career_ops.py mark-ready --output-file Ashish_Gupta_Silla_Sweed_v1.docx --review-status "Warning Accepted" --review-notes "Dense skills line accepted."
    python3 -B scripts/career_ops.py mark-applied --output-file Ashish_Gupta_Silla_Sweed_v1.docx --applied-date 2026-04-27
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
JOB_LOG = BASE / "data" / "job_search_log.csv"
TRACKER = BASE / "data" / "application_tracker.csv"

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


@dataclass
class Finding:
    severity: str
    path: Path
    message: str


def normalize(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def today() -> str:
    return date.today().isoformat()


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
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


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


def load_state() -> tuple[list[dict[str, str]], list[dict[str, str]], list[Finding]]:
    job_rows, job_findings = read_csv(JOB_LOG, JOB_LOG_FIELDS)
    tracker_rows, tracker_findings = read_csv(TRACKER, TRACKER_FIELDS)
    return job_rows, tracker_rows, job_findings + tracker_findings


def validate_state(args: argparse.Namespace) -> int:
    job_rows, tracker_rows, findings = load_state()
    findings.extend(validate_job_log(job_rows))
    findings.extend(validate_tracker(tracker_rows, job_rows))
    print_findings(findings)
    print(f"\nJob log rows: {len(job_rows)}")
    print(f"Tracker rows: {len(tracker_rows)}")
    errors = sum(1 for finding in findings if finding.severity == "ERROR")
    warnings = sum(1 for finding in findings if finding.severity == "WARN")
    print(f"Summary: {errors} error(s), {warnings} warning(s)")
    if args.strict:
        return 1 if findings else 0
    return 1 if errors else 0


def sort_state(args: argparse.Namespace) -> int:
    job_rows, tracker_rows, findings = load_state()
    if any(finding.severity == "ERROR" for finding in findings):
        print_findings(findings)
        return 1
    tracker_rows.sort(key=lambda row: (row.get("date", ""), row.get("company", ""), row.get("role", "")), reverse=True)
    job_rows.sort(key=lambda row: (row.get("search_date", ""), row.get("company", ""), row.get("role", "")))
    write_csv(TRACKER, TRACKER_FIELDS, tracker_rows)
    write_csv(JOB_LOG, JOB_LOG_FIELDS, job_rows)
    print(f"Sorted {TRACKER.relative_to(BASE)} and {JOB_LOG.relative_to(BASE)}")
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
    job_rows, tracker_rows, findings = load_state()
    if any(finding.severity == "ERROR" for finding in findings):
        print_findings(findings)
        return 1
    job_row = find_job_row(job_rows, args.company, args.role)
    if job_row.get("status") not in {"Pursued", "Monitoring"}:
        raise SystemExit(f"Job log status is {job_row.get('status')!r}; only Pursued/Monitoring roles can be promoted")
    if any(row.get("output_file") == args.output_file for row in tracker_rows):
        raise SystemExit(f"Tracker already has output_file {args.output_file!r}")

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
    if job_row.get("status") == "Monitoring":
        job_row["status"] = "Pursued"
    tracker_rows.sort(key=lambda row: (row.get("date", ""), row.get("company", ""), row.get("role", "")), reverse=True)
    write_csv(TRACKER, TRACKER_FIELDS, tracker_rows)
    write_csv(JOB_LOG, JOB_LOG_FIELDS, job_rows)
    print(f"Promoted {job_row.get('company')} - {job_row.get('role')} to Draft Built")
    return 0


def mark_review_needed(args: argparse.Namespace) -> int:
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
    row["status"] = "Resume Ready"
    row["review_status"] = args.review_status
    row["last_reviewed_at"] = args.reviewed_at or today()
    row["review_notes"] = args.review_notes or "Validation and whole-resume review passed."
    write_csv(TRACKER, TRACKER_FIELDS, tracker_rows)
    print(f"Marked Resume Ready: {row.get('company')} - {row.get('role')}")
    return 0


def mark_applied(args: argparse.Namespace) -> int:
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


def print_findings(findings: list[Finding]) -> None:
    if not findings:
        print("[PASS] career ops state is valid")
        return
    for finding in findings:
        rel = finding.path.relative_to(BASE) if finding.path.is_absolute() else finding.path
        print(f"{finding.severity}: {rel}: {finding.message}")


def add_common_match_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output-file")
    group.add_argument("--company")
    parser.add_argument("--role", help="Required when matching by --company")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-state", help="Validate tracker/log schemas and lifecycle invariants")
    validate.add_argument("--strict", action="store_true", help="Treat warnings as a non-zero exit")
    validate.set_defaults(func=validate_state)

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
    promote.set_defaults(func=promote_role)

    review_needed = subparsers.add_parser("mark-review-needed", help="Move a tracker row to Review Needed")
    add_common_match_args(review_needed)
    review_needed.set_defaults(func=mark_review_needed)

    ready = subparsers.add_parser("mark-ready", help="Move a tracker row to Resume Ready after review")
    add_common_match_args(ready)
    ready.add_argument("--review-status", required=True, choices=["Passed", "Warning Accepted"])
    ready.add_argument("--review-notes", default="")
    ready.add_argument("--reviewed-at")
    ready.set_defaults(func=mark_ready)

    applied = subparsers.add_parser("mark-applied", help="Mark tracker and job log rows as applied")
    add_common_match_args(applied)
    applied.add_argument("--applied-date")
    applied.add_argument("--follow-up-days", type=int, default=7)
    applied.set_defaults(func=mark_applied)

    args = parser.parse_args()
    if getattr(args, "company", None) and not getattr(args, "role", None) and args.command != "promote-role":
        parser.error("--role is required when matching by --company")
    return args


def main() -> int:
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
