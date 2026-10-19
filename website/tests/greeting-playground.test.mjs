import assert from 'node:assert/strict';
import test from 'node:test';
import { defaultRequests, parseRequest, runRequest, shellQuote } from '../src/lib/greeting-playground.mjs';
import { sanitizeAnalyticsEvent, posthogScript } from '../src/lib/analytics-privacy.mjs';
import vm from 'node:vm';

test('serialized PostHog before_send sanitizes the real SDK event envelope', () => {
  const posthog = { init(_key, config) { this.config = config; } };
  const document = { createElement() { return {}; }, getElementsByTagName() { return [{ parentNode: { insertBefore() {} } }]; } };
  const context = { document, window: { posthog }, posthog, URL, Date };
  vm.runInNewContext(posthogScript, context);
  const event = { event: '$pageview', properties: { token: 'phc_public', '$current_url': 'https://site.example/path/?utm_source=SECRET#HASH', '$initial_referring_domain': 'ref.example', '$referring_domain': 'modepot.io', '$session_referring_domain': '$direct', '$session_entry_utm_source': 'SECRET', '$session_exit_gclid': 'SECRET' }, timestamp: new Date('2026-01-01T00:00:00Z') };
  const config = posthog._i[0][1];
  assert.equal(config.capture_performance, true);
  const clean = config.before_send(event);
  assert.equal(clean.properties.token, 'phc_public');
  assert.equal(clean.properties.$current_url, 'https://site.example/path/');
  assert.equal(clean.properties.$initial_referring_domain, 'ref.example');
  assert.equal(clean.properties.$referring_domain, 'modepot.io');
  assert.equal(clean.properties.$session_referring_domain, '$direct');
  assert.ok(!JSON.stringify(clean).includes('SECRET'));
  assert.ok(clean.timestamp instanceof Date);
});

test('analytics scrubs URL sentinels in event and nested acquisition properties', () => {
  const event = { event: '$pageview', timestamp: new Date('2026-01-02T00:00:00Z'), properties: {
    '$current_url': 'https://intpot.modepot.io/playground/?secret=URL_SENTINEL#URL_HASH',
    '$initial_referrer': 'https://search.example/find?q=REFERRER_SENTINEL#FRAGMENT',
    '$set': { '$initial_referrer': 'https://evil.example/?secret=NESTED_SENTINEL', '$initial_referring_domain': 'evil.example', '$utm_source': 'SOURCE_SENTINEL', '$initial_utm_source': 'INITIAL_SOURCE_SENTINEL' },
    '$set_once': { '$initial_referrer': 'https://evil.example/?secret=ONCE_SENTINEL', '$gclid': 'CLICK_SENTINEL', '$initial_utm_source': 'ONCE_SOURCE_SENTINEL' },
    '$session_entry_utm_source': 'SESSION_SOURCE_SENTINEL', '$session_entry_gclid': 'SESSION_CLICK_SENTINEL', '$session_exit_utm_source': 'EXIT_SOURCE_SENTINEL',
    '$gad_source': 'GAD_SENTINEL', '$mc_cid': 'MC_SENTINEL', '$gclsrc': 'GCLSRC_SENTINEL', '$igshid': 'IG_SENTINEL', '$rdt_cid': 'RDT_SENTINEL', '$epik': 'EPIK_SENTINEL', '$qclid': 'QCLID_SENTINEL', '$sccid': 'SCCID_SENTINEL', '$irclid': 'IR_SENTINEL', '$_kx': 'KX_SENTINEL',
    '$referring_domain': 'modepot.io', '$initial_referring_domain': '$direct', '$direct_domain': '$direct', '$host': 'intpot.modepot.io',
    arbitrary_domain: 'not a valid domain', '$bad_referring_domain': 'modepot.io?secret=DOMAIN_SENTINEL',
  } };
  const clean = sanitizeAnalyticsEvent(event);
  const encoded = JSON.stringify(clean);
  for (const sentinel of ['URL_SENTINEL','URL_HASH','REFERRER_SENTINEL','FRAGMENT','NESTED_SENTINEL','SOURCE_SENTINEL','INITIAL_SOURCE_SENTINEL','ONCE_SENTINEL','CLICK_SENTINEL','ONCE_SOURCE_SENTINEL','SESSION_SOURCE_SENTINEL','SESSION_CLICK_SENTINEL','EXIT_SOURCE_SENTINEL','GAD_SENTINEL','MC_SENTINEL','GCLSRC_SENTINEL','IG_SENTINEL','RDT_SENTINEL','EPIK_SENTINEL','QCLID_SENTINEL','SCCID_SENTINEL','IR_SENTINEL','KX_SENTINEL','DOMAIN_SENTINEL']) assert.ok(!encoded.includes(sentinel), sentinel);
  assert.equal(clean.properties.$current_url, 'https://intpot.modepot.io/playground/');
  assert.equal(clean.properties.$referring_domain, 'modepot.io');
  assert.equal(clean.properties.$direct_domain, '$direct');
  assert.equal(clean.properties.$initial_referring_domain, '$direct');
  assert.equal(clean.properties.arbitrary_domain, 'not a valid domain');
  assert.ok(!('$bad_referring_domain' in clean.properties));
  assert.equal(clean.properties.$host, 'intpot.modepot.io');
  assert.ok(clean.timestamp instanceof Date);
});

test('analytics retains public SDK tokens but omits private credential-shaped fields', () => {
  const clean = sanitizeAnalyticsEvent({ properties: { token: 'phc_public', api_key: 'PRIVATE', nested: { token: 'PRIVATE' } } });
  assert.equal(clean.properties.token, 'phc_public');
  assert.ok(!JSON.stringify(clean).includes('PRIVATE'));
});

test('analytics removes campaign strings and prefixed advertising cookie identifiers', () => {
  const event = { properties: { token: 'phc_public', $initial_campaign: 'PRIVATE', $fbc: 'PRIVATE', $initial_fbp: 'PRIVATE', $session_entry_fbc: 'PRIVATE', $set_once: { $session_exit_campaign: 'PRIVATE' } } };
  const clean = sanitizeAnalyticsEvent(event);
  assert.equal(clean.properties.token, 'phc_public');
  assert.ok(!JSON.stringify(clean).includes('PRIVATE'));
});

test('analytics scrubs URL strings under arbitrary property names and nested arrays', () => {
  const event = { properties: { extra: 'https://x/path?PRIVATE#PRIVATE', entries: [{ value: 'https://y/path?PRIVATE#PRIVATE' }], token: 'phc_public' } };
  const clean = sanitizeAnalyticsEvent(event);
  const encoded = JSON.stringify(clean);
  assert.ok(!encoded.includes('PRIVATE'));
  assert.equal(clean.properties.extra, 'https://x/path');
  assert.equal(clean.properties.entries[0].value, 'https://y/path');
  assert.equal(clean.properties.token, 'phc_public');
});

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
  assert.equal((page.match(/class="output-view"/g) ?? []).length, 4);
  assert.match(page, /aria-label="Output views"/);
  assert.match(page, /id="output-panel" role="tabpanel"/);
  assert.match(page, /id="computed"/);
  assert.match(page, /\.inspector\{[^}]*height:/);
  assert.ok(!page.includes('<details class="definition'));
  assert.ok(!page.includes('fetch('));
});
