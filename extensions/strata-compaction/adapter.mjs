import { summarizeBounded } from './core.mjs';

const PROVIDER = 'strata';
const MODEL = 'qwen3.8-flash-next-iq3_xxs';

function checkAbort(signal) {
  signal?.throwIfAborted();
}

// Only locally assigned codes and validated numeric status are public diagnostics.
class CountFailure extends Error {
  constructor(code, status) { super(code); this.code = code; this.status = status; }
}

function cancellationNotice(error, stage, aborted) {
  let code = 'UNEXPECTED_ERROR', detail = 'Compaction failed unexpectedly.';
  const message = typeof error?.message === 'string' ? error.message : '';
  const countFailure = error instanceof CountFailure ? error
    : error?.cause instanceof CountFailure ? error.cause : undefined;
  if (aborted) { code = 'ABORTED'; detail = 'The operation was aborted.'; }
  else if (stage === 'snapshot') { code = 'MODEL_SNAPSHOT_FAILED'; detail = 'The selected model could not be snapshotted.'; }
  else if (stage === 'authentication') {
    const unavailable = message === 'Strata request authentication is unavailable.';
    code = unavailable ? 'AUTH_UNAVAILABLE' : 'AUTH_FAILED';
    detail = unavailable ? 'Model authentication is unavailable.' : 'Model authentication could not be resolved.';
  } else if (countFailure) {
    code = countFailure.code;
    const status = countFailure.status;
    detail = code === 'COUNT_TIMEOUT' ? 'The token-count deadline expired.'
      : code === 'COUNT_HTTP' ? (Number.isInteger(status) && status >= 100 && status <= 599
        ? `Token-count endpoint returned HTTP ${status}.` : 'Token-count endpoint rejected the request.')
        : 'Token counting failed.';
  } else {
    const known = [
      ['Exact token count unavailable or malformed;', 'COUNT_INVALID', 'count', 'Token counter returned an invalid count.'],
      ['Summary generation rejected (length):', 'SUMMARY_LENGTH', 'generation', 'Summary reached its output token limit.'],
      ['Summary generation returned an empty summary.', 'SUMMARY_EMPTY', 'generation', 'Model returned an empty summary.'],
      ['Summary generation returned an unexpected tool call', 'SUMMARY_NON_TEXT', 'generation', 'Model returned non-text content.'],
      ['Summary generation returned malformed text', 'SUMMARY_NON_TEXT', 'generation', 'Model returned non-text content.'],
      ['Summarization made no progress;', 'REDUCTION_STALLED', 'reduction', 'Intermediate summaries did not shrink.'],
      ['Summarization round limit reached;', 'ROUND_LIMIT', 'reduction', 'Summary reduction reached its round limit.'],
      ['Summarization completion limit reached;', 'CALL_LIMIT', 'reduction', 'Summary reduction reached its completion limit.'],
      ['Insufficient instruction-only space;', 'PROMPT_BUDGET', 'budget', 'Instructions and output reserve do not fit in the context.'],
      ['No source character fits', 'PROMPT_BUDGET', 'budget', 'Instructions and output reserve do not fit in the context.'],
    ].find(([prefix]) => message.startsWith(prefix));
    if (known) [, code, stage, detail] = known;
    else if (stage === 'generation') { code = 'SUMMARY_FAILED'; detail = 'Summary generation failed.'; }
    else if (stage === 'count') { code = 'COUNT_FAILED'; detail = 'Token counting failed.'; }
    else if (stage === 'configuration') { code = 'CONFIG_INVALID'; detail = 'Model or count configuration is unsupported.'; }
    else if (stage === 'budget') { code = 'INPUT_INVALID'; detail = 'Compaction source or budget settings are invalid.'; }
    else if (['file-tracking', 'serialization', 'checkpoint'].includes(stage)) {
      code = 'PREPARATION_FAILED'; detail = 'Compaction input preparation failed.';
    }
  }
  return `Strata compaction cancelled [${code}] at ${stage}. ${detail} No custom checkpoint saved.`;
}

function plainMessages(context) {
  return context.messages.map(message => ({
    role: message.role, content: message.content.map(block => block.text).join(''),
  }));
}

function withoutThinking(payload, context) {
  const result = { ...payload, messages: plainMessages(context),
    chat_template_kwargs: { ...payload.chat_template_kwargs, enable_thinking: false } };
  // A provider/compat default must not override the explicitly disabled template.
  for (const key of ['reasoning_effort', 'reasoningEffort', 'reasoning', 'thinking', 'thinking_budget', 'enable_thinking']) {
    delete result[key];
  }
  return result;
}

function conversationParts(preparation, convertToLlm, serializeConversation) {
  const messages = convertToLlm([...preparation.messagesToSummarize, ...preparation.turnPrefixMessages]);
  return messages.map(message => {
    if (message.role !== 'toolResult') return serializeConversation([message]);
    // Native tool-result serialization truncates at 2000 characters. Reuse its
    // lossless text path instead; bounded splitting belongs exclusively to core.
    return serializeConversation([{ ...message, role: 'user' }]).replace(/^\[User\]:/, '[Tool result]:');
  }).filter(Boolean);
}

