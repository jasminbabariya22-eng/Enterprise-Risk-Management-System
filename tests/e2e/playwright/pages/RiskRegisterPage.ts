import { Page, Locator } from '@playwright/test';

export class RiskRegisterPage {
  readonly page: Page;
  readonly searchInput: Locator;
  readonly riskTableRows: Locator;
  readonly createRiskButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.searchInput = page.locator('input[type="search"], input[placeholder*="Search"]');
    this.riskTableRows = page.locator('table tbody tr');
    this.createRiskButton = page.locator('a:has-text("Create Risk"), button:has-text("Add Risk")');
  }

  async goto() {
    await this.page.goto('/risk-register');
  }

  async searchRisk(query: string) {
    await this.searchInput.fill(query);
    await this.page.keyboard.press('Enter');
  }
}
