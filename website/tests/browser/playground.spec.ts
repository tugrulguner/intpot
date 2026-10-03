import { mkdirSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const evidence = process.env.PLAYGROUND_EVIDENCE_DIR ?? new URL('../../evidence/playground-refinement/intpot/', import.meta.url).pathname;
mkdirSync(evidence, { recursive: true });

test('output tabs share a 44px baseline and the active panel fits the inspector at every viewport', async ({ page }) => {
  for (const width of [1280, 768, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/playground/');
    await page.getByRole('button', { name: /Run local preview/ }).click();
    await page.evaluate(async () => {
      await document.fonts.ready;
      await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
    });
    const geometry = await page.evaluate(() => {
      const inspector = document.querySelector('.inspector')!.getBoundingClientRect();
      const panel = document.querySelector('#output-panel')!.getBoundingClientRect();
      const tabs = [...document.querySelectorAll('.output-nav button')].map((tab) => {
        const box = tab.getBoundingClientRect();
        return { top: box.top, height: box.height };
      });
      return { tabs, panelBottom: panel.bottom, inspectorBottom: inspector.bottom };
    });
    expect(Math.max(...geometry.tabs.map((tab) => tab.top)) - Math.min(...geometry.tabs.map((tab) => tab.top))).toBeLessThanOrEqual(1);
    for (const tab of geometry.tabs) expect(tab.height).toBe(44);
    expect(geometry.panelBottom).toBeLessThanOrEqual(geometry.inspectorBottom);
  }
});

test('one bounded output inspector stays in the source-request-inspect workbench after every output view is selected', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/playground/');
  await page.getByRole('button', { name: /Run local preview/ }).click();
  const inspector = page.getByRole('region', { name: 'Output inspection' });
  await expect(inspector).toBeVisible();
  const initial = await inspector.boundingBox();
  for (const view of ['Result', 'Typed arguments', 'Interface response', 'Request trace']) {
    const viewTab = page.getByRole('tab', { name: view });
    await viewTab.click();
    await expect(viewTab).toHaveAttribute('aria-selected', 'true');
    const current = await inspector.boundingBox();
    expect(current?.height).toBeLessThanOrEqual((initial?.height ?? 0) + 2);
    expect(current?.y).toBeLessThan(700);
    await page.screenshot({ path: `${evidence}1280-output-${view.toLowerCase().replaceAll(' ', '-')}.png`, fullPage: true });
  }
  await page.getByRole('tab', { name: 'Result' }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'Typed arguments' })).toHaveAttribute('aria-selected', 'true');

  await expect(page.locator('.definition code')).toContainText('def greet');
  const input = page.getByLabel('Editable interface request');
  await input.fill("greet 'Composition' --excited");
  await page.getByRole('button', { name: /Run local preview/ }).click();
  await expect(page.locator('#computed')).toHaveText('Hello, Composition!');
  const layout = await page.evaluate(() => {
    const rect = (selector: string) => document.querySelector(selector)!.getBoundingClientRect();
    const source = rect('.definition'); const request = rect('.request'); const inspector = rect('.inspector');
    return { source, request, inspector, width: innerWidth, pageWidth: document.documentElement.scrollWidth };
  });
  expect(layout.source.left).toBeLessThan(layout.request.left);
  expect(layout.request.left).toBeLessThan(layout.inspector.left);
  expect(layout.pageWidth).toBeLessThanOrEqual(layout.width);
  expect(layout.inspector.height).toBeGreaterThanOrEqual(400);
  expect(layout.inspector.height).toBeLessThanOrEqual(440);
  expect(layout.inspector.top).toBeLessThan(700);
});

