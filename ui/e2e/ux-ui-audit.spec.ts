import { test, expect, Page } from '@playwright/test';

/**
 * Helper to compute WCAG 2.1 relative luminance and contrast ratio inside page.evaluate
 */
async function checkContrastRatio(page: Page, selector: string): Promise<number> {
  return page.locator(selector).first().evaluate((el) => {
    const parseRgb = (colorStr: string): [number, number, number, number] => {
      const m = colorStr.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
      if (m) {
        return [
          Number(m[1]),
          Number(m[2]),
          Number(m[3]),
          m[4] !== undefined ? Number(m[4]) : 1,
        ];
      }
      const srgb = colorStr.match(
        /color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+))?\)/
      );
      if (srgb) {
        return [
          Math.round(Number(srgb[1]) * 255),
          Math.round(Number(srgb[2]) * 255),
          Math.round(Number(srgb[3]) * 255),
          srgb[4] !== undefined ? Number(srgb[4]) : 1,
        ];
      }
      return [0, 0, 0, 1];
    };

    const getEffectiveBg = (node: Element | null): [number, number, number] => {
      let cur: Element | null = node;
      while (cur) {
        const bg = window.getComputedStyle(cur).backgroundColor;
        const [r, g, b, a] = parseRgb(bg);
        if (a >= 0.85) return [r, g, b];
        cur = cur.parentElement;
      }
      return [248, 250, 253];
    };

    const fgStyle = window.getComputedStyle(el).color;
    const [fr, fg, fb] = parseRgb(fgStyle);
    const [br, bg, bb] = getEffectiveBg(el);

    const luminance = (r: number, g: number, b: number) => {
      const a = [r, g, b].map((v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
    };

    const l1 = luminance(fr, fg, fb);
    const l2 = luminance(br, bg, bb);
    const brightest = Math.max(l1, l2);
    const darkest = Math.min(l1, l2);
    return (brightest + 0.05) / (darkest + 0.05);
  });
}

