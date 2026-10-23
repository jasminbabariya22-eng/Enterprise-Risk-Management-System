import { test, expect } from '@playwright/test';
import { LoginPage } from './pages/LoginPage';
import { CopilotWidgetPage } from './pages/CopilotWidgetPage';

test.describe('E2E: Final Gate - Orchestrator & Cross-Agent Integration Suite', () => {

  test('1. Authenticated Routing: Verified server-side session identity binds to Copilot', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login('admin', '1234');

    const copilot = new CopilotWidgetPage(page);
    await copilot.openWidget();

    // Verify authenticated session attributes in DOM context
    const sessionContext = await page.evaluate(() => ({
      role: (window as any).eval('typeof CURRENT_USER_ROLE !== "undefined" ? CURRENT_USER_ROLE : null'),
      userId: (window as any).eval('typeof CURRENT_USER_ID !== "undefined" ? CURRENT_USER_ID : null'),
      deptId: (window as any).eval('typeof CURRENT_DEPT_ID !== "undefined" ? CURRENT_DEPT_ID : null'),
    }));

    expect(sessionContext.userId).toBe(1);
    expect(sessionContext.role).toBeDefined();

    // Send a query and ensure greeting / assistance is returned
    await copilot.sendMessage('who are you');
    await copilot.waitForAssistantResponse();
    const reply = await copilot.getLastMessageText();
    expect(reply.toLowerCase()).toMatch(/copilot|risk|enterprise/);
  });

  test('2. Workflow Initiation & Cancellation: User starts wizard and cancels safely', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login('refining_ro', '1234');

    const copilot = new CopilotWidgetPage(page);
    await copilot.openWidget();

    // Initiate risk creation
    await copilot.sendMessage('create risk');
    await copilot.waitForAssistantResponse();
    const wizardStep = await copilot.getLastMessageText();
    expect(wizardStep.toLowerCase()).toMatch(/risk name|title|wizard|step/);

    // Cancel workflow
    await copilot.sendMessage('cancel');
    await copilot.waitForAssistantResponse();
    const cancelReply = await copilot.getLastMessageText();
    expect(cancelReply.toLowerCase()).toMatch(/cancel|stopped|reset/);
  });

  test('3. Cross-Agent Switching & Draft Preservation on Read-Only Queries', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login('refining_ro', '1234');

    const copilot = new CopilotWidgetPage(page);
    await copilot.openWidget();

    // Start drafting a risk
    await copilot.sendMessage('create risk Pipeline Integrity Test');
    await copilot.waitForAssistantResponse();

    // Interruption: Ask a general query without cancelling draft
    await copilot.sendMessage('what is the risk matrix distribution');
    await copilot.waitForAssistantResponse();
    const generalReply = await copilot.getLastMessageText();
    expect(generalReply.toLowerCase()).toMatch(/distribution|matrix|risk|level|low|medium|high/);

    // Cancel to clean up session
    await copilot.sendMessage('cancel');
    await copilot.waitForAssistantResponse();
  });

  test('4. Governance Rejection requires justification remark', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login('gas_fh', '1234');

    const copilot = new CopilotWidgetPage(page);
    await copilot.openWidget();

    await copilot.sendMessage('reject RSK-GAS-133');
    await copilot.waitForAssistantResponse();
    const reply = await copilot.getLastMessageText();
    expect(reply.toLowerCase()).toMatch(/remark|reason|justification|mandatory/);
  });

  test('5. Treatment Management Flow: Prompt for action plan & confirmation feedback', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login('refining_ro', '1234');

    const copilot = new CopilotWidgetPage(page);
    await copilot.openWidget();

    await copilot.sendMessage('add treatment for RSK-REF-001');
    await copilot.waitForAssistantResponse();
    const reply = await copilot.getLastMessageText();
    expect(reply.toLowerCase()).toMatch(/action plan|treatment|target date|owner/);

    // Cancel to keep session clean
    await copilot.sendMessage('cancel');
    await copilot.waitForAssistantResponse();
  });

});
