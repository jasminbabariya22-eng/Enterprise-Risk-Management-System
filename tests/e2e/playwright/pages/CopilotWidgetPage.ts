import { Page, Locator, expect } from '@playwright/test';

export class CopilotWidgetPage {
  readonly page: Page;
  readonly widgetTriggerButton: Locator;
  readonly chatPanel: Locator;
  readonly chatInput: Locator;
  readonly sendButton: Locator;
  readonly messageList: Locator;
  readonly typingIndicator: Locator;

  constructor(page: Page) {
    this.page = page;
    this.widgetTriggerButton = page.locator('#erm-copilot-launcher, #erm-copilot-trigger, .erm-copilot-btn, [data-testid="copilot-trigger"]');
    this.chatPanel = page.locator('#erm-copilot-window, .erm-copilot-chat-container, [data-testid="copilot-panel"]');
    this.chatInput = page.locator('#copilot-user-input, #erm-chat-input, input[placeholder*="Ask"], textarea[placeholder*="Ask"], [data-testid="copilot-input"]');
    this.sendButton = page.locator('#copilot-send-btn, #erm-send-btn, button[title="Send Message"], [data-testid="copilot-send"]');
    this.messageList = page.locator('#erm-copilot-body, #erm-chat-messages, .erm-chat-body, [data-testid="copilot-messages"]');
    this.typingIndicator = page.locator('.copilot-typing-dots, .erm-typing-indicator, .typing-dots');
  }

  async openWidget() {
    const launcher = this.page.locator('#erm-copilot-launcher');
    if (await launcher.isVisible()) {
      await launcher.click();
    } else {
      await this.page.evaluate(() => {
        const win = document.getElementById('erm-copilot-window');
        const l = document.getElementById('erm-copilot-launcher');
        if (win) win.style.display = 'flex';
        if (l) l.style.display = 'none';
      });
    }
    await this.chatInput.waitFor({ state: 'visible', timeout: 10000 });
  }

  private botCount: number = 0;

  async sendMessage(message: string) {
    this.botCount = await this.page.locator('.chat-msg.bot').count();
    await this.chatInput.waitFor({ state: 'visible', timeout: 5000 });
    await this.chatInput.fill(message);
    await this.sendButton.click();
  }

  async waitForAssistantResponse() {
    const expected = this.botCount + 1;
    await expect(this.page.locator('.chat-msg.bot')).toHaveCount(expected, { timeout: 25000 });
    await this.page.locator('.copilot-typing-dots').waitFor({ state: 'detached', timeout: 20000 }).catch(() => {});
    await this.page.waitForTimeout(400);
  }

  async getLastMessageText(): Promise<string> {
    const botMessages = this.page.locator('.chat-msg.bot');
    const count = await botMessages.count();
    if (count === 0) return '';
    const lastBot = botMessages.nth(count - 1);
    const contentArea = lastBot.locator('.bot-content-area');
    if ((await contentArea.count()) > 0) {
      return (await contentArea.first().textContent()) || '';
    }
    return (await lastBot.textContent()) || '';
  }
}
