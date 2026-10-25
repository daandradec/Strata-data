import test from 'node:test';
import assert from 'node:assert/strict';
import { registerStrataCompaction } from './adapter.ts';

const usage = { input: 10, output: 2, cacheRead: 0, cacheWrite: 0, totalTokens: 12,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } };
const response = (text = 'Summary') => ({ stopReason: 'stop', content: [{ type: 'text', text }], usage });
const user = text => ({ role: 'user', content: [{ type: 'text', text }] });
// Controlled public-helper contracts, including native tool-result truncation.
const serializeConversation = messages => messages.map(message => {
  const text = message.content.filter(c => c.type === 'text').map(c => c.text).join('');
  if (message.role === 'assistant') return message.content.map(c =>
    c.type === 'toolCall' ? `[Assistant tool calls]: ${c.name}(${JSON.stringify(c.arguments)})` : c.text ?? '').join('\n');
  return message.role === 'toolResult' ? `[Tool result]: ${text.slice(0, 2000)}` : `[User]: ${text}`;
}).join('\n\n');
const getLatestCompactionEntry = entries => entries.findLast(e => e.type === 'compaction');

function harness({ complete, fetchImpl, timeout = 1000 } = {}) {
  let hook;
  const counts = [], calls = [], notifications = [], converted = [];
  const controller = new AbortController();
  const event = { reason: 'manual', signal: controller.signal, customInstructions: 'Keep decisions.',
    branchEntries: [
      { type: 'compaction', summary: 'obsolete', details: { readFiles: ['obsolete'] } },
      { type: 'compaction', fromHook: true, summary: 'previous summary',
        details: { readFiles: ['old-read', 'now-written'], modifiedFiles: ['old-edited'] } },
      { type: 'message', message: user('RETAINED TAIL MUST NOT BE SUMMARIZED') },
    ],
    preparation: { messagesToSummarize: [user('history source')], turnPrefixMessages: [user('split prefix')],
      previousSummary: 'previous summary', firstKeptEntryId: 'keep-native-boundary', tokensBefore: 120000,
      fileOps: { read: new Set(['z-read', 'old-read', 'now-written']),
        written: new Set(['now-written']), edited: new Set(['a-edited']) },
      settings: { reserveTokens: 32768, keepRecentTokens: 20000, enabled: true } } };
  const model = { provider: 'strata', id: 'qwen3.8-flash-next-iq3_xxs', api: 'openai-completions',
    baseUrl: 'https://strata.invalid/custom/v1/', contextWindow: 131072, maxTokens: 8192,
    headers: { 'x-model-setting': 'preserved' }, reasoning: true };
  let authCalls = 0;
  const ctx = { model, hasUI: true, ui: { notify: (...args) => notifications.push(args) },
    modelRegistry: {
      getApiKeyAndHeaders: async snapshot => {
        authCalls++; assert.deepEqual(snapshot, model);
        return { ok: true, headers: { 'x-registry-setting': 'preserved' } };
      },
      complete: async (snapshot, context, options) => {
        calls.push({ snapshot, context, options });
        const original = { messages: [{ role: 'developer', content: 'wrong' }],
          reasoning_effort: 'high', reasoning: { effort: 'high' }, thinking: { type: 'enabled' },
          chat_template_kwargs: { preserved: true, enable_thinking: true } };
        const payload = await options.onPayload(original, snapshot);
        calls.at(-1).payload = payload ?? original;
        return complete ? complete(snapshot, context, options) : response();
      },
    } };
  registerStrataCompaction({ on(name, callback) {
    assert.equal(name, 'session_before_compact'); assert.equal(hook, undefined); hook = callback;
  } }, { convertToLlm: messages => { converted.push(messages); return messages; },
    serializeConversation, getLatestCompactionEntry, countTimeoutMs: timeout,
    fetch: async (url, options) => {
      const body = JSON.parse(options.body); counts.push({ url: String(url), options, body });
      if (fetchImpl) return fetchImpl(url, options, body);
      return { ok: true, json: async () => ({ input_tokens: body.system.length + body.messages[0].content.length }) };
    } });
  return { event, ctx, model, counts, calls, converted, notifications, controller,
    get authCalls() { return authCalls; }, run: () => hook(event, ctx) };
}

