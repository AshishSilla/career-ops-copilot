# Career Ops Workflow

Career Ops Copilot models a job search as a controlled workflow with two CSV-backed state files:

- `data/sample_job_search_log.csv` stores researched roles, fit scores, decisions, and notes.
- `data/sample_application_tracker.csv` stores active resume/application work, review status, application dates, and follow-up tracking.

The sample files are anonymized demo data. For real usage, keep private CSVs outside the repository and pass them with `--job-log` and `--tracker`.

The resume orchestration queue is stored as JSON packets under `data/sample_resume_queue/` by default for public-safe demos. For real usage, keep private queue packets outside the repository and pass them with `--resume-queue`. Generated sample queue JSON and queue feedback logs are ignored by Git so private evidence maps and approval notes are not accidentally committed.

## Lifecycle

```text
Researched role
  -> Monitoring / Pursued / Excluded
  -> Draft Built
  -> Review Needed
  -> Resume Ready
  -> Applied
  -> Follow-up due
```

## Stage 1: Research Roles

The job log is the broad funnel. It can include roles that are promising, weak fits, closed, location-constrained, or still under review.

Important fields:

- `company`
- `role`
- `jd_url`
- `location_type`
- `track`
- `agent_score`
- `status`
- `decision_reason`
- `notes`

Allowed job-log statuses:

- `Monitoring`
- `Pursued`
- `Excluded`
- `Applied`
- `Skipped`

## Stage 2: Promote Strong Roles

When a role is worth active resume work, promote it from the job log into the tracker:

```bash
career-ops promote-role \
  --company "Northstar CRM" \
  --role "Product Analytics Lead" \
  --output-file "Ashish_Product_Analytics_Northstar.docx" \
  --tier1 88 \
  --tier2 81 \
  --legacy-no-queue
```

This creates a `Draft Built` tracker row and links the resume file back to the job log. New resume builds should normally come from a `ready` queue packet; `--legacy-no-queue` is only for the bundled sample flow or older/manual artifacts.

## Stage 3: Review Before Applying

The review gate exists because AI-assisted resume writing can move quickly, but it still needs quality control.

Move a draft into review:

```bash
career-ops mark-review-needed \
  --output-file "Ashish_Product_Analytics_Northstar.docx"
```

Mark it ready only after review:

```bash
career-ops mark-ready \
  --output-file "Ashish_Product_Analytics_Northstar.docx" \
  --review-status "Passed" \
  --legacy-no-queue
```

If a known issue is acceptable, record it explicitly:

```bash
career-ops mark-ready \
  --output-file "Ashish_Product_Analytics_Northstar.docx" \
  --review-status "Warning Accepted" \
  --review-notes "Accepted minor tenure gap; stronger evidence exists in role-specific experience." \
  --legacy-no-queue
```

## Stage 4: Mark Applied and Track Follow-Up

Applications can only be marked submitted after the tracker row is `Resume Ready`.

```bash
career-ops mark-applied \
  --output-file "Ashish_Product_Analytics_Northstar.docx" \
  --applied-date 2026-04-30
```

The command updates both CSV files and creates a default follow-up date.

## Stage 5: Orchestrate Resume Builds

The queue layer models the resume architecture directly:

```text
pending_gate -> master_recommended -> queue-feedback event -> archived
pending_gate -> gate_checked -> proposed -> approved -> building -> ready -> queue-feedback event
                       ^             ^          ^            |
                       |             |          |            |
                       +-------------+----------+------------+
                          queue-retry returns to retry_target
```

Multiple roles can be in `pending_gate`, `gate_checked`, `proposed`, or `approved` at the same time. Only one role can be in `building`, because DOCX generation and tracker writes are serialized workflow steps. The build slot is protected with a queue-level lock and atomic packet writes so concurrent CLI processes cannot both claim the build slot. Tracker and job-log writes use a separate state lock with atomic CSV replacement.

Useful commands:

