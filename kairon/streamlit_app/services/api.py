import requests
import streamlit as st
import logging
from typing import Dict, Any, Optional
from config import API_BASE_URL, TIMEOUT, DEFAULT_HEADERS

logger = logging.getLogger(__name__)

class ApiClient:
    @staticmethod
    def get_token() -> Optional[str]:
        """Retrieve token from session state."""
        return st.session_state.get("access_token")

    @staticmethod
    def set_token(token: str) -> None:
        """Save token in session state."""
        st.session_state["access_token"] = token

    @staticmethod
    def clear_token() -> None:
        """Remove token from session state."""
        if "access_token" in st.session_state:
            del st.session_state["access_token"]

    @staticmethod
    def get_headers() -> Dict[str, str]:
        """Construct request headers with authorization if available."""
        headers = DEFAULT_HEADERS.copy()
        token = ApiClient.get_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _handle_response(response: requests.Response) -> Dict[str, Any]:
        """Parse response and handle standard HTTP status codes."""
        try:
            res_data = response.json()
        except ValueError:
            res_data = {"message": response.text or "Unknown response from server"}

        if response.status_code == 401:
            ApiClient.clear_token()
            st.warning("Session expired. Please log in again.")
            st.rerun()

        # Handle Kairon custom error responses wrapped in 200 OK
        if isinstance(res_data, dict):
            if not res_data.get("success", True):
                error_msg = res_data.get("message") or "API Request Failed"
                if isinstance(error_msg, list):
                    error_msg = "; ".join([f"{e.get('loc', [-1])[-1]}: {e.get('msg', 'error')}" for e in error_msg])
                raise Exception(error_msg)

        if not response.ok:
            error_msg = res_data.get("message") or res_data.get("detail") or "API Request Failed"
            if isinstance(error_msg, list):
                # FastAPI validation errors might be list of dicts
                error_msg = "; ".join([f"{e.get('loc', [-1])[-1]}: {e.get('msg', 'error')}" for e in error_msg])
            raise Exception(error_msg)

        return res_data

    @staticmethod
    def get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform HTTP GET request."""
        url = f"{API_BASE_URL}/{endpoint.lstrip('/')}"
        try:
            response = requests.get(
                url,
                headers=ApiClient.get_headers(),
                params=params,
                timeout=TIMEOUT
            )
            return ApiClient._handle_response(response)
        except requests.RequestException as e:
            logger.error(f"GET {url} failed: {e}")
            raise Exception(f"Connection error to {url}: {e}")

    @staticmethod
    def post(endpoint: str, json_data: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform HTTP POST request."""
        url = f"{API_BASE_URL}/{endpoint.lstrip('/')}"
        headers = ApiClient.get_headers()
        if json_data is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = requests.post(
                url,
                headers=headers,
                json=json_data,
                data=data,
                timeout=TIMEOUT
            )
            return ApiClient._handle_response(response)
        except requests.RequestException as e:
            logger.error(f"POST {url} failed: {e}")
            raise Exception(f"Connection error to {url}: {e}")

    @staticmethod
    def put(endpoint: str, json_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform HTTP PUT request."""
        url = f"{API_BASE_URL}/{endpoint.lstrip('/')}"
        headers = ApiClient.get_headers()
        if json_data is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = requests.put(
                url,
                headers=headers,
                json=json_data,
                timeout=TIMEOUT
            )
            return ApiClient._handle_response(response)
        except requests.RequestException as e:
            logger.error(f"PUT {url} failed: {e}")
            raise Exception(f"Connection error to {url}: {e}")

    @staticmethod
    def delete(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform HTTP DELETE request."""
        url = f"{API_BASE_URL}/{endpoint.lstrip('/')}"
        try:
            response = requests.delete(
                url,
                headers=ApiClient.get_headers(),
                params=params,
                timeout=TIMEOUT
            )
            return ApiClient._handle_response(response)
        except requests.RequestException as e:
            logger.error(f"DELETE {url} failed: {e}")
            raise Exception(f"Connection error to {url}: {e}")
