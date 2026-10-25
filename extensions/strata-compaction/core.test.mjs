import test from 'node:test';
import assert from 'node:assert/strict';
import { summarizeBounded } from './core.ts';

const tokens = context => context.messages.reduce((n, m) =>
  n + m.content.reduce((sum, c) => sum + [...c.text].length, 0), 0);
const usage = { input: 10, output: 2, cacheRead: 3, cacheWrite: 4,
  totalTokens: 19, cost: { input: 1, output: 2, cacheRead: 3, cacheWrite: 4, total: 10 } };
const response = (text = 'short') => ({ stopReason: 'stop',
  content: [{ type: 'text', text }], usage: structuredClone(usage) });
const material = context => context.messages[1].content[0].text.split('\n').slice(1).join('\n');

function harness(overrides = {}) {
  const counts = [], calls = [];
  const options = { parts: ['hello'], contextWindow: 6000, maxOutputTokens: 32,
    countTokens: async context => { counts.push(context); return tokens(context); },
    complete: async (context, options) => {
      calls.push({ context, options });
      return response();
    }, ...overrides };
  return { options, counts, calls, run: () => summarizeBounded(options) };
}

// Calibrate a deterministic exact counter at the public callback boundary.
async function boundaryOptions(extra = {}) {
  const probe = harness(extra);
  await probe.run();
  const prompt = probe.calls[0].context;
  return { ...extra, contextWindow: tokens(prompt) + 32 + 8 + 4096, maxOutputTokens: 32 };
}

test('exact boundary uses the same complete canonical prompt for counting and generation', async () => {
  const h = harness(await boundaryOptions());
  const result = await h.run();
  assert.deepEqual(result, { summary: 'short', usage });
  assert.equal(h.calls.length, 1);
  const { context, options } = h.calls[0];
  assert.ok(h.counts.includes(context));
  assert.deepEqual(context.messages.map(m => m.role), ['system', 'user']);
  assert.deepEqual(Object.keys(context), ['messages']);
  assert.ok(context.messages.every(m => m.content.every(c => c.type === 'text')));
  assert.equal(tokens(context) + options.maxTokens + 8 + 4096, h.options.contextWindow);
  assert.equal(options.maxTokens, 32);
  const defaults = harness({ contextWindow: undefined, maxOutputTokens: undefined });
  await defaults.run();
  assert.equal(defaults.calls[0].options.maxTokens, 8192);
  assert.ok(tokens(defaults.calls[0].context) + 8192 + 8 + 4096 <= 131072);
});

test('oversized individual parts and previous summary retain every character in order', async () => {
  const previousSummary = 'earlier😀'.repeat(40);
  const parts = ['USER😀'.repeat(150), 'tool-argument𐐀'.repeat(90), 'end'];
  const original = structuredClone(parts);
  const h = harness({ parts, previousSummary, contextWindow: 4700 });
  await h.run();
  const source = h.calls.filter(c => c.context.messages[1].content[0].text.startsWith('Source material:\n'));
  assert.ok(source.length > 2);
  assert.equal(source.map(c => material(c.context)).join(''),
    `Previous summary:\n${previousSummary}\n\nSource part 1:\n${parts[0]}\n\nSource part 2:\n${parts[1]}\n\nSource part 3:\nend`);
  for (const { context, options } of h.calls) {
    const text = material(context);
    assert.ok(!/^[\uDC00-\uDFFF]|[\uD800-\uDBFF]$/.test(text));
    assert.ok(tokens(context) + options.maxTokens + 8 + 4096 <= h.options.contextWindow);
    assert.ok(h.counts.includes(context));
  }
  assert.deepEqual(parts, original);
});

test('recursively reduces multiple levels and aggregates Pi usage without mutation', async () => {
  const replies = [];
  const h = harness({ parts: ['x'.repeat(12000)], contextWindow: 4700,
    complete: async (context, options) => {
      h.calls.push({ context, options });
      const reply = response('r'.repeat(90)); replies.push(reply); return reply;
    } });
  const result = await h.run();
  const reductions = h.calls.filter(c => c.context.messages[1].content[0].text.startsWith('Summaries to reduce:\n'));
  assert.ok(reductions.length > 1);
  assert.ok(reductions.some(c => material(c.context).includes('Summary 2:')));
  assert.equal(result.summary, 'r'.repeat(90));
  for (const key of ['input', 'output', 'cacheRead', 'cacheWrite', 'totalTokens']) {
    assert.equal(result.usage[key], usage[key] * h.calls.length);
  }
  for (const key of Object.keys(usage.cost)) assert.equal(result.usage.cost[key], usage.cost[key] * h.calls.length);
  assert.ok(replies.every(r => JSON.stringify(r.usage) === JSON.stringify(usage)));
});

