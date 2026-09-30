import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

const posthogScript = `!function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture identify alias people.set people.set_once people.unset reset opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing onFeatureFlags getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey captureException startSessionRecording stopSessionRecording sessionRecordingStarted capturePerformance captureTraceFeedback captureTraceMetric startExceptionCapture stopExceptionCapture".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);posthog.init('phc_qXkp5FBQfrqHQwkqf3ys8iSoGoMYw2tpTHXGugXJhP8V',{api_host:'https://us.i.posthog.com',defaults:'2026-05-30',person_profiles:'identified_only',capture_pageview:true,capture_pageleave:true,autocapture:{dom_event_allowlist:['click'],element_allowlist:['a','button']},disable_session_recording:true});`;

export default defineConfig({
  site: 'https://intpot.modepot.io',
  integrations: [starlight({
    title: 'Intpot',
    description: 'Define typed Python tools once; expose CLI, API, and MCP interfaces.',
    favicon: '/intpot-mark.svg',
    social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/tugrulguner/intpot' }],
    customCss: ['./src/styles/custom.css'],
    head: [{ tag: 'script', attrs: {}, content: posthogScript }],
    sidebar: [
      { label: 'Start here', items: [{ slug: 'index', label: 'Overview' }, { slug: 'quickstart' }] },
      { label: 'Guides', items: [{ slug: 'capabilities' }] },
      { label: 'ModePot', link: 'https://modepot.io/' },
    ],
  })],
});
