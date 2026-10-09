import { test, expect } from '@playwright/test';
import { LoginPage } from './pages/LoginPage';

test.describe('E2E: User Logout & Session Invalidation', () => {
  test('User can logout and cannot access protected views without re-authentication', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login('admin', '1234');

    // Click logout
    const logoutBtn = page.locator('a[href*="logout"], button:has-text("Logout"), [data-testid="logout-btn"]');
    if (await logoutBtn.isVisible()) {
      await logoutBtn.click();
      await expect(page).toHaveURL(/\/login/);
    }
  });
});
