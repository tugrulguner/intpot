import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test } from '@playwright/test';

const evidence = process.env.PLAYGROUND_EVIDENCE_DIR;

const resources = [
  ['GitHub', 'https://github.com/tugrulguner/intpot'],
  ['Community', 'https://discord.gg/u3AANZr6RG'],
  ['About Tugrul', 'https://tugrul.modepot.io/'],
] as const;
const desktopResources = [
  ['ModePot', 'https://modepot.io/'],
  ...resources,
] as const;

async function settle(page: import('@playwright/test').Page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  });
}

test('desktop header exposes ordered family destinations as readable 44px links', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/');
  await settle(page);
  const links = page.locator('header.header .family-resources a');
  await expect(links).toHaveText(desktopResources.map(([label]) => label));
  for (const [label, href] of desktopResources) {
    const link = page.getByRole('link', { name: label, exact: true }).first();
    await expect(link).toHaveAttribute('href', href);
    const hit = await link.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const center = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return { width: rect.width, height: rect.height, centerHit: center === element || element.contains(center) };
    });
    expect(hit.width).toBeGreaterThanOrEqual(44);
    expect(hit.height).toBeGreaterThanOrEqual(44);
    expect(hit.centerHit).toBe(true);
  }
});

test('compact Menu exposes family resources first, dismisses with Escape, and returns focus', async ({ page }) => {
  for (const route of ['/', '/quickstart/', '/build-an-app/', '/playground/', '/404.html']) {
    for (const width of [768, 401, 400, 390, 320]) {
      await page.setViewportSize({ width, height: 850 });
      await page.goto(route);
      await settle(page);
      const compactFeedback = page.locator('.modepot-compact');
      await expect(compactFeedback).toBeVisible();
      await expect(compactFeedback).toHaveText('Feedback');
      await expect(compactFeedback).toHaveAttribute('href', /^https:\/\/github\.com\/tugrulguner\/intpot\/issues\/new\?/);
      await expect(compactFeedback).toHaveAttribute('target', '_blank');
      await expect(compactFeedback).toHaveAttribute('rel', 'noopener noreferrer');
      await expect(compactFeedback).toHaveClass(/ph-no-autocapture/);
      const feedbackUrl = new URL(await compactFeedback.getAttribute('href')!);
      const expectedPath = route === '/404.html' ? '/404/' : new URL(page.url()).pathname;
      expect(feedbackUrl.searchParams.get('body')).toBe(`Page: https://intpot.modepot.io${expectedPath}\n\nPlease describe the issue. Do not include private data.`);
      expect(feedbackUrl.searchParams.get('body')).not.toMatch(/[?#]|input|email|token|secret/i);
      const compactHit = await compactFeedback.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const center = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
        return { width: rect.width, height: rect.height, centerHit: center === element || element.contains(center) };
      });
      expect(compactHit.width).toBeGreaterThanOrEqual(44);
      expect(compactHit.height).toBeGreaterThanOrEqual(44);
      expect(compactHit.centerHit).toBe(true);
      const menu = page.locator('.family-menu-toggle');
      await expect(page.locator('.family-resources')).toBeHidden();
      await expect(menu).toBeVisible();
      await menu.focus();
      await page.keyboard.press('Enter');
      await expect(menu).toHaveAttribute('aria-expanded', 'true');
      const region = page.getByRole('region', { name: 'Menu' });
      await expect(region).toBeVisible();
      const resourceNav = region.getByRole('navigation', { name: 'Family resources' });
      const links = resourceNav.locator('a');
      await expect(links).toHaveText([['ModePot', 'https://modepot.io/'], ...resources].map(([label]) => label));
      await expect(resourceNav.getByRole('link', { name: 'ModePot', exact: true })).toHaveAttribute('href', 'https://modepot.io/');
      for (const [label, href] of resources) {
        const resourceLink = resourceNav.getByRole('link', { name: label, exact: true });
        await expect(resourceLink).toHaveAttribute('href', href);
        const hit = await resourceLink.evaluate((element) => {
          const rect = element.getBoundingClientRect();
          const center = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
          return { width: rect.width, height: rect.height, top: rect.top, bottom: rect.bottom, centerHit: center === element || element.contains(center) };
        });
        expect(hit.width).toBeGreaterThanOrEqual(44);
        expect(hit.height).toBeGreaterThanOrEqual(44);
        expect(hit.top).toBeGreaterThanOrEqual(0);
        expect(hit.bottom).toBeLessThanOrEqual(850);
        expect(hit.centerHit).toBe(true);
      }
      const docsNav = region.getByRole('navigation', { name: 'Intpot documentation' });
      await expect(docsNav.getByRole('link', { name: 'Overview', exact: true })).toHaveAttribute('href', '/');
      await expect(docsNav.getByRole('link', { name: 'Quickstart', exact: true })).toHaveAttribute('href', '/quickstart/');
      if (evidence && route === '/' && (width === 320 || width === 768)) {
        mkdirSync(evidence, { recursive: true });
        await page.screenshot({ path: join(evidence, `home-menu-${width}.png`), fullPage: true });
      }
      await page.keyboard.press('Escape');
      await expect(region).toBeHidden();
      await expect(menu).toHaveAttribute('aria-expanded', 'false');
      await expect(menu).toBeFocused();
    }
  }
});

test('Feedback header visual evidence at required widths and themes', async ({ page }) => {
  const evidence=process.env.FEEDBACK_EVIDENCE_DIR;
  test.skip(!evidence, 'evidence capture is opt-in'); mkdirSync(evidence!,{recursive:true});
  for(const width of [1280,390,320]) for(const theme of ['light','dark']) {
    await page.setViewportSize({width,height:850}); await page.goto('/'); await settle(page);
    await page.locator('header starlight-theme-select select').selectOption(theme);
    const feedback=width>=768?page.locator('header .family-feedback-links .feedback-link'):page.locator('header .modepot-compact');
    await expect(feedback).toBeVisible(); await feedback.screenshot({path:join(evidence!,`header-feedback-${width}-${theme}.png`)});
  }
});

test('creator attribution links to Tugrul in the homepage first fold', async ({ page }) => {
  for (const viewport of [{ width: 1280, height: 900 }, { width: 320, height: 850 }]) {
    await page.setViewportSize(viewport);
    await page.goto('/');
    await settle(page);
    const attribution = page.getByRole('link', { name: 'Created by Tugrul Guner', exact: true });
    await expect(attribution).toHaveAttribute('href', 'https://tugrul.modepot.io/');
    const box = await attribution.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height);
  }
});
