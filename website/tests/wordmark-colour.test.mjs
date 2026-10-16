import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const svg = await readFile(new URL('../../assets/intpot-lockup.svg', import.meta.url), 'utf8');
const card = await readFile(new URL('../public/social-card.svg', import.meta.url), 'utf8');
const compact = await readFile(new URL('../public/intpot-mark.svg', import.meta.url), 'utf8');

for (const [name, source] of [['canonical lockup', svg], ['social preview source', card]]) {
  test(`${name} uses continuous off-white int + amber pot wordmark`, () => {
    const match = source.match(/<text\b[^>]*>[\s\S]*?<\/text>/g)?.find((element) => element.includes('int'));
    assert.ok(match, 'wordmark text exists');
    assert.match(match, /fill="#F4F2EA"/);
    assert.match(match, /<tspan\b[^>]*fill="#F2B84B"[^>]*>pot<\/tspan>/);
    assert.equal(match.replace(/<[^>]+>/g, '').match(/intpot/)?.[0], 'intpot');
  });
}

test('compact mark remains unchanged and contains no wordmark suffix', () => {
  assert.match(compact, /#F2B84B/);
  assert.doesNotMatch(compact, /<text\b/);
});
