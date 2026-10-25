# Bounded Strata summary core

`core.mjs` provides dependency-free, in-memory hierarchical summarization for T2
(S1–S3). It prevents oversized summary requests without truncating source text or
clamping summary output to one token. The T3 adapter owns model selection,
transport, native compaction boundaries, file tracking and persistence.

## Adapter quick path

```js
import { summarizeBounded } from './core.mjs';

const result = await summarizeBounded({
  parts: orderedSourceStrings,
  previousSummary,       // optional string; included before the ordered parts
  customInstructions,    // optional string; included in every prompt
  signal,
  countTokens: async (context, { signal }) => {
    // Count this exact Context using the generation transport's template settings.
    return exactIntegerTokenCount;
  },
  complete: async (context, { maxTokens, signal }) => {
    // Send this exact Context, with this output reserve, to the selected model.
    return assistantMessage;
  },
});
// Only now may the adapter publish result.summary and result.usage.
```

Both callbacks receive the canonical `{ messages }` Context: one `role: 'system'`
message and one `role: 'user'` message, each containing only
`{ type: 'text', text }` content. There is no top-level `systemPrompt`, tools or
images. The exact same Context object successfully counted is passed to
completion, not a separately rebuilt prompt. Callbacks must not mutate it.
The adapter must preserve this content and use matching count/generation
serialization, model and template settings; the core cannot verify a remote
counter's accuracy. Disable thinking and tools at the transport boundary.

## Contract and budget

| Input | Meaning / default |
|---|---|
| `parts` | Required ordered array of strings; caller serializes messages/tool arguments |
| `previousSummary` | Optional string, default `''`; ordinary source, not hidden context |
| `customInstructions` | Optional string, default `''`; counted in every system message |
| `countTokens` | Required async or sync callback returning a nonnegative safe integer, not an object or estimate |
| `complete` | Required async or sync callback returning a Pi-style AssistantMessage |
| `signal` | Optional AbortSignal, forwarded to both callbacks |
| `contextWindow` | Positive safe integer, default **131072** |
| `maxOutputTokens` | Positive safe integer, default **8192**; never automatically lowered |
| `maxRounds` | Positive safe integer, default **16**, including the final generation level |
| `maxCompletions` | Positive safe integer, default **256**, across all levels |

Every generated request must satisfy:

```text
exact complete-prompt count + maxOutputTokens + 8 Strata slack + 4096 safety <= contextWindow
```

The counter includes summarization instructions, custom instructions, previous
summary and source/reduction labels. Instruction-only probes reject impossible
budgets before generation. Prefix candidates use the same builder and budget.

The result is `{ summary, usage }`. Usage sums successful calls, including
intermediate calls, in Pi fields `input`, `output`, `cacheRead`, `cacheWrite`,
`totalTokens`, and `cost.{input,output,cacheRead,cacheWrite,total}`. Missing usage
fields contribute zero. Input arrays and returned provider usage are not mutated.

## Reduction and failure behavior

Source parts are labeled, concatenated in order, and split into exactly counted
fitting prefixes. Splitting can occur inside one huge message, tool argument or
prior summary, but never between the halves of a Unicode surrogate pair.
Concatenating the first-level payloads reconstructs the complete labeled source.
Summaries are labeled and recursively reduced until the entire final prompt fits.
All intermediate data stays in local memory; no session or filesystem is accessed.

The core throws on unavailable/malformed counts, callback errors, cancellation,
insufficient instruction space, inability to fit even one source character,
non-`stop` responses (including error/aborted/length), non-text/tool-call content,
or empty summaries. Output is never trimmed or truncated. Abort is checked before
and after every awaited callback; callbacks must honor the signal to interrupt
in-flight transport work. Rejection starts no later callback and exposes no
partial result. T3 must catch failure and return `cancel: true`, never fall back to
an unbounded native request or persist an intermediate summary.

Work is bounded by the round/completion limits. Each reduction level must shrink
the labeled material's UTF-16 length, otherwise it fails with a no-progress error.
This is deliberately conservative: even a potentially compressible run may be
rejected if its intermediate output does not shrink. Prefix search selects a
known-fitting candidate; it does not require strictly monotonic token counts or
promise optimal packing. Inputs remain in memory, so available process memory
still limits practical source size. There is no timer or background work.

## Verification scope

Run `node --test extensions/strata-compaction/core.test.mjs` for deterministic
public-API tests with injected callbacks; no model, network or persisted state is
used. Tests cover budget boundaries, complete source coverage, multiple reduction
levels, usage, instruction/prior-summary budgeting, abort, failures and bounded
termination. They do not establish live Strata counter/template parity; T3/T4 own
that integration. No history-based differential CLI check applies: this is a new
library component with no prior shared CLI or existing command behavior.
