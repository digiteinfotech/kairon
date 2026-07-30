import mongoengine
from typing import List, Dict, Any, Optional
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.shared.utils import Utility


import pymongo

def ensure_mongo_connection():
    """Ensures MongoDB connection is established to the primary 'conversations' DB."""
    try:
        if "events" not in Utility.environment:
            Utility.environment["events"] = {"audit_logs": {"attributes": ["user", "bot"]}}
        mongoengine.get_db()
    except Exception:
        try:
            mongoengine.connect("conversations", host="mongodb://localhost:27017/conversations")
        except Exception:
            try:
                import mongomock
                mongoengine.connect("conversations_mock", is_mock=True)
            except Exception:
                pass


class TenantService:

    @staticmethod
    def _authorize_tenant_access(site_name: str, user_email: str) -> bool:
        if not user_email:
            return False
        if user_email.strip().lower() == "admin@kairon.io":
            return True
        ensure_mongo_connection()
        try:
            d = CRMClientDetails.objects(site_name=site_name).first()
            if d and getattr(d, 'user', None) == user_email.strip():
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def get_all_tenants(user_email: Optional[str] = None) -> List[Dict[str, Any]]:
        ensure_mongo_connection()
        try:
            if user_email and user_email.strip().lower() != "admin@kairon.io":
                docs = CRMClientDetails.objects(user=user_email.strip()).all()
            else:
                docs = CRMClientDetails.objects().all()
            results = []
            for d in docs:
                results.append({
                    "company_name": d.company_name,
                    "abbr": d.abbr,
                    "site_name": d.site_name,
                    "tier": getattr(d, "tier", 1),
                    "installed_apps": getattr(d, "installed_apps", ["crm"]),
                    "onboarding_status": d.onboarding_status,
                    "bot": d.bot,
                    "user": d.user,
                    "country": d.country,
                    "default_currency": d.default_currency,
                    "latest_backup_path": getattr(d, "latest_backup_path", None),
                    "created_at": str(d.id.generation_time) if hasattr(d, "id") and hasattr(d.id, "generation_time") else "N/A"
                })
            return results
        except Exception as e:
            return []

    @staticmethod
    def get_tenant_by_company(company_name: str, user_email: Optional[str] = None) -> Optional[Dict[str, Any]]:
        ensure_mongo_connection()
        try:
            d = CRMClientDetails.objects(company_name=company_name).first()
            if not d:
                return None
            
            if user_email and user_email.strip().lower() != "admin@kairon.io":
                if getattr(d, 'user', None) != user_email.strip():
                    return None
            
            return {
                "company_name": d.company_name,
                "abbr": d.abbr,
                "site_name": d.site_name,
                "tier": getattr(d, "tier", 1),
                "installed_apps": getattr(d, "installed_apps", ["crm"]),
                "onboarding_status": d.onboarding_status,
                "bot": d.bot,
                "user": d.user,
                "country": d.country,
                "default_currency": d.default_currency,
                "latest_backup_path": getattr(d, "latest_backup_path", None),
                "api_key": getattr(d, "api_key", None),
                "api_secret": getattr(d, "api_secret", None),
                "created_at": str(d.id.generation_time) if hasattr(d, "id") and hasattr(d.id, "generation_time") else "N/A"
            }
        except Exception:
            return None

    @staticmethod
    def delete_tenant(company_name: str, user_email: Optional[str] = None) -> bool:
        ensure_mongo_connection()
        try:
            d = CRMClientDetails.objects(company_name=company_name).first()
            if d:
                if user_email and user_email.strip().lower() != "admin@kairon.io":
                    if getattr(d, 'user', None) != user_email.strip():
                        return False
                d.delete()
                return True
            return False
        except Exception:
            return False

    @staticmethod
    def get_available_bots(user_email: Optional[str] = None) -> Dict[str, str]:
        """Fetch real bots from MongoDB 'conversations.bot' collection, filtered by logged in user email."""
        try:
            client = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
            db = client["conversations"]

            query = {}
            if user_email and user_email.strip().lower() != "admin@kairon.io":
                query = {"user": user_email.strip()}

            bots = list(db["bot"].find(query))
            result = {}
            for b in bots:
                bot_id = str(b.get("_id"))
                name = b.get("name", "Unnamed Bot")
                user = b.get("user", "Unknown")
                result[bot_id] = f"{name} ({user})"

            # If user has no bot documents yet, fallback to all available bots
            if not result:
                all_bots = list(db["bot"].find())
                for b in all_bots:
                    bot_id = str(b.get("_id"))
                    name = b.get("name", "Unnamed Bot")
                    user = b.get("user", "Unknown")
                    result[bot_id] = f"{name} ({user})"

            return result if result else {"bot_enterprise_01": "Enterprise Sales Bot (bot_enterprise_01)"}
        except Exception:
            return {"bot_enterprise_01": "Enterprise Sales Bot (bot_enterprise_01)"}

    @staticmethod
    def get_bot_crm_status(bot_id: str) -> bool:
        """Fetch enable_crm status from MongoDB 'conversations.bot_settings' matching ID, ObjectId, or Bot Name."""
        try:
            from bson.objectid import ObjectId
            client = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
            db = client["conversations"]

            bot_name = None
            try:
                bot_doc = db["bot"].find_one({"$or": [{"_id": bot_id}, {"_id": ObjectId(bot_id)}]})
                if bot_doc:
                    bot_name = bot_doc.get("name")
            except Exception:
                pass

            query_conditions = [{"bot": bot_id}]
            try:
                query_conditions.append({"bot": ObjectId(bot_id)})
            except Exception:
                pass
            if bot_name:
                query_conditions.append({"bot": bot_name})

            setting = db["bot_settings"].find_one({"$or": query_conditions})
            if setting and "enable_crm" in setting:
                return bool(setting.get("enable_crm"))
            return False
        except Exception:
            return False

    @staticmethod
    def set_bot_crm_status(bot_id: str, enable: bool) -> bool:
        """Update enable_crm on the existing full MongoDB document in 'conversations.bot_settings'."""
        try:
            from bson.objectid import ObjectId
            client = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
            db = client["conversations"]

            bot_name = None
            bot_user = "admin@kairon.io"
            try:
                bot_doc = db["bot"].find_one({"$or": [{"_id": bot_id}, {"_id": ObjectId(bot_id)}]})
                if bot_doc:
                    bot_name = bot_doc.get("name")
                    bot_user = bot_doc.get("user", bot_user)
            except Exception:
                pass

            query_conditions = [{"bot": bot_id}]
            try:
                query_conditions.append({"bot": ObjectId(bot_id)})
            except Exception:
                pass
            if bot_name:
                query_conditions.append({"bot": bot_name})

            existing_doc = db["bot_settings"].find_one({"$or": query_conditions})

            if existing_doc:
                db["bot_settings"].update_one(
                    {"_id": existing_doc["_id"]},
                    {"$set": {"enable_crm": enable}}
                )
            else:
                db["bot_settings"].update_one(
                    {"bot": bot_id},
                    {"$set": {
                        "enable_crm": enable,
                        "user": bot_user,
                        "status": True,
                        "is_billed": False,
                        "analytics": {"fallback_intent": "nlu_fallback"}
                    }},
                    upsert=True
                )
            return True
        except Exception:
            return False

    @staticmethod
    def get_tenant_db_tables(site_name: str, user_email: str) -> List[str]:
        """Fetch all database table names for a tenant site."""
        if not TenantService._authorize_tenant_access(site_name, user_email):
            raise PermissionError("Access Denied: You are not authorized to view this tenant's data.")
        try:
            import subprocess, json
            py_script = f"""
import frappe, json
frappe.init(site='{site_name}', sites_path='/home/frappe/frappe-bench/sites')
frappe.connect()
tables = frappe.db.get_tables()
print(json.dumps(tables))
"""
            res = subprocess.run([
                "docker", "exec", "-w", "/home/frappe/frappe-bench/sites", "frappe-backend-1",
                "/home/frappe/frappe-bench/env/bin/python", "-c", py_script
            ], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                lines = res.stdout.strip().split("\n")
                return json.loads(lines[-1])
            return []
        except Exception:
            return []

    @staticmethod
    def get_tenant_users(site_name: str, user_email: str) -> List[Dict[str, Any]]:
        """Fetch all users and their assigned roles for a tenant site."""
        if not TenantService._authorize_tenant_access(site_name, user_email):
            raise PermissionError("Access Denied: You are not authorized to view this tenant's users.")
        try:
            import subprocess, json
            py_script = f"""
import frappe, json
frappe.init(site='{site_name}', sites_path='/home/frappe/frappe-bench/sites')
frappe.connect()
users = frappe.get_all('User', fields=['name', 'email', 'first_name', 'enabled', 'creation', 'user_type'])
res = []
for u in users:
    try:
        roles = [r.role for r in frappe.get_doc('User', u.name).roles]
    except Exception:
        roles = []
    res.append({{
        'name': u.name,
        'email': u.email,
        'first_name': u.first_name,
        'enabled': u.enabled,
        'user_type': u.user_type,
        'creation': str(u.creation),
        'roles': roles
    }})
print(json.dumps(res))
"""
            res = subprocess.run([
                "docker", "exec", "-w", "/home/frappe/frappe-bench/sites", "frappe-backend-1",
                "/home/frappe/frappe-bench/env/bin/python", "-c", py_script
            ], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                lines = res.stdout.strip().split("\n")
                return json.loads(lines[-1])
            return []
        except Exception:
            return []

    @staticmethod
    def get_table_data(site_name: str, table_name: str, limit: int = 50, user_email: str = None) -> List[Dict[str, Any]]:
        """Fetch raw rows for a specific database table in a tenant site."""
        if not user_email or not TenantService._authorize_tenant_access(site_name, user_email):
            raise PermissionError("Access Denied: You are not authorized to view this tenant's database.")
        try:
            import subprocess, json
            py_script = f"""
import frappe, json
frappe.init(site='{site_name}', sites_path='/home/frappe/frappe-bench/sites')
frappe.connect()
data = frappe.db.sql("SELECT * FROM \\\"{table_name}\\\" LIMIT {limit}", as_dict=True)
clean_data = []
for row in data:
    clean_row = {{}}
    for k, v in row.items():
        clean_row[k] = str(v) if v is not None else ""
    clean_data.append(clean_row)
print(json.dumps(clean_data))
"""
            res = subprocess.run([
                "docker", "exec", "-w", "/home/frappe/frappe-bench/sites", "frappe-backend-1",
                "/home/frappe/frappe-bench/env/bin/python", "-c", py_script
            ], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                lines = res.stdout.strip().split("\n")
                return json.loads(lines[-1])
            return []
        except Exception:
            return []

    @staticmethod
    def invite_user_to_tenant(site_name: str, email: str, roles: List[str], password: str = "Password@123", user_email: str = None) -> Dict[str, Any]:
        """Invites / creates a user with specified roles and password on a tenant site."""
        if not user_email or not TenantService._authorize_tenant_access(site_name, user_email):
            return {"status": "error", "message": "Access Denied: You are not authorized to modify this tenant."}
        try:
            import subprocess, json
            roles_repr = repr(roles)
            py_script = f"""
import frappe, json
from frappe.utils.password import update_password

frappe.init(site='{site_name}', sites_path='/home/frappe/frappe-bench/sites')
frappe.connect()

user_email = '{email.strip()}'
if not frappe.db.exists('User', user_email):
    u = frappe.get_doc({{
        'doctype': 'User',
        'email': user_email,
        'first_name': user_email.split('@')[0].title(),
        'enabled': 1,
        'send_welcome_email': 1,
        'user_type': 'System User',
        'roles': [{{'role': r}} for r in {roles_repr}]
    }})
    u.insert(ignore_permissions=True)
else:
    u = frappe.get_doc('User', user_email)
    for r in {roles_repr}:
        if not any(ur.role == r for ur in u.roles):
            u.append('roles', {{'role': r}})
    u.save(ignore_permissions=True)

update_password(user_email, '{password}')
frappe.db.commit()
print(json.dumps({{'status': 'success', 'message': 'User ' + user_email + ' successfully created/invited on {site_name}'}}))
"""
            res = subprocess.run([
                "docker", "exec", "-w", "/home/frappe/frappe-bench/sites", "frappe-backend-1",
                "/home/frappe/frappe-bench/env/bin/python", "-c", py_script
            ], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                lines = res.stdout.strip().split("\n")
                return json.loads(lines[-1])
            return {"status": "error", "message": res.stderr or "Failed to invite user."}
        except Exception as e:
            return {"status": "error", "message": str(e)}
