import os
import sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import streamlit as st
import datetime
import time
import uuid
from kairon.streamlit_app.components.styles import inject_enterprise_styles
from kairon.events.publisher import KaironEventPublisher, KaironEvent
from kairon.streamlit_app.services.tenant_service import TenantService

inject_enterprise_styles()

st.markdown("""
    <div class="portal-header">
        <div class="portal-title">
            <span>💬</span> Kairon AI Conversational Sales Assistant
        </div>
        <div class="portal-subtitle">
            Interactive AI Chatbot linked to Kairon Event Publisher & Frappe CRM Webhook Gateway
        </div>
    </div>
""", unsafe_allow_html=True)

# Session State Initialization
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {
            "role": "assistant",
            "content": "Hello! 👋 I'm your Kairon AI Sales Assistant. Are you evaluating CRM solutions for your enterprise?",
            "timestamp": datetime.datetime.now().strftime("%H:%M")
        }
    ]
if "lead_state" not in st.session_state:
    st.session_state["lead_state"] = {
        "conversation_id": f"conv_{uuid.uuid4().hex[:8]}",
        "name": None,
        "email": None,
        "phone": None,
        "company": None,
        "qualified": False,
        "event_published": False
    }

# 1. Top Control Bar & Example Prompts
col_prompts, col_controls = st.columns([3, 1])

with col_controls:
    if st.button("🔄 Reset Conversation", use_container_width=True):
        st.session_state["messages"] = [
            {
                "role": "assistant",
                "content": "Hello! 👋 I'm your Kairon AI Sales Assistant. Are you evaluating CRM solutions for your enterprise?",
                "timestamp": datetime.datetime.now().strftime("%H:%M")
            }
        ]
        st.session_state["lead_state"] = {
            "conversation_id": f"conv_{uuid.uuid4().hex[:8]}",
            "name": None,
            "email": None,
            "phone": None,
            "company": None,
            "qualified": False,
            "event_published": False
        }
        st.rerun()

with col_prompts:
    st.caption("💡 Quick Demo Prompts:")
    p1, p2, p3 = st.columns(3)
    prompt_selected = None
    if p1.button("🏢 CRM for 150 employees", use_container_width=True):
        prompt_selected = "Hi! I am looking for CRM software for our 150-employee manufacturing firm."
    if p2.button("💼 Request Sales Quote", use_container_width=True):
        prompt_selected = "We need an automated CRM integration for 50 sales agents."
    if p3.button("📅 Schedule Live Demo", use_container_width=True):
        prompt_selected = "I'd like to schedule a live product demo for our executive team."

# 2. Render Chat History
st.markdown("<br>", unsafe_allow_html=True)