function cumulativeFiles(preparation, previous) {
  // Native fileOps already includes current/split/nested operations. Never mutate
  // those sets or re-extract operations with different tool-name/path rules.
  const read = new Set(preparation.fileOps.read);
  const modified = new Set([...preparation.fileOps.written, ...preparation.fileOps.edited]);
  const details = previous && previous.summary === preparation.previousSummary ? previous.details : undefined;
  for (const path of Array.isArray(details?.readFiles) ? details.readFiles : []) read.add(path);
  for (const path of Array.isArray(details?.modifiedFiles) ? details.modifiedFiles : []) modified.add(path);
  // Native helpers are not public exports. Keep their sorting, uniqueness and
  // modified-over-read precedence for these hook-owned details.
  return { readFiles: [...read].filter(path => !modified.has(path)).sort(), modifiedFiles: [...modified].sort() };
}

function fileTags({ readFiles, modifiedFiles }) {
  return [['read-files', readFiles], ['modified-files', modifiedFiles]]
    .filter(([, paths]) => paths.length)
    .map(([tag, paths]) => `\n\n<${tag}>\n${paths.join('\n')}\n</${tag}>`).join('');
}

async function countPrompt(context, { model, auth, fetch, signal, timeoutMs }) {
  checkAbort(signal);
  const url = new URL(auth.baseUrl ?? model.baseUrl);
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Count endpoint must use HTTP(S).');
  url.pathname = `${url.pathname.replace(/\/+$/, '')}/messages/count_tokens`;
  const headers = new Headers(model.headers);
  for (const [name, value] of new Headers(auth.headers)) headers.set(name, value);
  if (auth.apiKey && !headers.has('authorization')) headers.set('authorization', `Bearer ${auth.apiKey}`);
  headers.set('content-type', 'application/json');
  const [system, ...messages] = plainMessages(context);
  const controller = new AbortController();
  const onAbort = () => controller.abort(signal.reason);
  signal?.addEventListener('abort', onAbort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true; controller.abort(new Error('Exact count request timed out.'));
  }, timeoutMs);
  try {
    const response = await fetch(url, { method: 'POST', headers, signal: controller.signal,
      body: JSON.stringify({ model: model.id, system: system.content, messages, thinking: { type: 'disabled' } }) });
    controller.signal.throwIfAborted();
    if (!response.ok) throw new CountFailure('COUNT_HTTP', response.status);
    const body = await response.json();
    controller.signal.throwIfAborted();
    return body.input_tokens; // The core validates exact integer availability; never estimate.
  } catch (error) {
    if (signal?.aborted || error instanceof CountFailure) throw error;
    throw new CountFailure(timedOut ? 'COUNT_TIMEOUT' : 'COUNT_FAILED');
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }
}

/** Register one shared manual/automatic hook. All I/O is request-local. */
export function registerStrataCompaction(pi, {
  convertToLlm, serializeConversation, getLatestCompactionEntry,
  fetch = globalThis.fetch, countTimeoutMs = 15000,
}) {
  return pi.on('session_before_compact', async (event, ctx) => {
    let stage = 'preparation';
    try {
      const selected = ctx.model;
      if (selected?.provider !== PROVIDER || selected.id !== MODEL) return undefined;
      checkAbort(event.signal);
      stage = 'snapshot';
      const model = structuredClone(selected);
      stage = 'configuration';
      if (model.api !== 'openai-completions') throw new Error('Strata summary requires the verified OpenAI transport.');
      if (!Number.isSafeInteger(countTimeoutMs) || countTimeoutMs <= 0) throw new Error('Invalid count timeout.');
      const { preparation, signal } = event;
      stage = 'file-tracking';
      const details = cumulativeFiles(preparation, getLatestCompactionEntry(event.branchEntries));
      stage = 'serialization';
      const parts = conversationParts(preparation, convertToLlm, serializeConversation);
      stage = 'authentication';
      const auth = await ctx.modelRegistry.getApiKeyAndHeaders(model);
      checkAbort(signal);
      if (!auth.ok) throw new Error('Strata request authentication is unavailable.');
      stage = 'budget';
      const result = await summarizeBounded({
        parts, previousSummary: preparation.previousSummary, customInstructions: event.customInstructions, signal,
        contextWindow: model.contextWindow, maxOutputTokens: Math.min(8192, model.maxTokens),
        countTokens: (context, { signal }) => {
          stage = 'count';
          return countPrompt(context, { model, auth, fetch, signal, timeoutMs: countTimeoutMs });
        },
        complete: (context, { maxTokens, signal }) => {
          stage = 'generation';
          return ctx.modelRegistry.complete(model, context, {
            maxTokens, signal, cacheRetention: 'none',
            onPayload: payload => withoutThinking(payload, context),
          });
        },
      });
      checkAbort(signal);
      stage = 'checkpoint';
      return { compaction: {
        summary: result.summary + fileTags(details), usage: result.usage, details,
        firstKeptEntryId: preparation.firstKeptEntryId, tokensBefore: preparation.tokensBefore,
      } };
    } catch (error) {
      // Only fixed diagnostic text is displayed; provider errors stay private.
      // Even diagnostic/notification failures cannot escape into native fallback.
      try {
        await ctx.ui?.notify(cancellationNotice(error, stage, event.signal?.aborted), 'warning');
      } catch { /* Cancellation is authoritative even without a working UI. */ }
      return { cancel: true };
    }
  });
}
