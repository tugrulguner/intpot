import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const websiteRoot = fileURLToPath(new URL('..', import.meta.url));
const repoRoot = join(websiteRoot, '..');
const outputRoot = join(websiteRoot, 'src/content/docs/project');
const repository = execFileSync('git', ['config', '--get', 'remote.origin.url'], { cwd: repoRoot, encoding: 'utf8' }).trim().replace(/\.git$/, '');
const revision = process.env.GITHUB_SHA || execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repoRoot, encoding: 'utf8' }).trim();
const identity = process.env.DOCS_SOURCE_IDENTITY || `repository snapshot (not published-release metadata; ${revision.slice(0, 12)})`;

for (const sourceName of ['README.md', 'ROADMAP.md']) {
  const text = await readFile(join(repoRoot, sourceName), 'utf8');
  const base = `${repository}/blob/${revision}/`;
  const rewritten = text.replace(/(!?)\[([^\]]*)\]\((?!https?:|mailto:|#)([^)]+)\)/g, (_match, image, label, target) => {
    const destination = image ? `${repository.replace('github.com/', 'raw.githubusercontent.com/')}/${revision}/${target}` : `${base}${target}`;
    return `${image}[${label}](${destination})`;
  }).replace(/(<img\b[^>]*?\bsrc=["'])(?!https?:|data:)([^"']+)(["'])/gi, (_match, before, target, after) => `${before}${repository.replace('github.com/', 'raw.githubusercontent.com/')}/${revision}/${target}${after}`);
  const slug = sourceName.toLowerCase().replace('.md', '');
  const title = slug === 'readme' ? 'Project README' : 'Project roadmap';
  const content = `---\ntitle: ${title}\ndescription: "Generated from the repository ${sourceName}; source identity: ${identity}."\n---\n\n> **Source:** [${sourceName}](${base}${sourceName}) at \`${revision}\`. This is a repository snapshot, not a claim about the latest published release.\n\n${rewritten}`;
  const destination = join(outputRoot, `${slug}.md`);
  await mkdir(dirname(destination), { recursive: true });
  await writeFile(destination, content);
}
console.log(`Synchronized README.md and ROADMAP.md from ${revision} (${identity}).`);
