# Career Ops Copilot

An AI-assisted career workflow control layer for managing job-search state, resume review gates, and application follow-ups with auditable CSV files.

This project started as a real personal operating system for evaluating roles, generating tailored resumes, tracking review quality, and managing application follow-ups. I converted it into a public-safe sample project by removing private application history and replacing it with anonymized example data.

## What This Demonstrates

- AI workflow design with human review gates instead of blind generation.
- Product analytics judgment around lifecycle states, source-of-truth rules, and exception handling.
- Lightweight automation over transparent data rather than unnecessary platform complexity.
- Practical operating discipline: schema validation, status transitions, duplicate checks, and follow-up tracking.

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

## Workflow Model

```text
Researched -> Pursued -> Draft Built -> Review Needed -> Resume Ready -> Applied
```

The key design choice is that generated work cannot jump straight to completion. For example, a resume cannot be marked `Resume Ready` unless the review status is `Passed` or `Warning Accepted`. That forces the workflow to record quality judgment before an application is treated as ready.

## Resume Workflow Architecture

The resume workflow is designed as a gated system, not a one-shot generation task. The agent first decides whether customization is even justified, then maps the job description to source-backed achievements, asks for approval, builds the resume, and runs a final critic pass before the artifact is treated as ready.

```text
USER REQUEST
  "Create resume for this role"
        |
        v
[1] JD Ingest
    - Parse role, company, location, seniority, tools, domain, must-haves
        |
        v
[2] Master Resume Check
    - Compare the JD against the relevant master resume
    - Score requirement intensity from 1-10
    - Decide whether the master is sufficient
        |
        v
 +-----------------------------+
 | [3A] Master Sufficient      |
 | - Recommend master as-is    |
 | - Ask before tailoring      |
 | - No new resume artifacts   |
 +-------------+---------------+
               |
               | If user approves tailoring anyway
               v
 +-------------+---------------+
 | [3B] Customization Needed   |
 | - Scan achievement bank     |
 | - Compare master bullets    |
 | - Identify swaps and risks  |
 +-------------+---------------+
               |
               v
 +-------------+---------------+
 | [4] Evidence Map            |
 | - JD requirement -> bullets |
 | - Selected proof/rationale  |
 | - Rejected/watchlist items  |
 | - Summary and skills edits  |
 +-------------+---------------+
               |
               v
 +-------------+---------------+
 | [5] Human Approval Gate     |
 | - Approve, edit, or reject  |
 +-------------+---------------+
               |
               v
 +-------------+---------------+
 | [6] Build Resume            |
 | - Generate config and DOCX  |
 | - Preserve honest gaps      |
 +-------------+---------------+
               |
               v
 +-------------+---------------+
 | [7] Mechanical QA           |
 | - Config validation         |
 | - Preflight review          |
 | - Generated resume review   |
 | - DOCX integrity            |
 +-------------+---------------+
               |
               | If QA fails:
               | fix config, bullets, summary, or formatting
               | and rebuild from [6]
               |
               v
 +-------------+---------------+
 | [8] Final Critic Review     |
 | - Answers the real JD?      |
 | - Strongest proof visible?  |
 | - Unsupported tools absent? |
 | - Better than master as-is? |
 +-------------+---------------+
               |
               | If critic fails:
               | return to [4] Evidence Map or [6] Build Resume,
               | revise the strategy, and run QA again
               |
               v
 +-------------+---------------+
 | [9] Tracker State           |
 | - Review Needed             |
 | - Resume Ready              |
 | - Applied                   |
 +-------------+---------------+
               |
               v
            COMPLETE
```

The key product decision is the separation between **generation** and **approval**. AI can draft and compare quickly, but the workflow forces evidence mapping, explicit approval, mechanical validation, and a final critic review before a resume moves forward.

Failures are expected to loop backward, not move forward with caveats. Mechanical QA failures go back to the build/config layer. Final critic failures go back to the evidence map or resume strategy layer, because the issue is usually strategic rather than formatting-related. A resume reaches tracker state only after both loops are clean.

