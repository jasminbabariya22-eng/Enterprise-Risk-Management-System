# 🎨 Centralized Response Formatter Engine Documentation (`ERMResponseFormatter`)

---

## 📌 1. Overview & Identity
- **Class Name:** [`ERMResponseFormatter`](file:///d:/ERM/ERM_Copilot/formatters/response_formatter.py#L11)
- **Singleton Instance:** [`response_formatter`](file:///d:/ERM/ERM_Copilot/formatters/response_formatter.py#L464)
- **File Location:** [`d:/ERM/ERM_Copilot/formatters/response_formatter.py`](file:///d:/ERM/ERM_Copilot/formatters/response_formatter.py)
- **Role:** The centralized, single-source-of-truth visual rendering and template formatting engine for all ERM Copilot agents (Orchestrator, Risk Creation, Approval, Treatment).
- **Core Benefits:**
  - Standardizes tables, status badges, severity pills, confirmation cards, and action buttons across all subagents.
  - Eliminates raw markdown syntax artifacts (`###`, unescaped pipes, or bullet dashes) by generating clean, deterministic structures.
  - Decouples UI styling and theme changes from domain agent logic.

---

## 🛠️ 2. Comprehensive Method Catalogue

| Method Name | Parameters | Purpose | Output Format |
|---|---|---|---|
| `get_severity_badge` | `score_or_level: Union[int, float, str]` | Returns color-coded severity pill | `🔴 **Critical** (16)`, `🟠 **High** (12)`, `🟡 **Medium** (6)`, `🟢 **Low** (3)` |
| `get_status_badge` | `status: Union[int, str]` | Returns official ERM status badge with icon | `📝 Draft`, `⏳ Submitted to FH`, `🟣 FH Approved`, `👑 RM Approved`, `✅ Approved`, `🎯 Pending for Action` |
| `format_table` | `headers: List[str]`, `rows: List[List[str]]`, `alignments: Optional[List[str]]` | Builds aligned markdown table with customizable alignments (`left`, `center`, `right`) | Markdown table string |
| `format_key_value_table` | `items: List[Tuple[str, Any]]`, `header_left="Property"`, `header_right="Value"` | Formats 2-column key-value summary card | Clean 2-column table with bold property titles |
| `format_action_buttons` | `buttons: List[Tuple[str, str, Optional[str]]]` | Formats 1-click interactive action buttons | `[btn-confirm:Approve\|Approve RSK-001]`, `[btn-cancel:Reject\|Reject RSK-001]`, `[btn:Details\|Show details]` |
| `format_risk_creation_success` | `data: Dict[str, Any]` | Formats successful risk creation summary card | 2-column property card with generated ID, department, ratings, and populated tables |
| `format_approval_queue` | `data: List[Dict[str, Any]]`, `scope: str` | Formats governance approval queue | Structured table with inline `[btn-confirm:Approve]`, `[btn-cancel:Return]`, and `[btn:Audit Trail]` buttons |
| `format_audit_trail` | `data: Dict[str, Any]` | Formats 4-stage governance timeline & treatment milestones | Detailed lifecycle audit timeline (Stage 1 to Stage 4) + associated treatments table |
| `format_risk_scoring` | `data: Dict[str, Any]` | Formats $5\times 5$ matrix scoring calculation | Metric evaluation table + mandatory control actions |
| `format_department_summary` | `data: List[Dict[str, Any]]`, `scope: str` | Formats enterprise department breakdown | Aggregate table with department totals, pending counts, and enterprise fleet total |
| `format_overdue_actions` | `data: List[Dict[str, Any]]`, `scope: str` | Formats open and overdue treatment action plans | Table with risk ID, mitigation task, responsible owner, due date, progress, and status badge |
| `format_treatment_strategy` | `query: str`, `data: Any` | Formats proposed mitigation strategies and recommended assignees | Multi-phase action plan table + department personnel assignment table |
| `format_risk_register_list` | `data: List[Dict[str, Any]]`, `scope: str` | Formats active risk register listing | Table with Risk ID, title, severity pill, department, and current status |
| `format_daily_briefing` | `user_role: str`, `briefing_type: str`, `pending_count: int`, `items: List[Dict[str, Any]]` | Formats personalized morning briefing | Task summary + action table with contextual 1-click buttons |
| `format_resubmit_success` | `res: Dict[str, Any]` | Formats risk resubmission confirmation | 2-column summary confirming stage reset to Functional Head and history logged |
| `format_heatmap_matrix` | `dist: Dict[str, Any]`, `scope_title: str` | Formats interactive $5\times 5$ risk matrix | Full $5\times 5$ likelihood $\times$ impact grid with risk count badges and instant severity filter chips |
| `format_no_results` | `query: str`, `scope: str`, `suggestions: List[str]` | Formats user-friendly fallback with action chips | Clear notice + selectable suggestion buttons |

---

## 🎨 3. CSS Classes & Frontend Widget Binding

The formatted responses bind directly with the CSS stylesheet in [`erm_copilot_widget.html`](file:///d:/ERM/ERM_WEB_APP/app/templates/partials/erm_copilot_widget.html):

| UI Component | CSS Class / Selector | Visual Styling & Behavior |
|---|---|---|
| **Tables** | `.copilot-table-wrapper`, `.copilot-table` | Border-radius `8px`, subtle `#e2e8f0` border, hover row highlight (`#f8fafc`), clean padding `8px 12px`. |
| **Inline Code** | `.copilot-inline-code` | Monospace font, subtle background (`#f1f5f9`), rounded chip. |
| **Dividers** | `.copilot-divider` | Subtle 1px horizontal rule (`#e2e8f0`). |
| **Section Header** | `.copilot-section-header` | Bold 14px text, dark slate color (`#0f172a`), flex gap. |
| **Critical Pill** | `.copilot-badge.badge-critical` | Rose red background (`#ffe4e6`), dark red text (`#9f1239`), font-weight 600. |
| **High Pill** | `.copilot-badge.badge-high` | Orange background (`#ffedd5`), dark orange text (`#c2410c`), font-weight 600. |
| **Medium Pill** | `.copilot-badge.badge-medium` | Yellow background (`#fef9c3`), gold text (`#854d0e`), font-weight 600. |
| **Low Pill** | `.copilot-badge.badge-low` | Green background (`#dcfce7`), dark green text (`#166534`), font-weight 600. |
| **Confirm Button** | `.copilot-action-btn[btn-confirm]` | Emerald green background (`#16a34a`), white text, hover lift `-1px`, shadow `0 2px 4px rgba(22,163,74,0.2)`. |
| **Cancel Button** | `.copilot-action-btn[btn-cancel]` | Crimson red background (`#dc2626`), white text, hover lift `-1px`, shadow `0 2px 4px rgba(220,38,38,0.2)`. |
| **Action Button** | `.copilot-action-btn` | Royal blue outline (`#3b82f6`), text `#1d4ed8`, hover background `#eff6ff`, hover glow. |

---

## 🔄 4. Button Syntax & Parser Architecture

Copilot responses embed action buttons using the micro-syntax:
```text
[btn-confirm:Button Label|Command To Send]
[btn-cancel:Button Label|Command To Send]
[btn:Button Label|Command To Send]
```

### Frontend Parsing Pipeline
When the browser receives the markdown from Copilot:
1. The regex pattern `/\[(btn|btn-confirm|btn-cancel):([^\|]+)\|([^\]]+)\]/g` extracts the button metadata.
2. An interactive `<button class="copilot-action-btn ...">` element is created.
3. Clicking the button automatically populates the chat input and submits the command to the active workflow without requiring manual typing.
