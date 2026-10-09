import { test, expect } from '@playwright/test';
import { LoginPage } from './pages/LoginPage';

test.describe('E2E: Authentication & Login Flow', () => {
  test('User can successfully login with valid credentials', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login('admin', '1234');
    await expect(page).toHaveURL(/\/(dashboard|home|risk)/);
  });

  test('User sees error on invalid credentials', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login('invalid_user', 'wrong_pass');
    await expect(loginPage.errorMessage).toBeVisible();
  });
});