test('all three interface tabs share a 44px baseline and retain reachable active state', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 390 });
  await page.goto('/playground/');
  const measurements = await page.locator('.interface-nav [role="tab"]').evaluateAll((tabs) => tabs.map((tab) => {
    const rect = tab.getBoundingClientRect();
    return { top: rect.top, height: rect.height, left: rect.left, right: rect.right };
  }));
  expect(Math.max(...measurements.map((tab) => tab.top)) - Math.min(...measurements.map((tab) => tab.top))).toBeLessThanOrEqual(1);
  expect(measurements.every((tab) => tab.height >= 44 && tab.left >= 0 && tab.right <= 320)).toBe(true);
  const actions = await page.locator('.actions button').evaluateAll((buttons) => buttons.map((button) => {
    const rect = button.getBoundingClientRect();
    const style = getComputedStyle(button);
    return { top: rect.top, height: rect.height, font: style.fontFamily, padding: style.padding };
  }));
  expect(actions[0]).toEqual(actions[1]);
  expect(actions[0].height).toBe(44);
  expect(actions[0].padding).toBe(actions[1].padding);
  const activeIndicator = await page.getByRole('tab', { name: /CLI/ }).evaluate((tab) => getComputedStyle(tab).borderBottomColor);
  expect(activeIndicator).not.toBe('rgba(0, 0, 0, 0)');
  await page.getByRole('tab', { name: /CLI/ }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: /HTTP/ })).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: /MCP/ })).toHaveAttribute('aria-selected', 'true');
});

