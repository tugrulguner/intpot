import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

const homepage = await readFile(new URL('../src/content/docs/index.mdx', import.meta.url), 'utf8');
const styles = await readFile(new URL('../src/styles/custom.css', import.meta.url), 'utf8');

test('homepage uses one consistent hero, install strip, honest playground, then deeper content', () => {
  const hero = homepage.indexOf('class="framework-hero"');
  const install = homepage.indexOf('class="installation-strip"');
  const demo = homepage.indexOf('class="project-demo"');
  const deeper = homepage.indexOf('## One definition, three ways to run');
  assert.ok(hero >= 0 && install > hero && demo > install && deeper > demo, 'hero → install → project demo → deeper content');
  for (const label of ['Quick start', 'Playground', 'GitHub', 'Created by Tugrul Guner', 'Browser-local preview', 'not Python execution']) assert.ok(homepage.includes(label), label);
  assert.match(homepage, /intpot_image\.webp/);
  assert.match(homepage, /intpot\[all\]/);
  assert.match(homepage, /aria-label="Primary actions"/);
  assert.match(homepage, /aria-label="Installation"/);
  assert.match(homepage, /aria-label="Project demonstration"/);
  assert.ok(styles.includes('.framework-hero'));
  assert.ok(styles.includes('@media (max-width: 50rem)'));
});