```bash
career-ops queue-add --company "Northstar CRM" --role "Product Analytics Lead" --track A
career-ops queue-gate --role-id northstar-crm__product-analytics-lead --requirement-intensity 8 --gate-decision customization_needed --reason "The JD requires a specialized evidence map beyond the master resume." --next-action "Scan achievements and request approval."
career-ops queue-propose --role-id northstar-crm__product-analytics-lead --evidence-map "JD requirements mapped to source-backed bullets." --proposed-changes "Change summary, move data-quality proof up, and avoid unsupported tools."
career-ops queue-approve --role-id northstar-crm__product-analytics-lead --approval-note "Approved after reviewing the evidence map and proposed bullet swaps."
career-ops queue-start-build --role-id northstar-crm__product-analytics-lead --output-file Ashish_Product_Analytics_Northstar.docx
career-ops queue-complete-build --role-id northstar-crm__product-analytics-lead --output-file Ashish_Product_Analytics_Northstar.docx --mechanical-qa Passed --final-critic Passed
```

If QA or the final critic fails, use `queue-fail` with a retry target:

```bash
career-ops queue-fail \
  --role-id northstar-crm__product-analytics-lead \
  --stage final_critic \
  --reason "The strongest evidence was not above the fold." \
  --retry-target evidence_map

career-ops queue-retry \
  --role-id northstar-crm__product-analytics-lead \
  --retry-target evidence_map \
  --note "Reopen the evidence map and approval loop before rebuilding."
```

`queue-fail` records the failed stage and the required retry target. The packet cannot move directly from `failed` to `building`; `queue-retry` must reopen the required step first. Retry targets map to workflow steps as follows:

- `master_check` returns to `pending_gate`.
- `evidence_map` returns to `gate_checked`, requiring a new proposal.
- `human_approval` returns to `proposed`, requiring approval again.
- `build_resume` returns to `approved`, allowing a rebuild after build/content repair.

Capture learning feedback after review, manual edits, approval/rejection, accepted warnings, or application:

```bash
career-ops queue-feedback \
  --role-id northstar-crm__product-analytics-lead \
  --signal-type accepted_warning \
  --note "Accepted a minor warning because the selected evidence was stronger than the master resume."

career-ops queue-archive \
  --role-id northstar-crm__product-analytics-lead \
  --reason "Master resume was recommended and no tailored artifact was needed."
```

`queue-feedback` can capture proposal-stage rejection/edit signals before a build, and `queue-archive` can close `master_recommended`, `proposed`, `approved`, `ready`, or `failed` packets with a reason. Archiving is for intentional closure; failure/retry is for work that should be repaired and continued.

New tracker updates are queue-required by default. `promote-role` and `mark-ready` require a matching `ready` queue packet unless `--legacy-no-queue` is passed for an older/manual artifact.

## Validation Rules

`career-ops validate-state` checks for:

- Missing files.
- Header/schema mismatches.
- Invalid dates.
- Invalid lifecycle statuses.
- Invalid review statuses.
- Tracker rows not sorted by date.
- `Applied` rows without `applied=Yes`.
- `Resume Ready` rows without an accepted review state.
- Duplicate URLs and suspicious duplicate company/role pairs.
- Queue packet schema, allowed statuses, completed gate/proposal/approval prerequisites, single active build slot, stale failures, and accepted warning notes.

Strict mode treats warnings as failures:

```bash
career-ops validate-state --strict
career-ops validate-queue --strict
```

An empty queue passing validation only means there are no invalid queue packets; it does not mean there is active resume work in progress.

## Why This Matters

The workflow is designed for AI-assisted work where speed can create quality risk. The CLI keeps the process grounded by making state explicit, review gates visible, and follow-up actions traceable.

This pattern is not limited to job search. The same idea applies to product analytics and operational reporting: AI can accelerate drafting and exploration, but durable systems need source-of-truth rules, validation, review status, and reproducible state.