test('manual and automatic use one hook, retain native metadata and cumulative hook file tracking', async t => {
  for (const reason of ['manual', 'threshold', 'overflow']) await t.test(reason, async () => {
    const h = harness(); h.event.reason = reason;
    const before = { ...structuredClone(h.event), signal: h.event.signal };
    const result = await h.run();
    assert.deepEqual(result, { compaction: {
      summary: 'Summary\n\n<read-files>\nold-read\nz-read\n</read-files>\n\n<modified-files>\na-edited\nnow-written\nold-edited\n</modified-files>',
      firstKeptEntryId: before.preparation.firstKeptEntryId, tokensBefore: before.preparation.tokensBefore,
      usage, details: { readFiles: ['old-read', 'z-read'], modifiedFiles: ['a-edited', 'now-written', 'old-edited'] },
    } });
    assert.deepEqual(h.event, before);
    const source = h.calls[0].context.messages[1].content[0].text;
    for (const text of ['history source', 'split prefix', 'previous summary']) assert.ok(source.includes(text));
    assert.ok(!source.includes('RETAINED TAIL'));
    assert.ok(!result.compaction.details.readFiles.includes('obsolete'));
    assert.ok(h.calls[0].context.messages[0].content[0].text.includes('Keep decisions.'));
  });
});

test('count wire body matches canonical complete context and generation disables competing thinking', async () => {
  const h = harness(); await h.run();
  assert.equal(h.authCalls, 1);
  const { snapshot, context, options, payload } = h.calls[0];
  assert.notEqual(snapshot, h.model); assert.deepEqual(snapshot, h.model);
  const wire = context.messages.map(m => ({ role: m.role, content: m.content.map(c => c.text).join('') }));
  const count = h.counts.find(c => c.body.messages[0].content === wire[1].content);
  assert.deepEqual(count.body, { model: h.model.id, system: wire[0].content,
    messages: [wire[1]], thinking: { type: 'disabled' } });
  assert.equal(count.url, 'https://strata.invalid/custom/v1/messages/count_tokens');
  assert.equal(new Headers(count.options.headers).get('x-model-setting'), 'preserved');
  assert.equal(new Headers(count.options.headers).get('x-registry-setting'), 'preserved');
  assert.equal(count.options.method, 'POST');
  assert.deepEqual(payload.messages, wire);
  assert.deepEqual(payload.chat_template_kwargs, { preserved: true, enable_thinking: false });
  for (const field of ['reasoning_effort', 'reasoning', 'thinking']) assert.ok(!(field in payload));
  assert.equal(options.cacheRetention, 'none'); assert.equal(options.maxTokens, 8192);
  assert.equal(options.signal, h.event.signal);
  assert.equal(h.model.reasoning, true);
});

test('large history, split prefix, tool result and prior summary reach core without truncation', async () => {
  const h = harness();
  h.model.contextWindow = 4700; h.model.maxTokens = 32;
  h.event.preparation.previousSummary = 'PRIOR😀'.repeat(120);
  h.event.preparation.messagesToSummarize = [user('HISTORY😀'.repeat(130))];
  h.event.preparation.turnPrefixMessages = [
    user('PREFIX𐐀'.repeat(120)),
    { role: 'assistant', content: [{ type: 'toolCall', name: 'write', arguments: { path: 'synthetic', content: 'ARG😀'.repeat(500) } }] },
    { role: 'toolResult', content: [{ type: 'text', text: 'TOOL😀'.repeat(600) }] },
  ];
  const result = await h.run();
  assert.ok(result.compaction);
  const chunks = h.calls.filter(c => c.context.messages[1].content[0].text.startsWith('Source material:\n'));
  const source = chunks.map(c => c.context.messages[1].content[0].text.slice('Source material:\n'.length)).join('');
  for (const text of [h.event.preparation.previousSummary, 'HISTORY😀'.repeat(130),
    'PREFIX𐐀'.repeat(120), 'ARG😀'.repeat(500), 'TOOL😀'.repeat(600)]) assert.ok(source.includes(text));
  assert.ok(!source.includes('truncated'));
  assert.equal(result.compaction.usage.totalTokens, usage.totalTokens * h.calls.length);
});

