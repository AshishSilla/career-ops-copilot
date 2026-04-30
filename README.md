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
    job_search_log.csv
    application_tracker.csv
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

I also separated `job_search_log.csv` from `application_tracker.csv` because the job-search funnel has two different modes: many roles are researched and rejected, while only a smaller set become active resume/application work.

## Sample Data

The repository includes anonymized sample rows only. The original private job-search data, personal resume files, application history, and company-specific notes are intentionally excluded.

## Repository Description

Suggested GitHub description:

> AI-assisted career operations copilot for job tracking, resume workflow management, review gates, and application follow-ups.

## Topics

Suggested GitHub topics:

`python`, `cli`, `csv`, `workflow-automation`, `job-search`, `ai-workflows`, `product-analytics`, `career-ops`
