import streamlit as st

def inject_enterprise_styles():
    """Injects modern Linear/Vercel inspired dark mode CSS stylesheet into Streamlit."""
    st.markdown("""
        <style>
        /* Modern Dark Theme Palette */
        :root {
            --bg-primary: #0D0F12;
            --bg-secondary: #14171D;
            --bg-tertiary: #1C2029;
            --border-color: #272C38;
            --border-hover: #373E4F;
            --text-primary: #F3F4F6;
            --text-secondary: #9CA3AF;
            --text-muted: #6B7280;
            --accent-purple: #6366F1;
            --accent-blue: #3B82F6;
            --accent-green: #10B981;
            --accent-amber: #F59E0B;
            --accent-rose: #EF4444;
            --accent-pink: #EC4899;
        }

        /* Main View Background */
        .stApp {
            background-color: var(--bg-primary);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }

        /* Sidebar Styling */
        section[data-testid="stSidebar"] {
            background-color: var(--bg-secondary) !important;
            border-right: 1px solid var(--border-color);
        }

        /* Enterprise Header Card */
        .portal-header {
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.12) 0%, rgba(59, 130, 246, 0.05) 100%);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px 24px;
            margin-bottom: 24px;
        }

        .portal-title {
            font-size: 1.6rem;
            font-weight: 700;
            color: #FFFFFF;
            margin: 0;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .portal-subtitle {
            font-size: 0.9rem;
            color: var(--text-secondary);
            margin-top: 4px;
        }

        /* Enterprise Metric Card */
        .metric-card {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 16px 20px;
            transition: all 0.2s ease-in-out;
        }

        .metric-card:hover {
            border-color: var(--border-hover);
            transform: translateY(-1px);
        }

        .metric-label {
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
        }

        .metric-value {
            font-size: 1.8rem;
            font-weight: 700;
            color: #FFFFFF;
            margin-top: 4px;
        }

        .metric-subtext {
            font-size: 0.78rem;
            color: var(--text-secondary);
            margin-top: 4px;
        }

        /* Status Badges */
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.02em;
        }

        .badge-healthy, .badge-active, .badge-success {
            background: rgba(16, 185, 129, 0.15);
            color: #34D399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .badge-warning, .badge-upgrading {
            background: rgba(245, 158, 11, 0.15);
            color: #FBBF24;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }

        .badge-failed, .badge-error {
            background: rgba(239, 68, 68, 0.15);
            color: #F87171;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }

        .badge-tier1 {
            background: rgba(99, 102, 241, 0.15);
            color: #818CF8;
            border: 1px solid rgba(99, 102, 241, 0.3);
        }

        .badge-tier2 {
            background: rgba(236, 72, 153, 0.15);
            color: #F472B6;
            border: 1px solid rgba(236, 72, 153, 0.3);
        }

        /* Monospace Code Pill */
        .code-pill {
            background: var(--bg-tertiary);
            color: #60A5FA;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 0.82rem;
            border: 1px solid var(--border-color);
        }

        /* Live Terminal Box */
        .terminal-box {
            background: #090B0E;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 14px;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.8rem;
            color: #D1D5DB;
            max-height: 350px;
            overflow-y: auto;
        }

        .terminal-line {
            margin: 2px 0;
            line-height: 1.4;
        }

        .terminal-line.info { color: #60A5FA; }
        .terminal-line.success { color: #34D399; }
        .terminal-line.warn { color: #FBBF24; }
        .terminal-line.error { color: #F87171; }

        /* Custom Streamlit Buttons */
        .stButton>button {
            background-color: var(--bg-tertiary) !important;
            color: #FFFFFF !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
            transition: all 0.2s ease !important;
        }

        .stButton>button:hover {
            background-color: var(--border-hover) !important;
            border-color: var(--accent-purple) !important;
            color: #FFFFFF !important;
        }

        /* Hide Streamlit Default Branding */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)
