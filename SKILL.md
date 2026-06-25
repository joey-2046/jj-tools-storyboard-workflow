---
name: jj-tools-storyboard-workflow
description: Maintain, diagnose, extend, run, test, and deploy the JJ Tools director-storyboard application built from FastAPI, SQLite, a single-file HTML frontend, DOCX episode splitting, queued SSE jobs, two-stage LLM generation, Seedance 2.0 validation, ZIP downloads, and optional Feishu delivery. Use when working on this JJ Tools/FilmFlow codebase or a copy of it, especially server.py, main.py, web/index.html, model providers, prompts, session/job isolation, history/download APIs, restart scripts, Docker, online deployment, or Feishu bot flows.
---

# JJ Tools Storyboard Workflow

## Establish the project root

1. Locate a directory containing `server.py`, `web/index.html`, `requirements.txt`, and the two Chinese knowledge-base Markdown files.
2. Read the project-local `AGENTS.md` before changing anything. Treat it as the current project contract; use this skill for procedure and cross-file impact analysis.
3. Run searches from that directory. Prefer `rg` and `rg --files`.
4. Re-check actual code before relying on a remembered model list, environment default, port, or prompt format. These drift frequently.

If the folder does not match this layout, stop applying project-specific assumptions and explain the mismatch.

## Protect the non-negotiable invariants

- Never print, copy, commit, or summarize values from `.env`, `.env.8001`, `.env.7002`, or cloud secrets. Inspect example files and whether a key is set, never the key value.
- Preserve `session_id` isolation across upload, result lookup, history, single download, batch download, and clear operations. A browser session identifier is isolation, not authentication.
- Preserve `job_id` scoping for “download this run.” Do not silently broaden a current-task ZIP to every historical result for the upload.
- Preserve completed results in SQLite while recognizing that queues, SSE event streams, and running jobs are process memory. A restart interrupts in-flight work.
- Keep model calls off the FastAPI event loop by using `asyncio.to_thread()` or an equivalent non-blocking boundary.
- Keep Stage 1 and Stage 2 contracts aligned with their validators. Prompt-only edits are incomplete if parsers, validation, retry text, tests, UI labels, or downloads still assume the old format.
- Preserve exact source-dialogue text and order. Do not “improve” dialogue in either generation stage.
- Preserve UTF-8 `filename*` handling for Chinese downloads and safe ZIP member names.
- Use `Optional[...]` instead of `X | None` when maintaining compatibility with older local Python runtimes required by this project.
- Avoid destructive file operations. The project may not have Git history to recover from.

## Route the task before editing

Read only the references needed for the request:

- Read [architecture-and-flows.md](references/architecture-and-flows.md) for end-to-end browser, queue, persistence, or Feishu flow work.
- Read [generation-contracts.md](references/generation-contracts.md) before changing prompts, model routing, output formats, counts, dialogue handling, knowledge bases, or retry logic.
- Read [api-state-and-operations.md](references/api-state-and-operations.md) for endpoint contracts, identifiers, SQLite, ports, environment configuration, Docker, or deployment work.
- Read [maintenance-playbook.md](references/maintenance-playbook.md) for change-impact checklists, verification commands, and symptom-based diagnosis.

## Use the maintenance workflow

### 1. Inspect the live implementation

Search the narrowest relevant surface before reading large files:

```bash
rg -n "search_term|function_name|/api/route" server.py main.py web/index.html tests
rg -n "ENV_NAME|MODEL_ID" server.py .env.example .env.8001.example .env.7002.example
```

Map the change across all consumers. Typical chains are:

```text
frontend action -> API payload -> queue/job -> model stage -> validator -> SQLite
-> SSE event -> frontend state -> result/history/download
```

or:

```text
Feishu event -> idempotent task row -> attachment download -> shared episode pipeline
-> ZIP assembly -> Feishu upload/send -> task status
```

### 2. Define the contract being changed

