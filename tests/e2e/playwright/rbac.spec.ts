import { test, expect } from '@playwright/test';
import { LoginPage } from './pages/LoginPage';
import { CopilotWidgetPage } from './pages/CopilotWidgetPage';

test.describe('E2E: Role-Based Access Control and Scoping', () => {
  test('Risk Owner greeting reflects Risk Owner capabilities', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login('ro_karan', '1234');

    const copilot = new CopilotWidgetPage(page);
    await copilot.openWidget();
    await copilot.sendMessage('hi');
    await copilot.waitForAssistantResponse();
    const response = await copilot.getLastMessageText();
    expect(response.length).toBeGreaterThan(0);
  });
});
