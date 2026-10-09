import { test, expect } from '@playwright/test';
import { LoginPage } from './pages/LoginPage';
import { CopilotWidgetPage } from './pages/CopilotWidgetPage';

test.describe('E2E: Risk Search via Copilot and UI', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login('admin', '1234');
  });

  test('Search risks via Copilot query', async ({ page }) => {
    const copilot = new CopilotWidgetPage(page);
    await copilot.openWidget();
    await copilot.sendMessage('Show high severity risks in Gas Processing');
    await copilot.waitForAssistantResponse();
    const response = await copilot.getLastMessageText();
    expect(response.toLowerCase()).toContain('risk');
  });
});
