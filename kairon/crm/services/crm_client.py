import json
from typing import Dict, Any, List, Optional
from loguru import logger
from kairon.exceptions import AppException
from kairon.crm.services.base_frappe_client import BaseFrappeClient


class CRMClient(BaseFrappeClient):
    """
    REST API Client dedicated to Standalone Frappe CRM (frappe/crm).
    Provides type-safe wrappers for CRM Lead, CRM Deal, CRM Organization, and CRM Contact.
    """

    def create_lead(self, lead_name: str, email: str, mobile_no: Optional[str] = None, organization: Optional[str] = None) -> Dict[str, Any]:
        """Creates a CRM Lead in Frappe CRM."""
        url = f"{self.site_url}/api/resource/CRM Lead"
        payload = {
            "lead_name": lead_name,
            "email": email,
        }
        if mobile_no:
            payload["mobile_no"] = mobile_no
        if organization:
            payload["organization"] = organization

        res = self.session.post(url, data=json.dumps(payload), headers=self.get_headers(), timeout=15)
        if res.status_code in (200, 201):
            logger.info(f"[CRMClient] Created CRM Lead: {lead_name}")
            return res.json().get("data", {})
        raise AppException(f"[CRMClient] Failed to create CRM Lead: {res.text}")

    def get_leads(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves list of CRM Leads."""
        url = f"{self.site_url}/api/resource/CRM Lead?limit_page_length={limit}"
        res = self.session.get(url, headers=self.get_headers(), timeout=15)
        if res.status_code == 200:
            return res.json().get("data", [])
        return []

    def create_organization(self, organization_name: str, website: Optional[str] = None) -> Dict[str, Any]:
        """Creates a CRM Organization in Frappe CRM."""
        url = f"{self.site_url}/api/resource/CRM Organization"
        payload = {"organization_name": organization_name}
        if website:
            payload["website"] = website

        res = self.session.post(url, data=json.dumps(payload), headers=self.get_headers(), timeout=15)
        if res.status_code in (200, 201):
            logger.info(f"[CRMClient] Created CRM Organization: {organization_name}")
            return res.json().get("data", {})
        raise AppException(f"[CRMClient] Failed to create CRM Organization: {res.text}")

    def create_deal(self, deal_name: str, organization: str, deal_value: float = 0.0) -> Dict[str, Any]:
        """Creates a CRM Deal in Frappe CRM."""
        url = f"{self.site_url}/api/resource/CRM Deal"
        payload = {
            "deal_name": deal_name,
            "organization": organization,
            "deal_value": deal_value
        }
        res = self.session.post(url, data=json.dumps(payload), headers=self.get_headers(), timeout=15)
        if res.status_code in (200, 201):
            logger.info(f"[CRMClient] Created CRM Deal: {deal_name}")
            return res.json().get("data", {})
        raise AppException(f"[CRMClient] Failed to create CRM Deal: {res.text}")