test('previous summary and custom instructions consume the exact prompt budget', async () => {
  const extra = { previousSummary: 'prior decisions', customInstructions: 'Keep every important decision.' };
  const h = harness(await boundaryOptions(extra));
  await h.run();
  const context = h.calls[0].context;
  assert.ok(context.messages[0].content[0].text.includes(extra.customInstructions));
  assert.ok(material(context).includes(extra.previousSummary));
  assert.equal(tokens(context) + 32 + 8 + 4096, h.options.contextWindow);
});

test('rejects insufficient instruction-only space without completing', async () => {
  const h = harness({ contextWindow: 4200, customInstructions: 'z'.repeat(1000) });
  await assert.rejects(h.run(), /instruction.*space|instructions.*fit/i);
  assert.equal(h.calls.length, 0);
});

test('rejects unavailable, malformed and failing exact counts before generation', async t => {
  for (const value of [undefined, NaN, -1, 1.5, { tokens: 12 }, '12']) {
    await t.test(String(value), async () => {
      const h = harness({ countTokens: async () => value });
      await assert.rejects(h.run(), /count/i);
      assert.equal(h.calls.length, 0);
    });
  }
  const h = harness({ countTokens: async () => { throw new Error('counter offline'); } });
  await assert.rejects(h.run(), /counter offline/);
  assert.equal(h.calls.length, 0);
  const missing = harness({ countTokens: undefined });
  await assert.rejects(missing.run(), /countTokens/);
  assert.equal(missing.calls.length, 0);
  const late = harness({ parts: ['x'.repeat(2000)], contextWindow: 4700,
    countTokens: async context => {
      if (late.calls.length) throw new Error('counter failed after first phase');
      return tokens(context);
    } });
  await assert.rejects(late.run(), /counter failed after first phase/);
  assert.equal(late.calls.length, 1);
});

test('abort is checked before and after counting and completion', async t => {
  for (const stage of ['before', 'count', 'complete']) {
    await t.test(stage, async () => {
      const controller = new AbortController();
      let counts = 0;
      const h = harness({ signal: controller.signal,
        countTokens: async (context, options) => {
          assert.equal(options.signal, controller.signal);
          counts++; if (stage === 'count') controller.abort(); return tokens(context);
        },
        complete: async (context, options) => {
          assert.equal(options.signal, controller.signal);
          h.calls.push({ context, options }); controller.abort(); return response();
        } });
      if (stage === 'before') controller.abort();
      await assert.rejects(h.run(), /abort/i);
      assert.equal(h.calls.length, stage === 'complete' ? 1 : 0);
      if (stage === 'before') assert.equal(counts, 0);
    });
  }
});

test('generation failures never yield partial results or later completions', async t => {
  const failures = [
    ['error', { ...response(), stopReason: 'error', errorMessage: 'provider failed' }],
    ['aborted', { ...response(), stopReason: 'aborted' }],
    ['length', { ...response(), stopReason: 'length' }],
    ['empty', response('   ')],
    ['tool', { ...response(), content: [{ type: 'toolCall', name: 'unexpected' }] }],
    ['throw', null],
  ];
  for (const [name, reply] of failures) {
    await t.test(name, async () => {
      let calls = 0;
      const h = harness({ parts: ['x'.repeat(2000)], contextWindow: 4700,
        complete: async () => {
          calls++;
          if (calls === 1) return response();
          if (name === 'throw') throw new Error('generation offline');
          return reply;
        } });
      await assert.rejects(h.run(), /error|failed|aborted|length|empty|tool|offline/i);
      assert.equal(calls, 2);
    });
  }
});

test('terminates without progress or when the configured work bound is reached', async () => {
  let calls = 0;
  const noProgress = harness({ parts: ['x'.repeat(2000)], contextWindow: 4700,
    complete: async context => { calls++; return response(material(context)); } });
  await assert.rejects(noProgress.run(), /progress/i);
  const stoppedAt = calls;
  await Promise.resolve();
  assert.equal(calls, stoppedAt);
  const bounded = harness({ parts: ['x'.repeat(2000)], contextWindow: 4700, maxCompletions: 1 });
  await assert.rejects(bounded.run(), /limit|bound/i);
  assert.equal(bounded.calls.length, 1);
  const roundBound = harness({ parts: ['x'.repeat(2000)], contextWindow: 4700, maxRounds: 1 });
  await assert.rejects(roundBound.run(), /round limit/i);
  assert.ok(roundBound.calls.length > 1);
});