test('unrelated providers and model IDs are strict no-ops, even without preparation or registry', async () => {
  for (const model of [undefined, { provider: 'other', id: 'qwen3.8-flash-next-iq3_xxs' },
    { provider: 'strata', id: 'different' }]) {
    const h = harness(); h.ctx.model = model;
    delete h.event.preparation; delete h.ctx.modelRegistry;
    assert.equal(await h.run(), undefined);
    assert.equal(h.counts.length, 0); assert.equal(h.calls.length, 0); assert.equal(h.authCalls, 0);
    assert.equal(h.notifications.length, 0); assert.equal(h.converted.length, 0);
  }
});

test('model snapshot survives an active model switch during async auth resolution', async () => {
  const h = harness();
  h.ctx.modelRegistry.getApiKeyAndHeaders = async () => {
    h.ctx.model = { provider: 'other', id: 'new-model' }; return { ok: true };
  };
  assert.ok((await h.run()).compaction);
  assert.equal(h.calls[0].snapshot.id, h.model.id);
  assert.equal(h.calls[0].snapshot.baseUrl, h.model.baseUrl);
});

test('count/generation failures and abort always cancel without later calls or native fallback', async t => {
  for (const failure of ['error', 'length', 'empty', 'abort', 'count', 'malformed-count', 'timeout', 'auth']) {
    await t.test(failure, async () => {
      const h = harness({ timeout: failure === 'timeout' ? 5 : 1000,
        complete: async () => {
          if (failure === 'abort') h.controller.abort();
          if (failure === 'error') throw new Error('private transport diagnostic');
          if (failure === 'length') return { ...response(), stopReason: 'length' };
          if (failure === 'empty') return response(' ');
          return response();
        },
        fetchImpl: async (_url, options) => {
          if (failure === 'timeout') return new Promise((_resolve, reject) => {
            options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
          });
          if (failure === 'count') return { ok: false, status: 503 };
          return { ok: true, json: async () => ({ input_tokens: failure === 'malformed-count' ? null : 1 }) };
        } });
      if (failure === 'auth') h.ctx.modelRegistry.getApiKeyAndHeaders = async () => ({ ok: false, error: 'private auth diagnostic' });
      // Pi may fall back when an extension throws or returns undefined: neither is allowed.
      let fallback = 0, result;
      try { result = await h.run(); if (!result?.cancel && !result?.compaction) fallback++; }
      catch { fallback++; }
      assert.deepEqual(result, { cancel: true }); assert.equal(fallback, 0);
      assert.equal(h.calls.length, ['count', 'malformed-count', 'timeout', 'auth'].includes(failure) ? 0 : 1);
      if (['count', 'malformed-count', 'timeout'].includes(failure)) assert.equal(h.counts.length, 1);
      if (failure === 'auth') assert.equal(h.counts.length, 0);
      assert.ok(!JSON.stringify(h.notifications).includes('private'));
    });
  }
});

test('pre-abort, count abort and notification failures cannot escape the cancellation guard', async () => {
  const before = harness(); before.controller.abort();
  assert.deepEqual(await before.run(), { cancel: true });
  assert.equal(before.authCalls, 0); assert.equal(before.counts.length, 0); assert.equal(before.calls.length, 0);
  const counting = harness({ fetchImpl: async () => {
    counting.controller.abort(); return { ok: true, json: async () => ({ input_tokens: 1 }) };
  } });
  counting.ctx.ui.notify = async () => { throw new Error('notification unavailable'); };
  assert.deepEqual(await counting.run(), { cancel: true });
  assert.equal(counting.counts.length, 1); assert.equal(counting.calls.length, 0);
});

