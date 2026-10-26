import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import test from 'node:test';
const root = new URL('../../', import.meta.url);
const text = path => readFile(new URL(path, root), 'utf8');

test('assessment placements supplement rather than replace the overview', async () => {
  for (const path of ['README.md', 'website/src/content/docs/index.mdx']) {
    const source = await text(path);
    assert.ok(source.includes('intpot-flow.png'), path);
    assert.ok(source.indexOf('intpot-assessment.png') > source.indexOf('intpot-flow.png'), path);
    assert.match(source, /ApplicationSchema/, path);
    assert.ok(!source.includes('normalized ToolInfo schema'), path);
  }
  const guide = await text('website/src/content/docs/conversion-boundaries.md');
  assert.ok(guide.includes('intpot-assessment.png'));
  assert.ok(guide.includes('full-size assessment diagram'));
});

test('README assessment belongs to conversion, before community and roadmap', async () => {
  const source = await text('README.md');
  const sections = [
    '## Convert an existing app',
    '## Conversion assessment before output',
    '## Give your coding agent intpot context',
    '## What conversion preserves',
    '## Actionable binding context (v0.13.0)',
    '## Missing body bindings (v0.11)',
    '## Bounded helper recovery (v0.11)',
    '## Architecture',
    '## Community',
    '## Roadmap',
    '## Support intpot',
    '## License',
  ];
  let previous = -1;
  for (const section of sections) {
    const position = source.indexOf(section + '\n');
    assert.ok(position > previous, `${section} must follow the preceding section`);
    previous = position;
  }
});

test('diagram sources, PNG derivatives and original branding stay in sync', async () => {
  const manifest = JSON.parse(await text('docs/assets/diagram-manifest.json'));
  for (const [path, digest] of Object.entries({...manifest.sources,...manifest.outputs,...manifest.preserved})) {
    assert.equal(createHash('sha256').update(await readFile(new URL(path,root))).digest('hex'),digest,path);
  }
  for (const name of ['intpot-flow','intpot-assessment']) {
    assert.deepEqual(await readFile(new URL(`docs/assets/${name}.png`,root)),await readFile(new URL(`website/public/${name}.png`,root)));
  }
  execFileSync(process.execPath,['website/scripts/render-diagrams.mjs','--check'],{cwd:root});
  const svg=await text('docs/assets/intpot-assessment.svg');
  for (const token of ['missing_annotation_binding',"names=['Model']",'Scaffold permission cannot bypass','Detection imports trusted code','No type evaluation']) assert.ok(svg.includes(token),token);
});
