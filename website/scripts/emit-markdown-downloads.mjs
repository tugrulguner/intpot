import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';

const root = new URL('../src/content/docs/', import.meta.url);
const out = new URL('../dist/downloads/', import.meta.url);
const pages = [
  { file: 'build-an-app.md', label: 'Build and run an Intpot app' },
  { file: 'conversion-boundaries.md', label: 'Convert, inspect, and eject applications' },
  { file: 'schema-reference.md', label: 'Schema and parameter reference' },
  { file: 'architecture-internals.md', label: 'Architecture internals' },
];

const escapeHtml = (value) => value.replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

await mkdir(out, { recursive: true });
for (const { file } of pages) {
  const markdown = await readFile(new URL(file, root), 'utf8');
  const destination = new URL(file, out);
  await mkdir(dirname(destination.pathname), { recursive: true });
  await writeFile(destination, markdown);
}
const description = 'Find and download Intpot’s canonical Markdown guide exports for building apps, converting frameworks, using the schema reference, and understanding internals.';
const index = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="${escapeHtml(description)}">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="https://intpot.modepot.io/downloads/">
  <title>Intpot Markdown exports</title>
</head>
<body>
  <main>
    <h1>Download Intpot guides as Markdown</h1>
    <p>These files are the canonical Markdown sources for Intpot’s detailed guides. They preserve the full guide text for offline reading, editors, and coding agents.</p>
    <ul>${pages.map(({ file, label }) => `<li><a href="/downloads/${escapeHtml(file)}">${escapeHtml(label)} (Markdown)</a></li>`).join('\n      ')}</ul>
    <p>For an overview and links to the documentation, see <a href="/">Intpot documentation</a>. For the agent-oriented discovery map, read <a href="/llms.txt">the Intpot agent discovery map</a>.</p>
  </main>
</body>
</html>
`;
await writeFile(new URL('index.html', out), index);
console.log(`Emitted ${pages.length} downloadable Markdown guides from canonical Starlight sources.`);
