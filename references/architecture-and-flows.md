# Architecture and End-to-End Flows

## Contents

1. System shape
2. Browser workflow
3. Worker and episode workflow
4. Persistence and identity
5. Feishu workflow
6. CLI workflow
7. Concurrency and recovery boundaries

## System shape

JJ Tools is primarily a FastAPI application in `server.py` with a single-file frontend in `web/index.html`.

Core supporting files:

- `main.py`: older/local CLI path, primarily DeepSeek-oriented; it duplicates some splitting, knowledge-base, prompt, and model-call logic.
- `feishu_client.py`: Feishu event normalization and API client.
- `电影感光效提示词知识库规则文档.md`: cinematic lighting guidance.
- `ai视频影视视听语言知识库规则文档.md`: audiovisual-language guidance.
- `data/*.db`: SQLite persistence selected through `APP_DB_PATH`.
- `tests/test_online_workflow.py`: splitting, ZIP, Feishu event/client, idempotency, restore, and delivery tests.
- `Dockerfile` and `ONLINE_DEPLOYMENT.md`: single-instance online service and Feishu deployment.

The web and Feishu inputs converge on the same split, queue, generation, validation, result, and ZIP code. Preserve this convergence rather than building a second pipeline.

## Browser workflow

```text
Browser startup
  -> create/read localStorage session_id
  -> GET /api/models
  -> select configured model/channel

Script mode
  -> POST /api/upload (multipart DOCX + session_id)
  -> extract paragraphs and table cells in document order
  -> strip recognized front matter
  -> split headings into episodes
  -> persist upload in memory + SQLite
  -> render episode cards

Episode mode
  -> use pasted text as one synthetic episode

Both modes
  -> POST /api/process (episodes, upload_id, session_id, mode, model_id)
  -> receive SSE: queued -> job_started -> progress/complete/error -> auto_retry -> done
  -> GET /api/result/{episode_id}
  -> render storyboard and Seedance output
  -> GET /api/download or /api/download-all
```

The frontend's `API_BASE` uses `window.location.origin` for normal HTTP access and a fixed fallback when opened through `file://`. Prefer serving the frontend from FastAPI so upload and request behavior remain same-origin.

Key frontend functions:

- `loadModels()` and `selectedModelIdForProcess()`
- `uploadFile()` and `renderEpisodeGrid()`
- `processSelectedEpisodes()` and `processEpisodeText()`
- `runPipeline()` and `handleSSEEvent()`
- `fetchResult()`, `downloadResult()`, and `downloadAll()`
- `openHistoryArchive()`, `loadHistoryArchive()`, and `loadArchiveJob()`

## Worker and episode workflow

At application startup:

1. Initialize SQLite schema and migrations.
2. Create `PROCESS_QUEUE`.
3. Start `TASK_CONCURRENCY` worker tasks.
4. If Feishu is enabled, validate configuration, start the ingest worker, and restore recoverable tasks.

At `/api/process`:

1. Validate queue readiness and create missing `session_id`.
2. Generate a fresh `job_id`.
3. Create an in-memory event queue in `JOB_EVENTS[job_id]`.
4. Put the job onto `PROCESS_QUEUE`.
5. Return an SSE stream, beginning with `queued`.

Inside `process_job()`:

1. Add stable `_queue_index` values.
2. Validate the selected model and configured API key.
3. Emit `job_started`.
4. Process episodes sequentially through `process_episode_attempt()`.
5. Skip an already completed result with the same deterministic episode result ID.
6. Collect failed episodes and retry those episodes once at the job level.
7. Emit `done`; optionally finalize Feishu delivery.

Inside `process_episode_attempt()`:

1. Resolve source text from the request or persisted upload.
2. Save a `processing` result row.
3. Emit Stage 1 progress.
4. Generate and validate the KF storyboard; retry once for severe count mismatch.
5. Emit Stage 2 progress.
6. Generate and validate Seedance segments; retry once for blocking format/quality mismatch.
7. Save `done` with both outputs, or save `error` with the error text.
8. Emit `complete` or `error`.

Model-call retries inside `call_deepseek()` are separate from Stage validation retries and the outer job-level failed-episode retry. Account for all three layers when estimating cost or diagnosing duplicate calls.

## Persistence and identity

### Identity hierarchy

```text
session_id
  -> upload_id
       -> job_id (one run over selected episodes)
            -> episode_id (one result row)
```

- `session_id`: stored in browser localStorage or synthesized for another channel. It scopes user-visible data but is not authentication.
- `upload_id`: identifies the source document and its split episodes.
- `job_id`: identifies one processing submission. A regenerated or retried whole task gets a different job ID.
- `episode_id`: built from session, job, episode title, and queue index so repeated titles can still be distinguished.
- Feishu `message_id`: idempotency key for incoming file or regeneration commands.

### Memory versus SQLite

Memory:

- `UPLOADS`: upload cache.
- `RESULTS`: result cache.
- `PROCESS_QUEUE`: waiting jobs.
- `JOB_EVENTS`: live SSE queues.
- `FEISHU_QUEUE`: incoming Feishu tasks.

SQLite:

- `uploads`: source document text and serialized episode list.
- `results`: per-episode status and generated outputs.
- `feishu_tasks`: idempotent channel task state.

The caches fall back to SQLite. Completed rows survive a restart; the live queue and SSE connection do not. Feishu task restoration reconstructs some queued work from durable task/upload state, whereas browser jobs are not generally reconstructed.

## Feishu workflow

```text
POST /api/feishu/events
  -> verify token and normalize event
  -> challenge: return challenge
  -> text: handle 状态 / 重试 / 重新生成 / 帮助
  -> file: INSERT task by message_id; ignore duplicates
  -> FEISHU_QUEUE
  -> download DOCX attachment
  -> shared DOCX extraction and episode splitting
  -> persist upload and queue shared processing job
  -> send progress messages at configured interval
  -> assemble successful Seedance TXT files into ZIP
  -> upload ZIP and send it to original chat
  -> persist done/error/delivery_error state
```

Recovery must avoid calling the model again for episode IDs already marked `done`. File uploads have a configurable size cap; delivery can fail after generation even when results are safely stored.

## CLI workflow

`main.py` provides a separate filesystem-oriented flow:

```text
DOCX path -> extract -> split -> for each episode
-> Stage 1 model call -> Stage 2 model call -> save text outputs
```

Web behavior is authoritative for queueing, multi-provider routing, persistence, history, modern validation, and Feishu integration. When changing shared generation semantics, inspect `main.py` for duplicated contracts and either keep it aligned or explicitly document why it differs.

## Concurrency and recovery boundaries

- Each worker processes the episodes in one job sequentially.
- `TASK_CONCURRENCY` controls how many jobs can actively run in parallel.
- Every episode performs at least two long model calls before retries.
- Multiple Uvicorn workers would create separate in-memory queues and locks while pointing at one SQLite file; do not use them as a scaling strategy.
- Keep one process/one Uvicorn worker for the current architecture.
- For horizontal scale, migrate queues and locks to a shared service and files/results to appropriate shared storage before adding instances.
