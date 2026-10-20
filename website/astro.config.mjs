import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

import { posthogScript } from './src/lib/analytics-privacy.mjs';

const structuredData = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'SoftwareApplication',
      name: 'Intpot',
      applicationCategory: 'DeveloperApplication',
      operatingSystem: 'Python 3.11 or later',
      description: 'A typed Python interface framework that serves or converts one definition across CLI, HTTP API, and MCP.',
      url: 'https://intpot.modepot.io/',
      codeRepository: 'https://github.com/tugrulguner/intpot',
      installUrl: 'https://pypi.org/project/intpot/',
      license: 'https://opensource.org/license/mit',
      isPartOf: { '@type': 'Organization', name: 'ModePot', url: 'https://modepot.io/' },
    },
    { '@type': 'WebSite', name: 'Intpot documentation', url: 'https://intpot.modepot.io/', inLanguage: 'en' },
  ],
};

export default defineConfig({
  site: 'https://intpot.modepot.io',
  vite: { preview: { strictPort: true } },
  integrations: [starlight({
    title: 'Intpot',
    description: 'Define typed Python tools once; expose CLI, API, and MCP interfaces.',
    favicon: '/intpot-mark.svg',
    social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/tugrulguner/intpot' }],
    customCss: ['./src/styles/custom.css'],
    components: { Header: './src/components/FamilyHeader.astro', Head: './src/components/DocumentationHead.astro' },
    head: [
      { tag: 'script', attrs: {}, content: posthogScript },
      { tag: 'meta', attrs: { property: 'og:image', content: 'https://intpot.modepot.io/social-card-v2.png' } },
      { tag: 'meta', attrs: { property: 'og:image:width', content: '1200' } },
      { tag: 'meta', attrs: { property: 'og:image:height', content: '630' } },
      { tag: 'meta', attrs: { property: 'og:image:alt', content: 'Intpot: one typed Python definition, three interfaces' } },
      { tag: 'meta', attrs: { name: 'twitter:card', content: 'summary_large_image' } },
      { tag: 'meta', attrs: { name: 'twitter:image', content: 'https://intpot.modepot.io/social-card-v2.png' } },
      { tag: 'meta', attrs: { name: 'twitter:image:alt', content: 'Intpot: one typed Python definition, three interfaces' } },
      { tag: 'script', attrs: { type: 'application/ld+json' }, content: JSON.stringify(structuredData) },
    ],
    sidebar: [
      { label: 'Start here', items: [{ slug: 'index', label: 'Overview' }, { slug: 'quickstart' }, { slug: 'playground' }] },
      { label: 'Guides', items: [{ slug: 'build-an-app' }, { slug: 'conversion-boundaries' }, { slug: 'capabilities' }] },
      { label: 'Reference', items: [{ slug: 'schema-reference' }, { slug: 'architecture-internals' }, { slug: 'project/readme', label: 'Project README' }, { slug: 'project/roadmap', label: 'Project roadmap' }] },
    ],
  })],
});
