import assert from 'node:assert/strict';
import test from 'node:test';

import { buildRepresentations, greet, shellQuote } from '../src/lib/greeting-playground.mjs';

test('greet matches the shipped example defaults and excited output', () => {
  assert.equal(greet('Ada'), 'Hello, Ada');
  assert.equal(greet('Ada', false), 'Hello, Ada');
  assert.equal(greet('Ada', true), 'Hello, Ada!');
});

test('interfaces carry both typed parameters and the string-returning greeting', () => {
  const views = buildRepresentations('Ada', true);
  assert.match(views.definition, /def greet\(name: str, excited: bool = False\) -> str:/);
  assert.match(views.cli, /intpot serve examples\/semantic_schema\.py --cli/);
  assert.match(views.cli, /greet --name 'Ada' --excited/);
  assert.deepEqual(JSON.parse(views.http), {
    method: 'POST', path: '/greet', body: { name: 'Ada', excited: true },
  });
  assert.deepEqual(JSON.parse(views.mcp), {
    name: 'greet', arguments: { name: 'Ada', excited: true },
  });
  assert.equal(views.result, greet('Ada', true));
});

test('default excitement is represented consistently across interfaces', () => {
  const views = buildRepresentations('Ada', false);
  assert.doesNotMatch(views.cli, /--excited/);
  assert.deepEqual(JSON.parse(views.http).body, { name: 'Ada', excited: false });
  assert.deepEqual(JSON.parse(views.mcp).arguments, { name: 'Ada', excited: false });
  assert.equal(views.result, 'Hello, Ada');
});

test('CLI names use POSIX single-quote escaping, not shell interpolation', () => {
  const name = "O'Brien $HOME `whoami`";
  assert.equal(shellQuote(name), "'O'\\''Brien $HOME `whoami`'");
  const command = buildRepresentations(name, true).cli.split('\n').at(-1);
  assert.equal(command, "greet --name 'O'\\''Brien $HOME `whoami`' --excited");
  assert.equal(greet(name, true), "Hello, O'Brien $HOME `whoami`!");
});