test('cancellation reports a safe cause and stage without exposing private diagnostics', async t => {
  const privateText = 'SECRET https://private.invalid/token?key=secret C:/private/session.json';
  const cases = [
    ['snapshot', 'MODEL_SNAPSHOT_FAILED', 'snapshot', 'The selected model could not be snapshotted.'],
    ['serialization', 'PREPARATION_FAILED', 'serialization', 'Compaction input preparation failed.'],
    ['auth', 'AUTH_UNAVAILABLE', 'authentication', 'Model authentication is unavailable.'],
    ['auth-throw', 'AUTH_FAILED', 'authentication', 'Model authentication could not be resolved.'],
    ['count', 'COUNT_HTTP', 'count', 'Token-count endpoint returned HTTP 503.'],
    ['network', 'COUNT_FAILED', 'count', 'Token counting failed.'],
    ['timeout', 'COUNT_TIMEOUT', 'count', 'The token-count deadline expired.'],
    ['malformed', 'COUNT_INVALID', 'count', 'Token counter returned an invalid count.'],
    ['generation', 'SUMMARY_FAILED', 'generation', 'Summary generation failed.'],
    ['length', 'SUMMARY_LENGTH', 'generation', 'Summary reached its output token limit.'],
    ['empty', 'SUMMARY_EMPTY', 'generation', 'Model returned an empty summary.'],
    ['non-text', 'SUMMARY_NON_TEXT', 'generation', 'Model returned non-text content.'],
    ['budget', 'PROMPT_BUDGET', 'budget', 'Instructions and output reserve do not fit in the context.'],
    ['abort', 'ABORTED', 'preparation', 'The operation was aborted.'],
  ];
  for (const [failure, code, stage, detail] of cases) await t.test(failure, async () => {
    const h = harness({ timeout: failure === 'timeout' ? 5 : 1000,
      complete: async () => {
        if (failure === 'generation') throw new Error(privateText);
        if (failure === 'length') return { ...response(), stopReason: 'length', errorMessage: privateText };
        if (failure === 'empty') return response(' ');
        if (failure === 'non-text') return { ...response(), content: [{ type: 'thinking', thinking: privateText }] };
        return response();
      },
      fetchImpl: async (_url, options) => {
        if (failure === 'network') throw new Error(privateText);
        if (failure === 'timeout') return new Promise((_resolve, reject) => {
          options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
        });
        if (failure === 'count') return { ok: false, status: 503, text: async () => privateText };
        return { ok: true, json: async () => ({ input_tokens: failure === 'malformed' ? null : 1 }) };
      } });
    if (failure === 'snapshot') h.model.privateCallback = () => privateText;
    if (failure === 'serialization') h.event.preparation.messagesToSummarize = undefined;
    if (failure === 'auth') h.ctx.modelRegistry.getApiKeyAndHeaders = async () => ({ ok: false, error: privateText });
    if (failure === 'auth-throw') h.ctx.modelRegistry.getApiKeyAndHeaders = async () => { throw new Error(privateText); };
    if (failure === 'budget') h.model.contextWindow = 4096;
    if (failure === 'abort') h.controller.abort(new Error(privateText));
    const before = structuredClone(h.event.preparation);
    assert.deepEqual(await h.run(), { cancel: true });
    assert.deepEqual(h.event.preparation, before);
    assert.deepEqual(h.notifications, [[`Strata compaction cancelled [${code}] at ${stage}. ${detail} No custom checkpoint saved.`, 'warning']]);
    assert.ok(!JSON.stringify(h.notifications).includes('SECRET'));
    assert.ok(!JSON.stringify(h.notifications).includes('private.invalid'));
    assert.ok(!JSON.stringify(h.notifications).includes('C:/private'));
    assert.equal(h.calls.length, ['generation', 'length', 'empty', 'non-text'].includes(failure) ? 1 : 0);
  });
});

test('first compaction without a previous checkpoint succeeds and preserves current files', async () => {
  const h = harness();
  h.event.branchEntries = [];
  h.event.preparation.previousSummary = undefined;
  const before = structuredClone(h.event.preparation);
  const result = await h.run();
  assert.ok(result?.compaction, 'No previous checkpoint must not cancel the first compaction');
  assert.equal(result.compaction.firstKeptEntryId, before.firstKeptEntryId);
  assert.equal(result.compaction.tokensBefore, before.tokensBefore);
  assert.deepEqual(result.compaction.details, {
    readFiles: ['old-read', 'z-read'], modifiedFiles: ['a-edited', 'now-written'],
  });
  assert.deepEqual(result.compaction.usage, usage);
  assert.deepEqual(h.event.preparation, before);
  assert.equal(h.authCalls, 1); assert.equal(h.calls.length, 1); assert.equal(h.counts.length, 2);
  assert.deepEqual(h.notifications, []);
});
