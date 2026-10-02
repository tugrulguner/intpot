import assert from 'node:assert/strict';
import test from 'node:test';
import { defaultRequests, parseRequest, runRequest, shellQuote } from '../src/lib/greeting-playground.mjs';

test('all three bounded request contracts call the same typed function', () => {
  const drafts = defaultRequests('Ada', true);
  for (const kind of ['CLI', 'HTTP', 'MCP']) {
    const output = runRequest(kind, drafts[kind]);
    assert.deepEqual(output.args, { name: 'Ada', excited: true });
    assert.equal(output.result, 'Hello, Ada!');
    assert.deepEqual(output.trace, [`${kind} request parsed`, 'Typed arguments: name="Ada", excited=true', 'Same function: greet(name, excited)']);
  }
  assert.deepEqual(runRequest('HTTP', drafts.HTTP).response, { status: 200, body: 'Hello, Ada!' });
  assert.deepEqual(runRequest('MCP', drafts.MCP).response.structuredContent, { result: 'Hello, Ada!' });
});

test('accepts canonical default and rejects invalid route, tool, fields and types', () => {
  assert.equal(runRequest('HTTP', JSON.stringify({ method: 'POST', path: '/greet', body: { name: 'Lin' } })).result, 'Hello, Lin');
  assert.throws(() => parseRequest('HTTP', JSON.stringify({ method: 'GET', path: '/greet', body: { name: 'Lin' } })), /POST \/greet/);
  assert.throws(() => parseRequest('HTTP', JSON.stringify({ method: 'POST', path: '/other', body: { name: 'Lin' } })), /POST \/greet/);
  assert.throws(() => parseRequest('MCP', JSON.stringify({ name: 'delete', arguments: { name: 'Lin' } })), /greet MCP tool/);
  assert.throws(() => parseRequest('MCP', JSON.stringify({ name: 'greet', arguments: { name: 'Lin', extra: 1 } })), /Only name and excited/);
  assert.throws(() => parseRequest('HTTP', JSON.stringify({ method: 'POST', path: '/greet', body: { name: 4 } })), /name must be/);
  assert.throws(() => parseRequest('HTTP', JSON.stringify({ method: 'POST', path: '/greet', body: { name: 'Lin', excited: 'yes' } })), /excited must be a boolean/);
  assert.throws(() => parseRequest('MCP', '{'), /valid JSON/);
  assert.throws(() => parseRequest('HTTP', 'x'.repeat(513)), /512 characters/);
});

test('CLI grammar rejects other commands and shell quoting preserves literal input', () => {
  assert.throws(() => parseRequest('CLI', "rm --name 'Ada'"), /greet command/);
  assert.throws(() => parseRequest('CLI', "greet Ada --output x"), /Unsupported CLI argument/);
  assert.equal(shellQuote("O'Brien $HOME `whoami`"), "'O'\\''Brien $HOME `whoami`'");
  const raw = `greet ${shellQuote("O'Brien $HOME `whoami`")} --excited`;
  assert.deepEqual(parseRequest('CLI', raw), { name: "O'Brien $HOME `whoami`", excited: true });
  assert.equal(runRequest('CLI', raw).result, "Hello, O'Brien $HOME `whoami`!");
});

test('CLI quoting follows shell lexical escaping without executing expansions', () => {
  assert.equal(parseRequest('CLI', String.raw`greet Ada\ Lovelace`).name, 'Ada Lovelace');
  assert.equal(parseRequest('CLI', String.raw`greet "Ada\q"`).name, String.raw`Ada\q`);
  assert.equal(parseRequest('CLI', String.raw`greet "Ada\"Lovelace"`).name, 'Ada"Lovelace');
  assert.throws(() => parseRequest('CLI', "greet '' --excited"), /non-empty/);
  assert.throws(() => parseRequest('CLI', "greet Ada\\"), /Trailing shell escape/);
});

test('workbench exposes all interfaces, shared definition, focused editable request, and truthful boundary', async () => {
  const { readFile } = await import('node:fs/promises');
  const page = await readFile(new URL('../src/components/GreetingPlayground.astro', import.meta.url), 'utf8');
  for (const marker of ['functionDefinition', 'data-kind="CLI"', 'data-kind="HTTP"', 'data-kind="MCP"', 'role="tablist"', 'id="request"', 'Run local preview', 'id="reset-request"', 'browser-local preview', 'FastAPI', 'FastMCP', '/quickstart/', 'semantic_schema.py']) assert.ok(page.includes(marker), marker);
  assert.ok(!page.includes('<details'));
  assert.ok(!page.includes('fetch('));
});
