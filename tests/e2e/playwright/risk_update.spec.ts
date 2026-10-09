import { test, expect } from '@playwright/test';
import { LoginPage } from './pages/LoginPage';
import { CopilotWidgetPage } from './pages/CopilotWidgetPage';

test.describe('E2E: Treatment Management & Risk Updates', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login('admin', '1234');
  });

  test('Query and update treatment progress via Copilot', async ({ page }) => {
    const copilot = new CopilotWidgetPage(page);
    await copilot.openWidget();
    await copilot.sendMessage('update progress of treatment #1 to 75%');
    await copilot.waitForAssistantResponse();
    const response = await copilot.getLastMessageText();
    expect(response.length).toBeGreaterThan(0);
  });
});