In the private version of this system, future tailored resume configs are blocked unless they record the master-resume gate and the achievement-bank scan. That makes the review process auditable instead of relying on the agent to remember the right sequence.

## Evidence-Mapping Pattern

The customization step uses a simple evidence matrix rather than keyword stuffing:

```text
JD requirement:
  "Develop datasets, data systems, and simple pipelines"

Achievement-bank candidates:
  HR_24 -> reporting modernization with validated staging layers
  HR_18 -> analytics migration QA across production queries
  BW_14 -> SQL dimensional model / source of truth
  RZ_02 -> checkout data normalization

Decision:
  Use HR_24 and BW_14 as primary evidence.
  Use HR_18 only if migration or pipeline support is central to the JD.
```

This keeps the workflow grounded in verified achievements. It also creates a visible audit trail for why a bullet was selected, why another was rejected, and which claims should not appear in the resume.

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

Example output:

```text
[PASS] career ops state is valid
Job log rows: 3
Tracker rows: 1
Summary: 0 error(s), 0 warning(s)
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

Together, these commands show the intended operating loop: validate state, promote a role, move the resume into review, mark it ready only after review, then mark the application submitted.

## Design Choices

I kept the storage layer as CSV because it is easy to audit, easy to edit manually, and works well with AI-assisted workflows. The CLI provides the guardrails that spreadsheets usually lack: required headers, controlled status values, date validation, duplicate detection, and lifecycle rules.

I also separated `sample_job_search_log.csv` from `sample_application_tracker.csv` because the job-search funnel has two different modes: many roles are researched and rejected, while only a smaller set become active resume/application work.

## Sample Data

The repository includes anonymized sample rows only. The original private job-search data, personal resume files, application history, and company-specific notes are intentionally excluded.

The sample files are intentionally named with the `sample_` prefix so they are clearly public demo data, not production state.

## Inspiration and Attribution

This project was inspired in part by the publicly available [santifer/career-ops](https://github.com/santifer/career-ops) project, an open-source AI-powered job search system that shows how agentic tools can support job evaluation, CV generation, batch processing, and pipeline tracking.

Career Ops Copilot is an independent, smaller implementation focused on the control layer I wanted to demonstrate publicly: CSV-backed state, lifecycle validation, review gates, and auditable status transitions. The inspiration was the broader idea of treating career operations as a structured workflow; the implementation here is intentionally simplified, anonymized, and public-safe.

## Repository Description

Suggested GitHub description:

> AI-assisted career operations copilot for job tracking, resume workflow management, review gates, and application follow-ups.

## Topics

Suggested GitHub topics:

`python`, `cli`, `csv`, `workflow-automation`, `job-search`, `ai-workflows`, `product-analytics`, `career-ops`

## Change Log and Design Learnings

### 2026-05-13: Strengthened AI workflow guardrails

I refined the project framing to make the central design principle clearer: AI can accelerate drafting, comparison, and reasoning, but final decisions still need explicit review gates. In this workflow, a resume or application cannot move forward just because it was generated. It needs a visible lifecycle state, accepted review status, and traceable notes.

This is the same discipline I apply in analytics and product work. A dashboard, experiment readout, or AI-generated recommendation is only useful when definitions are clear, ownership is explicit, and the system prevents low-quality outputs from being treated as final.

### 2026-05-13: Kept the source of truth deliberately simple

I kept the storage layer as plain CSV instead of moving immediately to a database because the goal is auditability and control, not technical complexity. CSVs make every state change visible, easy to inspect, and easy to reconcile. The CLI adds the missing guardrails: schema validation, lifecycle checks, controlled statuses, duplicate detection, and review requirements.

The product lesson is that good automation does not always require a heavier stack. For small operational systems, the right design is often a thin control layer over a simple, transparent source of truth.

### 2026-05-13: Separated reusable workflow logic from private data

The original workflow came from a real job-search operating system with private resumes, application history, and company-specific notes. I intentionally converted this repository into a public-safe version with anonymized sample files. That separation matters because the reusable value is the workflow pattern, not the private data.

This reflects a broader analytics design habit: separate the reusable framework from sensitive records. The same validation, state management, and review-gate pattern can be reused without exposing confidential inputs.
