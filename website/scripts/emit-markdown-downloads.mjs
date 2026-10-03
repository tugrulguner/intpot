import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';

const root = new URL('../src/content/docs/', import.meta.url);
const out = new URL('../dist/downloads/', import.meta.url);
const pages = [
  'build-an-app.md',
  'conversion-boundaries.md',
  'schema-reference.md',
  'architecture-internals.md',
];

await mkdir(out, { recursive: true });
for (const page of pages) {
  const markdown = await readFile(new URL(page, root), 'utf8');
  const destination = new URL(page, out);
  await mkdir(dirname(destination.pathname), { recursive: true });
  await writeFile(destination, markdown);
}
const index = `<!doctype html><html lang="en"><meta charset="utf-8"><title>Intpot Markdown guides</title><h1>Intpot Markdown guides</h1><ul>${pages.map((page) => `<li><a href="${page}">${page.replaceAll('-', ' ').replace('.md', '')}</a></li>`).join('')}</ul></html>`;
await writeFile(new URL('index.html', out), index);
console.log(`Emitted ${pages.length} downloadable Markdown guides from canonical Starlight sources.`);
