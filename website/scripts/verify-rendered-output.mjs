import { readdir, readFile } from 'node:fs/promises';
import { join, relative } from 'node:path';

const distRoot = new URL('../dist/', import.meta.url).pathname;
const requiredPosthogConfig = [
  "posthog.init('phc_qXkp5FBQfrqHQwkqf3ys8iSoGoMYw2tpTHXGugXJhP8V'",
  "api_host:'https://us.i.posthog.com'",
  "defaults:'2026-05-30'",
  "person_profiles:'identified_only'",
  'capture_pageview:true',
  'capture_pageleave:true',
  "dom_event_allowlist:['click']",
  "element_allowlist:['a','button']",
  'disable_session_recording:true',
];

async function* htmlFiles(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) yield* htmlFiles(path);
    else if (entry.name.endsWith('.html')) yield path;
  }
}

const failures = [];
let htmlCount = 0;
for await (const path of htmlFiles(distRoot)) {
  htmlCount += 1;
  const html = await readFile(path, 'utf8');
  const outputPath = relative(distRoot, path);
  for (const setting of requiredPosthogConfig) {
    if (!html.includes(setting)) failures.push(`${relative(distRoot, path)}: missing ${setting}`);
  }
  if ((html.match(/posthog\.init\(/g) ?? []).length !== 1) {
    failures.push(`${relative(distRoot, path)}: expected exactly one PostHog initialization`);
  }
  if (outputPath === 'playground/index.html') {
    for (const token of ['One definition. Three ways in.', 'Run local preview', 'id="reset-request"', 'Browser-local preview', 'data-kind="CLI"', 'data-kind="HTTP"', 'data-kind="MCP"', 'id="request"', 'examples/semantic_schema.py', 'FastAPI', 'FastMCP']) {
      if (!html.includes(token)) failures.push(`${outputPath}: missing dedicated playground feature ${token}`);
    }
  }
  if (outputPath === 'index.html') {
    for (const token of ['Explore the interface playground', 'Open the interface playground →', 'href="/playground/"']) {
      if (!html.includes(token)) failures.push(`${outputPath}: missing playground route link ${token}`);
    }
    if (html.includes('data-playground')) failures.push(`${outputPath}: homepage duplicates the playground instead of linking to it`);
  }
  if (outputPath !== '404.html' && !html.includes('https://modepot.io/')) {
    failures.push(`${relative(distRoot, path)}: missing canonical ModePot return link`);
  }
  if (html.includes('modepot.com')) failures.push(`${relative(distRoot, path)}: stale ModePot domain`);
  for (const token of [
    'rel="alternate" type="text/plain" href="/llms.txt"',
    'property="og:image" content="https://intpot.modepot.io/social-card-v2.png"',
    'name="twitter:image" content="https://intpot.modepot.io/social-card-v2.png"',
  ]) {
    if (!html.includes(token)) failures.push(`${outputPath}: missing discovery metadata ${token}`);
  }
  const jsonLd = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/)?.[1];
  if (!jsonLd) {
    failures.push(`${outputPath}: missing JSON-LD`);
  } else {
    try {
      const data = JSON.parse(jsonLd);
      const types = new Set((data['@graph'] ?? [data]).map((node) => node['@type']));
      for (const type of ['SoftwareApplication', 'WebSite']) {
        if (!types.has(type)) failures.push(`${outputPath}: missing ${type} structured data`);
      }
    } catch (error) {
      failures.push(`${outputPath}: invalid JSON-LD (${error.message})`);
    }
  }
}

const llms = await readFile(join(distRoot, 'llms.txt'), 'utf8');
if (!llms.includes('https://modepot.io/')) failures.push('llms.txt: missing canonical ModePot URL');
if (llms.includes('modepot.com')) failures.push('llms.txt: stale ModePot domain');
for (const token of ['## Install', '## Quick start', '## Boundaries and license', 'https://pypi.org/project/intpot/', 'License: MIT']) {
  if (!llms.includes(token)) failures.push(`llms.txt: missing ${token}`);
}
const socialCard = await readFile(join(distRoot, 'social-card-v2.png'));
if (socialCard.readUInt32BE(16) !== 1200 || socialCard.readUInt32BE(20) !== 630) {
  failures.push('social-card-v2.png: expected 1200x630 PNG');
}
const notFound = await readFile(join(distRoot, '404.html'), 'utf8');
if (!notFound.includes('href="https://modepot.io/"')) {
  failures.push('404.html: missing canonical ModePot return link');
}
if (htmlCount === 0) failures.push('no rendered HTML files found');
if (failures.length) {
  console.error(failures.join('\n'));
  process.exitCode = 1;
} else {
  console.log(`Verified analytics and discovery metadata in ${htmlCount} rendered HTML files.`);
}