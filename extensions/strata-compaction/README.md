# Strata bounded compaction hook

This local Pi extension replaces manual and automatic compaction only for
**`strata/qwen3.8-flash-next-iq3_xxs`**. It uses the [bounded core](core.README.md)
so an oversized conversation, individual message, tool argument, tool result or
previous summary cannot create an unbudgeted summary request. Other models keep
native behavior without counting, authentication or generation calls.

The extension is registered in the current Gentle Shell agent profile at
`C:/Users/daand/.gentle-shell/agent/settings.json`. Start a new Gentle process to load this revision; `/reload` alone can retain
previously loaded `.mjs` helpers. Select the Strata model
as usual; no special compaction command is required.

The exact-model reserve is **32768**, so automatic compaction triggers above
**98304 / 131072 tokens (75%)**. Normal conversation thinking remains unchanged;
only summary requests disable thinking. Installed packages and existing session
records were not edited.

`settings.fragment.json` shows the two intended settings. Merge its model override
and extension entry into existing settings; never replace unrelated overrides or
extension entries. To disable this integration, remove only this extension entry
and the added Strata reserve value, preserving any other model settings. Local
pre-change backups are in `.launcher-tests/strata-compaction/` under the project.

## Operation

- `/compact` and automatic threshold/overflow compaction share
  `session_before_compact`; optional `/compact` instructions are counted too.
- Native preparation decides what to summarize and retain. The hook summarizes
  `messagesToSummarize` plus `turnPrefixMessages`, never the retained tail.
- The previous summary, when present, is included in full. A first compaction
  with no earlier checkpoint uses current file tracking only; missing previous
  details are not an error. Successful results preserve `firstKeptEntryId` and
  `tokensBefore` verbatim; Pi alone persists the checkpoint.
- Any failure returns `{ cancel: true }`. Check the count endpoint/model and retry
  `/compact` after resolving the cause. There is no unbounded fallback, extension
  retry or partial custom checkpoint. Notification failures also cannot escape.

Native overflow recovery can persist omission bookkeeping before this hook runs.
The guarantee is no partial **custom compaction**, not zero native bookkeeping.

## Transport and bookkeeping contracts

| Area | Behavior |
|---|---|
| Model | Capture a deep snapshot of the exact selected model; do not change active model/thinking |
| Completion | Public `ctx.modelRegistry.complete`, not `streamSimple`; output reserve is `min(8192, model.maxTokens)`, never a remaining-context clamp |
| Context | Core's counted system/user text Context is passed directly to completion |
| Generation payload | Plain system/user strings; `chat_template_kwargs.enable_thinking = false`; competing top-level effort/thinking fields removed |
| Count | POST configured `model.baseUrl` + `/messages/count_tokens`, with system, user messages, model ID and `thinking: { type: 'disabled' }` |
| Authentication | Public `getApiKeyAndHeaders`; configured/resolved headers and resolved base-URL override are honored; no direct auth-file reads |
| Count timeout | 15 seconds per fetch, covering response-body parsing; caller abort is forwarded; timers/listeners are removed in `finally` |
| Prompt budget | Core enforces exact input + output reserve + 8 slack + 4096 safety <= model context window |
| Cache | Completion uses `cacheRetention: 'none'` |
| Usage | All successful core phases are aggregated into returned compaction usage |
| File tracking | Copy prepared sets, merge the matching latest branch compaction's file lists even with `fromHook: true`; deduplicate/sort and exclude modified paths from reads |

The adapter reuses public `convertToLlm`, `serializeConversation` and
`getLatestCompactionEntry`. Native serialization truncates tool results at 2000
characters, so tool results use the same serializer's non-truncating user-text
path with the tool-result label restored. Thinking and images are not sent to the
summary model. All budget-driven splitting/reduction remains in the core.

Native file-list/format helpers are not public exports. The hook's small file-list
union preserves their set semantics and native `<read-files>` / `<modified-files>`
format rather than importing unsupported internals or re-extracting tool calls.
Only file-tracking arrays are carried from prior details, not arbitrary unrelated
extension state. Prior file lists apply only when that compaction's summary
matches preparation's previous summary. Prepared sets and branch entries are
never mutated.

The adapter adds no storage or background work. Core limits (16 rounds, 256
completions and conservative no-progress termination) remain unchanged. Fetch
implementations must honor AbortSignal, as native fetch does. Failure notices use
fixed cause codes and stages, not raw provider diagnostics, payloads or credentials.

## Cancellation diagnostics

After updating the extension, start a new Gentle process for the affected session,
then try `/compact` once. Both automatic and manual cancellation now report:

```text
Strata compaction cancelled [CODE] at STAGE. Safe explanation. No custom checkpoint saved.
```

