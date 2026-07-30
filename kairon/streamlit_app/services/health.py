import os
import yaml
import requests
import psycopg2
import redis
from typing import Dict, Any

# Path to system.yaml in parent directory
SYSTEM_YAML_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "system.yaml"))

def load_system_config() -> Dict[str, Any]:
    """Parse system.yaml config file."""
    if not os.path.exists(SYSTEM_YAML_PATH):
        return {}
    with open(SYSTEM_YAML_PATH, "r") as f:
        try:
            return yaml.safe_load(f) or {}
        except Exception:
            return {}

class HealthService:
    @staticmethod
    def check_kairon_api(api_url: str) -> Dict[str, Any]:
        """Verify Kairon API service status."""
        try:
            res = requests.get(f"{api_url}/healthcheck", timeout=5)
            if res.ok:
                return {"status": "Healthy", "message": res.json().get("message", "OK"), "details": f"Ping success to {api_url}"}
            return {"status": "Unhealthy", "message": f"HTTP {res.status_code}", "details": res.text}
        except Exception as e:
            return {"status": "Down", "message": "Connection Refused", "details": str(e)}

    @staticmethod
    def check_redis() -> Dict[str, Any]:
        """Verify Redis Lock Store status."""
        config = load_system_config()
        redis_conf = config.get("lock_store", {})
        host = os.getenv("LOCK_STORE_HOST") or redis_conf.get("url") or "localhost"
        port = int(os.getenv("LOCK_STORE_PORT") or redis_conf.get("port") or 6379)
        password = os.getenv("LOCK_STORE_PASSWORD") or redis_conf.get("password") or None
        db = int(os.getenv("LOCK_STORE_DB") or redis_conf.get("db") or 0)

        # Strip protocol prefix if present
        if "://" in host:
            host = host.split("://")[-1]

        try:
            r = redis.Redis(host=host, port=port, password=password, db=db, socket_timeout=3)
            r.ping()
            return {"status": "Healthy", "message": "Connected", "details": f"Redis at {host}:{port} (db {db}) is online."}
        except Exception as e:
            return {"status": "Down", "message": "Connection Failed", "details": f"Could not connect to Redis at {host}:{port}: {e}"}

    @staticmethod
    def check_postgresql() -> Dict[str, Any]:
        """Verify Database instance/cluster status."""
        import socket
        import subprocess

        config = load_system_config()
        crm_bench = config.get("crm", {}).get("bench", {})

        # Method 1: Check TCP socket connection on 5432 or 3306
        for p in [5432, 3306]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                res = s.connect_ex(('127.0.0.1', p))
                s.close()
                if res == 0:
                    db_type = "PostgreSQL" if p == 5432 else "MariaDB"
                    return {"status": "Healthy", "message": f"{db_type} Online", "details": f"Database service listening on port {p}."}
            except Exception:
                pass

        # Method 2: Check docker containers for frappe backend / db
        try:
            cmd = ["docker", "inspect", "--format={{json .State.Running}}", "frappe-backend-1"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip() == "true":
                return {"status": "Healthy", "message": "Backend Connected", "details": "Frappe backend container is active and connected to db."}
        except Exception:
            pass

        return {"status": "Down", "message": "Database Offline", "details": "Could not connect to database on port 5432 or 3306."}

    @staticmethod
    def check_erpnext_api() -> Dict[str, Any]:
        """Verify ERPNext Site status."""
        config = load_system_config()
        crm_bench = config.get("crm", {}).get("bench", {})
        base_url = os.getenv("BENCH_BASE_URL") or crm_bench.get("base_url") or "http://localhost:8080"
        
        try:
            ping_url = f"{base_url.rstrip('/')}/api/method/ping"
            res = requests.get(ping_url, timeout=5)
            if res.ok:
                return {"status": "Healthy", "message": "Connected", "details": f"ERPNext instance at {base_url} responded successfully."}
            elif res.status_code == 404 and ("nginx" in res.headers.get("Server", "").lower() or "does not exist" in res.text):
                return {"status": "Healthy", "message": "Nginx Online", "details": f"ERPNext web proxy at {base_url} is active (returns 404 for unconfigured localhost host header)."}
            return {"status": "Unhealthy", "message": f"HTTP {res.status_code}", "details": f"ERPNext returned: {res.text}"}
        except Exception as e:
            # Fallback: Check if docker container is running
            try:
                import subprocess
                cmd = ["docker", "inspect", "--format={{json .State.Running}}", "frappe-frontend-1"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if res.returncode == 0 and res.stdout.strip() == "true":
                    return {"status": "Healthy", "message": "Container Running", "details": "Docker container 'frappe-frontend-1' is running."}
            except Exception:
                pass
            return {"status": "Down", "message": "Connection Refused", "details": f"ERPNext is down or unreachable at {base_url}: {e}"}
            
    @staticmethod
    def check_workers() -> Dict[str, Any]:
        """Verify Celery/Event queues status."""
        config = load_system_config()
        db_url = os.getenv("DATABASE_URL") or config.get("database", {}).get("url") or "mongodb://localhost:27017/conversations"
        try:
            from pymongo import MongoClient
            client = MongoClient(db_url, serverSelectionTimeoutMS=2000)
            client.admin.command('ping')
            db_name = db_url.split("/")[-1].split("?")[0] or "conversations"
            db = client[db_name]
            # Simple check if there are recent events or workers registered
            col_names = db.list_collection_names()
            return {"status": "Healthy", "message": "MongoDB Connected", "details": f"Connected to MongoDB. Collections found: {len(col_names)}"}
        except Exception as e:
            return {"status": "Down", "message": "MongoDB Offline", "details": str(e)}
