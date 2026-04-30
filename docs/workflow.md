# Career Ops Workflow

Career Ops Copilot models a job search as a controlled workflow with two CSV-backed state files:

- `data/sample_job_search_log.csv` stores researched roles, fit scores, decisions, and notes.
- `data/sample_application_tracker.csv` stores active resume/application work, review status, application dates, and follow-up tracking.

The sample files are anonymized demo data. For real usage, keep private CSVs outside the repository and pass them with `--job-log` and `--tracker`.

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
  --tier2 81
```

This creates a `Draft Built` tracker row and links the resume file back to the job log.

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
  --review-status "Passed"
```

If a known issue is acceptable, record it explicitly:

```bash
career-ops mark-ready \
  --output-file "Ashish_Product_Analytics_Northstar.docx" \
  --review-status "Warning Accepted" \
  --review-notes "Accepted minor tenure gap; stronger evidence exists in role-specific experience."
```

## Stage 4: Mark Applied and Track Follow-Up

Applications can only be marked submitted after the tracker row is `Resume Ready`.

```bash
career-ops mark-applied \
  --output-file "Ashish_Product_Analytics_Northstar.docx" \
  --applied-date 2026-04-30
```

The command updates both CSV files and creates a default follow-up date.

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

Strict mode treats warnings as failures:

```bash
career-ops validate-state --strict
```

## Why This Matters

The workflow is designed for AI-assisted work where speed can create quality risk. The CLI keeps the process grounded by making state explicit, review gates visible, and follow-up actions traceable.

This pattern is not limited to job search. The same idea applies to product analytics and operational reporting: AI can accelerate drafting and exploration, but durable systems need source-of-truth rules, validation, review status, and reproducible state.