Share that warning's code and stage for diagnosis. Do not repeatedly retry an
unchanged failure. The diagnostic does not remove the protection, retry requests,
write session entries or change the context, output reserve or count timeout.

| Code | Meaning |
|---|---|
| `ABORTED` | The operation's AbortSignal was cancelled; not necessarily a user action |
| `MODEL_SNAPSHOT_FAILED` | The selected model could not be cloned before requests |
| `CONFIG_INVALID` | Unsupported model transport or count-timeout configuration |
| `PREPARATION_FAILED` | File tracking, source serialization or checkpoint construction failed; stage identifies which |
| `AUTH_UNAVAILABLE` / `AUTH_FAILED` | Credentials unavailable or public auth resolution failed |
| `COUNT_TIMEOUT` | The existing 15-second token-count deadline expired |
| `COUNT_HTTP` | Counter returned an HTTP failure; a validated numeric status may be shown |
| `COUNT_FAILED` / `COUNT_INVALID` | Counting failed or did not return a valid integer |
| `SUMMARY_LENGTH` | Summary generation reached its output limit |
| `SUMMARY_EMPTY` / `SUMMARY_NON_TEXT` | No usable plain-text summary was returned |
| `SUMMARY_FAILED` | Generation failed or did not end with a complete response |
| `REDUCTION_STALLED` / `ROUND_LIMIT` / `CALL_LIMIT` | Bounded reduction stopped without publishing partial output |
| `PROMPT_BUDGET` / `INPUT_INVALID` | Instructions/output budget cannot fit or source/settings are invalid |
| `UNEXPECTED_ERROR` | Unclassified error; only the fixed current stage is exposed |

Only locally assigned codes, fixed explanations, fixed stages and validated HTTP
status numbers are displayed. Exception text, response bodies, URLs, paths,
conversation text and authentication details remain private. Notification failure
still returns `{ cancel: true }` and never invokes native fallback. The original
generic warning cannot be retroactively assigned a cause; a new affected-session
attempt is needed. This diagnostic change does not claim to fix that unknown cause.

## Offline verification

```sh
node --test extensions/strata-compaction/adapter.test.mjs
node --check extensions/strata-compaction/adapter.mjs
node --test extensions/strata-compaction/*.test.mjs
```

Public hook tests inject the public-helper contracts, registry and fetch. They
cover manual/threshold/overflow success, complete large source inclusion, retained
metadata, previous-hook files, exact wire content, disabled thinking, unrelated
models, model switching, abort and failure cancellation. No real model, credential
or session is needed. A separate installed-Pi loader check validates `index.ts`.
A scratch copy of T2's base was compared with the new adapter for another model:
both produced identical exit/stdout/stderr, native continuation and zero I/O calls.

## Parent's isolated live-hook check

Use public `discoverAndLoadExtensions([absoluteIndexPath], scratch, scratch)` with
both project and agent directories set to a fresh system-temp directory. Obtain
`loaded.extensions[0].handlers.get('session_before_compact')[0]` and invoke it with:

- A synthetic event containing `reason: 'manual'`, an AbortSignal,
  `branchEntries: []`, optional custom instructions, and preparation with synthetic
  `messagesToSummarize`, `turnPrefixMessages`, `previousSummary`, `firstKeptEntryId`,
  `tokensBefore`, `fileOps: { read: new Set(), written: new Set(), edited: new Set() }`
  and ordinary compaction settings.
- A context containing the exact model obtained from the existing public registry,
  that `modelRegistry`, and an optional notification-only `ui`. No session manager
  or user's conversation is required. Do not persist the returned compaction.

Disable jiti disk caching (`JITI_FS_CACHE=0`) for the isolated loader process and
remove the scratch directory in teardown. Validate the returned boundary, usage
and file details; repeat with an aborted signal to confirm cancellation. The
initial plain-prompt parity check reported **74 counted = 74 generated prompt
tokens** with thinking disabled. The full live hook check subsequently passed:
**133 counted = 133 actual input tokens**, 32 output tokens, preserved boundaries
and cumulative file lists, abort returning cancellation with no further calls,
and an unrelated model returning a no-op. The hook used synthetic preparation
without a SessionManager or real conversation. Runtime setup used a read-only
in-memory CredentialStore with public ModelRuntime/ModelRegistry APIs; AuthStorage
is not exported from the package entry.

Independent verification passed the 42-test suite, syntax checks, isolated loader,
two additional public-helper probes and selective configuration-preservation check.
Registration readback confirmed that only the approved reserve and extension path
differ from the original settings. Oversized and multi-level cases are tested
offline; the user's original session was not compacted for verification. Repeat
the isolated checks before registering an updated implementation.
