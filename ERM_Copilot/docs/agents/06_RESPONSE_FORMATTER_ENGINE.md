# 🎨 Centralized Response Formatter Engine Documentation (`ERMResponseFormatter`)

---

## 📌 1. Overview & Identity
- **Class Name:** [`ERMResponseFormatter`](file:///d:/ERM/ERM_Copilot/formatters/response_formatter.py#L11)
- **File Location:** [`d:/ERM/ERM_Copilot/formatters/response_formatter.py`](file:///d:/ERM/ERM_Copilot/formatters/response_formatter.py)
- **Role:** The centralized, single-source-of-truth visual rendering and template formatting engine for all ERM Copilot responses.
- **Why It Matters:**
  - Prevents hardcoded markdown strings from being duplicated across different agents.
  - Allows changing colors, badges, tables, button designs, and card structures globally from a single module.
  - Eliminates raw markdown syntax artifacts (`###`, `**`, `| :--- |`, unescaped pipes, or bullet dashes) by outputting clean, standardized structures.

---

## 🛠️ 2. Core API Methods & Formatter Catalogue

| Method Name | Purpose | Example Input | Formatted Output Component |
|---|---|---|---|
| `get_severity_badge(score_or_level)` | Returns color-coded severity pill | `16` | `🔴 **Critical** (16)` |
| `get_status_badge(status)` | Returns status label with emoji | `2` | `⏳ Submitted to FH` |
| `format_table(headers, rows, alignments)` | Builds well-aligned markdown table | `headers, rows` | Clean table structure |
| `format_key_value_table(items)` | Formats 2-column parameter review card | `[("Risk ID", "RSK-001")]` | 2-column summary card |
| `format_action_buttons(buttons)` | Builds 1-click interactive action buttons | `[("Approve", "approve RSK-001", "confirm")]` | `[btn-confirm:Approve\|approve RSK-001]` |
| `format_risk_creation_success(data)` | Risk registration confirmation card | `data` dict | 2-column property card + milestones |
| `format_approval_queue(data, scope)` | Approval queue table with 1-click actions | `data` list | Table with inline Approve, Return & Audit buttons |
| `format_audit_trail(data)` | Comprehensive lifecycle audit history | `data` dict | 4-stage governance timeline + treatment milestones |
| `format_risk_scoring(data)` | $5\times 5$ matrix scoring calculation | `data` dict | Metric evaluation table + mandatory controls |
| `format_department_summary(data, scope)` | Enterprise department risk breakdown | `data` list | Aggregate summary table with fleet totals |
| `format_daily_briefing(role, type, count, items)` | Proactive morning task overview | `items` list | Action queue table with 1-click review buttons |
| `format_heatmap_matrix(dist, scope)` | Interactive $5\times 5$ risk matrix | `dist` dict | Full $5\times 5$ distribution grid + severity filters |
| `format_resubmit_success(res)` | Risk resubmission confirmation | `res` dict | Resubmission table + reset verification |

---

## 🎨 3. CSS Classes in Frontend Widget Binding

The formatted responses bind directly with the CSS stylesheet in [`erm_copilot_widget.html`](file:///d:/ERM/ERM_WEB_APP/app/templates/partials/erm_copilot_widget.html):

| UI Component | CSS Class | Visual Styling |
|---|---|---|
| **Tables** | `.copilot-table-wrapper`, `.copilot-table` | Rounded borders, hover row highlight, clean padding. |
| **Inline Code** | `.copilot-inline-code` | Monospace font, subtle background (`#f1f5f9`), rounded chip. |
| **Dividers** | `.copilot-divider` | Subtle 1px horizontal rule (`#e2e8f0`). |
| **Section Header** | `.copilot-section-header` | Bold 14px text, dark slate color (`#0f172a`), flex gap. |
| **Critical Pill** | `.copilot-badge.badge-critical` | Rose red background (`#ffe4e6`), dark red text (`#9f1239`). |
| **High Pill** | `.copilot-badge.badge-high` | Orange background (`#ffedd5`), dark orange text (`#c2410c`). |
| **Medium Pill** | `.copilot-badge.badge-medium` | Yellow background (`#fef9c3`), gold text (`#854d0e`). |
| **Low Pill** | `.copilot-badge.badge-low` | Green background (`#dcfce7`), dark green text (`#166534`). |
| **Confirm Button** | `.copilot-action-btn[btn-confirm]` | Emerald green (`#16a34a`), white text, hover lift. |
| **Cancel Button** | `.copilot-action-btn[btn-cancel]` | Crimson red (`#dc2626`), white text, hover lift. |
| **Action Button** | `.copilot-action-btn` | Royal blue outline (`#3b82f6`), hover glow. |
