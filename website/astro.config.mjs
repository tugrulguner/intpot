import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

const posthogScript = `!function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture identify alias people.set people.set_once people.unset reset opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing onFeatureFlags getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey captureException startSessionRecording stopSessionRecording sessionRecordingStarted capturePerformance captureTraceFeedback captureTraceMetric startExceptionCapture stopExceptionCapture".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);posthog.init('phc_qXkp5FBQfrqHQwkqf3ys8iSoGoMYw2tpTHXGugXJhP8V',{api_host:'https://us.i.posthog.com',defaults:'2026-05-30',person_profiles:'identified_only',capture_pageview:true,capture_pageleave:true,autocapture:{dom_event_allowlist:['click'],element_allowlist:['a','button']},disable_session_recording:true});`;

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
    components: { Header: './src/components/FamilyHeader.astro' },
    head: [
      { tag: 'script', attrs: {}, content: posthogScript },
      { tag: 'link', attrs: { rel: 'alternate', type: 'text/plain', href: '/llms.txt', title: 'Intpot summary for AI agents' } },
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
      { label: 'Reference', items: [{ slug: 'schema-reference' }, { slug: 'architecture-internals' }] },
    ],
  })],
});
