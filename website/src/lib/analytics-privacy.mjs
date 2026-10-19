export function sanitizeAnalyticsEvent(event) {
  const PRIVATE_CAMPAIGN_KEY = /campaign|utm_|(?:^|[_$])(fbc|fbp|gclid|dclid|fbclid|gbraid|wbraid|msclkid|ttclid|li_fat_id|twclid|gad_source|mc_cid|gclsrc|igshid|rdt_cid|epik|qclid|sccid|irclid|_kx)/i;
  const URL_KEY = /url|referrer|referring_domain|destination/i;
  function visit(value, key = '') {
    if (value instanceof Date) return value;
    if (Array.isArray(value)) return value.map((item) => visit(item));
    if (!value || typeof value !== 'object') {
      if (typeof value !== 'string') return value;
      if (PRIVATE_CAMPAIGN_KEY.test(key)) return undefined;
      if (/^(?:token|api_key)$/i.test(key)) return key === 'token' && /^phc_[A-Za-z0-9_]+$/.test(value) ? value : undefined;
      const domainKey = /(?:^|[_$])referring_domain$/i.test(key);
      if (domainKey && value === '$direct') return value;
      if (domainKey && /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/i.test(value)) return value.toLowerCase();
      const looksLikeUrl = /^(?:https?:)?\/\//i.test(value);
      if (!URL_KEY.test(key) && !looksLikeUrl) return value;
      try {
        const url = new URL(value);
        return /domain/i.test(key) ? url.hostname : url.origin + url.pathname;
      } catch { return undefined; }
    }
    const output = {};
    for (const [childKey, childValue] of Object.entries(value)) {
      if (PRIVATE_CAMPAIGN_KEY.test(childKey)) continue;
      const cleaned = visit(childValue, childKey);
      if (cleaned !== undefined) output[childKey] = cleaned;
    }
    return output;
  }
  return visit(event);
}

export const posthogScript = `!function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture identify alias people.set people.set_once people.unset reset opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing onFeatureFlags getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey captureException startSessionRecording stopSessionRecording sessionRecordingStarted capturePerformance captureTraceFeedback captureTraceMetric startExceptionCapture stopExceptionCapture".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);posthog.init('phc_qXkp5FBQfrqHQwkqf3ys8iSoGoMYw2tpTHXGugXJhP8V',{api_host:'https://us.i.posthog.com',defaults:'2026-05-30',person_profiles:'identified_only',capture_pageview:true,capture_pageleave:true,autocapture:false,disable_session_recording:true,save_campaign_params:false,save_referrer:false,advanced_disable_flags:true,capture_performance:true,before_send:function(event){return event?(${sanitizeAnalyticsEvent.toString()})(event):event}});`;
