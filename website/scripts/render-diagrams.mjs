import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { chromium } from '@playwright/test';

const root = new URL('../../', import.meta.url);
const baseline = 'a662e8c04a6c03d1629d21ed538bb176bff609d1';
const hash = data => createHash('sha256').update(data).digest('hex');
const inputPaths = ['docs/assets/intpot-flow-label.svg', 'docs/assets/intpot-assessment.svg'];
const preservedPaths = ['intpot_image.webp', 'website/src/assets/intpot_image.webp'];
const sources = Object.fromEntries(await Promise.all(inputPaths.map(async path => [path, hash(await readFile(new URL(path, root)))])));
const preserved = Object.fromEntries(await Promise.all(preservedPaths.map(async path => [path, hash(await readFile(new URL(path, root)))])));
const manifestURL = new URL('docs/assets/diagram-manifest.json', root);
if (process.argv.includes('--check')) {
  const manifest = JSON.parse(await readFile(manifestURL, 'utf8'));
  for (const [path, digest] of Object.entries({ ...sources, ...preserved, ...manifest.outputs })) {
    if (hash(await readFile(new URL(path, root))) !== digest) throw Error(`Diagram drift: ${path}`);
  }
  for (const [path, digest] of Object.entries(sources)) if (manifest.sources[path] !== digest) throw Error(`Source not rendered: ${path}`);
  for (const [path, digest] of Object.entries(preserved)) if (manifest.preserved[path] !== digest) throw Error(`Preserved artwork changed: ${path}`);
  console.log('Diagram sources, derivatives and preserved artwork verified.');
} else if (process.argv.includes('--write')) {
  const old = execFileSync('git', ['show', `${baseline}:docs/assets/intpot-flow.png`], { cwd: root });
  const browser = await chromium.launch();
  const outputs = {};
  try {
    for (const [name, width, height] of [['intpot-flow', 2400, 1350], ['intpot-assessment', 2000, 1380]]) {
      const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
      const svg = await readFile(new URL(`docs/assets/${name === 'intpot-flow' ? 'intpot-flow-label' : name}.svg`, root), 'utf8');
      const background = name === 'intpot-flow' ? `<img src="data:image/png;base64,${old.toString('base64')}" style="position:absolute;inset:0;width:${width}px;height:${height}px">` : '';
      await page.setContent(`<html><head><style>html,body{margin:0;width:${width}px;height:${height}px}svg{position:absolute;inset:0}</style></head><body>${background}${svg}</body></html>`);
      await page.evaluate(() => Promise.all([...document.images].map(i => i.decode())));
      const overflows = await page.evaluate(() => [...document.querySelectorAll('svg text')].flatMap(text => {
        const b = text.getBBox(); const panel = text.closest('[data-panel]')?.querySelector('rect');
        if (!panel) return [];
        const p = panel.getBBox();return b.x < p.x + 15 || b.x+b.width > p.x+p.width-15 || b.y < p.y+10 || b.y+b.height>p.y+p.height-10 ? [text.textContent] : [];
      }));
      if (overflows.length) throw Error(`Clipped diagram labels: ${overflows.join('; ')}`);
      let png = await page.screenshot({ type: 'png' });
      if (name === 'intpot-flow') {
        // A whole-browser screenshot can change alpha/color management everywhere.
        // Composite only the approved badge crop into the original decoded pixels.
        const composite = 'import sys,json,io,base64;from PIL import Image;d=json.load(sys.stdin);a=Image.open(io.BytesIO(base64.b64decode(d["original"]))).convert("RGBA");b=Image.open(io.BytesIO(base64.b64decode(d["rendered"]))).convert("RGBA");r=(1009,564,1391,646);a.paste(b.crop(r),r);a.save(sys.stdout.buffer,format="PNG")';
        png = execFileSync('uv', ['run','--no-project','--python','3.11','--with','pillow','python','-c',composite], {
          input: JSON.stringify({original: old.toString('base64'), rendered: png.toString('base64')}), maxBuffer: 10*1024*1024,
        });
      }
      for (const path of [`docs/assets/${name}.png`, `website/public/${name}.png`]) {
        await mkdir(new URL('./', new URL(path, root)), { recursive: true });
        await writeFile(new URL(path, root), png);outputs[path] = hash(png);
      }
      await page.close();
    }
  } finally { await browser.close(); }
  await writeFile(manifestURL, JSON.stringify({ baseline, overviewEditBounds: [1009,564,1391,646], sources, outputs, preserved }, null, 2)+'\n');
  console.log('Rendered the label-only overview correction and supplementary assessment diagram.');
} else { throw Error('Use --write to render or --check to verify committed artifacts.'); }