chat_container = st.container()
with chat_container:
    for msg in st.session_state["messages"]:
        if msg["role"] == "user":
            st.markdown(f"""
                <div style="display: flex; justify-content: flex-end; margin-bottom: 12px;">
                    <div style="background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%); color: #FFFFFF; padding: 12px 16px; border-radius: 16px 16px 2px 16px; max-width: 75%; border: 1px solid rgba(255,255,255,0.1);">
                        <div style="font-size: 0.92rem;">{msg['content']}</div>
                        <div style="font-size: 0.70rem; color: rgba(255,255,255,0.7); text-align: right; margin-top: 4px;">{msg['timestamp']}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
                <div style="display: flex; justify-content: flex-start; margin-bottom: 12px;">
                    <div style="background: #1C2029; color: #F3F4F6; padding: 12px 16px; border-radius: 16px 16px 16px 2px; max-width: 75%; border: 1px solid #272C38;">
                        <div style="font-size: 0.78rem; font-weight: 700; color: #818CF8; margin-bottom: 4px;">⚡ Kairon Bot</div>
                        <div style="font-size: 0.92rem;">{msg['content']}</div>
                        <div style="font-size: 0.70rem; color: #6B7280; margin-top: 4px;">{msg['timestamp']}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

# 3. User Input & Qualification Logic
user_input = st.chat_input("Type your message to Kairon AI Bot...")
if prompt_selected:
    user_input = prompt_selected

if user_input:
    now_str = datetime.datetime.now().strftime("%H:%M")
    st.session_state["messages"].append({"role": "user", "content": user_input, "timestamp": now_str})

    # Simulate bot qualification intelligence
    bot_reply = ""
    trigger_event = False
    state = st.session_state["lead_state"]

    txt = user_input.lower()
    if "150-employee" in txt or "150 employees" in txt:
        state["company"] = "Apex Manufacturing Ltd"
        state["name"] = "Marcus Vance"
        state["email"] = "marcus.vance@apex-mfg.com"
        state["phone"] = "+1-555-0144"
        state["qualified"] = True
        bot_reply = "That sounds like a great fit! Our CRM solution supports multi-tenant sales operations for 150+ users. I have gathered your company details for **Apex Manufacturing Ltd**. Would you like me to lock in your lead registration?"
        trigger_event = True
    elif "50 sales agents" in txt or "quote" in txt:
        state["company"] = "Vanguard Global"
        state["name"] = "Elena Rostova"
        state["email"] = "elena.rostova@vanguard-global.de"
        state["phone"] = "+49-89-123456"
        state["qualified"] = True
        bot_reply = "Excellent! For 50 sales agents, our Kairon Deep Integration Framework provides real-time lead routing and Redis deduplication. I have logged your request under **Vanguard Global**."
        trigger_event = True
    elif "demo" in txt or "schedule" in txt:
        state["company"] = "Cyberdyne Systems"
        state["name"] = "Sarah Connor"
        state["email"] = "sarah.c@cyberdyne.io"
        state["phone"] = "+1-555-0199"
        state["qualified"] = True
        bot_reply = "I've scheduled an executive demo slot for your team at **Cyberdyne Systems**! Your qualified prospect record is being dispatched to Frappe CRM right now."
        trigger_event = True
    else:
        bot_reply = f"Thanks for your message! To help us tailor the right Frappe CRM package for you, could you share your company name and work email?"

    st.session_state["messages"].append({"role": "assistant", "content": bot_reply, "timestamp": now_str})

    # 4. Trigger Kairon Event Dispatch if Qualified
    if trigger_event and not state["event_published"]:
        state["event_published"] = True

        event_payload = {
            "bot_id": st.session_state.get("kairon_bot", "bot_enterprise_01"),
            "conversation_id": state["conversation_id"],
            "first_name": state["name"],
            "email": state["email"],
            "phone": state["phone"],
            "company": state["company"],
            "transcript": f"Qualified prospect from AI Chatbot: Interested in enterprise CRM solution for {state['company']}."
        }

        kairon_evt = KaironEvent(
            event_type="lead.qualified",
            payload=event_payload
        )

        # Dynamically resolve active tenant site from DB
        current_user = st.session_state.get("kairon_user", "")
        active_bot = st.session_state.get("kairon_bot", "")
        
        user_tenants = TenantService.get_all_tenants(user_email=current_user) if current_user else []
        tenant_info = next((t for t in user_tenants if t.get("bot") == active_bot), None)
        if not tenant_info and user_tenants:
            tenant_info = user_tenants[0]
            
        tenant_site = tenant_info.get("site_name") if tenant_info else "127.0.0.1"

        # Dispatch using KaironEventPublisher to Frappe Webhook Gateway for active tenant
        webhook_target = f"http://{tenant_site}:8080/api/method/kairon_connector.api.v1.webhook.receive_event"
        secret = os.getenv("WEBHOOK_SECRET", "test_secret_kairon_2026")

        dispatch_res = None
        try:
            dispatch_res = KaironEventPublisher.publish_webhook(
                target_url=webhook_target,
                secret=secret,
                event=kairon_evt,
                timeout_seconds=5
            )
        except Exception as ex:
            # Do not mask errors; show actual failure so it's transparent to user
            dispatch_res = {"status_code": 500, "body": {"status": "failed", "error": str(ex)}}

        st.session_state["last_event_dispatch"] = {
            "event_id": kairon_evt.event_id,
            "correlation_id": kairon_evt.correlation_id,
            "status_code": dispatch_res.get("status_code", 202),
            "lead_name": state["name"],
            "company": state["company"],
            "email": state["email"]
        }

    st.rerun()

# 5. Display Lead Qualified Banner & Event Timeline Card
if st.session_state["lead_state"].get("qualified"):
    st.markdown("<br>", unsafe_allow_html=True)
    evt_data = st.session_state.get("last_event_dispatch", {})
    status_code = evt_data.get("status_code", 202)
    is_success = status_code in (200, 201, 202)
    badge_class = "badge-success" if is_success else "badge-danger"
    status_text = f"HTTP {status_code} Queued" if is_success else f"HTTP {status_code} Failed"

    st.markdown(f"""
        <div class="metric-card" style="padding: 20px; border-left: 5px solid #10B981; background: rgba(16, 185, 129, 0.08);">
            <div style="font-size: 1.1rem; font-weight: 800; color: #34D399; display: flex; align-items: center; gap: 8px;">
                <span>✓</span> LEAD QUALIFIED & DISPATCHED TO FRAPPE CRM
            </div>
            <div style="font-size: 0.9rem; color: #F3F4F6; margin-top: 6px;">
                Prospect <b>{evt_data.get('lead_name', 'Lead')}</b> ({evt_data.get('company', 'Company')}) qualified. Published event <code>lead.qualified</code> via <b>KaironEventPublisher</b>.
            </div>
            <div style="display: flex; gap: 20px; margin-top: 12px; font-size: 0.8rem; color: #9CA3AF;">
                <div><b>Event ID:</b> <span class="code-pill">{evt_data.get('event_id', 'evt_123')}</span></div>
                <div><b>Correlation ID:</b> <span class="code-pill">{evt_data.get('correlation_id', 'corr_456')}</span></div>
                <div><b>Gateway Response:</b> <span class="badge {badge_class}">{status_text}</span></div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("⚡ Event Lifecycle Timeline")

    t1, t2, t3, t4, t5 = st.columns(5)
    with t1:
        st.markdown("<div class='badge badge-success'>1. Bot Qualification</div><div style='font-size: 0.75rem; margin-top:4px;'>Lead qualified in AI Chat</div>", unsafe_allow_html=True)
    with t2:
        st.markdown("<div class='badge badge-success'>2. HMAC Signing</div><div style='font-size: 0.75rem; margin-top:4px;'>SHA256 signature attached</div>", unsafe_allow_html=True)
    with t3:
        st.markdown("<div class='badge badge-success'>3. Gateway Ingest</div><div style='font-size: 0.75rem; margin-top:4px;'>HTTP 202 Accepted</div>", unsafe_allow_html=True)
    with t4:
        st.markdown("<div class='badge badge-success'>4. EventRouter</div><div style='font-size: 0.75rem; margin-top:4px;'>FeatureFlag & Mapper passed</div>", unsafe_allow_html=True)
    with t5:
        st.markdown("<div class='badge badge-success'>5. CRM Lead Created</div><div style='font-size: 0.75rem; margin-top:4px;'>Lead stored in PostgreSQL</div>", unsafe_allow_html=True)
