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
    this.widgetTriggerButton = page.locator('#erm-copilot-trigger, .erm-copilot-btn, [data-testid="copilot-trigger"]');
    this.chatPanel = page.locator('#erm-copilot-window, .erm-copilot-chat-container, [data-testid="copilot-panel"]');
    this.chatInput = page.locator('#erm-chat-input, input[placeholder*="Ask"], textarea[placeholder*="Ask"], [data-testid="copilot-input"]');
    this.sendButton = page.locator('#erm-send-btn, button[title="Send Message"], [data-testid="copilot-send"]');
    this.messageList = page.locator('#erm-chat-messages, .erm-chat-body, [data-testid="copilot-messages"]');
    this.typingIndicator = page.locator('.erm-typing-indicator, .typing-dots');
  }

  async openWidget() {
    if (await this.widgetTriggerButton.isVisible()) {
      await this.widgetTriggerButton.click();
    }
  }

  async sendMessage(message: string) {
    await this.chatInput.fill(message);
    await this.sendButton.click();
  }

  async waitForAssistantResponse() {
    await this.page.waitForTimeout(1000);
  }

  async getLastMessageText(): Promise<string> {
    const messages = this.page.locator('.erm-message.assistant, .bot-message');
    const count = await messages.count();
    if (count > 0) {
      return (await messages.nth(count - 1).textContent()) || '';
    }
    return '';
  }
}
