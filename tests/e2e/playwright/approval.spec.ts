import { test, expect } from '@playwright/test';
import { LoginPage } from './pages/LoginPage';
import { CopilotWidgetPage } from './pages/CopilotWidgetPage';

test.describe('E2E: Governance Approval Flow', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login('admin', '1234');
  });

  test('Approver prompts for mandatory remark during approval', async ({ page }) => {
    const copilot = new CopilotWidgetPage(page);
    await copilot.openWidget();
    await copilot.sendMessage('approve RSK-GAS-087');
    await copilot.waitForAssistantResponse();
    const response = await copilot.getLastMessageText();
    expect(response.toLowerCase()).toContain('remark');
  });
});
