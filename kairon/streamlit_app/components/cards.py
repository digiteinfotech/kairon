import streamlit as st
from typing import List, Optional


def render_header(title: str, subtitle: str, icon: str = "⚡"):
    """Renders a modern header banner."""
    st.markdown(f"""
        <div class="portal-header">
            <div class="portal-title">
                <span>{icon}</span> {title}
            </div>
            <div class="portal-subtitle">{subtitle}</div>
        </div>
    """, unsafe_allow_html=True)


def render_stat_card(label: str, value: str, subtext: str = "", border_color: str = "#272C38"):
    """Renders a clean metric card."""
    st.markdown(f"""
        <div class="metric-card" style="border-left: 3px solid {border_color};">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            {"<div class='metric-subtext'>" + subtext + "</div>" if subtext else ""}
        </div>
    """, unsafe_allow_html=True)


def render_status_badge(status: str) -> str:
    """Returns HTML for a colored status pill."""
    status_lower = str(status).lower()
    if status_lower in ["healthy", "active", "site_created", "success", "completed"]:
        css_class = "badge-healthy"
        dot = "●"
    elif status_lower in ["warning", "upgrading", "upgrading_to_tier_2"]:
        css_class = "badge-warning"
        dot = "▲"
    elif status_lower in ["failed", "failed_upgrade", "error"]:
        css_class = "badge-failed"
        dot = "✖"
    elif status_lower in ["tier 1", "tier_1", "1"]:
        css_class = "badge-tier1"
        dot = "1"
    elif status_lower in ["tier 2", "tier_2", "2"]:
        css_class = "badge-tier2"
        dot = "2"
    else:
        css_class = "badge-healthy"
        dot = "•"

    return f'<span class="badge {css_class}">{dot} {status.upper()}</span>'


def render_plan_preview(tier: int, strategy_key: str, apps: List[str], home_page: str, default_roles: List[str], dependencies: List[str], upgrade_supported: bool):
    """Renders a sleek preview card of the calculated ProvisioningPlan."""
    tier_badge = f'<span class="badge badge-tier{tier}">TIER {tier} ({("STANDALONE" if tier == 1 else "MONOLITHIC SUITE")})</span>'
    apps_html = " ".join([f'<span class="code-pill">{app}</span>' for app in apps])
    roles_html = " ".join([f'<span class="code-pill">{role}</span>' for role in default_roles])
    deps_html = " ".join([f'<span class="code-pill">{dep}</span>' for dep in dependencies])

    st.markdown(f"""
        <div class="metric-card" style="border: 1px solid var(--accent-purple);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <div style="font-weight: 700; font-size: 1.1rem; color: #FFFFFF;">Calculated Provisioning Target</div>
                {tier_badge}
            </div>
            <table style="width: 100%; border-collapse: collapse; font-size: 0.88rem; color: var(--text-primary);">
                <tr>
                    <td style="padding: 6px 0; color: var(--text-muted); width: 140px;">Strategy Key:</td>
                    <td style="padding: 6px 0; font-weight: 600; color: #60A5FA;"><code>{strategy_key}</code></td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: var(--text-muted);">Target Apps:</td>
                    <td style="padding: 6px 0;">{apps_html}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: var(--text-muted);">Landing Page:</td>
                    <td style="padding: 6px 0;"><code>{home_page}</code></td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: var(--text-muted);">Default Roles:</td>
                    <td style="padding: 6px 0;">{roles_html}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: var(--text-muted);">Dependencies:</td>
                    <td style="padding: 6px 0;">{deps_html}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: var(--text-muted);">In-Place Upgrade:</td>
                    <td style="padding: 6px 0; color: {"#34D399" if upgrade_supported else "#F87171"}; font-weight: 600;">
                        {"Supported (Tier 1 ──► Tier 2)" if upgrade_supported else "N/A (Monolithic Suite Installed)"}
                    </td>
                </tr>
            </table>
        </div>
    """, unsafe_allow_html=True)


def render_terminal_logs(logs: List[str]):
    """Renders a streaming monospace log box."""
    lines_html = []
    for line in logs:
        line_clean = line.strip()
        if "ERROR" in line_clean or "FAILED" in line_clean or "Failure" in line_clean:
            cls = "error"
        elif "WARN" in line_clean:
            cls = "warn"
        elif "SUCCESS" in line_clean or "PASSED" in line_clean or "completed" in line_clean:
            cls = "success"
        else:
            cls = "info"
        lines_html.append(f'<div class="terminal-line {cls}">{line_clean}</div>')

    st.markdown(f"""
        <div class="terminal-box">
            {"".join(lines_html)}
        </div>
    """, unsafe_allow_html=True)