State the affected input, output, identifier, persistence boundary, error behavior, and user-visible result. For prompt work, also state the parser and validator that consume the output.

### 3. Make the smallest coherent change

Update every layer that shares the contract, but do not perform unrelated cleanup. Preserve user changes in a dirty or non-versioned folder.

Use these mandatory pairings:

- Episode parsing: update `find_episode_title()` / `split_into_episodes()` and add splitting tests.
- Model option: update `MODELS_CONFIG`, provider routing, relevant `.env*.example`, `/api/models` expectations, and frontend selection behavior.
- SSE event: update the emitter and `handleSSEEvent()`.
- Result identity or filters: update memory lookup, SQLite queries, API parameters, frontend calls, history, and ZIP scope.
- Output format: update prompt, builder, parser/count helper, validator, retry message, tests, and any UI/download assumptions.
- Feishu behavior: update event parsing/client or task state code, recovery behavior, tests, and online deployment notes.

### 4. Validate in increasing cost order

Run the bundled safe structural audit first:

```bash
python3 ~/.codex/skills/jj-tools-storyboard-workflow/scripts/project_check.py --root .
```

Then run project checks appropriate to the change:

```bash
PYTHONPYCACHEPREFIX=.pycache python3 -m py_compile server.py main.py feishu_client.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

When a local service is already running, add read-only health checks:

```bash
python3 ~/.codex/skills/jj-tools-storyboard-workflow/scripts/project_check.py \
  --root . --health-url http://127.0.0.1:7000
curl -sS http://127.0.0.1:7000/api/models
```

Do not invoke a paid model probe unless the user requested live connectivity testing or it is necessary to verify a model integration. `/api/diagnostics/volcengine?probe=true` makes a real model call.

### 5. Verify the user path

For backend-only changes, test the affected function or API. For cross-layer changes, exercise the browser path through a backend URL rather than `file://` whenever possible. Confirm:

- correct session and job scoping;
- visible queued, progress, retry, complete, error, and done states as applicable;
- persistence after a controlled restart only when restart behavior is in scope;
- one TXT per successful episode in ZIP order;
- first and last episode content to catch truncation;
- no secret values in console output.

## Handle common task families

### Upload and episode splitting

Preserve document-order extraction from both paragraphs and table cells. Treat recognized episode headings as boundaries; strip front matter only after explicit body markers. If no heading is found, return one `完整剧本` episode. Keep `upload_id + index` text recovery working when the frontend sends metadata without full text.

### Queue, state, and history

Keep one in-process queue with `TASK_CONCURRENCY` workers. Jobs process episodes sequentially; workers provide bounded cross-job concurrency. Persist each episode transition needed for history and recovery. Distinguish `upload_id` (source upload), `job_id` (one processing run), and `episode_id` (one episode result in one run).

### Generation and quality validation

Treat Stage 1 and Stage 2 as one pipeline with separate contracts. Stage 1 produces a hard-targeted KF sequence. Stage 2 re-cuts that master into Seedance segments, validates timing, references, station continuity, dialogue density, exact dialogue coverage/order, and shot-scale distribution. Read [generation-contracts.md](references/generation-contracts.md) before touching this area.

### Downloads

Return a single storyboard or Seedance TXT from `/api/download`. Build `/api/download-all` from successful rows only, in original episode order, with unique normalized Chinese filenames. Keep the older combined-text endpoint compatible unless explicitly removing it.

### Feishu and online deployment

Reuse the same upload, split, generation, validation, result, and ZIP functions as the browser path. Keep `message_id` idempotency and SQLite recovery. Deploy a single Uvicorn worker with persistent `/app/data`; scale model concurrency through `TASK_CONCURRENCY`, not multiple web workers.

## Report completion

Lead with the outcome. List changed files, verification performed, and any checks skipped because they would consume paid API quota, require secrets, restart a live service, or depend on external infrastructure. Never include secret values or full model outputs in the report.
