import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://intpot.modepot.io',
  integrations: [starlight({
    title: 'Intpot',
    description: 'Define typed Python tools once; expose CLI, API, and MCP interfaces.',
    favicon: '/intpot-mark.svg',
    social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/tugrulguner/intpot' }],
    customCss: ['./src/styles/custom.css'],
    sidebar: [
      { label: 'Start here', items: [{ slug: 'index', label: 'Overview' }, { slug: 'quickstart' }] },
      { label: 'Guides', items: [{ slug: 'capabilities' }] }
    ],
  })],
});
