import { mkdirSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const evidence = process.env.PLAYGROUND_EVIDENCE_DIR ?? new URL('../../evidence/family-design-system/intpot/', import.meta.url).pathname;
mkdirSync(evidence, { recursive: true });

test('compact header keeps Intpot identity and every control visible and hittable', async ({ page }) => {
  for (const route of ['/', '/quickstart/', '/playground/']) {
    for (const width of [320, 390, 400, 401]) {
      await page.setViewportSize({ width, height: 390 });
      await page.goto(route);
      await page.evaluate(async () => {
        await document.fonts.ready;
        await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
      });
      const audit = await page.evaluate(() => {
        const brand = document.querySelector<HTMLElement>('.title-wrapper');
        const title = brand?.innerText?.trim();
        const bounds = brand?.getBoundingClientRect();
        const titleElement = brand?.querySelector<HTMLElement>('a');
        const titleBounds = titleElement?.getBoundingClientRect();
        const controls = [...document.querySelectorAll<HTMLElement>('.header a, .header button, .header select, .header input, starlight-menu-button button')]
          .filter((element) => element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden');
        return {
          title,
          titleVisible: Boolean(titleBounds && bounds && titleBounds.left >= bounds.left && titleBounds.right <= bounds.right && titleBounds.width > 35),
          canonicalMark: brand?.querySelector<HTMLImageElement>('.intpot-mark')?.getAttribute('src'),
          themeIconsVisible: [...document.querySelectorAll<SVGElement>('starlight-theme-select svg')].some((icon) => icon.getClientRects().length > 0 && getComputedStyle(icon).visibility !== 'hidden' && getComputedStyle(icon).display !== 'none'),
          headerBackground: getComputedStyle(document.querySelector('header.header')!).backgroundColor,
          raisedBackground: getComputedStyle(document.documentElement).getPropertyValue('--mp-raised').trim(),
          controls: controls.map((element) => {
            const rect = element.getBoundingClientRect();
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;
            const hit = document.elementFromPoint(centerX, centerY);
            return { text: element.textContent?.trim() || element.getAttribute('aria-label') || element.tagName, width: rect.width, height: rect.height, centerHit: hit === element || element.contains(hit), hitElement: hit?.tagName + (hit instanceof HTMLElement ? `.${hit.className}` : '') };
          }),
        };
      });
      expect(audit.title).toBe('Intpot');
      expect(audit.titleVisible, `${route} ${width}: ${JSON.stringify(audit)}`).toBe(true);
      expect(audit.canonicalMark).toBe('/intpot-mark.svg');
      expect(audit.themeIconsVisible).toBe(false);
      expect(audit.headerBackground).toBe(audit.raisedBackground === '#eceef1' ? 'rgb(236, 238, 241)' : 'rgb(41, 45, 51)');
      for (const control of audit.controls) {
        expect(control.width, `${route} ${width}: ${JSON.stringify(control)}`).toBeGreaterThan(0);
        expect(control.height, `${route} ${width}: ${JSON.stringify(control)}`).toBeGreaterThanOrEqual(44);
        expect(control.centerHit, `${route} ${width}: ${JSON.stringify(control)}`).toBe(true);
      }
      for (const theme of ['light', 'dark'] as const) {
        await page.emulateMedia({ colorScheme: theme === 'light' ? 'dark' : 'light', reducedMotion: 'reduce' });
        await page.locator('starlight-theme-select select').first().selectOption(theme);
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
        await page.evaluate(async () => {
          await document.fonts.ready;
          await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        });
        const palette = await page.evaluate(() => ({
          background: getComputedStyle(document.querySelector('header.header')!).backgroundColor,
          raised: getComputedStyle(document.documentElement).getPropertyValue('--mp-raised').trim(),
        }));
        expect(palette.background, `${theme}: ${JSON.stringify(palette)}`).toBe(theme === 'light' ? 'rgb(236, 238, 241)' : 'rgb(41, 45, 51)');
        expect(palette.raised).toBe(theme === 'light' ? '#eceef1' : '#292d33');
        const routeName = route === '/' ? 'home' : route.slice(1, -1);
        await page.screenshot({ path: `${evidence}${routeName}-header-${width}-${theme}-reduce.png`, clip: { x: 0, y: 0, width, height: 64 } });
      }
    }
  }
});

test('every visible header control meets 44px target size and search boundary contrast at all family widths', async ({ page }) => {
  for (const route of ['/', '/quickstart/', '/playground/']) {
    for (const width of [1280, 768, 320]) {
      await page.setViewportSize({ width, height: 768 });
      await page.goto(route);
      const audit = await page.evaluate(() => {
        const visible = (element: HTMLElement) => element.getClientRects().length > 0 && getComputedStyle(element).visibility !== 'hidden';
        const candidates = [...document.querySelectorAll<HTMLElement>('.header a, .header button, .header select, .header input, starlight-menu-button button')].filter(visible);
        const search = document.querySelector<HTMLElement>('.header starlight-search button, .header button[data-open-modal]');
        const rgb = (value: string) => (value.match(/[0-9.]+/g) ?? []).slice(0, 3).map(Number);
        const lum = (value: string) => rgb(value).map((v) => v / 255).map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
        let parent: HTMLElement | null = search;
        let background = 'rgb(255, 255, 255)';
        while (parent) { const value = getComputedStyle(parent).backgroundColor; if (value !== 'rgba(0, 0, 0, 0)' && value !== 'transparent') { background = value; break; } parent = parent.parentElement; }
        const border = search ? getComputedStyle(search).borderTopColor : '';
        const ratio = search && border ? (Math.max(lum(border), lum(background)) + .05) / (Math.min(lum(border), lum(background)) + .05) : 0;
        return { controls: candidates.map((el) => ({ name: el.getAttribute('aria-label') || el.textContent?.trim() || el.tagName, width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height })), searchFound: Boolean(search), ratio };
      });
      expect(audit.controls.length, `${route} ${width}`).toBeGreaterThan(0);
      for (const control of audit.controls) {
        expect(control.width, `${route} ${width}: ${JSON.stringify(control)}`).toBeGreaterThanOrEqual(44);
        expect(control.height, `${route} ${width}: ${JSON.stringify(control)}`).toBeGreaterThanOrEqual(44);
      }
      expect(audit.searchFound, `${route} ${width}: search button`).toBe(true);
      expect(audit.ratio, `${route} ${width}: search border contrast`).toBeGreaterThanOrEqual(3);
      await page.locator('starlight-theme-select select').first().selectOption('dark');
      const darkRatio = await page.evaluate(() => {
        const search = document.querySelector<HTMLElement>('.header starlight-search button, .header button[data-open-modal]')!;
        const rgb = (value: string) => (value.match(/[0-9.]+/g) ?? []).slice(0, 3).map(Number);
        const lum = (value: string) => rgb(value).map((v) => v / 255).map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
        const border = getComputedStyle(search).borderTopColor;
        const background = getComputedStyle(search).backgroundColor;
        return (Math.max(lum(border), lum(background)) + .05) / (Math.min(lum(border), lum(background)) + .05);
      });
      expect(darkRatio, `${route} ${width}: dark search border contrast`).toBeGreaterThanOrEqual(3);
      if (width === 1280) {
        await page.keyboard.press('Tab');
        await page.keyboard.press('Tab');
        await page.keyboard.press('Tab');
        const searchButton = page.getByRole('button', { name: 'Search' });
        await expect(searchButton).toBeFocused();
        await expect(searchButton).toHaveCSS('outline-style', 'solid');
      }
    }
  }
});

test('family typography and shapes render consistently across homepage, docs, and playground', async ({ page }) => {
  for (const route of ['/', '/quickstart/', '/playground/']) {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(route);
    await page.evaluate(async () => {
      await document.fonts.ready;
      await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
    });
    const result = await page.evaluate(() => {
      const heading = document.querySelector<HTMLElement>(location.pathname === '/playground/' ? '[data-playground] h1' : location.pathname === '/' ? '.framework-hero h1' : 'main h1')!;
      const familyLink = [...document.querySelectorAll<HTMLAnchorElement>('.family-resources a')].find((link) => link.textContent?.trim() === 'ModePot');
      const actions = [...document.querySelectorAll<HTMLElement>('.framework-actions .framework-action, .actions button')];
      const headingStyle = getComputedStyle(heading);
      return { font: getComputedStyle(document.body).fontFamily, headingSize: Number.parseFloat(headingStyle.fontSize), headingCase: headingStyle.textTransform, familyHref: familyLink?.getAttribute('href'), headerFamilyLinks: document.querySelectorAll('.family-resources a[href="https://modepot.io/"]').length, actionRadii: actions.map((action) => Number.parseFloat(getComputedStyle(action).borderTopLeftRadius)) };
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
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
        await page.evaluate(async () => {
          await document.fonts.ready;
          await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        });
        const reading = await page.evaluate(() => {
          const heading = document.querySelector<HTMLElement>(location.pathname === '/playground/' ? '[data-playground] h1' : location.pathname === '/' ? '.framework-hero h1' : 'main h1')!;
          const family = document.querySelector<HTMLElement>('.family-resources a[href="https://modepot.io/"], .family-menu-panel a[href="https://modepot.io/"]')!;
          const opaqueBackground = (element: HTMLElement) => {
            let current: HTMLElement | null = element;
            while (current) {
              const value = getComputedStyle(current).backgroundColor;
              if (value !== 'rgba(0, 0, 0, 0)' && value !== 'transparent') return value;
              current = current.parentElement;
            }
            return 'rgb(255, 255, 255)';
          };
          const candidates = [heading, family, ...document.querySelectorAll<HTMLElement>('.framework-actions .framework-action.primary, .run, .reset, .interface-nav button, .output-nav button, starlight-menu-button button')];
          const checks = candidates.map((element) => {
            const style = getComputedStyle(element);
            let background = style.backgroundColor;
            if (background === 'rgba(0, 0, 0, 0)' || background === 'transparent') background = opaqueBackground(element);
            const rgb = (input: string) => (input.match(/[0-9.]+/g) ?? []).slice(0, 3).map(Number);
            const lum = (input: string) => rgb(input).map((v) => v / 255).map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
            const fg = lum(style.color); const bg = lum(background);
            return { text: element.textContent?.trim().slice(0, 48), color: style.color, background, ratio: (Math.max(fg, bg) + .05) / (Math.min(fg, bg) + .05) };
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
      await page.reload();
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
      await page.screenshot({ path: `${evidence}${route === '/' ? 'home' : route.slice(1, -1)}-${viewport.width}-auto.png`, fullPage: true });
      await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'no-preference' });
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    }
  }
});
