import re
import requests
from urllib.parse import urlparse
import streamlit as st
from components.ui import inject_custom_css, render_sidebar, get_status_badge
from components.auth import require_login
from services.crm import CrmService

inject_custom_css()
render_sidebar()
require_login()

st.markdown('# CRM &amp; <span class="gradient-text">ERPNext Onboarding</span>', unsafe_allow_html=True)
st.markdown("---")

bot_id = st.session_state.get("selected_bot_id")
bot_name = st.session_state.get("selected_bot_name", "Selected Bot")

if not bot_id:
    st.info("Select a bot from the sidebar to continue.")
    st.stop()

COUNTRIES = [
    "India", "United States", "United Kingdom", "Germany", "Canada",
    "Australia", "Singapore", "United Arab Emirates", "France", "Netherlands",
]
CURRENCIES = ["INR", "USD", "GBP", "EUR", "CAD", "AUD", "SGD", "AED"]
ABBR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,4}$")

FAILED_STATES = {
    "FAILED_PROJECT", "FAILED_BENCH", "FAILED_HEALTH",
    "FAILED_COMPANY", "FAILED_USER", "FAILED_VERIFICATION", "FAILED_UPGRADE",
}
STATUS_STEPS = [
    "PENDING", "PROJECT_CREATED", "BENCH_RUNNING", "SITE_CREATED",
    "SITE_HEALTHY", "COMPANY_CREATED", "USER_CREATED", "COMPLETED",
]


# ---------------------------------------------------------------------------
# Step 1: Real bot settings check (server-enforced; UI only reflects it)
# ---------------------------------------------------------------------------
try:
    with st.spinner("Checking bot settings..."):
        bot_settings = CrmService.get_bot_settings(bot_id)
    crm_enabled = bool(bot_settings.get("enable_crm", False))
except Exception as e:
    st.error(f"Unable to load bot settings for **{bot_name}**: {e}")
    st.stop()

if not crm_enabled:
    st.warning(f"CRM integration is not enabled for this bot ({bot_name}).")
    st.caption("Enabling requires bot admin access. This calls the existing Kairon bot settings API.")
    if st.button("Enable CRM for this bot", type="primary", disabled=st.session_state.get("enabling_crm", False)):
        st.session_state["enabling_crm"] = True
        try:
            with st.spinner("Enabling CRM..."):
                CrmService.enable_crm(bot_id, enable=True)
            st.success("CRM enabled. Reloading...")
        except Exception as e:
            st.error(f"Could not enable CRM: {e}")
        finally:
            st.session_state["enabling_crm"] = False
        st.rerun()
    st.stop()

st.success(f"CRM integration is enabled for **{bot_name}**.")

# ---------------------------------------------------------------------------
# Step 2: Resolve current tenant state from the backend (refresh-safe).
# A record already existing here means a tenant was already requested for
# this bot — never re-show the creation form in that case.
# ---------------------------------------------------------------------------
try:
    existing = CrmService.get_crm_details(bot_id)
except Exception as e:
    st.error(f"Could not reach the Kairon backend: {e}")
    st.stop()

current_status = existing.get("onboarding_status") if existing else None


def _resolve_open_url(site_url: str) -> str:
    """The backend returns the canonical http://<site> URL. In some local dev
    setups a reverse proxy in front of the frontend container force-redirects
    plain HTTP to HTTPS without a route for freshly provisioned tenant hosts,
    which 404s. Probe the canonical URL and fall back to the frontend
    container's own exposed port (same host, no path change) only if the
    canonical one isn't actually reachable. Cached per site for this session."""
    cache = st.session_state.setdefault("_resolved_open_urls", {})
    if site_url in cache:
        return cache[site_url]

    resolved = site_url
    try:
        resp = requests.get(site_url, timeout=3, allow_redirects=True)
        if not resp.ok:
            raise ValueError(f"status {resp.status_code}")
    except Exception:
        parsed = urlparse(site_url)
        fallback = f"http://{parsed.hostname}:8080{parsed.path or '/'}"
        try:
            resp = requests.get(fallback, timeout=3, allow_redirects=True)
            if resp.ok:
                resolved = fallback
        except Exception:
            pass

    cache[site_url] = resolved
    return resolved


