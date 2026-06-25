# API, State, and Operations Reference

## Contents

1. HTTP API
2. SSE events
3. SQLite schema
4. Environment groups
5. Local instances
6. Docker and Feishu deployment
7. Security and operational boundaries

## HTTP API

Always verify current decorators in `server.py` before changing a client.

| Method and path | Purpose | Required scope/input |
|---|---|---|
| `GET /` | Serve `web/index.html` | none |
| `GET /api/health` | Queue and optional Feishu readiness | none |
| `GET /api/models` | Public configured model choices | keys must be configured server-side |
| `GET /api/diagnostics/volcengine` | Ark config and DNS diagnostics | optional `model_id`; `probe=true` incurs a model call |
| `POST /api/upload` | Parse and persist DOCX | multipart `file`, `session_id` |
| `POST /api/process` | Queue episodes and stream SSE | JSON episodes, upload/session/model/mode |
| `GET /api/result/{episode_id}` | Return storyboard and Seedance | `session_id` |
| `GET /api/download` | Download one TXT | `episode_id`, `kind`, `session_id` |
| `GET /api/results` | List result metadata | `session_id`; optional upload/job filters |
| `GET /api/history` | Group uploads and runs | `session_id` |
| `GET /api/download-all` | ZIP successful Seedance TXT files | `session_id` plus `job_id` or `upload_id` |
| `GET /api/download-all-text` | Legacy combined TXT | same scope as ZIP |
| `DELETE /api/clear` | Delete one upload and its results | `upload_id`, `session_id` |
| `POST /api/feishu/events` | Feishu challenge/message webhook | enabled integration and verified event |

### Upload response

The response includes `session_id`, `upload_id`, source filename, character count, episode count, and episode objects. Each episode contains an index, title, character count, preview, text, and upload ID.

### Process request

The browser sends:

```json
{
  "episodes": [],
  "upload_id": "...",
  "session_id": "...",
  "mode": "script-or-episode",
  "model_id": "..."
}
```

An episode may contain its text directly. If text is missing, the backend resolves it from the persisted upload using the upload ID and episode index.

## SSE events

The `/api/process` response uses `data: <json>\n\n` frames.

| Event | Meaning | Important fields |
|---|---|---|
| `queued` | Job accepted | job/session ID, position, concurrency, total |
| `job_started` | Worker took job | message, concurrency |
| `progress` | Episode Stage 1 or 2 | episode/index, stage, current/total, retry |
| `complete` | One episode succeeded | job/episode ID, lengths, current/total |
| `error` | One episode or job failed | episode/index, error, retry |
| `auto_retry` | Failed episodes will rerun once | job ID, count, message |
| `done` | Stream terminal event | job ID, success/error counts |

If adding an event, update both backend emission and frontend `handleSSEEvent()`. Ensure every stream reaches `done`, including worker exceptions, or the client may wait forever.

## SQLite schema

`APP_DB_PATH` selects the database.

### uploads

- `upload_id` primary key
- `session_id`
- `filename`
- `full_text`
- `episodes_json`
- `timestamp`

### results

- `episode_id` primary key
- `upload_id`, `job_id`, `session_id`
- `title`, `status`, `model_id`
- `storyboard`, `seedance`
- output lengths, error, timestamp

The startup migration currently ensures the `job_id` column exists. Add migrations through the same idempotent pattern; do not assume every local database was freshly created.

### feishu_tasks

- `message_id` primary key/idempotency key
- chat, tenant, sender, and source file metadata
- session/upload/job/model IDs
- status, error, created and updated timestamps

Task states include received/downloading/queued/processing and terminal or delivery-related states. Inspect the current functions before adding transitions.

## Environment groups

Use `.env.example` and port-specific example files as the public contract.

- Provider credentials and URLs: `DEEPSEEK_*`, `SILICONFLOW_*`, `OPENROUTER_*`, `PIXEL_*`, `GEMINI_*`, `ARK_*`.
- Model runtime: `MODEL_STREAM_OUTPUT`, `MODEL_MAX_TOKENS`, `MODEL_SDK_MAX_RETRIES`, `MODEL_TRUST_ENV`, `LOG_MODEL_CONTENT`.
- Queue/data: `TASK_CONCURRENCY`, `APP_DATA_DIR`, `APP_DB_PATH`.
- Environment loading: `ENV_FILE`, `ENV_FILE_ONLY`.
- Web: `CORS_ALLOW_ORIGINS`.
- Feishu: `FEISHU_ENABLED`, app credentials/token, base URL, timeout, upload limit, trust-env, model ID, and progress interval.

`ARK_API_KEY` takes precedence over the legacy `VOLCENGINE_API_KEY` fallback. Do not duplicate or log either value.

## Local instances

- Port 7000: `restart_7000.command`; normally loads `.env` and uses the default database.
- Port 7001: `restart_7001.command`; sets `ENV_FILE_ONLY=1`, loads only `.env.8001`, and uses `data/app_8001.db`.
- Port 7002: `restart_7002.command`; loads only `.env.7002` and uses `data/app_7002.db`.
- `start_both_ports.command`: opens separate Terminal processes for 7000 and 7001.

Port-specific startup scripts may intentionally choose different models, proxies, timeouts, and concurrency. Do not collapse them into one environment unless requested.

Prefer browser access through the backend origin. The fixed `file://` fallback is a compatibility path, not the primary deployment design.

## Docker and Feishu deployment

The Docker image:

- installs Python dependencies;
- copies backend, frontend, Feishu client, and knowledge bases;
- runs as a non-root user;
- stores persistent data under `/app/data`;
- exposes one FastAPI/Uvicorn process;
- health-checks `/api/health`.

For Feishu:

1. Use a public HTTPS callback at `/api/feishu/events`.
2. Grant only the message read, file download/upload, and bot send permissions needed by the selected chat mode.
3. Configure event subscription for message receive.
4. Mount persistent `/app/data`.
5. Run one service instance and one Uvicorn worker.
6. Confirm health reports Feishu configured and the selected model ready.
7. Test with a small multi-episode DOCX and inspect the returned ZIP.

The current verifier supports a Verification Token. Do not claim encrypted event-body support unless the code implements it.

## Security and operational boundaries

- Session IDs are guess-resistant local identifiers but not user accounts or authorization.
- Every configured user shares server-side model keys and provider limits.
- SQLite plus in-memory queues suits one instance and a small team, not horizontal scale.
- Full model content logging can expose scripts and generated material; keep `LOG_MODEL_CONTENT=0` outside deliberate debugging.
- Probe endpoints and provider test scripts may incur quota and send content externally.
- A `401` from an unauthenticated base-URL curl can still prove DNS/TLS reachability; do not mislabel it as a model authorization result.
