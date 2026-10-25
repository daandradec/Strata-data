import { summarizeBounded } from './core.mjs';

const PROVIDER = 'strata';
const MODEL = 'qwen3.8-flash-next-iq3_xxs';

function checkAbort(signal) {
  signal?.throwIfAborted();
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
  const details = previous?.summary === preparation.previousSummary ? previous.details : undefined;
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
  const timer = setTimeout(() => controller.abort(new Error('Exact count request timed out.')), timeoutMs);
  try {
    const response = await fetch(url, { method: 'POST', headers, signal: controller.signal,
      body: JSON.stringify({ model: model.id, system: system.content, messages, thinking: { type: 'disabled' } }) });
    controller.signal.throwIfAborted();
    if (!response.ok) throw new Error('Exact count endpoint rejected the request.');
    const body = await response.json();
    controller.signal.throwIfAborted();
    return body.input_tokens; // The core validates exact integer availability; never estimate.
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
    try {
      const selected = ctx.model;
      if (selected?.provider !== PROVIDER || selected.id !== MODEL) return undefined;
      checkAbort(event.signal);
      const model = structuredClone(selected);
      if (model.api !== 'openai-completions') throw new Error('Strata summary requires the verified OpenAI transport.');
      if (!Number.isSafeInteger(countTimeoutMs) || countTimeoutMs <= 0) throw new Error('Invalid count timeout.');
      const { preparation, signal } = event;
      const details = cumulativeFiles(preparation, getLatestCompactionEntry(event.branchEntries));
      const parts = conversationParts(preparation, convertToLlm, serializeConversation);
      const auth = await ctx.modelRegistry.getApiKeyAndHeaders(model);
      checkAbort(signal);
      if (!auth.ok) throw new Error('Strata request authentication is unavailable.');
      const result = await summarizeBounded({
        parts, previousSummary: preparation.previousSummary, customInstructions: event.customInstructions, signal,
        contextWindow: model.contextWindow, maxOutputTokens: Math.min(8192, model.maxTokens),
        countTokens: (context, { signal }) => countPrompt(context, {
          model, auth, fetch, signal, timeoutMs: countTimeoutMs,
        }),
        complete: (context, { maxTokens, signal }) => ctx.modelRegistry.complete(model, context, {
          maxTokens, signal, cacheRetention: 'none',
          onPayload: payload => withoutThinking(payload, context),
        }),
      });
      checkAbort(signal);
      return { compaction: {
        summary: result.summary + fileTags(details), usage: result.usage, details,
        firstKeptEntryId: preparation.firstKeptEntryId, tokensBefore: preparation.tokensBefore,
      } };
    } catch {
      // Do not expose provider diagnostics, URLs, payloads or auth to notifications.
      // Even a failed notification must not escape: runner errors can fall back.
      try {
        await ctx.ui?.notify('Strata compaction cancelled without a custom checkpoint. Check the count endpoint/model availability, then retry /compact; cancellation and bounded-summary limits also cancel safely.', 'warning');
      } catch { /* Cancellation is authoritative even without a working UI. */ }
      return { cancel: true };
    }
  });
}
