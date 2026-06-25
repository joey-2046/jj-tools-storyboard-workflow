# Generation and Validation Contracts

## Contents

1. Model registry and routing
2. Knowledge-base injection
3. Stage 1 contract
4. Stage 2 contract
5. Validation and retries
6. Safe change procedure

## Model registry and routing

Treat `MODELS_CONFIG` in `server.py` as the current registry. Each entry supplies a display name, provider, API key source, base URL, upstream model name, and default flag. `/api/models` filters out entries with no configured key and may hide internal channel variants while exposing them as frontend sub-options.

The historical function name `call_deepseek()` is a provider router, not a DeepSeek-only function.

Current provider behaviors are selected in code and can include:

- OpenAI-compatible Chat Completions for DeepSeek, SiliconFlow, OpenRouter, Pixel, Gemini-compatible relays, and usually Volcengine Ark.
- Optional Ark Responses API when `ARK_API_MODE=responses`.
- OpenRouter attribution headers when configured.
- DeepSeek reasoning parameters.
- Provider-specific streaming and token settings.
- Ark-specific timeout, DNS/connection retry, and ModelNotOpen handling.

When adding or changing a model:

1. Add or update the registry entry.
2. Confirm the provider branch builds a supported request.
3. Add only key names and safe defaults to `.env*.example`.
4. Confirm `/api/models` exposes the intended public choice.
5. Confirm `selectedModelIdForProcess()` sends the intended model/channel ID.
6. Test without logging the key or full model content.

## Knowledge-base injection

`build_system_prompt()` appends context extracted from two Markdown knowledge bases. The loader caches by file signature and prefers the designated “总提示词” section over blindly injecting the full documents.

Knowledge-base guidance may enrich:

- light direction and light type;
- shot scale and camera angle;
- camera motion and composition;
- sound, color, and edit rhythm.

It may not override:

- source-script facts or event order;
- exact dialogue and speaker ownership;
- character and spatial continuity;
- required output structure;
- validator-compatible labels.

When renaming knowledge-base headings, verify the extraction logic still finds the intended section.

## Stage 1 contract

Stage 1 converts one episode into a complete movie-storyboard KF master.

### Target count

`recommended_keyframe_count()` currently derives a hard target from source character count:

| Source length | Target |
|---|---:|
| up to 600 characters | 32 KF |
| 601-1000 | 38 KF |
| 1001-1500 | 42 KF |
| 1501-2000 | 48 KF |
| above 2000 | 55 KF |

The output must end at the requested KF number. `count_stage1_keyframes()` extracts the maximum KF label. A count is severely mismatched when no KF is found or the absolute difference exceeds 3.

### Narrative and visual rules

- Follow source events, evidence, reversals, reactions, and dialogue in original order.
- Cover the ending; do not finish early because the middle generated expansively.
- Label insert shots with an explicit shot scale.
- Use restrained character close-ups at emotional and information pivots.
- Avoid extreme micro close-ups and runs of three or more close shots.
- Break long speeches with reaction coverage while preserving exact, non-overlapping speaker fragments.
- Establish confrontation geography with two-shots or over-shoulders before close reverse coverage.

The exact output template lives in `STAGE1_PROMPT`; do not paraphrase it in code consumers. Inspect the prompt and count parser together.

## Stage 2 contract

Stage 2 does not copy the KF list one-for-one. It re-cuts the Stage 1 master and original script into Seedance segments.

### Segment target

`recommended_segment_count()` chooses the larger of:

- ceiling(KF count / 6);
- ceiling(source dialogue count / 3).

This prevents either visual coverage or dialogue volume from being compressed too aggressively.

### Required structure

- Use `【段落 01｜0-15秒｜核心情绪：...】` style headers.
- Produce roughly the target count; the validator permits a narrow range below/above it.
- Use 4-6 explicit time slices per segment.
- Keep segments at approximately 12-15 seconds.
- Include `站位延续` in every segment.
- End every segment with `【参考】@人物：...；@场景：...；@关键道具：...`.
- Keep references limited to entities actually present; do not output image-number references or explanatory “used for consistency” language.
- Use no more than three non-empty dialogue/OS/VO lines per segment. One slightly dense segment is warning-level; repeated or severe density becomes blocking.
- Include every extracted source dialogue in exact text and order. Do not treat character lists and scene metadata as dialogue.
- Do not output a flat `【镜头 X】` list.

### Shot-scale quality

Time-slice analysis distinguishes large views and person-close views. Current policy blocks large-view share above 22%. A person-close share below 40%, too many large views inside a segment, or weak close coverage in strong-emotion segments produces warnings unless another blocking rule is hit.

## Validation and retries

There are three independent retry layers:

1. Model transport/API retry inside `call_deepseek()`.
2. One Stage 1 rewrite for severe KF count mismatch and one Stage 2 rewrite for blocking segment validation.
3. One outer reprocessing pass for episodes whose attempt ended in `error`.

This can multiply paid calls. Do not add another retry loop without calculating the worst-case call count.

Stage 2 blocking conditions include:

- no segments or segment count outside tolerance;
- fewer than 4 or more than 6 time slices;
- missing or invalid reference line;
- missing `站位延续`;
- severe/repeated dialogue density;
- missing source dialogue or reordered dialogue;
- large-view ratio over the hard limit.

Non-blocking warnings include low person-close share, limited strong-emotion close coverage, and some per-segment composition concerns.

## Safe change procedure

For any output-format or policy change:

1. Locate `STAGE1_PROMPT` or `STAGE2_PROMPT`.
2. Locate input builders that repeat the contract.
3. Locate counters, splitters, regexes, and validators.
4. Locate retry-note builders and human-facing error summaries.
5. Locate tests and frontend labels/download assumptions.
6. Create representative valid, borderline, and invalid samples.
7. Test parsers/validators locally before making a live paid model call.
8. Run one deliberately small live sample only when authorized and necessary.

Do not relax validation solely to make a weak model pass. Decide whether the prompt is unclear, the parser is brittle, or the policy is genuinely too strict, then change the appropriate layer.