test('long output scrolls inside one inspector and edits clear the selected trace without switching tabs', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/playground/');
  const input = page.getByLabel('Editable interface request');
  await page.getByRole('tab', { name: /MCP/ }).click();
  // Forty characters is the preview's bound; newlines exercise long rendered output without widening it.
  const name = '\n'.repeat(39) + 'x';
  await input.fill(JSON.stringify({ name: 'greet', arguments: { name, excited: true } }));
  await page.getByRole('button', { name: /Run local preview/ }).click();
  await expect(page.locator('#computed')).toHaveText(`Hello, ${name}!`);
  for (const view of ['Result', 'Typed arguments', 'Interface response', 'Request trace']) {
    await page.getByRole('tab', { name: view, exact: true }).click();
    await expect(page.locator('.output-view:visible')).toHaveCount(1);
    const bounds = await page.locator('.inspector').boundingBox();
    expect(bounds?.height).toBe(420);
    const scroller = page.locator('.output-view:visible pre, .output-view:visible ol');
    const scrolling = await scroller.evaluate((element) => {
      element.scrollTop = element.scrollHeight;
      return { scrollTop: element.scrollTop, overflow: getComputedStyle(element).overflowY };
    });
    expect(scrolling.overflow).toBe('auto');
    if (view === 'Result' || view === 'Interface response') expect(scrolling.scrollTop).toBeGreaterThan(0);
  }
  await input.fill(JSON.stringify({ name: 'greet', arguments: { name: 'Edited' } }));
  await expect(page.getByRole('tab', { name: 'Request trace', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#trace')).toHaveText('Request edited; run again to compute a fresh result.');
  await expect(page.locator('#arguments')).toHaveText('Not run');
  await page.getByRole('button', { name: /Run local preview/ }).click();
  await expect(page.locator('#trace')).toContainText('name="Edited"');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.locator('#trace')).toHaveText('Choose a request and run its browser-local preview.');
});

test('bounded requests compute correct results, reject invalid requests safely, and reset', async ({ page }) => {
  await page.goto('/playground/');
  const input = page.getByLabel('Editable interface request');
  await page.getByRole('tab', { name: /CLI/ }).click();
  await input.fill("greet '<img src=x onerror=alert(1)>' --excited");
  await page.getByRole('button', { name: /Run local preview/ }).click();
  await expect(page.locator('#computed')).toHaveText("Hello, <img src=x onerror=alert(1)>!");
  await expect(page.locator('.inspector img')).toHaveCount(0);
  await page.getByRole('tab', { name: /HTTP/ }).click();
  await input.fill('{"method":"POST","path":"/greet","body":{"name":"World","excited":true}}');
  await page.getByRole('button', { name: /Run local preview/ }).click();
  await expect(page.locator('#computed')).toHaveText('Hello, World!');
  await expect(page.locator('#response')).toContainText('"status": 200');
  await page.getByRole('tab', { name: /MCP/ }).click();
  await input.fill('{"name":"greet","arguments":{"name":"MCP"}}');
  await page.getByRole('button', { name: /Run local preview/ }).click();
  await expect(page.locator('#computed')).toHaveText('Hello, MCP');
  await expect(page.locator('#response')).toContainText('structuredContent');
  await input.fill('{"name":"delete","arguments":{"name":"MCP"}}');
  await page.getByRole('button', { name: /Run local preview/ }).click();
  await expect(page.getByRole('alert')).toContainText('Only the greet MCP tool');
  await page.getByRole('button', { name: 'Reset' }).click();
  await expect(page.locator('#computed')).toHaveText('Not run');
  await expect(page.getByRole('alert')).toBeEmpty();
  await expect(input).toHaveValue(/Ada/);
});

test('workbench fits viewports in both themes and reduced motion; captures durable screenshots', async ({ page }) => {
  await page.goto('/playground/');
  await page.getByRole('button', { name: /Run local preview/ }).click();
  await expect(page.locator('#computed')).toHaveText('Hello, Ada');
  for (const viewport of [{ width: 1280, height: 900 }, { width: 768, height: 768 }, { width: 320, height: 390 }]) {
    await page.setViewportSize(viewport);
    for (const colorScheme of ['light', 'dark'] as const) {
      for (const reducedMotion of ['no-preference', 'reduce'] as const) {
        await page.emulateMedia({ colorScheme, reducedMotion });
        await page.evaluate(async () => {
          await document.fonts.ready;
          await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        });
        const geometry = await page.evaluate(() => {
          const workbench = document.querySelector<HTMLElement>('[data-playground]')!;
          const definition = document.querySelector<HTMLElement>('.definition')!;
          const source = document.querySelector<HTMLElement>('.definition .code-file')!;
          const language = document.querySelector<HTMLElement>('.run-panel .panel-heading .code-file')!;
          const sourceBox = source.getBoundingClientRect();
          const languageBox = language.getBoundingClientRect();
          return {
            width: innerWidth,
            documentWidth: document.documentElement.scrollWidth,
            bodyWidth: document.body.scrollWidth,
            workbenchRight: workbench.getBoundingClientRect().right,
            definitionRight: definition.getBoundingClientRect().right,
            labelsFit: source.scrollWidth <= source.clientWidth && language.scrollWidth <= language.clientWidth,
            codeCanScrollInternally: (definition.querySelector('pre')?.scrollWidth ?? 0) > (definition.querySelector('pre')?.clientWidth ?? 0),
            outputTabsFit: (() => { const tabs = document.querySelector<HTMLElement>('.output-nav')!; return tabs.scrollWidth <= tabs.clientWidth; })(),
            interfaceTabsShareRow: (() => { const tabs = [...document.querySelectorAll<HTMLElement>('.interface-nav [role="tab"]')]; return Math.max(...tabs.map((tab) => tab.getBoundingClientRect().top)) - Math.min(...tabs.map((tab) => tab.getBoundingClientRect().top)) <= 1; })(),
            offenders: [...document.querySelectorAll('body *')].map((element) => ({ tag: element.tagName, id: element.id, className: typeof element.className === 'string' ? element.className : '', text: element.textContent?.trim().slice(0, 40), left: Math.round(element.getBoundingClientRect().left), right: Math.round(element.getBoundingClientRect().right) })).filter((element) => element.right > innerWidth + 1 || element.left < -1).slice(0, 8),
          };
        });
        expect(geometry.documentWidth, JSON.stringify(geometry)).toBeLessThanOrEqual(viewport.width);
        expect(geometry.bodyWidth, JSON.stringify(geometry)).toBeLessThanOrEqual(viewport.width);
        expect(geometry.workbenchRight, JSON.stringify(geometry)).toBeLessThanOrEqual(viewport.width);
        expect(geometry.definitionRight, JSON.stringify(geometry)).toBeLessThanOrEqual(viewport.width);
        expect(geometry.outputTabsFit, JSON.stringify(geometry)).toBe(true);
        expect(geometry.interfaceTabsShareRow, JSON.stringify(geometry)).toBe(true);
        if (viewport.width === 320) expect(geometry.codeCanScrollInternally).toBe(false);
        await page.screenshot({ path: `${evidence}${viewport.width}-${viewport.height}-${colorScheme}-${reducedMotion}.png`, fullPage: true });
      }
    }
  }
});

test('primary controls and highlighted code remain readable in both themes', async ({ page }) => {
  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme });
    await page.goto('/playground/');
    await page.evaluate(() => document.fonts.ready);
    const readings = await page.evaluate(() => {
      const luminance = (rgb: number[]) => rgb.map((v) => v / 255).map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
      const rgb = (value: string) => (value.match(/[0-9.]+/g) ?? []).slice(0, 3).map(Number);
      const root = document.querySelector<HTMLElement>('.workbench')!;
      const styles = getComputedStyle(root);
      const foregrounds = [...document.querySelectorAll<HTMLElement>('.run, .definition pre, .definition code span[style]')].map((el) => {
        let parent: HTMLElement | null = el;
        let background = 'rgba(0, 0, 0, 0)';
        while (parent && (background === 'rgba(0, 0, 0, 0)' || background === 'transparent')) {
          background = getComputedStyle(parent).backgroundColor;
          parent = parent.parentElement;
        }
        const foreground = luminance(rgb(getComputedStyle(el).color));
        const back = luminance(rgb(background));
        return { text: el.textContent?.slice(0, 40), contrast: (Math.max(foreground, back) + .05) / (Math.min(foreground, back) + .05) };
      });
      return {
        palette: { background: styles.getPropertyValue('--wb-bg').trim(), surface: styles.getPropertyValue('--wb-surface').trim(), ink: styles.getPropertyValue('--wb-ink').trim(), muted: styles.getPropertyValue('--wb-muted').trim(), gold: styles.getPropertyValue('--wb-gold').trim() },
        actualBackground: styles.backgroundColor,
        actualInputBackground: getComputedStyle(document.querySelector<HTMLElement>('#request')!).backgroundColor,
        foregrounds,
      };
    });
    expect(readings.palette).toEqual(colorScheme === 'light'
      ? { background: '#f8f7f4', surface: '#ffffff', ink: '#181a1d', muted: '#616b78', gold: '#795711' }
      : { background: '#16181b', surface: '#202226', ink: '#edeff2', muted: '#aeb4bc', gold: '#dfbd72' });
    expect(readings.actualBackground).not.toBe('rgba(0, 0, 0, 0)');
    expect(readings.actualInputBackground).not.toBe('rgba(0, 0, 0, 0)');
    for (const reading of readings.foregrounds) expect(reading.contrast, `${colorScheme}: ${JSON.stringify(reading)}`).toBeGreaterThanOrEqual(4.5);
    const tops = await page.locator('.interface-nav [role="tab"]').evaluateAll((tabs) => tabs.map((tab) => tab.getBoundingClientRect().top));
    expect(Math.max(...tops) - Math.min(...tops)).toBeLessThanOrEqual(1);
  }
});