test.describe('AtelierNova Table 2 — UX/UI & Design Skills Playwright Audit', () => {
  test('1. Design System, Google Light & Gemini Dark Themes, No Emoji Icons & WCAG Contrast', async ({
    page,
  }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    await page.goto('/ui');

    // Verify Google 4-color ribbon and Vertex AI header pill
    await expect(page.locator('.google-ribbon').first()).toBeVisible();
    await expect(page.getByText('Google Cloud · Vertex AI')).toBeVisible();

    // Default theme is google-light
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'google-light');

    // Verify theme button uses crisp inline SVG icon, not emoji
    const themeBtn = page.getByRole('button', { name: /Gemini Dark|Google Light/i });
    await expect(themeBtn).toBeVisible();
    await expect(themeBtn.locator('svg[aria-hidden="true"]')).toBeVisible();
    const themeBtnText = await themeBtn.textContent();
    expect(themeBtnText).not.toContain('🌙');
    expect(themeBtnText).not.toContain('☀️');

    // Verify WCAG AA contrast (>= 4.5:1) in Google Light mode
    const lightHeadingContrast = await checkContrastRatio(page, 'h1');
    expect(lightHeadingContrast).toBeGreaterThanOrEqual(4.5);

    const lightSignInContrast = await checkContrastRatio(
      page,
      'button:has-text("Sign in with GitHub")'
    );
    expect(lightSignInContrast).toBeGreaterThanOrEqual(4.5);

    // Toggle to Gemini Dark Studio
    await themeBtn.click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'google-dark');
    await expect(page.getByRole('button', { name: /Google Light/i })).toBeVisible();

    // Verify WCAG AA contrast (>= 4.5:1) in Gemini Dark mode
    const darkHeadingContrast = await checkContrastRatio(page, 'h1');
    expect(darkHeadingContrast).toBeGreaterThanOrEqual(4.5);

    // Switch back to Google Light
    await themeBtn.click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'google-light');
    expect(pageErrors).toEqual([]);
  });

  test('2. All 5 Navigation Tabs, Queue Approval, Auto-Approve Switch & Results Analytics', async ({
    page,
  }) => {
    await page.goto('/ui');

    // Tab 01 Overview
    await expect(
      page.getByRole('heading', { name: /One layout for every shopper is costing conversion/i })
    ).toBeVisible();
    await expect(page.locator('.kpi-grid .card')).toHaveCount(8);
    await expect(page.locator('.opp-grid .card')).toHaveCount(3);

    // Auto-approve accessible switch
    const autoSwitch = page.getByRole('switch', { name: /Auto-approve queue/i });
    await expect(autoSwitch).toHaveAttribute('aria-checked', 'false');
    await autoSwitch.click();
    await expect(autoSwitch).toHaveAttribute('aria-checked', 'true');
    await autoSwitch.click();
    await expect(autoSwitch).toHaveAttribute('aria-checked', 'false');

    // Tab 02 Queue
    await page.getByRole('link', { name: /02 Queue/i }).click();
    await expect(page.getByRole('heading', { name: /Optimization queue/i })).toBeVisible();
    await expect(page.getByText('EXP-0057').first()).toBeVisible();

    // Tab 03 Work in progress
    await page.getByRole('link', { name: /03 Work in progress/i }).click();
    await expect(page.getByRole('heading', { name: /Work in progress/i })).toBeVisible();

    // Tab 04 Published
    await page.getByRole('link', { name: /04 Published/i }).click();
    await expect(page.getByRole('heading', { name: /Published storefronts/i })).toBeVisible();
    await expect(page.getByText('EXP-0074').first()).toBeVisible();

    // Tab 05 Results
    await page.getByRole('link', { name: /05 Results/i }).click();
    await expect(page.getByRole('heading', { name: /Performance over time/i })).toBeVisible();
  });

  test('3. Storefront Preview Modal, Recreate Hero Image, Guardrails (<=30%, Margin, SKU-0017) & A2A Sync', async ({
    page,
  }) => {
    await page.goto('/ui');

    // Navigate to 02 Queue and open Preview Modal for EXP-0057
    await page.getByRole('link', { name: /02 Queue/i }).click();
    await page.getByRole('button', { name: 'Preview' }).first().click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute('aria-modal', 'true');
    await expect(dialog).toContainText('EXP-0057');

    // Verify Hero Lifestyle Image has NO filter, NO blend-mode, and 100% opacity in Light & Dark modes
    const heroImg = dialog.getByTestId('hero-preview-image');
    await expect(heroImg).toBeVisible();
    const heroStyleBefore = await heroImg.evaluate((el: HTMLImageElement) => {
      const cs = window.getComputedStyle(el);
      return {
        filter: cs.filter,
        mixBlendMode: cs.mixBlendMode,
        opacity: cs.opacity,
        naturalWidth: el.naturalWidth,
      };
    });
    expect(heroStyleBefore.filter).toBe('none');
    expect(heroStyleBefore.mixBlendMode).toBe('normal');
    expect(heroStyleBefore.opacity).toBe('1');
    expect(heroStyleBefore.naturalWidth).toBeGreaterThan(0);

    // Recreate Hero Lifestyle Image via GEMINI_IMAGE_MODEL
    const recreateBtn = dialog.getByRole('button', { name: /Recreate image/i }).first();
    await recreateBtn.click();
    await expect(dialog.getByText(/Hero lifestyle render \(v2\)/i)).toBeVisible();

    const heroStyleAfter = await heroImg.evaluate((el: HTMLImageElement) => {
      const cs = window.getComputedStyle(el);
      return {
        filter: cs.filter,
        mixBlendMode: cs.mixBlendMode,
        opacity: cs.opacity,
        src: el.getAttribute('src') || '',
      };
    });
    expect(heroStyleAfter.filter).toBe('none');
    expect(heroStyleAfter.mixBlendMode).toBe('normal');
    expect(heroStyleAfter.opacity).toBe('1');
    expect(heroStyleAfter.src).toContain('hero_SEG-057');

    // Open Real Photo Lightbox & verify Zoom + Pinch-to-Zoom + Open Original
    await dialog.getByTestId('view-real-photo-btn').click();
    const lightbox = page.getByTestId('real-photo-lightbox');
    await expect(lightbox).toBeVisible();

    const lightboxImg = page.getByTestId('real-photo-lightbox-img');
    await expect(lightboxImg).toBeVisible();
    const lightboxComputed = await lightboxImg.evaluate((el: HTMLImageElement) => {
      const cs = window.getComputedStyle(el);
      return {
        objectFit: cs.objectFit,
        filter: cs.filter,
        mixBlendMode: cs.mixBlendMode,
        opacity: cs.opacity,
        naturalWidth: el.naturalWidth,
      };
    });
    expect(lightboxComputed.objectFit).toBe('contain');
    expect(lightboxComputed.filter).toBe('none');
    expect(lightboxComputed.mixBlendMode).toBe('normal');
    expect(lightboxComputed.opacity).toBe('1');
    expect(lightboxComputed.naturalWidth).toBeGreaterThan(0);

    // 1. Button zoom in (+ -> 150%)
    await expect(page.getByTestId('lightbox-zoom-level')).toHaveText('100%');
    await page.getByTestId('lightbox-zoom-in').click();
    await expect(page.getByTestId('lightbox-zoom-level')).toHaveText('150%');

    // 2. Reset zoom (-> 100%) and double-click stage (-> 250%)
    await page.getByTestId('lightbox-zoom-reset').click();
    await expect(page.getByTestId('lightbox-zoom-level')).toHaveText('100%');
    await page.getByTestId('lightbox-stage').dblclick();
    await expect(page.getByTestId('lightbox-zoom-level')).toHaveText('250%');

    // 3. Simulate 2-finger pinch-to-zoom gesture on the stage (distance 100px -> 200px from 100% -> 200%)
    await page.getByTestId('lightbox-zoom-reset').click();
    await page.getByTestId('lightbox-stage').evaluate((stageEl) => {
      const makeTouch = (id: number, x: number, y: number) =>
        new Touch({
          identifier: id,
          target: stageEl,
          clientX: x,
          clientY: y,
          pageX: x,
          pageY: y,
        });
      const tStart1 = makeTouch(1, 200, 200);
      const tStart2 = makeTouch(2, 300, 200); // dist = 100
      stageEl.dispatchEvent(
        new TouchEvent('touchstart', {
          bubbles: true,
          cancelable: true,
          touches: [tStart1, tStart2],
        })
      );
      const tMove1 = makeTouch(1, 150, 200);
      const tMove2 = makeTouch(2, 350, 200); // dist = 200 (2x pinch)
      stageEl.dispatchEvent(
        new TouchEvent('touchmove', {
          bubbles: true,
          cancelable: true,
          touches: [tMove1, tMove2],
        })
      );
      stageEl.dispatchEvent(
        new TouchEvent('touchend', {
          bubbles: true,
          cancelable: true,
          touches: [],
        })
      );
    });
    await expect(page.getByTestId('lightbox-zoom-level')).toHaveText('200%');

    // 4. Verify Open original link points to the generated asset
    const openOriginalHref = await page.getByTestId('lightbox-open-original').getAttribute('href');
    expect(openOriginalHref).toContain('hero_SEG-057');

    // 5. Escape closes only the Real Photo Lightbox, keeping StorefrontPreviewModal open
    await page.keyboard.press('Escape');
    await expect(lightbox).toBeHidden();
    await expect(dialog).toBeVisible();

    // Test <=30% Discount Cap Guardrail
    const sliders = dialog.locator('input[type="range"]');
    const discountSlider = sliders.nth(0);
    await discountSlider.fill('40');
    await discountSlider.dispatchEvent('change');
    await expect(dialog.getByText('REJECTED_POLICY_CAP')).toBeVisible();
    const publishBtn = dialog.getByRole('button', { name: /Approve & publish/i });
    await expect(publishBtn).toBeDisabled();

    // Restore valid discount (15%)
    await discountSlider.fill('15');
    await discountSlider.dispatchEvent('change');
    await expect(dialog.getByText('SUCCESS').first()).toBeVisible();
    await expect(publishBtn).toBeEnabled();

    // Test SKU-0022 Low-Margin Guardrail (margin 24.0% with 20% discount -> net 4% < 15% buffer)
    const skuSelect = dialog.locator('select').first();
    await skuSelect.selectOption('SKU-0022');
    await discountSlider.fill('20');
    await discountSlider.dispatchEvent('change');
    await expect(dialog.getByText('REJECTED_MARGIN_POLICY')).toBeVisible();
    await expect(publishBtn).toBeDisabled();

    // Test SKU-0017 Prompt Injection Defense
    await skuSelect.selectOption('SKU-0017');
    await expect(
      dialog.getByText('Prompt Injection Defense Active (SKU-0017 Sanitized)')
    ).toBeVisible();
    const warningTitleContrast = await checkContrastRatio(page, '.alert-warning strong');
    expect(warningTitleContrast).toBeGreaterThanOrEqual(4.5);

    // Test Sister Table 1 A2A Sync (valid CPM <= €25)
    await skuSelect.selectOption('SKU-0057');
    await discountSlider.fill('15');
    await discountSlider.dispatchEvent('change');
    await dialog.getByRole('button', { name: /Sync Table 1 \(A2A\)/i }).click();
    await expect(dialog.getByText(/STOREFRONT_TO_CAMPAIGN_SYNC/i)).toBeVisible();

    // Test Escape key closes StorefrontPreviewModal
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
  });

  test('4. ADK Copilot Drawer & GitHub Authentication Modal Keyboard Escape & ARIA Compliance', async ({
    page,
  }) => {
    await page.goto('/ui');

    // Open ADK Copilot Drawer
    await page.getByRole('button', { name: '✦ ADK Copilot', exact: true }).click();
    const copilotDialog = page.getByRole('dialog', { name: /ADK Agent Copilot/i });
    await expect(copilotDialog).toBeVisible();
    await expect(copilotDialog).toHaveAttribute('aria-modal', 'true');

    // Verify accessible input label and send a quick prompt
    const chatInput = copilotDialog.getByRole('textbox', { name: 'Ask ADK Copilot' });
    await expect(chatInput).toBeVisible();
    await copilotDialog
      .getByRole('button', { name: /Test SKU-0017 95% prompt injection guardrail/i })
      .click();
    await expect(copilotDialog.getByText(/SKU-0017/i).first()).toBeVisible();

    // Press Escape to close Copilot Drawer
    await page.keyboard.press('Escape');
    await expect(copilotDialog).toBeHidden();

    // Open GitHub Authentication Modal
    await page.getByRole('button', { name: /Sign in with GitHub/i }).click();
    const authDialog = page.getByRole('dialog', { name: /Sign in with GitHub/i });
    await expect(authDialog).toBeVisible();
    await expect(authDialog).toHaveAttribute('aria-modal', 'true');

    // Sign in with 1-click Team Roster (@rafalitox2)
    await authDialog.getByRole('button', { name: /@rafalitox2/i }).click();
    await expect(authDialog).toBeHidden();
    await expect(page.getByRole('button', { name: /@rafalitox2/i })).toBeVisible();
  });

  test('5. Responsive Layout & Zero Horizontal Overflow across Desktop, Tablet, and Mobile', async ({
    page,
  }) => {
    const viewports = [
      { name: 'Desktop', width: 1440, height: 900 },
      { name: 'Tablet', width: 768, height: 1024 },
      { name: 'Mobile', width: 375, height: 812 },
    ];

    for (const vp of viewports) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto('/ui');

      const overflow = await page.evaluate(() => {
        return document.documentElement.scrollWidth > window.innerWidth;
      });
      expect(
        overflow,
        `Expected no horizontal overflow on ${vp.name} (${vp.width}x${vp.height})`
      ).toBe(false);

      // Navigate to 02 Queue and open Storefront Preview Modal on Mobile/Tablet/Desktop
      await page.getByRole('link', { name: /02 Queue/i }).click();
      await page.getByRole('button', { name: 'Preview' }).first().click();
      await expect(page.getByRole('dialog')).toBeVisible();
      const modalOverflow = await page.evaluate(() => {
        return document.documentElement.scrollWidth > window.innerWidth;
      });
      expect(
        modalOverflow,
        `Expected no horizontal overflow with modal open on ${vp.name}`
      ).toBe(false);
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog')).toBeHidden();
    }
  });
});
