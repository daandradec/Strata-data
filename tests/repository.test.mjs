import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, isAbsolute, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { after, test } from 'node:test';

const root = fileURLToPath(new URL('../', import.meta.url));
const parent = resolve(tmpdir());
const fixture = mkdtempSync(join(parent, 'strata-ignore-policy-'));
after(() => {
  const rel = relative(parent, resolve(fixture));
  assert.ok(rel && !isAbsolute(rel) && !rel.startsWith('..'));
  assert.ok(basename(fixture).startsWith('strata-ignore-policy-'));
  rmSync(fixture, { recursive: true, force: true });
});

const gitOptions = { cwd: fixture, encoding: 'utf8', windowsHide: true };
execFileSync('git', ['init', '--quiet'], gitOptions);
writeFileSync(join(fixture, '.gitignore'), readFileSync(join(root, '.gitignore')));

function ignored(path) {
  const result = spawnSync('git', ['-c', 'core.excludesFile=', 'check-ignore', '--quiet', '--no-index', '--', path], gitOptions);
  assert.ok(result.status === 0 || result.status === 1, result.stderr || String(result.error));
  return result.status === 0;
}

const sourcePaths = [
  '.gitignore', '.gitattributes', 'README.md',
  'docs/backup-and-restore.md',
  'tests/repository.test.mjs', 'tests/test_launchers.py',
  'start_model_qwen.ps1', 'start_web_strata.ps1',
  'extensions/strata-compaction/index.ts',
  'extensions/strata-compaction/adapter.ts',
  'extensions/strata-compaction/core.ts',
  'extensions/strata-compaction/adapter.test.mjs',
  'extensions/strata-compaction/README.md',
  'extensions/strata-compaction/settings.fragment.json',
  'odd/tasks/strata-compaction.md',
  'odd/tasks/strata-compaction-reload.md',
  'odd/tasks/strata-dedicated-port.md',
];

test('the explicit source allowlist includes launchers, all maintained tasks and repository configuration', () => {
  for (const path of sourcePaths) assert.equal(ignored(path), false, `Source must not be ignored: ${path}`);
});

test('runtime data and unknown root files stay outside Git', () => {
  for (const path of [
    'models/model.gguf', 'packs/iq3_xxs/experts.bin', 'mtp/rt/experts.bin',
    'logs/server.log', 'pip-cache/entry', '.launcher-tests/backup/manifest.json',
    '.codegraph/graph.db', '.atl/state.json', 'tmp-rkh-evaluation/result.json',
    'launcher-verification.json', 'strata-iq3_xxs.json', 'unknown/new-file.txt',
    'extensions/another-extension/index.ts', 'odd/tasks/private-notes.md',
    '.github/workflows/verify.yml', '.github/workflows/new-workflow.yaml',
  ]) assert.equal(ignored(path), true, `Runtime data must be ignored: ${path}`);
});

test('secrets, weights, local state and build output are ignored even inside allowed directories', () => {
  const generated = [
    '.env', '.env.local', '.env.example', 'auth.json', 'credentials.json',
    'secrets.json', 'id_rsa', 'id_ed25519', 'private.pem', 'private.key',
    'certificate.p12', 'certificate.pfx', 'session.jsonl', 'server.log',
    'server.pid', 'checkpoint.tmp', 'download.part', 'config.bak',
    'worker.out', 'worker.err', 'cache.db', 'cache.sqlite3', 'module.pyc',
    'node_modules/pkg/index.js', 'nested/node_modules/pkg/index.js',
    '.venv/Scripts/python.exe', '__pycache__/module.pyc',
    '.pytest_cache/state', '.cache/state', '.codegraph/graph.db', '.atl/state',
    'coverage/summary.json', 'dist/output.js', 'build/output.o',
    'weights.gguf', 'weights.safetensors', 'experts.bin', 'engine.dll', 'model.zip',
  ];
  for (const directory of ['extensions/strata-compaction', 'docs', 'tests']) {
    for (const path of generated) {
      assert.equal(ignored(`${directory}/${path}`), true, `Generated/private file must be ignored: ${directory}/${path}`);
    }
  }
});

test('the Git index contains no ignored payload, binary data, oversized files or obvious secret tokens', () => {
  const paths = execFileSync('git', ['ls-files', '-z'], { cwd: root, encoding: 'utf8', windowsHide: true })
    .split('\0').filter(Boolean);
  for (const path of sourcePaths) assert.ok(paths.includes(path), `Required source is not versioned: ${path}`);
  assert.equal(paths.some(path => path.startsWith('.github/workflows/')), false, 'GitHub Actions is intentionally not used');
  const markers = [
    /-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/,
    /github_pat_[A-Za-z0-9_]{30,}/,
    /gh[pousr]_[A-Za-z0-9]{30,}/,
    /\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/,
    /\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b/,
  ];
  for (const path of paths) {
    assert.equal(ignored(path), false, `Ignored file is tracked: ${path}`);
    const bytes = execFileSync('git', ['show', `:${path}`], { cwd: root, windowsHide: true, maxBuffer: 2 * 1024 * 1024 });
    assert.ok(bytes.length <= 1024 * 1024, `File exceeds the 1 MiB source limit: ${path}`);
    assert.equal(bytes.includes(0), false, `Binary payload is tracked: ${path}`);
    // High-signal guard only: manual review is still required before publication.
    for (const marker of markers) assert.equal(marker.test(bytes.toString('utf8')), false, `Potential secret in: ${path}`);
  }
});