def render_ready(details: dict, temp_password: str = None):
    site_name = details.get("site_name", "")
    site_url = details.get("site_url") or (f"http://{site_name}" if site_name else "")
    owner_email = details.get("erpnext_user", "")
    st.markdown(
        f"""
        <div class="glass-card" style="border-left:3px solid #10B981;">
            <h3>✅ Tenant Ready</h3>
            <p><b>Company:</b> {details.get("company_name", "N/A")}</p>
            <p><b>Site:</b> <code>{site_name}</code></p>
            <p><b>Status:</b> {get_status_badge("COMPLETED")}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if temp_password:
        # NOTE: this is the one-time login password for the CRM owner's own ERPNext
        # user account (owner_email, assigned System/Sales Manager roles) - issued
        # because SMTP is disabled in this environment so no welcome-email link can
        # be sent. It is NOT the Frappe "Administrator" superuser's password, which
        # is never returned by the backend and never shown here.
        st.warning(
            f"One-time login password for **{owner_email or 'your ERPNext user'}** "
            f"(shown once, this session only): `{temp_password}`\n\n"
            "Change this password immediately after your first login."
        )
    if site_url:
        open_url = _resolve_open_url(site_url)
        if open_url != site_url:
            st.caption(
                f"`{site_url}` isn't reachable through this environment's proxy — "
                f"opening via the frontend's direct port instead."
            )
        st.link_button("Open ERPNext →", open_url, use_container_width=True, type="primary")
    st.page_link("views/3_Invite_User.py", label="Continue to Invite User →", icon="✉️")


def render_failed(details: dict):
    st.error(f"Provisioning failed at step **{current_status}**.")
    last_error = details.get("last_error")
    if last_error:
        st.code(str(last_error))
    st.caption("You can retry — this will resume onboarding for the same company using the existing tenant record.")
    if st.button("Retry Provisioning", type="primary"):
        _run_onboarding(
            details.get("company_name"), details.get("abbr"),
            details.get("country"), details.get("default_currency"),
        )


def render_in_progress(details: dict):
    st.info(f"Onboarding already in progress for **{details.get('company_name')}**.")
    st.write(f"Current Status: {get_status_badge(current_status)}", unsafe_allow_html=True)
    try:
        step_idx = STATUS_STEPS.index(current_status) if current_status in STATUS_STEPS else 0
        st.progress(float(step_idx + 1) / len(STATUS_STEPS))
    except Exception:
        pass
    if st.button("Refresh Status"):
        st.rerun()


def _run_onboarding(company_name, abbr, country, currency):
    st.session_state["provisioning_inflight"] = True
    request_key = f"{bot_id}:{company_name.strip().lower()}"
    prior_result = st.session_state.get("provisioning_result")
    if (
        st.session_state.get("last_onboard_request_key") == request_key
        and prior_result
        and prior_result.get("status") == "COMPLETED"
    ):
        # Already completed this exact request in this session; do not resubmit.
        st.session_state["provisioning_inflight"] = False
        st.rerun()
        return
    try:
        with st.status("Provisioning CRM tenant...", expanded=True) as status_box:
            status_box.write("✓ Request accepted by Kairon backend")
            status_box.write("⏳ Creating ERPNext site, installing CRM, configuring tenant...")
            res = CrmService.onboard_crm(
                bot_id, company_name.strip(), country, currency, abbr.strip().upper(),
                selected_modules=["CRM"],
            )
            data = res.get("data", res) or {}
            # Keep the temporary_password out of the persisted provisioning_result --
            # that dict survives reruns/page revisits, which would silently redisplay
            # the credential every time despite the "shown once" message below.
            temp_password = data.pop("temporary_password", None)
            st.session_state["provisioning_result"] = data
            if temp_password:
                st.session_state["provisioning_temp_password"] = temp_password
            st.session_state["last_onboard_request_key"] = request_key
            final_status = data.get("status")
            if final_status == "COMPLETED":
                status_box.update(label="Provisioning complete", state="complete")
            else:
                status_box.update(label=f"Provisioning stopped: {final_status}", state="error")
    except Exception as e:
        st.error(f"Provisioning request failed: {e}")
    finally:
        st.session_state["provisioning_inflight"] = False
    st.rerun()


# ---------------------------------------------------------------------------
# Step 3: Route to the correct screen based on real backend state.
# ---------------------------------------------------------------------------
if current_status == "COMPLETED":
    # pop(), not get() -- read the one-time password exactly once, then it's gone
    # from session state so a later rerun/page revisit can't redisplay it.
    temp_pw = st.session_state.pop("provisioning_temp_password", None)
    render_ready(existing, temp_password=temp_pw)

elif current_status in FAILED_STATES:
    render_failed(existing)

elif current_status is not None:
    render_in_progress(existing)

else:
    st.markdown("### Create CRM Tenant")
    with st.form("tenant_creation_form"):
        company_name = st.text_input("Company Name", placeholder="e.g. Acme Restaurants Pvt Ltd")
        abbr = st.text_input("Company Abbreviation", placeholder="e.g. ARPL", max_chars=5)
        col1, col2 = st.columns(2)
        with col1:
            country = st.selectbox("Country", COUNTRIES)
        with col2:
            currency = st.selectbox("Currency", CURRENCIES)

        submitted = st.form_submit_button(
            "Create CRM Tenant",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.get("provisioning_inflight", False),
        )

    if submitted:
        errors = []
        if not company_name or not company_name.strip():
            errors.append("Company Name is required.")
        if not abbr or not abbr.strip():
            errors.append("Company Abbreviation is required.")
        elif not ABBR_RE.match(abbr.strip()):
            errors.append("Abbreviation must be 2-5 alphanumeric characters, starting with a letter.")

        if errors:
            for err in errors:
                st.error(err)
        else:
            _run_onboarding(company_name, abbr, country, currency)
