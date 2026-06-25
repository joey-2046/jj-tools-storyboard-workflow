# Maintenance and Troubleshooting Playbook

## Contents

1. Baseline inspection
2. Change-impact matrix
3. Verification ladder
4. Troubleshooting by symptom
5. Release and handoff checklist

## Baseline inspection

Run from the project root:

```bash
rg --files -g '!data/**' -g '!.pycache/**'
rg -n "^(def |async def |@app\.|MODELS_CONFIG|STAGE1_PROMPT|STAGE2_PROMPT)" server.py
rg -n "^function |const API_BASE|currentSessionId|currentJobId" web/index.html
python3 ~/.codex/skills/jj-tools-storyboard-workflow/scripts/project_check.py --root .
```

Check the working folder for unrelated user edits before modifying files. If no Git repository exists, make narrower patches and inspect exact before/after content carefully.

## Change-impact matrix

| Change | Inspect together | Minimum verification |
|---|---|---|
| Episode heading support | extraction, normalization, heading regex, split fallback, filename normalization | splitting unit tests with paragraphs and tables |
| Front-matter behavior | body markers and split start | tests with synopsis before marker and no marker |
| New model/provider | registry, env examples, request branch, model list, frontend channel selector | syntax, model list, safe provider connectivity test if authorized |
| Prompt wording | prompt, knowledge-base injection, input builder | parser/validator fixtures; one live small episode only if needed |
| Stage output format | prompt, counters/splitters, validators, retry notes, downloads | valid/invalid unit tests and end-to-end result rendering |
| Queue/concurrency | startup, queue, workers, `to_thread`, SSE lifecycle | multi-job test; terminal `done`; no event-loop blocking |
| Result identity | episode ID creation, save/get/list queries, frontend matching | duplicate-title and repeated-job tests |
| History | result filters, grouping SQL, archive UI | two jobs on one upload stay distinct |
| ZIP/download | ordering, success filtering, UTF-8 headers, frontend query | archive names/content/order and Chinese browser download |
| Feishu input | parser, idempotency row, ingest worker, attachment client | challenge/token/file/text tests |
| Feishu delivery | ZIP, upload/send, status transitions, recovery | mocked client and restore tests |
| Port/env startup | command script, env-only loading, DB path | process starts with intended model set/database |
| Docker | requirements, copied runtime files, persistent data, health | unit tests, image build, health endpoint |

## Verification ladder

### Level 1: no network

```bash
python3 ~/.codex/skills/jj-tools-storyboard-workflow/scripts/project_check.py --root .
PYTHONPYCACHEPREFIX=.pycache python3 -m py_compile server.py main.py feishu_client.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

For frontend edits, search for missing IDs/functions and inspect the edited browser path. If browser automation is available, serve the app and test it visually.

### Level 2: local service, no paid probe

```bash
curl -fsS http://127.0.0.1:7000/api/health
curl -fsS http://127.0.0.1:7000/api/models
curl -fsS http://127.0.0.1:7000/
```

Test upload with a throwaway DOCX only if creating the file is in scope. Avoid using confidential production scripts as fixtures.

### Level 3: external integration

Use provider-specific test scripts or `probe=true` only when explicitly warranted. State that the check can consume API quota and send a prompt to the provider. Never echo `.env`.

### Level 4: channel/deployment acceptance

Verify persistent storage, one-worker topology, HTTPS callback, permissions, webhook validation, a small DOCX, progress updates, returned ZIP, and restart recovery where relevant.

## Troubleshooting by symptom

### Model dropdown falls back to only DeepSeek

1. Compile `server.py`; a startup error makes frontend model loading fail.
2. Call `/api/models` directly.
3. Confirm the intended provider key is set without printing it.
4. Confirm the correct port-specific env file loaded.
5. Restart the intended backend and hard-refresh the browser.

### Upload reports `Failed to fetch`

1. Confirm the backend is listening at the origin shown in the footer/status.
2. Prefer opening the page through `http://host:port/`.
3. If using `file://`, verify the fixed `API_BASE` address is reachable.
4. Inspect CORS only after verifying host/port and process health.

### Too few or incorrectly split episodes

1. Inspect extracted paragraphs and table cell ordering without exposing confidential content unnecessarily.
2. Check hidden/full-width whitespace normalization.
3. Test the exact heading through `find_episode_title()`.
4. Check whether synopsis lines resemble headings and whether a body marker exists.
5. Add a regression test before broadening the regex.

### Job stalls in the UI

1. Check `/api/health` and server logs.
2. Determine whether the SSE stream received `queued`, `job_started`, and later events.
3. Confirm every exception path emits terminal `done`.
4. Check provider timeout versus in-memory queue wait.
5. Do not restart until explaining that in-flight browser jobs will be lost.

### Duplicate or cross-user results

Audit `session_id`, `upload_id`, `job_id`, and episode queue index from request through SQL. Check any query missing a scope clause. Do not treat changing the episode ID string alone as a complete fix.

### Current-task ZIP contains old episodes

Confirm the frontend supplies `currentJobId`, the endpoint filters by `job_id`, and history uses the selected run. `upload_id` alone intentionally spans multiple jobs.

### Chinese filename fails

Confirm `Content-Disposition` uses both an ASCII fallback and UTF-8 `filename*`, CORS exposes that header, and frontend parsing prefers `filename*`.

### Stage 1 count failure

Compare target, parsed maximum KF, and actual output labels. Decide whether the model ignored the hard target or the regex failed to recognize a legitimate label. Do not merely widen tolerance without product approval.

### Stage 2 format failure

Use the validation summary to isolate segment count, time slices, references, position continuity, dialogue density, dialogue omission/order, or shot-scale policy. Fix prompt, parser, or policy at the correct layer.

### Ark `ModelNotOpen`

Treat it as account/model activation or endpoint-ID configuration until evidence shows otherwise. Confirm the configured model is enabled in Ark and update the corresponding example-safe model ID if the public contract changed.

### Ark connection error or timeout

1. Call diagnostics without a model probe.
2. Separate DNS/TLS/proxy failure from provider response failure.
3. Check `MODEL_TRUST_ENV`, VPN/proxy/certificate environment, timeout, and concurrency.
4. Use the macOS Terminal/Finder restart script if a sandbox-launched process lacks normal networking.
5. Prefer lower `TASK_CONCURRENCY` before adding nested retries.

### Feishu duplicates, missing reply, or failed delivery

1. Verify token and event normalization.
2. Check `message_id` idempotency row.
3. Distinguish ingest, generation, ZIP upload, and message-send failures.
4. Check file-size limits and task terminal status.
5. Exercise restore logic with mocked clients before touching production callbacks.

## Release and handoff checklist

- Re-read local `AGENTS.md` for project-specific instructions.
- Run syntax checks and relevant unit tests.
- Verify env examples contain names/defaults only.
- Confirm no full model content or secrets were added to logs.
- Confirm prompt format and validators agree.
- Confirm browser request/response and SSE fields agree.
- Confirm session/job scope for history and downloads.
- Confirm restart implications were communicated before restarting.
- List external checks not run and why.
