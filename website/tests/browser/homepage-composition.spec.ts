import { expect, test } from '@playwright/test';

const output = process.env.SCREENSHOT_DIR;
const viewports = [
  { name: 'desktop-1280x850', width: 1280, height: 850 },
  { name: 'tablet-768x850', width: 768, height: 850 },
  { name: 'mobile-390x850', width: 390, height: 850 },
  { name: 'mobile-320x850', width: 320, height: 850 },
];

test('homepage composition renders in both themes at required widths', async ({ page }) => {
  for (const theme of ['light', 'dark']) {
    for (const viewport of viewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto('/');
      await page.evaluate((value) => {
        document.documentElement.dataset.theme = value;
        localStorage.setItem('starlight-theme', value);
      }, theme);
      await page.reload();
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator('main > .content-panel:first-child')).toHaveCSS('display', 'none');
      await expect(page.locator('.framework-art img')).toBeVisible();
      await expect.poll(() => page.locator('.framework-art img').evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0)).toBeTruthy();
      await expect(page.locator('.installation-strip')).toBeVisible();
      await expect(page.locator('.installation-strip code')).toHaveText('pip install "intpot[all]"');
      await expect(page.locator('.project-demo')).toBeVisible();
      await expect(page.getByRole('link', { name: 'Created by Tugrul Guner' }).first()).toBeVisible();
      await expect(page.locator('.framework-actions a')).toHaveText(['Quick start', 'Playground', 'GitHub ↗']);
      const geometry = await page.evaluate(() => {
        const art = document.querySelector('.framework-art img').getBoundingClientRect();
        const text = document.querySelector('.framework-copy').getBoundingClientRect();
        const actions = [...document.querySelectorAll('.framework-actions a')].map((el) => {
          const r = el.getBoundingClientRect(); return { x:r.x,y:r.y,width:r.width,height:r.height };
        });
        return { art:{x:art.x,y:art.y,width:art.width,height:art.height}, text:{x:text.x,y:text.y,width:text.width,height:text.height}, actions, scrollWidth:document.documentElement.scrollWidth, viewport:innerWidth, theme:document.documentElement.dataset.theme };
      });
      expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.viewport);
      expect(geometry.actions.every((action) => action.height >= 44)).toBeTruthy();
      if (viewport.width > 608) expect(geometry.art.x).toBeGreaterThan(geometry.text.x + geometry.text.width - 1);
      else expect(geometry.art.y).toBeGreaterThan(geometry.text.y + geometry.text.height - 1);
      if (output) await page.screenshot({ path: `${output}/${theme}-${viewport.name}.png` });
    }
  }
});