test('explicit site themes keep aligned headers and a continuous code surface opposite system preference', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  for (const theme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: theme === 'light' ? 'dark' : 'light' });
    await page.goto('/playground/');
    await page.locator('starlight-theme-select select').first().selectOption(theme);
    await page.evaluate(async () => {
      await document.fonts.ready;
      await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
    });
    const geometry = await page.evaluate(() => ({
      theme: document.documentElement.dataset.theme,
      headers: [...document.querySelectorAll('.panel-heading')].map((element) => {
        const box = element.getBoundingClientRect();
        return { top: box.top, bottom: box.bottom };
      }),
      codeSurface: getComputedStyle(document.querySelector('.definition')!).backgroundColor,
      codeBackground: getComputedStyle(document.querySelector('.definition pre')!).backgroundColor,
    }));
    expect(geometry.theme).toBe(theme);
    expect(Math.max(...geometry.headers.map((header) => header.top)) - Math.min(...geometry.headers.map((header) => header.top))).toBeLessThanOrEqual(1);
    expect(Math.max(...geometry.headers.map((header) => header.bottom)) - Math.min(...geometry.headers.map((header) => header.bottom))).toBeLessThanOrEqual(1);
    expect(geometry.codeSurface).toBe(geometry.codeBackground);
  }
});

