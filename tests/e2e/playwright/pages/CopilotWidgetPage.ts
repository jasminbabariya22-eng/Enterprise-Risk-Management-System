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
    if (await this.widgetTriggerButton.isVisible()) {
      await this.widgetTriggerButton.click({ force: true });
    }
    await this.page.evaluate(() => {
      const win = document.getElementById('erm-copilot-window');
      const launcher = document.getElementById('erm-copilot-launcher');
      if (win && win.style.display !== 'flex') {
        win.style.display = 'flex';
        if (launcher) launcher.style.display = 'none';
      }
    });
    await this.chatInput.waitFor({ state: 'visible', timeout: 10000 });
  }

  async sendMessage(message: string) {
    await this.chatInput.waitFor({ state: 'visible', timeout: 5000 });
    await this.chatInput.fill(message);
    await this.sendButton.click();
  }

  async waitForAssistantResponse() {
    await this.page.waitForSelector('.chat-msg.bot', { timeout: 20000 });
    await this.page.waitForTimeout(500);
  }

  async getLastMessageText(): Promise<string> {
    const messages = this.page.locator('.chat-msg.bot .bot-content-area, .chat-msg.bot, .bot-bubble-wrapper, .erm-message.assistant');
    const count = await messages.count();
    if (count > 0) {
      return (await messages.nth(count - 1).textContent()) || '';
    }
    return '';
  }
}
