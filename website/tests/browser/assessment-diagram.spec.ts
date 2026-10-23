import { test, expect } from '@playwright/test';
for (const width of [390, 1280]) {
  test(`assessment diagram is readable, ordered and expandable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    for (const route of ['/', '/conversion-boundaries/', '/project/readme/']) {
      // External README badges are not the diagram's readiness signal.
      // The actual owned image decode and full-size navigation are asserted below.
      await page.goto(route, { waitUntil: 'domcontentloaded' });
      const image = page.locator('img[src="/intpot-assessment.png"]');
      await expect(image).toHaveCount(1);
      await image.scrollIntoViewIfNeeded();
      await expect(image).toBeVisible();
      await expect.poll(() => image.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth === 2000 && el.naturalHeight === 1380)).toBeTruthy();
      const bounds = await image.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1);
      expect(bounds!.height / bounds!.width).toBeCloseTo(1380 / 2000, 2);
      const link = image.locator('..');
      await expect(link).toHaveAttribute('href', '/intpot-assessment.png');
      const response = await page.request.get('/intpot-assessment.png');
      expect(response.status()).toBe(200);
      expect(response.headers()['content-type']).toContain('image/png');
      if (route !== '/conversion-boundaries/') {
        const order = await page.locator('img').evaluateAll(images => images.map(image => image.getAttribute('src') || '').filter(src => /intpot-(flow|assessment)\.png/.test(src)));
        expect(order[0]).toContain('intpot-flow.png');
        expect(order[1]).toContain('intpot-assessment.png');
      }
      if (route === '/project/readme/') {
        const order = await page.locator('h2, img[src="/intpot-assessment.png"]').evaluateAll(nodes =>
          nodes.map(node => node.tagName === 'IMG' ? 'assessment-image' : node.id));
        let previous = -1;
        for (const section of [
          'convert-an-existing-app', 'conversion-assessment-before-output', 'assessment-image',
          'give-your-coding-agent-intpot-context', 'what-conversion-preserves',
          'actionable-binding-context-unreleased', 'missing-body-bindings-v011',
          'bounded-helper-recovery-v011', 'architecture', 'community', 'roadmap', 'support-intpot', 'license',
        ]) {
          const position = order.indexOf(section);
          expect(position, `${section} must follow its preceding conversion/documentation section`).toBeGreaterThan(previous);
          previous = position;
        }
      }
      if (await link.getAttribute('target') === '_blank') {
        const [popup] = await Promise.all([page.waitForEvent('popup'), link.click()]);
        await expect(popup.locator('img')).toBeVisible();
        expect(popup.url()).toContain('/intpot-assessment.png');
        await popup.close();
      } else {
        await Promise.all([page.waitForURL('**/intpot-assessment.png'), link.click()]);
        await expect(page.locator('img')).toBeVisible();
      }
    }
  });
}
