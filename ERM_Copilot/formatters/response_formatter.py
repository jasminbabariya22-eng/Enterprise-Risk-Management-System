"""
Centralized Response Formatter Engine for ERM Copilot.
Provides unified, consistent, and beautiful UI response layouts for all Copilot agents.
Enables changing themes, markdown structures, table formats, and cards from a single location.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union


class ERMResponseFormatter:
    """
    Centralized Formatter for generating rich, consistent Copilot responses.
    """

    # --- STATUS & SEVERITY MAPS ---
    STATUS_MAP: Dict[Union[int, str], str] = {
        1: "📝 Draft",
        2: "⏳ Submitted to FH",
        3: "🟣 FH Approved",
        4: "👑 RM Approved",
        5: "✅ Approved",
        6: "🎯 Pending for Action",
        "draft": "📝 Draft",
        "submitted": "⏳ Submitted to FH",
        "submitted to functional head": "⏳ Submitted to FH",
        "fh approved": "🟣 FH Approved",
        "rm approved": "👑 RM Approved",
        "approved": "✅ Approved",
        "pending": "⏳ Pending Review"
    }

    @classmethod
    def get_severity_badge(cls, score_or_level: Union[int, float, str]) -> str:
        """Return standardized severity badge with colored indicator."""
        if isinstance(score_or_level, (int, float)):
            score = int(score_or_level)
            if score >= 15:
                return f"🔴 **Critical** ({score})"
            elif score >= 10:
                return f"🟠 **High** ({score})"
            elif score >= 5:
                return f"🟡 **Medium** ({score})"
            else:
                return f"🟢 **Low** ({score})"
        
        level_str = str(score_or_level).strip().lower()
        if "crit" in level_str:
            return "🔴 **Critical**"
        elif "high" in level_str:
            return "🟠 **High**"
        elif "med" in level_str:
            return "🟡 **Medium**"
        elif "low" in level_str:
            return "🟢 **Low**"
        return f"⚪ **{score_or_level}**"

    @classmethod
    def get_status_badge(cls, status: Union[int, str]) -> str:
        """Return standardized status badge with icon."""
        if isinstance(status, int):
            return cls.STATUS_MAP.get(status, f"⚠️ Status {status}")
        st_lower = str(status).strip().lower()
        return cls.STATUS_MAP.get(st_lower, f"⚠️ {status}")

    @classmethod
    def format_table(
        cls,
        headers: List[str],
        rows: List[List[str]],
        alignments: Optional[List[str]] = None
    ) -> str:
        """
        Generate a well-aligned markdown table.
        alignments: list of 'left', 'center', 'right'
        """
        if not headers or not rows:
            return ""

        # Default alignments
        num_cols = len(headers)
        if not alignments or len(alignments) != num_cols:
            alignments = ["left"] * num_cols

        sep_map = {"left": ":---", "center": ":---:", "right": "---:"}
        separator = [sep_map.get(a, ":---") for a in alignments]

        header_line = "| " + " | ".join(headers) + " |"
        sep_line = "| " + " | ".join(separator) + " |"
        row_lines = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]

        return "\n".join([header_line, sep_line] + row_lines)

    @classmethod
    def format_key_value_table(
        cls,
        items: List[Tuple[str, Any]],
        header_left: str = "Property",
        header_right: str = "Value"
    ) -> str:
        """Format 2-column key-value summary table."""
        headers = [header_left, header_right]
        rows = [[f"**{k}**", str(v)] for k, v in items]
        return cls.format_table(headers, rows, ["left", "left"])

    @classmethod
    def format_action_buttons(cls, buttons: List[Tuple[str, str, Optional[str]]]) -> str:
        """
        Format action buttons list.
        Each item is (label, command, type) where type is 'confirm', 'cancel', or None (standard).
        """
        btn_strs = []
        for item in buttons:
            label = item[0]
            cmd = item[1]
            b_type = item[2] if len(item) > 2 else None
            if b_type == "confirm":
                btn_strs.append(f"[btn-confirm:{label}|{cmd}]")
            elif b_type == "cancel":
                btn_strs.append(f"[btn-cancel:{label}|{cmd}]")
            else:
                btn_strs.append(f"[btn:{label}|{cmd}]")
        return " ".join(btn_strs)

    # --- SPECIFIC RESPONSES BUILDERS ---

    @classmethod
    def format_risk_creation_success(cls, data: Dict[str, Any]) -> str:
        """Format successful risk creation response."""
        rid = data.get("risk_id", "RSK-NEW-001")
        rname = data.get("risk_name", "Industrial Risk Assessment")
        dept = data.get("department_name", "Refining")
        st_label = data.get("status_label", "Draft (Status 1)")
        l = data.get("inherent_likelihood", 4)
        i = data.get("inherent_impact", 5)
        score = data.get("inherent_score", l * i)
        sev_badge = cls.get_severity_badge(score)
        created_at = str(data.get("created_on", ""))[:19]

        kv_items = [
            ("Generated Risk ID", f"**{rid}**"),
            ("Risk Title", f"**{rname}**"),
            ("Department", dept),
            ("Database Status", st_label),
            ("Inherent Rating", f"Likelihood {l} × Impact {i} = {sev_badge}"),
            ("Tables Populated", "`ers.risk_register`, `ers.risk_description`, `ers.risk_treatment`"),
            ("Created At", f"**{created_at}**")
        ]

        table_md = cls.format_key_value_table(kv_items, "Record Property", "Details & Database Values")
        treatments_text = ""
        if data.get("treatments"):
            treatments_text = "\n\n**🛠️ Initial Action Plans Created:**\n" + "\n".join([f"- {t}" for t in data.get("treatments")])

        return (
            f"### 💾 Risk Successfully Created & Saved in Database!\n\n"
            f"{table_md}\n"
            f"{treatments_text}"
        )

    @classmethod
    def format_approval_queue(cls, data: List[Dict[str, Any]], scope: str) -> str:
        """Format governance approval queue table with instant 1-click action buttons."""
        if not data:
            return (
                f"### 🛡️ Governance Approval Queue ({scope})\n\n"
                f"🎉 **No risks currently pending governance sign-off in this queue.**"
            )

        headers = ["Risk ID", "Risk Name & Description", "Department", "Owner", "Current Status"]
        rows = []
        action_buttons = []
        for r in data:
            rid = r.get("risk_id", "RSK-001")
            title = r.get("risk_title") or r.get("risk_name") or "Plant Hazard"
            dept = r.get("department_name") or "Enterprise"
            owner = r.get("owner_name") or "Risk Owner"
            st = r.get("risk_status", 2)
            st_label = cls.get_status_badge(st)
            rows.append([f"**{rid}**", f"**{title}**", dept, owner, st_label])
            action_buttons.append(
                f"[btn-confirm:✅ Approve {rid}|Approve {rid}] "
                f"[btn-cancel:❌ Return {rid}|Reject {rid} with remark Revision Required] "
                f"[btn:📜 Audit Trail|Show audit trail for {rid}]"
            )

        table_md = cls.format_table(headers, rows, ["left", "left", "left", "left", "left"])
        buttons_section = "\n\n👉 *Click an instant action below to sign off or inspect:*\n\n" + "\n\n".join(action_buttons)

        return (
            f"### 🛡️ Governance Approval Queue ({scope})\n\n"
            f"{table_md}"
            f"{buttons_section}"
        )

    @classmethod
    def format_audit_trail(cls, data: Dict[str, Any]) -> str:
        """Format structured audit trail & lifecycle history."""
        rid = data.get("risk_id", "RSK-001")
        rname = data.get("risk_name", "N/A")
        dept = data.get("department", "N/A")
        fy = data.get("financial_year", "2026-2027")

        lines = [
            f"### 📜 Comprehensive Audit Trail & Lifecycle History: **{rid}**\n",
            f"**Risk Title:** {rname}<br>",
            f"**Department:** {dept} | **Financial Year:** {fy}\n",
            "---",
            "#### 📌 Governance Stage Timeline\n",
            f"1. **Risk Creation & Assessment:** Registered on **{str(data.get('created_on', 'N/A'))[:19]}** by **{data.get('created_by_name', 'Risk Owner')}**.",
            f"   - *Inherent Score:* Likelihood {data.get('inherent_likelihood', 3)} × Impact {data.get('inherent_impact', 3)}",
            f"2. **Functional Head Approval:** {'✅ Approved' if data.get('fh_status') == 1 else '⚠️ Pending / In Progress'}",
            f"   - *Approver:* **{data.get('fh_approver', 'N/A')}** on **{str(data.get('fh_on', 'N/A'))[:19]}**",
            f"   - *Remark:* \"{data.get('fh_remark') or 'No remarks logged'}\"",
            f"3. **Risk Manager Validation:** {'✅ Approved' if data.get('rm_status') == 1 else '⚠️ Pending / In Progress'}",
            f"   - *Approver:* **{data.get('rm_approver', 'N/A')}** on **{str(data.get('rm_on', 'N/A'))[:19]}**",
            f"   - *Remark:* \"{data.get('rm_remark') or 'No remarks logged'}\"",
            f"4. **Risk Head Final Sign-off:** {'✅ Final Approved' if data.get('rh_status') == 1 else '⚠️ Pending / In Progress'}",
            f"   - *Approver:* **{data.get('rh_approver', 'N/A')}** on **{str(data.get('rh_on', 'N/A'))[:19]}**"
        ]

        treatments = data.get("treatments", [])
        if treatments:
            lines.append("\n#### 🛠️ Associated Treatment Milestones\n")
            t_headers = ["Task Plan", "Action Owner", "Target Date", "Progress", "Status"]
            t_rows = []
            for t in treatments:
                t_rows.append([
                    t.get("action_plan", ""),
                    t.get("action_owner", ""),
                    str(t.get("target_date", ""))[:10],
                    str(t.get("progress", "")),
                    str(t.get("status", ""))
                ])
            lines.append(cls.format_table(t_headers, t_rows, ["left", "left", "center", "center", "center"]))

        return "\n".join(lines)

    @classmethod
    def format_risk_scoring(cls, data: Dict[str, Any]) -> str:
        """Format 5x5 matrix scoring calculation."""
        l = data.get("likelihood", 4)
        i = data.get("impact", 4)
        score = data.get("risk_score", 16)
        sev_badge = cls.get_severity_badge(score)

        headers = ["Metric", "Parameter Value", "Governance Standard"]
        rows = [
            ["**Likelihood Rating (L)**", f"**{l} / 5**", "Scale 1 (Rare) to 5 (Almost Certain)"],
            ["**Impact Rating (I)**", f"**{i} / 5**", "Scale 1 (Insignificant) to 5 (Catastrophic)"],
            ["**Calculated Score (L × I)**", f"**{score} / 25**", "Risk Severity Index"],
            ["**Risk Severity Band**", sev_badge, f"Matrix Band {l}x{i}"]
        ]
        table_md = cls.format_table(headers, rows, ["left", "center", "left"])

        return (
            f"### 🎯 Risk Assessment & Scoring Calculation\n\n"
            f"{table_md}\n\n"
            f"**Mandatory Control Actions:**\n"
            f"- High-severity risk requires immediate engineering mitigation controls (e.g. automated interlocks, redundant monitoring).\n"
            f"- This risk requires formal 3-tier sign-off: **Functional Head → Risk Manager → Risk Head**."
        )

    @classmethod
    def format_department_summary(cls, data: List[Dict[str, Any]], scope: str) -> str:
        """Format enterprise-wide department breakdown table."""
        headers = ["Department", "Total Active Risks", "Pending FH Review", "Pending Exec Review", "Fully Approved"]
        rows = []
        tot_all, fh_all, exec_all, app_all = 0, 0, 0, 0
        for d in data:
            tot = d.get("total_risks", 0)
            fh = d.get("pending_fh_risks", 0)
            ex = d.get("pending_exec_risks", 0)
            ap = d.get("fully_approved_risks", 0)
            tot_all += tot
            fh_all += fh
            exec_all += ex
            app_all += ap
            rows.append([
                f"**{d.get('department', 'Unknown')}**",
                str(tot),
                f"{fh} ⚠️",
                f"{ex} 🟣",
                f"{ap} ✅"
            ])
        rows.append([
            "**Enterprise Fleet Total**",
            f"**{tot_all}**",
            f"**{fh_all}**",
            f"**{exec_all}**",
            f"**{app_all}**"
        ])
        table_md = cls.format_table(headers, rows, ["left", "center", "center", "center", "center"])

        return (
            f"### 📊 Department Risk Profile Summary ({scope})\n\n"
            f"{table_md}"
        )

    @classmethod
    def format_overdue_actions(cls, data: List[Dict[str, Any]], scope: str) -> str:
        """Format open and overdue action plan table."""
        headers = ["Risk ID", "Mitigation Task", "Responsible Owner", "Target Date", "Progress", "Status"]
        rows = []
        for a in data:
            rid = a.get("risk_id", "RSK-001")
            task = a.get("action_plan", "Inspection & Maintenance")
            owner = a.get("action_owner", "Owner")
            due = str(a.get("target_date", "2026-10-15"))[:10]
            prog = a.get("progress", "45%")
            st = a.get("status", "In Progress")
            st_badge = "✅ **Completed**" if "complete" in st.lower() else ("🔴 **Overdue**" if "overdue" in st.lower() else f"⚠️ {st}")
            rows.append([f"**{rid}**", f"**{task}**", owner, due, str(prog), st_badge])

        table_md = cls.format_table(headers, rows, ["left", "left", "left", "center", "center", "center"])
        return (
            f"### ⏰ Open & Overdue Action Plan Follow-ups ({scope})\n\n"
            f"{table_md}"
        )

    @classmethod
    def format_treatment_strategy(cls, query: str, data: Any) -> str:
        """Format proposed mitigation and treatment strategy."""
        dept_users = data.get("available_department_personnel", []) if isinstance(data, dict) else []
        assignees_table = ""
        if dept_users:
            u_headers = ["User ID", "Personnel Name", "Official Role", "Department", "Recommended Assignment"]
            u_rows = []
            for u in dept_users[:6]:
                uid = u.get("user_id", "")
                uname = u.get("full_name", "")
                urole = u.get("role_name", "")
                udept = u.get("department_name", "")
                recom = "Action Owner (Engineering & Maintenance)" if "_ao" in str(u.get("log_id")).lower() else ("Risk Co-Owner / Reviewer" if "owner" in urole.lower() else "Department Approver")
                u_rows.append([f"**{uid}**", f"**{uname}**", urole, udept, recom])
            assignees_table = "\n\n#### 👥 Recommended Department Assignees & Co-Owners (Selectable)\n\n" + cls.format_table(u_headers, u_rows, ["center", "left", "left", "left", "left"])

        phase_headers = ["Phase", "Mitigation Action & Control Tier", "Designated Owner", "Timeline", "KPI / Success Metric"]
        phase_rows = [
            ["1. Assessment", "Conduct root-cause FMEA & vibration baseline analysis.", "Reliability Engineering", "14 Days", "Completed FMEA Report"],
            ["2. Engineering Control", "Install dual pressurized mechanical seal barrier system with auto-flush.", "Maintenance Lead", "30 Days", "Zero seal leakage in 1000 hrs"],
            ["3. Condition Monitoring", "Deploy wireless vibration & temperature sensors linked to plant DCS.", "Instrumentation Eng", "45 Days", "Real-time telemetry configured"],
            ["4. Operational PM", "Revise preventive maintenance schedule to monthly lubrication & torque checks.", "Operations Tech", "60 Days", "Updated PM in CMMS"]
        ]
        phase_md = cls.format_table(phase_headers, phase_rows, ["left", "left", "left", "center", "left"])

        return (
            f"### ✍️ Proposed Risk Mitigation & Treatment Strategy\n"
            f"**Target Objective:** {query.strip()}\n\n"
            f"{phase_md}"
            f"{assignees_table}"
        )

    @classmethod
    def format_risk_register_list(cls, data: List[Dict[str, Any]], scope: str) -> str:
        """Format active risk register table."""
        headers = ["Risk ID", "Risk Title & Description", "Severity", "Department", "Current Status"]
        rows = []
        for r in data:
            rid = r.get("risk_id", "RSK-001")
            title = r.get("risk_title") or r.get("risk_name") or "Operational Risk"
            dept = r.get("department_name", "Enterprise")
            l = r.get("inherent_likelihood", 3)
            i = r.get("inherent_impact", 4)
            score = r.get("inherent_score") or (l * i)
            sev_badge = cls.get_severity_badge(score)
            st_code = r.get("risk_status", 1)
            st_label = cls.get_status_badge(st_code)
            rows.append([f"**{rid}**", f"**{title}**", sev_badge, dept, st_label])

        table_md = cls.format_table(headers, rows, ["left", "left", "center", "left", "left"])
        return (
            f"### 🛡️ Active Risk Register ({scope})\n\n"
            f"{table_md}"
        )

    @classmethod
    def format_daily_briefing(
        cls,
        user_role: str,
        briefing_type: str,
        pending_count: int,
        items: List[Dict[str, Any]]
    ) -> str:
        """Format proactive daily briefing summary."""
        lines = [
            f"### ☀️ Personalized Daily Briefing: {user_role or 'ERM Personnel'}\n",
            f"📊 **{briefing_type}:** `{pending_count} items pending`\n"
        ]
        if items:
            headers = ["Item ID", "Title / Action Plan", "Timeline", "Instant Action"]
            rows = []
            for it in items:
                r_code = it.get("risk_id") or f"TRT-{it.get('risk_treatment_id')}"
                r_text = it.get("risk_name") or it.get("action_plan") or "Operational Item"
                t_date = str(it.get("target_date") or it.get("created_on") or "2026-2027")[:10]
                if "owner" in user_role.lower() and "action" not in user_role.lower():
                    btn_code = f"[btn-confirm:🚀 Resubmit|Resubmit risk {r_code}] [btn:➕ Add Action Plan|Add action plan to risk {r_code}] [btn:📜 Audit|Show audit trail for {r_code}]" if "risk_id" in it else f"[btn:🔍 View|Show details for {r_code}]"
                else:
                    btn_code = f"[btn-confirm:✅ Approve|Approve {r_code}] [btn:📜 Audit|Show audit trail for {r_code}]" if "risk_id" in it else f"[btn:🔍 View|Show details for {r_code}]"
                rows.append([f"**{r_code}**", f"**{r_text}**", t_date, btn_code])
            lines.append(cls.format_table(headers, rows, ["left", "left", "center", "left"]))
        else:
            lines.append("🎉 **All clear!** No pending sign-offs or overdue actions currently assigned to your queue.")

        return "\n".join(lines)

    @classmethod
    def format_resubmit_success(cls, res: Dict[str, Any]) -> str:
        """Format resubmission confirmation."""
        kv_items = [
            ("Risk Identifier", f"**{res['risk_id']}** (Register #{res['risk_register_id']})"),
            ("Risk Title", f"**{res['risk_title']}**"),
            ("Current Status", "⏳ **Submitted to Functional Head**"),
            ("Target Review Queue", f"**{res['stage']}**"),
            ("Previous Approvals", "🧹 **Cleared (FH, RM, RH reset to Fresh Review)**"),
            ("Resubmitted By", f"**{res.get('resubmitted_by', 'Risk Owner')}** ({res.get('resubmitted_role', 'Risk Owner')})"),
            ("Timestamp", f"**{res['timestamp']}**")
        ]
        table_md = cls.format_key_value_table(kv_items, "Property", "Value")
        return (
            f"### 🚀 Risk Successfully Resubmitted for Governance Approval!\n\n"
            f"The risk record has been resubmitted to the **Functional Head** review queue. All previous review actions have been reset for a fresh evaluation cycle:\n\n"
            f"{table_md}\n\n"
            f"🛡️ *Audit Confirmation: Immutable governance audit record logged in `ers.risk_register_hist`. The risk is now pending Stage 1 Functional Head review.*"
        )

    @classmethod
    def format_heatmap_matrix(cls, dist: Dict[str, Any], scope_title: str) -> str:
        """Format 5x5 heatmap distribution."""
        g = dist.get("grid", {})
        headers = ["Likelihood \\ Impact", "1 (Insignificant)", "2 (Minor)", "3 (Moderate)", "4 (Major)", "5 (Catastrophic)"]
        rows = [
            ["**5 (Almost Certain)**", f"🟡 {g.get('5x1', 0)}", f"🟠 {g.get('5x2', 0)}", f"🔴 {g.get('5x3', 0)}", f"🔴 {g.get('5x4', 0)}", f"🔴 {g.get('5x5', 0)}"],
            ["**4 (Likely)**", f"🟡 {g.get('4x1', 0)}", f"🟡 {g.get('4x2', 0)}", f"🟠 {g.get('4x3', 0)}", f"🔴 {g.get('4x4', 0)}", f"🔴 {g.get('4x5', 0)}"],
            ["**3 (Possible)**", f"🟢 {g.get('3x1', 0)}", f"🟡 {g.get('3x2', 0)}", f"🟡 {g.get('3x3', 0)}", f"🟠 {g.get('3x4', 0)}", f"🔴 {g.get('3x5', 0)}"],
            ["**2 (Unlikely)**", f"🟢 {g.get('2x1', 0)}", f"🟢 {g.get('2x2', 0)}", f"🟡 {g.get('2x3', 0)}", f"🟡 {g.get('2x4', 0)}", f"🟠 {g.get('2x5', 0)}"],
            ["**1 (Rare)**", f"🟢 {g.get('1x1', 0)}", f"🟢 {g.get('1x2', 0)}", f"🟢 {g.get('1x3', 0)}", f"🟡 {g.get('1x4', 0)}", f"🟡 {g.get('1x5', 0)}"]
        ]
        table_md = cls.format_table(headers, rows, ["left", "center", "center", "center", "center", "center"])

        return (
            f"### 📊 Interactive 5×5 Risk Matrix Heatmap ({scope_title})\n\n"
            f"Total Monitored Risks: **{dist.get('total', 0)}** | 🔴 Critical: **{dist.get('critical_count', 0)}** | 🟠 High: **{dist.get('high_count', 0)}** | 🟡 Medium: **{dist.get('medium_count', 0)}** | 🟢 Low: **{dist.get('low_count', 0)}**\n\n"
            f"{table_md}\n\n"
            f"👉 **Instant Filter by Severity:**\n\n"
            f"[btn:🔴 View Critical Risks|Show top open high-severity risks in the plant] "
            f"[btn:🟠 View High Risks|Show top open high-severity risks in the plant] "
            f"[btn:⏰ View Overdue Actions|Which risk action plans are overdue or pending?]"
        )

    @classmethod
    def format_no_results(cls, query: str, scope: str, suggestions: List[str]) -> str:
        """Format no results fallback message with action chips."""
        btn_str = " ".join([f"[btn:{s}|{s}]" for s in suggestions]) if suggestions else "[btn:Show all active risks|Show all risks in the register]"
        return (
            f"### ℹ️ No Matching Risk Records Found\n\n"
            f"No risk items matched **\"{query.strip()}\"** within `{scope}`.\n\n"
            f"👉 **Try one of the following actions:**\n\n"
            f"{btn_str}"
        )


response_formatter = ERMResponseFormatter()
