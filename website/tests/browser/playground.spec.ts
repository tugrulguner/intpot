import { mkdirSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const evidence = new URL('../../evidence/playground-redesign/', import.meta.url).pathname;
mkdirSync(evidence, { recursive: true });

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
  for (const viewport of [{ width: 1280, height: 768 }, { width: 768, height: 768 }, { width: 320, height: 390 }]) {
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
      const rgb = (value: string) => (value.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
      return [...document.querySelectorAll<HTMLElement>('.run, .definition pre, .definition code span[style]')].map((el) => {
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
    });
    for (const reading of readings) expect(reading.contrast, `${colorScheme}: ${JSON.stringify(reading)}`).toBeGreaterThanOrEqual(4.5);
    const tops = await page.getByRole('tab').evaluateAll((tabs) => tabs.map((tab) => tab.getBoundingClientRect().top));
    expect(Math.max(...tops) - Math.min(...tops)).toBeLessThanOrEqual(1);
  }
});