test('documentation guides navigate, expose stable anchors, and serve canonical Markdown downloads on desktop and mobile', async ({ page }) => {
  for (const viewport of [{ width: 1280, height: 900 }, { width: 375, height: 812 }]) {
    await page.setViewportSize(viewport);
    await page.goto('/');
    await page.getByRole('link', { name: 'Build and run an app' }).click();
    await expect(page).toHaveURL(/\/build-an-app\/$/);
    await expect(page.getByRole('heading', { name: 'Build and run an Intpot app', level: 1 })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Download this guide as Markdown' })).toHaveAttribute('href', '/downloads/build-an-app.md');
    const download = await page.request.get('/downloads/build-an-app.md');
    expect(download.status()).toBe(200);
    expect(await download.text()).toContain('intpot serve app.py --api');
    await page.getByRole('main').locator('a[href="/schema-reference/"]').first().click();
    await expect(page).toHaveURL(/\/schema-reference\/$/);
    await expect(page.getByRole('heading', { name: 'Schema and parameter reference', level: 1 })).toBeVisible();
    await expect(page.locator('a[href="/architecture-internals/"]').first()).toHaveAttribute('href', '/architecture-internals/');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
    expect(overflow).toBe(true);
  }
});

 test('code, run, and output are aligned panels with legible selected and action states', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 768 });
  await page.goto('/playground/');
  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme });
    const geometry = await page.evaluate(() => {
      const boxes = ['.definition', '.run-panel', '.inspector'].map((selector) => {
        const rect = document.querySelector(selector)!.getBoundingClientRect();
        return { top: rect.top, bottom: rect.bottom };
      });
      const tabs = [...document.querySelectorAll<HTMLElement>('.interface-nav [role="tab"], .output-nav [role="tab"]')];
      const contrast = (element: HTMLElement) => {
        const color = (value: string) => (value.match(/[0-9.]+/g) ?? []).slice(0, 3).map(Number);
        const luminance = (value: string) => color(value).map((v) => v / 255).map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
        let ancestor: HTMLElement | null = element;
        let background = 'rgba(0, 0, 0, 0)';
        while (ancestor && (background === 'rgba(0, 0, 0, 0)' || background === 'transparent')) {
          background = getComputedStyle(ancestor).backgroundColor;
          ancestor = ancestor.parentElement;
        }
        const foreground = luminance(getComputedStyle(element).color), backdrop = luminance(background);
        return (Math.max(foreground, backdrop) + .05) / (Math.min(foreground, backdrop) + .05);
      };
      const selected = tabs.find((tab) => tab.getAttribute('aria-selected') === 'true')!;
      const inactive = tabs.find((tab) => tab.getAttribute('aria-selected') === 'false')!;
      const button = document.querySelector<HTMLElement>('.run')!;
      return { boxes, tabHeights: tabs.map((tab) => tab.getBoundingClientRect().height), selectedBackground: getComputedStyle(selected).backgroundColor, inactiveBackground: getComputedStyle(inactive).backgroundColor, buttonHeight: button.getBoundingClientRect().height, buttonContrast: contrast(button), selectedContrast: contrast(selected), inactiveContrast: contrast(inactive) };
    });
    expect(Math.max(...geometry.boxes.map((box) => box.top)) - Math.min(...geometry.boxes.map((box) => box.top))).toBeLessThanOrEqual(1);
    expect(Math.max(...geometry.boxes.map((box) => box.bottom)) - Math.min(...geometry.boxes.map((box) => box.bottom))).toBeLessThanOrEqual(1);
    expect(geometry.tabHeights.every((height) => height >= 44)).toBe(true);
    expect(geometry.selectedBackground).not.toBe(geometry.inactiveBackground);
    expect(geometry.buttonHeight).toBe(44);
    expect(geometry.buttonContrast).toBeGreaterThanOrEqual(4.5);
    expect(geometry.selectedContrast).toBeGreaterThanOrEqual(4.5);
    expect(geometry.inactiveContrast).toBeGreaterThanOrEqual(4.5);
  }
});
