import { mkdirSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const evidence = process.env.PLAYGROUND_EVIDENCE_DIR ?? new URL('../../evidence/playground-refinement/intpot/', import.meta.url).pathname;
mkdirSync(evidence, { recursive: true });

test('one compact workbench keeps source, request and result in the same two-column composition', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/playground/');
  const details = page.locator('.result-details');
  await expect(details).toHaveCount(2);
  await expect(details.nth(0)).not.toHaveAttribute('open', '');
  await expect(details.nth(1)).not.toHaveAttribute('open', '');
  await expect(page.locator('.definition code')).toContainText('def greet');
  const input = page.getByLabel('Editable interface request');
  await input.fill("greet 'Composition' --excited");
  await page.getByRole('button', { name: /Run local preview/ }).click();
  await expect(page.locator('#computed')).toHaveText('Hello, Composition!');
  const layout = await page.evaluate(() => {
    const box = (selector: string) => {
      const rect = document.querySelector(selector)!.getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
    };
    return { source: box('.definition'), tabs: box('.interface-nav'), request: box('.request'), result: box('.result'), documentHeight: document.documentElement.scrollHeight };
  });
  expect(layout.source.left).toBeLessThan(layout.tabs.left);
  expect(Math.abs(layout.source.top - layout.tabs.top)).toBeLessThanOrEqual(2);
  expect(layout.request.left).toBeGreaterThan(layout.source.left);
  expect(layout.result.left).toBe(layout.request.left);
  expect(layout.result.right).toBeLessThanOrEqual(layout.request.right + 1);
  expect(layout.result.top - layout.request.top).toBeLessThan(320);
  expect(layout.result.bottom).toBeLessThan(layout.documentHeight - 100);
  await details.nth(0).locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(details.nth(0)).toHaveAttribute('open', '');
  await expect(details.nth(1)).not.toHaveAttribute('open', '');
  await details.nth(1).locator('summary').focus();
  await page.keyboard.press('Space');
  await expect(details.nth(1)).toHaveAttribute('open', '');
});

test('all three interface tabs share a 44px baseline and retain reachable active state', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 390 });
  await page.goto('/playground/');
  const measurements = await page.getByRole('tab').evaluateAll((tabs) => tabs.map((tab) => {
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

test('bounded requests compute correct results, reject invalid requests safely, and reset', async ({ page }) => {
  await page.goto('/playground/');
  const input = page.getByLabel('Editable interface request');
  await page.getByRole('tab', { name: /CLI/ }).click();
  await input.fill("greet '<img src=x onerror=alert(1)>' --excited");
  await page.getByRole('button', { name: /Run local preview/ }).click();
  await expect(page.locator('#computed')).toHaveText("Hello, <img src=x onerror=alert(1)>!");
  await expect(page.locator('.result img')).toHaveCount(0);
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
          const source = document.querySelector<HTMLElement>('.code-bar span:first-child')!;
          const language = document.querySelector<HTMLElement>('.code-bar span:last-child')!;
          const sourceBox = source.getBoundingClientRect();
          const languageBox = language.getBoundingClientRect();
          return {
            width: innerWidth,
            documentWidth: document.documentElement.scrollWidth,
            bodyWidth: document.body.scrollWidth,
            workbenchRight: workbench.getBoundingClientRect().right,
            definitionRight: definition.getBoundingClientRect().right,
            labelsOverlap: sourceBox.right > languageBox.left,
            codeCanScrollInternally: (definition.querySelector('pre')?.scrollWidth ?? 0) > (definition.querySelector('pre')?.clientWidth ?? 0),
            offenders: [...document.querySelectorAll('body *')].map((element) => ({ tag: element.tagName, id: element.id, className: typeof element.className === 'string' ? element.className : '', text: element.textContent?.trim().slice(0, 40), left: Math.round(element.getBoundingClientRect().left), right: Math.round(element.getBoundingClientRect().right) })).filter((element) => element.right > innerWidth + 1 || element.left < -1).slice(0, 8),
          };
        });
        expect(geometry.documentWidth, JSON.stringify(geometry)).toBeLessThanOrEqual(viewport.width);
        expect(geometry.bodyWidth, JSON.stringify(geometry)).toBeLessThanOrEqual(viewport.width);
        expect(geometry.workbenchRight, JSON.stringify(geometry)).toBeLessThanOrEqual(viewport.width);
        expect(geometry.definitionRight, JSON.stringify(geometry)).toBeLessThanOrEqual(viewport.width);
        expect(geometry.labelsOverlap, JSON.stringify(geometry)).toBe(false);
        if (viewport.width === 320) expect(geometry.codeCanScrollInternally).toBe(true);
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
      ? { background: '#f8f7f4', surface: '#fff', ink: '#181a1d', muted: '#626970', gold: '#795711' }
      : { background: '#16181b', surface: '#202226', ink: '#edeff2', muted: '#aeb4bc', gold: '#dfbd72' });
    expect(readings.actualBackground).not.toBe('rgba(0, 0, 0, 0)');
    expect(readings.actualInputBackground).not.toBe('rgba(0, 0, 0, 0)');
    for (const reading of readings.foregrounds) expect(reading.contrast, `${colorScheme}: ${JSON.stringify(reading)}`).toBeGreaterThanOrEqual(4.5);
    const tops = await page.getByRole('tab').evaluateAll((tabs) => tabs.map((tab) => tab.getBoundingClientRect().top));
    expect(Math.max(...tops) - Math.min(...tops)).toBeLessThanOrEqual(1);
  }
});
