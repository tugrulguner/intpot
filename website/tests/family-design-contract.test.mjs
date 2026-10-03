import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import assert from 'node:assert/strict';

const contract = JSON.parse(await readFile(new URL('../family-design-contract.json', import.meta.url), 'utf8'));
const css = await readFile(new URL('../src/styles/custom.css', import.meta.url), 'utf8');

test('family foundation uses the canonical shared font and maps light/dark values to public mp tokens', () => {
  assert.ok(css.includes(`--mp-font: ${contract.font};`));
  assert.ok(css.includes(`--mp-font-code: ${contract.fontCode};`));
  for (const [key, value] of Object.entries(contract.light)) assert.ok(css.includes(`--mp-${key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}: ${value};`), `missing light ${key}`);
  for (const [key, value] of Object.entries(contract.dark)) assert.ok(css.includes(`--mp-${key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}: ${value};`), `missing dark ${key}`);
  assert.ok(css.includes(`--mp-radius: ${contract.shape.radiusPx}px;`));
  assert.ok(css.includes(`--mp-header-height: ${contract.shape.headerHeightPx}px;`));
  assert.ok(css.includes(`--mp-content-max: ${contract.shape.contentMaxPx}px;`));
});
