import { mkdirSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const evidence = process.env.PLAYGROUND_EVIDENCE_DIR ?? new URL('../../evidence/family-design-system/intpot/', import.meta.url).pathname;
mkdirSync(evidence, { recursive: true });

test('family typography and shapes render consistently across homepage, docs, and playground', async ({ page }) => {
  for (const route of ['/', '/quickstart/', '/playground/']) {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(route);
    await page.evaluate(async () => {
      await document.fonts.ready;
      await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
    });
    const result = await page.evaluate(() => {
      const heading = document.querySelector<HTMLElement>(location.pathname === '/playground/' ? '[data-playground] h1' : location.pathname === '/' ? '.hero h1' : 'main h1')!;
      const familyLink = [...document.querySelectorAll<HTMLAnchorElement>('header a')].find((link) => link.textContent?.trim() === 'ModePot');
      const actions = [...document.querySelectorAll<HTMLElement>('.hero .sl-link-button, .actions button')];
      const headingStyle = getComputedStyle(heading);
      return { font: getComputedStyle(document.body).fontFamily, headingSize: Number.parseFloat(headingStyle.fontSize), headingCase: headingStyle.textTransform, familyHref: familyLink?.getAttribute('href'), headerFamilyLinks: [...document.querySelectorAll('header a')].filter((link) => link.textContent?.trim() === 'ModePot').length, actionRadii: actions.map((action) => Number.parseFloat(getComputedStyle(action).borderTopLeftRadius)) };
    });
    expect(result.font).toContain('Avenir Next');
    expect(result.headingSize).toBeLessThanOrEqual(56);
    expect(result.headingCase).toBe('none');
    expect(result.familyHref).toBe('https://modepot.io/');
    expect(result.headerFamilyLinks).toBe(1);
    if (route !== '/quickstart/') {
      expect(result.actionRadii.length).toBeGreaterThan(0);
      expect(result.actionRadii.every((radius) => radius === 6)).toBe(true);
    }
  }
});

test('home, docs, and playground honor manual opposite-OS themes and Auto at family viewport bounds', async ({ page }) => {
  for (const route of ['/', '/quickstart/', '/playground/']) {
    for (const viewport of [{ width: 1280, height: 900 }, { width: 768, height: 768 }, { width: 320, height: 390 }]) {
      await page.setViewportSize(viewport);
      await page.goto(route);
      for (const theme of ['light', 'dark'] as const) {
        await page.emulateMedia({ colorScheme: theme === 'light' ? 'dark' : 'light', reducedMotion: 'reduce' });
        await page.locator('starlight-theme-select select').first().selectOption(theme);
        await page.evaluate(async () => {
          await document.fonts.ready;
          await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        });
        const reading = await page.evaluate(() => {
          const heading = document.querySelector<HTMLElement>(location.pathname === '/playground/' ? '[data-playground] h1' : location.pathname === '/' ? '.hero h1' : 'main h1')!;
          const family = document.querySelector<HTMLElement>('.modepot-return')!;
          const opaqueBackground = (element: HTMLElement) => {
            let current: HTMLElement | null = element;
            while (current) {
              const value = getComputedStyle(current).backgroundColor;
              if (value !== 'rgba(0, 0, 0, 0)' && value !== 'transparent') return value;
              current = current.parentElement;
            }
            return 'rgb(255, 255, 255)';
          };
          const candidates = [heading, family, ...document.querySelectorAll<HTMLElement>('.hero .sl-link-button.primary, .run, .reset, .interface-nav button, .output-nav button')];
          const checks = candidates.map((element) => {
            const style = getComputedStyle(element);
            let background = style.backgroundColor;
            if (background === 'rgba(0, 0, 0, 0)' || background === 'transparent') background = opaqueBackground(element);
            const rgb = (input: string) => (input.match(/[0-9.]+/g) ?? []).slice(0, 3).map(Number);
            const lum = (input: string) => rgb(input).map((v) => v / 255).map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
            const fg = lum(style.color); const bg = lum(background);
            return { text: element.textContent?.trim().slice(0, 48), ratio: (Math.max(fg, bg) + .05) / (Math.min(fg, bg) + .05) };
          });
          return { theme: document.documentElement.dataset.theme, font: getComputedStyle(document.body).fontFamily, documentWidth: document.documentElement.scrollWidth, bodyWidth: document.body.scrollWidth, checks };
        });
        expect(reading.theme).toBe(theme);
        expect(reading.font).toContain('Avenir Next');
        expect(reading.documentWidth).toBeLessThanOrEqual(viewport.width);
        expect(reading.bodyWidth).toBeLessThanOrEqual(viewport.width);
        for (const check of reading.checks) expect(check.ratio, `${route} ${theme}: ${JSON.stringify(check)}`).toBeGreaterThanOrEqual(4.5);
        await page.screenshot({ path: `${evidence}${route === '/' ? 'home' : route.slice(1, -1)}-${viewport.width}-${theme}-reduce.png`, fullPage: true });
      }
      await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'no-preference' });
      await page.locator('starlight-theme-select select').first().selectOption('auto');
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
      await page.screenshot({ path: `${evidence}${route === '/' ? 'home' : route.slice(1, -1)}-${viewport.width}-auto.png`, fullPage: true });
      await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'no-preference' });
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    }
  }
});
