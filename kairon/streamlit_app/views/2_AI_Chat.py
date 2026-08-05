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
            Interactive AI Chatbot linked to Kairon Event Publisher & CRM Webhook Gateway
        </div>
    </div>
""", unsafe_allow_html=True)

# Profile Cache Service
import json

CACHE_FILE = "/tmp/kairon_prospect_profiles.json"
DEFAULT_PROFILES = [
    {
        "id": "geet_more",
        "name": "Geet",
        "company": "Reliance Tech Solutions",
        "email": "geet@reliancetech.in",
        "phone": "+91-98200-11223",
        "prompt": "Hi! I am Geet. We are looking for an automated CRM solution for 200 sales users at Reliance Tech.",
        "tag": "🏢 200 Sales Users"
    },
    {
        "id": "aryan_sharma",
        "name": "Aryan",
        "company": "Tata Digital Enterprises",
        "email": "aryan@tata-digital.in",
        "phone": "+91-98330-44556",
        "prompt": "We need real-time CRM lead dispatch for 50 sales agents across India.",
        "tag": "💼 50 Sales Agents"
    },
    {
        "id": "om_patel",
        "name": "Om",
        "company": "Infosys Systems Ltd",
        "email": "om@infosys-systems.in",
        "phone": "+91-98440-77889",
        "prompt": "I am Om. I'd like to schedule a live product demo for our executive team at Infosys.",
        "tag": "📅 Executive Demo"
    },
    {
        "id": "rohan_verma",
        "name": "Rohan",
        "company": "Mahindra Enterprise Ltd",
        "email": "rohan@mahindra-auto.in",
        "phone": "+91-98550-99001",
        "prompt": "Hi! I am Rohan. We evaluate Frappe CRM integration for Mahindra Enterprise.",
        "tag": "🚘 Enterprise CRM"
    },
    {
        "id": "yash_gupta",
        "name": "Yash",
        "company": "Bajaj Finance Ltd",
        "email": "yash@bajaj-finance.in",
        "phone": "+91-98660-33445",
        "prompt": "I am Yash. Please provide a quote for automated lead distribution at Bajaj Finance.",
        "tag": "💰 Financial Quote"
    }
]

def load_cached_profiles():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                saved = json.load(f)
                if isinstance(saved, list) and len(saved) > 0:
                    return saved
        except Exception:
            pass
    return DEFAULT_PROFILES

def save_profile_to_cache(profile):
    profiles = load_cached_profiles()
    # Replace if ID exists, else append
    existing = [p for p in profiles if p["id"] == profile["id"]]
    if existing:
        profiles = [profile if p["id"] == profile["id"] else p for p in profiles]
    else:
        profiles.append(profile)
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(profiles, f, indent=2)
    except Exception:
        pass
    return profiles

# Session State Initialization
if "prospect_profiles" not in st.session_state:
    st.session_state["prospect_profiles"] = load_cached_profiles()

if "active_profile_id" not in st.session_state:
    st.session_state["active_profile_id"] = st.session_state["prospect_profiles"][0]["id"]

def get_active_profile():
    pid = st.session_state.get("active_profile_id")
    for p in st.session_state["prospect_profiles"]:
        if p["id"] == pid:
            return p
    return st.session_state["prospect_profiles"][0]

if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {
            "role": "assistant",
            "content": "Hello! 👋 I'm your Kairon AI Sales Assistant. Are you evaluating CRM solutions for your enterprise?",
            "timestamp": datetime.datetime.now().strftime("%H:%M")
        }
    ]
if "lead_state" not in st.session_state:
    act_p = get_active_profile()
    st.session_state["lead_state"] = {
        "conversation_id": f"conv_{uuid.uuid4().hex[:8]}",
        "name": act_p["name"],
        "email": act_p["email"],
        "phone": act_p["phone"],
        "company": act_p["company"],
        "qualified": False,
        "event_published": False
    }

# --- Sidebar: Prospect Profile Manager ---
with st.sidebar:
    st.markdown("### 👤 Prospect Profiles (Cached)")
    st.caption("Select or create test personas to distinguish leads dispatched to Frappe CRM:")
    
    profiles = st.session_state["prospect_profiles"]
    profile_options = {f"{p['name']} ({p['company']})": p["id"] for p in profiles}
    
    # Determine current selection index
    curr_id = st.session_state["active_profile_id"]
    curr_index = 0
    for idx, p in enumerate(profiles):
        if p["id"] == curr_id:
            curr_index = idx
            break
            
    selected_label = st.selectbox(
        "Active Test Persona",
        options=list(profile_options.keys()),
        index=curr_index
    )
    selected_id = profile_options[selected_label]
    
    if selected_id != st.session_state["active_profile_id"]:
        st.session_state["active_profile_id"] = selected_id
        active_p = get_active_profile()
        st.session_state["lead_state"] = {
            "conversation_id": f"conv_{uuid.uuid4().hex[:8]}",
            "name": active_p["name"],
            "email": active_p["email"],
            "phone": active_p["phone"],
            "company": active_p["company"],
            "qualified": False,
            "event_published": False
        }
        st.session_state["messages"] = [
            {
                "role": "assistant",
                "content": f"Hello {active_p['name']}! 👋 I'm your Kairon AI Sales Assistant. How can we help **{active_p['company']}** today?",
                "timestamp": datetime.datetime.now().strftime("%H:%M")
            }
        ]
        st.rerun()

    active_p = get_active_profile()
    st.info(f"""
    **Current Persona:** {active_p['name']}  
    **Company:** {active_p['company']}  
    **Email:** `{active_p['email']}`  
    **Phone:** `{active_p['phone']}`
    """)

    with st.expander("➕ Create Custom Prospect Persona"):
        with st.form("create_profile_form"):
            c_name = st.text_input("Full Name", value="Elon Musk")
            c_company = st.text_input("Company Name", value="Tesla Motors")
            c_email = st.text_input("Work Email", value="elon@tesla.com")
            c_phone = st.text_input("Mobile No", value="+1-555-9988")
            c_prompt = st.text_area("Test Requirement Prompt", value="Hi, we need automated CRM lead distribution across 500 sales agents.")
            
            submit_btn = st.form_submit_button("💾 Save Persona to Cache")
            if submit_btn and c_name and c_email:
                new_id = f"profile_{uuid.uuid4().hex[:6]}"
                new_p = {
                    "id": new_id,
                    "name": c_name.strip(),
                    "company": c_company.strip(),
                    "email": c_email.strip(),
                    "phone": c_phone.strip(),
                    "prompt": c_prompt.strip(),
                    "tag": f"✨ Custom ({c_company})"
                }
                st.session_state["prospect_profiles"] = save_profile_to_cache(new_p)
                st.session_state["active_profile_id"] = new_id
                st.session_state["lead_state"] = {
                    "conversation_id": f"conv_{uuid.uuid4().hex[:8]}",
                    "name": new_p["name"],
                    "email": new_p["email"],
                    "phone": new_p["phone"],
                    "company": new_p["company"],
                    "qualified": False,
                    "event_published": False
                }
                st.session_state["messages"] = [
                    {
                        "role": "assistant",
                        "content": f"Hello {new_p['name']}! 👋 I'm your Kairon AI Sales Assistant. How can we help **{new_p['company']}** today?",
                        "timestamp": datetime.datetime.now().strftime("%H:%M")
                    }
                ]
                st.success(f"Created profile for {c_name}!")
                st.rerun()

# 1. Main Page Top Persona Bar & Quick Selection Buttons
st.markdown("### 👤 Select Test Prospect Persona")

profiles = st.session_state["prospect_profiles"]
profile_map = {f"{p['name']} ({p['company']})": p["id"] for p in profiles}

curr_id = st.session_state["active_profile_id"]
curr_idx = 0
for idx, p in enumerate(profiles):
    if p["id"] == curr_id:
        curr_idx = idx
        break

c_select, c_controls = st.columns([3, 1])

with c_select:
    selected_main_label = st.selectbox(
        "Active Persona",
        options=list(profile_map.keys()),
        index=curr_idx,
        key="main_persona_selector",
        label_visibility="collapsed"
    )
    selected_main_id = profile_map[selected_main_label]

    if selected_main_id != st.session_state["active_profile_id"]:
        st.session_state["active_profile_id"] = selected_main_id
        active_p = get_active_profile()
        st.session_state["lead_state"] = {
            "conversation_id": f"conv_{uuid.uuid4().hex[:8]}",
            "name": active_p["name"],
            "email": active_p["email"],
            "phone": active_p["phone"],
            "company": active_p["company"],
            "qualified": False,
            "event_published": False
        }
        st.session_state["messages"] = [
            {
                "role": "assistant",
                "content": f"Hello {active_p['name']}! 👋 I'm your Kairon AI Sales Assistant. How can we help **{active_p['company']}** today?",
                "timestamp": datetime.datetime.now().strftime("%H:%M")
            }
        ]
        st.rerun()

with c_controls:
    col_r, col_s = st.columns(2)
    with col_r:
        if st.button("🔄 Reset", use_container_width=True):
            active_p = get_active_profile()
            st.session_state["messages"] = [
                {
                    "role": "assistant",
                    "content": f"Hello {active_p['name']}! 👋 I'm your Kairon AI Sales Assistant. How can we help **{active_p['company']}** today?",
                    "timestamp": datetime.datetime.now().strftime("%H:%M")
                }
            ]
            st.session_state["lead_state"] = {
                "conversation_id": f"conv_{uuid.uuid4().hex[:8]}",
                "name": active_p["name"],
                "email": active_p["email"],
                "phone": active_p["phone"],
                "company": active_p["company"],
                "qualified": False,
                "event_published": False
            }
            st.rerun()
    with col_s:
        if st.button("📥 Sync CRM", use_container_width=True):
            st.rerun()

st.caption("⚡ 1-Click Quick Select Personas:")
p_cols = st.columns(min(len(profiles), 5))
prompt_selected = None

for idx, p in enumerate(profiles[:5]):
    with p_cols[idx]:
        is_active = p["id"] == st.session_state["active_profile_id"]
        btn_label = f"✓ {p['name']}" if is_active else f"👤 {p['name']}"
        if st.button(btn_label, key=f"quick_p_{p['id']}", use_container_width=True):
            st.session_state["active_profile_id"] = p["id"]
            st.session_state["lead_state"] = {
                "conversation_id": f"conv_{uuid.uuid4().hex[:8]}",
                "name": p["name"],
                "email": p["email"],
                "phone": p["phone"],
                "company": p["company"],
                "qualified": False,
                "event_published": False
            }
            st.session_state["messages"] = [
                {
                    "role": "assistant",
                    "content": f"Hello {p['name']}! 👋 I'm your Kairon AI Sales Assistant. How can we help **{p['company']}** today?",
                    "timestamp": datetime.datetime.now().strftime("%H:%M")
                }
            ]
            prompt_selected = p.get("prompt", f"Hi! I am {p['name']}. We are evaluating CRM solutions for {p['company']}.")

# 2. Render Chat History
st.markdown("<br>", unsafe_allow_html=True)

def sync_crm_messages():
    cid = st.session_state["lead_state"].get("conversation_id")
    if not cid:
        return
    try:
        import requests
        url = f"http://yash_123.localhost:8080/api/method/kairon_connector.api.v1.reply.get_conversation_history?conversation_id={cid}"
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            data = resp.json().get("message", {})
            comms = data.get("communications", [])
            existing_texts = {m["content"].strip().lower() for m in st.session_state["messages"]}
            
            active_p = get_active_profile()
            cust_name = (st.session_state["lead_state"].get("name") or active_p.get("name") or "").strip().lower()
            cust_email = (st.session_state["lead_state"].get("email") or active_p.get("email") or "").strip().lower()
            
            for comm in comms:
                text_raw = (comm.get("content") or "").strip()
                synced = comm.get("custom_kairon_synced", 0)

                # 1. Skip items created by Kairon inbound customer message sync
                if synced == 1:
                    continue
                
                # 2. Skip automated transcripts, bot logs, or headers
                text_lower = text_raw.lower()
                if "customer (" in text_lower or "customer message:" in text_lower or "qualified prospect" in text_lower or "kairon chatbot conversation transcript" in text_lower:
                    continue

                # 3. Clean up HTML tags if present (e.g. <p>hello</p>)
                text_clean = text_raw
                if "<" in text_clean and ">" in text_clean:
                    import re
                    text_clean = re.sub('<[^<]+?>', '', text_clean).strip()

                if text_clean and text_clean.lower() not in existing_texts:
                    st.session_state["messages"].append({
                        "role": "crm_sales",
                        "sender": comm.get("sender_full_name") or comm.get("sender") or "Sales Representative",
                        "content": text_clean,
                        "timestamp": datetime.datetime.now().strftime("%H:%M")
                    })
                    existing_texts.add(text_clean.lower())
    except Exception:
        pass

sync_crm_messages()

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
        elif msg["role"] == "crm_sales":
            st.markdown(f"""
                <div style="display: flex; justify-content: flex-start; margin-bottom: 12px;">
                    <div style="background: #064E3B; color: #ECFDF5; padding: 12px 16px; border-radius: 16px 16px 16px 2px; max-width: 75%; border: 1px solid #059669;">
                        <div style="font-size: 0.78rem; font-weight: 700; color: #34D399; margin-bottom: 4px;">👔 {msg.get('sender', 'Sales Representative')} (Frappe CRM)</div>
                        <div style="font-size: 0.92rem;">{msg['content']}</div>
                        <div style="font-size: 0.70rem; color: #A7F3D0; margin-top: 4px;">{msg['timestamp']}</div>
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
    active_p = get_active_profile()
    
    state["name"] = active_p["name"]
    state["email"] = active_p["email"]
    state["company"] = active_p["company"]
    state["phone"] = active_p["phone"]
    state["qualified"] = True
    
    bot_reply = f"Thank you **{active_p['name']}**! Our Kairon AI CRM integration is configured for **{active_p['company']}**. I have registered your inquiry details and dispatched your qualified lead to Frappe CRM!"
    trigger_event = True

    st.session_state["messages"].append({"role": "assistant", "content": bot_reply, "timestamp": now_str})

    # 4. Trigger Kairon Event Dispatch
    if not state["event_published"]:
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
            
        tenant_site = tenant_info.get("site_name") if tenant_info else "yash_123.localhost"

        # Dispatch using KaironEventPublisher to Webhook Gateway for active tenant
        webhook_target = f"http://{tenant_site}:8080/api/method/kairon_connector.api.v1.webhook.receive_event"
        secret = os.getenv("WEBHOOK_SECRET", "test_secret_123")

        dispatch_res = None
        try:
            dispatch_res = KaironEventPublisher.publish_webhook(
                target_url=webhook_target,
                secret=secret,
                event=kairon_evt,
                timeout_seconds=5
            )
        except Exception as ex:
            dispatch_res = {"status_code": 500, "body": {"status": "failed", "error": str(ex)}}

        st.session_state["last_event_dispatch"] = {
            "event_id": kairon_evt.event_id,
            "correlation_id": kairon_evt.correlation_id,
            "status_code": dispatch_res.get("status_code", 202),
            "lead_name": state["name"],
            "company": state["company"],
            "email": state["email"]
        }

    else:
        # Lead is already qualified; dispatch continuous inbound conversation reply event!
        current_user = st.session_state.get("kairon_user", "")
        active_bot = st.session_state.get("kairon_bot", "")
        user_tenants = TenantService.get_all_tenants(user_email=current_user) if current_user else []
        tenant_info = next((t for t in user_tenants if t.get("bot") == active_bot), None)
        if not tenant_info and user_tenants:
            tenant_info = user_tenants[0]
        tenant_site = tenant_info.get("site_name") if tenant_info else "yash_123.localhost"

        msg_payload = {
            "conversation_id": state["conversation_id"],
            "bot_id": active_bot or "bot_enterprise_01",
            "sender": state["name"],
            "sender_type": "customer",
            "message": user_input,
            "lead_id": state["name"]
        }
        msg_evt = KaironEvent(
            event_type="conversation.message.received",
            payload=msg_payload
        )
        webhook_target = f"http://{tenant_site}:8080/api/method/kairon_connector.api.v1.webhook.receive_event"
        secret = os.getenv("WEBHOOK_SECRET", "test_secret_123")
        try:
            KaironEventPublisher.publish_webhook(
                target_url=webhook_target,
                secret=secret,
                event=msg_evt,
                timeout_seconds=5
            )
        except Exception:
            pass

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
                <span>✓</span> LEAD QUALIFIED & DISPATCHED TO CRM
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
