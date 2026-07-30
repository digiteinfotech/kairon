import os

# API configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8082").rstrip("/")
TIMEOUT = int(os.getenv("TIMEOUT", "300"))
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Default headers
DEFAULT_HEADERS = {
    "Accept": "application/json"
}
