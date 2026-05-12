# Career Ops Copilot

A lightweight command-line copilot for managing an AI-assisted job search with structured state, review gates, and auditable CSV files.

This project started as a real personal operating system for evaluating roles, generating tailored resumes, tracking review quality, and managing application follow-ups. I converted it into a public-safe sample project by removing private application history and replacing it with anonymized example data.

## Why I Built This

Modern job search creates a messy workflow: job descriptions, fit scoring, resume versions, review status, application dates, follow-ups, and notes all live in different places. I wanted a small system that could keep a simple CSV workflow but add enough structure to make it reliable.

The goal was not to build a heavy SaaS app. The goal was to build a high-agency operating layer around AI-assisted career work: use AI to research and draft faster, but keep the final workflow grounded in schema validation, status transitions, review notes, and source-of-truth discipline.

## What It Does

- Validates job-search and application-tracker CSV schemas.
- Enforces clean lifecycle states such as `Pursued`, `Draft Built`, `Review Needed`, `Resume Ready`, and `Applied`.
- Promotes a pursued role from the job log into the application tracker.
- Tracks resume coverage scores, review status, accepted warnings, application dates, and follow-up dates.
- Sorts state files into a consistent order.
- Keeps the workflow transparent by using plain CSV files instead of a hidden database.

For the full lifecycle, see [docs/workflow.md](docs/workflow.md).

## Why This Shows AI Fluency

This project reflects how I use AI in practical work: not as a replacement for judgment, but as a speed layer inside a controlled system.

The AI-assisted parts of the workflow help with job description analysis, resume tailoring, coverage review, and next-step reasoning. The CLI then acts as the control layer that keeps the system honest: it validates schemas, forces review gates, records accepted warnings, and prevents applications from being marked complete before the resume is ready.

That combination is important for new-age analytics work too. AI can accelerate analysis and reporting, but the durable value comes from trusted foundations, clear definitions, reproducible workflows, and human judgment.

## Project Structure

```text
career-ops-copilot/
  career_ops/
    cli.py
  data/
    sample_job_search_log.csv
    sample_application_tracker.csv
  docs/
    workflow.md
  README.md
  pyproject.toml
```

## Quick Start

Run directly with Python:

```bash
python3 -B career_ops/cli.py validate-state
```

Or install locally in editable mode:

```bash
python3 -m pip install -e .
career-ops validate-state
```

By default, commands run against the bundled anonymized sample files:

```text
data/sample_job_search_log.csv
data/sample_application_tracker.csv
```

To use your own CSV files, pass the file paths before the command:

```bash
career-ops \
  --job-log path/to/job_search_log.csv \
  --tracker path/to/application_tracker.csv \
  validate-state
```

## Example Commands

Validate the current state:

```bash
career-ops validate-state
```

Sort the CSV files into canonical order:

```bash
career-ops sort
```

Promote a role from the job log into the application tracker:

```bash
career-ops promote-role \
  --company "Northstar CRM" \
  --role "Product Analytics Lead" \
  --output-file "Ashish_Product_Analytics_Northstar.docx" \
  --tier1 88 \
  --tier2 81
```

Mark a resume as needing review:

```bash
career-ops mark-review-needed \
  --output-file "Ashish_Product_Analytics_Northstar.docx"
```

Mark a resume as ready after review:

```bash
career-ops mark-ready \
  --output-file "Ashish_Product_Analytics_Northstar.docx" \
  --review-status "Passed"
```

Mark an application as submitted and create a follow-up date:

```bash
career-ops mark-applied \
  --output-file "Ashish_Product_Analytics_Northstar.docx" \
  --applied-date 2026-04-30
```

## Design Choices

I kept the storage layer as CSV because it is easy to audit, easy to edit manually, and works well with AI-assisted workflows. The CLI provides the guardrails that spreadsheets usually lack: required headers, controlled status values, date validation, duplicate detection, and lifecycle rules.

I also separated `sample_job_search_log.csv` from `sample_application_tracker.csv` because the job-search funnel has two different modes: many roles are researched and rejected, while only a smaller set become active resume/application work.

## Sample Data

The repository includes anonymized sample rows only. The original private job-search data, personal resume files, application history, and company-specific notes are intentionally excluded.

The sample files are intentionally named with the `sample_` prefix so they are clearly public demo data, not production state.

## Repository Description

Suggested GitHub description:

> AI-assisted career operations copilot for job tracking, resume workflow management, review gates, and application follow-ups.

## Topics

Suggested GitHub topics:

`python`, `cli`, `csv`, `workflow-automation`, `job-search`, `ai-workflows`, `product-analytics`, `career-ops`

## Change Log and Design Learnings

### 2026-05-13: Added clearer review-gate positioning

I refined the project documentation to make the core idea more explicit: AI can help draft, compare, and reason quickly, but the workflow still needs hard gates before anything is treated as final. The important learning was that "reviewed" cannot just mean a human or model looked at a draft. It needs a visible state transition, an accepted review status, and a file or artifact that can be traced back to the exact work being approved.

This mirrors how I think about product analytics and analytics operations. A dashboard, report, or AI-generated recommendation is not reliable just because it exists. It becomes useful when definitions are clear, edge cases are handled, ownership is explicit, and the system prevents accidental skips in the workflow.

### 2026-05-13: Clarified why CSV is intentional

I kept the storage layer as plain CSV instead of moving immediately to a database because the goal of this project is auditability and control, not technical complexity. CSVs make every state change visible, easy to diff, and easy to inspect manually. The CLI adds the missing guardrails: schema validation, lifecycle checks, controlled statuses, duplicate detection, and review requirements.

The learning here is that good automation does not always mean a heavier stack. For small operational systems, the right design is often a thin control layer over a simple source of truth.

### 2026-05-13: Separated public-safe workflow from private source data

The original workflow came from a real job-search operating system with private resumes, application history, and company-specific notes. I intentionally converted this repository into a public-safe version with anonymized sample files. That separation matters because the reusable value is the workflow pattern, not the private data.

The product lesson is similar to analytics system design: separate the framework from the sensitive underlying records. The same validation, state management, and review-gate pattern can be reused without exposing confidential inputs.

### 2026-05-13: Added the exact-artifact review principle

One practical failure mode in AI-assisted workflows is reviewing the wrong artifact: an older file, a stale output, or a same-named document from a previous run. The fix is conceptual as much as technical: any review gate should point to the exact artifact produced by the current workflow run.

That principle applies beyond resumes. In analytics and product work, a sign-off should connect to the exact dataset, query version, dashboard, experiment readout, or document being approved. Otherwise, the workflow can look controlled while still allowing stale evidence to pass through.
