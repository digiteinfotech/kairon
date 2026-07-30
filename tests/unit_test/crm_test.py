import os
from unittest.mock import patch, MagicMock
# pyrefly: ignore [missing-import]
import pytest
from mongoengine import connect, disconnect
from fastapi import HTTPException
from fastapi.testclient import TestClient

from kairon.shared.utils import Utility
from kairon.shared.data.data_objects import BotSettings
from kairon.crm.processor import CRMProcessor
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.exceptions import AppException
from kairon.shared.models import User
from kairon.api.app.main import app

mock_user = User(
    email="test@user.com",
    first_name="Test",
    last_name="User",
    active_bot="test_crm_bot",
    account=1,
    status=True,
)


@pytest.fixture(autouse=True, scope="module")
def setup_module():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    connect(
        **Utility.mongoengine_connection(Utility.environment["database"]["url"])
    )
    CRMClientDetails.drop_collection()
    BotSettings.objects(bot="test_crm_bot").delete()
    yield
    disconnect()


def test_is_crm_enabled_default():
    # If bot settings don't exist, is_crm_enabled should raise/return False
    BotSettings.objects(bot="test_crm_bot").delete()
    with pytest.raises(Exception):
        CRMProcessor.is_crm_enabled("test_crm_bot")

    # Create BotSettings with enable_crm = False
    BotSettings(bot="test_crm_bot", user="test_user", enable_crm=False).save()
    assert CRMProcessor.is_crm_enabled("test_crm_bot") is False


def test_is_crm_enabled_true():
    # Update BotSettings with enable_crm = True
    bot_settings = BotSettings.objects(bot="test_crm_bot").get()
    bot_settings.enable_crm = True
    bot_settings.save()
    assert CRMProcessor.is_crm_enabled("test_crm_bot") is True


def test_save_crm_details_validation():
    # Invalid company name characters
    with pytest.raises(AppException, match="Company name can only contain"):
        CRMProcessor.save_crm_details(
            company_name="My Company!!!",
            abbr="MC",
            default_currency="USD",
            country="United States",
            bot="test_crm_bot",
            user="test_user",
        )

    # Empty company name
    with pytest.raises(AppException, match="Company Name cannot be empty"):
        CRMProcessor.save_crm_details(
            company_name="",
            abbr="MC",
            default_currency="USD",
            country="United States",
            bot="test_crm_bot",
            user="test_user",
        )

    # Empty abbr
    with pytest.raises(AppException, match="Abbr cannot be empty"):
        CRMProcessor.save_crm_details(
            company_name="My Company",
            abbr="",
            default_currency="USD",
            country="United States",
            bot="test_crm_bot",
            user="test_user",
        )


def test_save_crm_details_success():
    CRMClientDetails.drop_collection()
    record = CRMProcessor.save_crm_details(
        company_name="My Company",
        abbr="MC",
        default_currency="USD",
        country="United States",
        bot="test_crm_bot",
        user="test_user",
    )
    assert record["company_name"] == "My Company"
    assert record["abbr"] == "MC"
    assert record["onboarding_status"] == CRMOnboardingStatus.PENDING.value

    # Test duplicate check
    with pytest.raises(AppException, match="Company already exists for this bot"):
        CRMProcessor.save_crm_details(
            company_name="My Company",
            abbr="MC",
            default_currency="USD",
            country="United States",
            bot="test_crm_bot",
            user="test_user",
        )


def test_get_crm_details():
    details = CRMProcessor.get_crm_details("test_crm_bot")
    assert details["company_name"] == "My Company"
    assert details["abbr"] == "MC"

    with pytest.raises(
        AppException, match="No CRM configuration found for this bot"
    ):
        CRMProcessor.get_crm_details("non_existent_bot")


def test_update_onboarding_status():
    CRMProcessor.update_onboarding_status(
        "test_crm_bot", "My Company", CRMOnboardingStatus.COMPLETED
    )
    details = CRMProcessor.get_crm_details("test_crm_bot")
    assert details["onboarding_status"] == CRMOnboardingStatus.COMPLETED.value


def test_delete_crm_details():
    res = CRMProcessor.delete_crm_details("My Company")
    assert res["success"] is True

    with pytest.raises(HTTPException):
        CRMProcessor.delete_crm_details("My Company")


@patch("kairon.crm.services.bench_executor.BenchExecutor._database_exists")
@patch("subprocess.run")
@patch("kairon.crm.services.provisioning.ERPNextClient")
@patch("kairon.crm.services.provision_verifier.ProvisionVerifier.verify_health")
@patch("kairon.crm.services.provision_verifier.ProvisionVerifier.verify_provisioning_state")
def test_onboard_company_flow(mock_verify_state, mock_verify_health, mock_erpnext_client, mock_sub_run, mock_db_exists):
    mock_db_exists.return_value = False
    mock_verify_health.return_value = True
    mock_verify_state.return_value = True
    mock_client_instance = MagicMock()
    mock_client_instance.generate_keys_for_user.return_value = {"api_key": "mock_key", "api_secret": "mock_secret"}
    mock_client_instance.ensure_invitation_webhook.return_value = "HOOK-001"
    mock_erpnext_client.return_value = mock_client_instance

    import json
    def mock_run(cmd, *args, **kwargs):
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        res = MagicMock()
        res.returncode = 0
        if "show-config" in cmd_str:
            res.stdout = json.dumps({
                "new_company.localhost": {
                    "db_name": "erpnext_new_company",
                    "db_user": "erpnext_new_company",
                    "db_password": "mock_db_password"
                }
            })
        elif "cat sites/" in cmd_str:
            res.stdout = json.dumps({
                "db_name": "erpnext_new_company",
                "db_user": "erpnext_new_company",
                "db_password": "mock_db_password"
            })
        else:
            res.stdout = ""
        return res
    mock_sub_run.side_effect = mock_run

    # Setup: enable crm and verify it's clean
    CRMClientDetails.drop_collection()
    try:
        bot_settings = BotSettings.objects(bot="test_crm_bot").get()
    except BotSettings.DoesNotExist:
        bot_settings = BotSettings(bot="test_crm_bot", user="test_user")
    bot_settings.enable_crm = True
    bot_settings.save()

    processor = CRMProcessor()
    result = processor.onboard_company(
        company_name="New Company",
        abbr="NC",
        default_currency="INR",
        country="India",
        bot="test_crm_bot",
        current_user=mock_user,
    )

    assert result["status"] == "COMPLETED"

    # Status should be COMPLETED after onboarding
    details = CRMProcessor.get_crm_details("test_crm_bot")
    assert details["onboarding_status"] == CRMOnboardingStatus.COMPLETED.value
    assert details["postgres_port"] == 5432
    assert details["db_name"] == "erpnext_new_company"
    assert details["db_user"] == "erpnext_new_company"
    assert details["db_password"] is not None
    assert details["site_name"] == "new_company.localhost"


def test_onboard_company_disabled_crm():
    try:
        bot_settings = BotSettings.objects(bot="test_crm_bot").get()
    except BotSettings.DoesNotExist:
        bot_settings = BotSettings(bot="test_crm_bot", user="test_user")
    bot_settings.enable_crm = False
    bot_settings.save()

    processor = CRMProcessor()
    with pytest.raises(AppException, match="CRM integration is not enabled"):
        processor.onboard_company(
            company_name="Other Company",
            abbr="OC",
            default_currency="EUR",
            country="France",
            bot="test_crm_bot",
            current_user=mock_user,
        )


@patch("subprocess.run")
def test_create_crm_user(mock_sub_run):
    mock_sub_run.return_value = MagicMock(returncode=0)

    CRMClientDetails.objects(bot="test_crm_bot").delete()
    CRMClientDetails(
        company_name="New Company",
        abbr="NC",
        default_currency="INR",
        country="India",
        bot="test_crm_bot",
        user="test_user",
        site_name="new_company.localhost",
        onboarding_status=CRMOnboardingStatus.COMPLETED.value
    ).save()

    res = CRMProcessor.create_crm_user(
        bot="test_crm_bot",
        user="test_user",
        email="crmuser@company.com",
        role="Sales User",
    )
    assert res["status"] == "success"
    assert res["email"] == "crmuser@company.com"
    assert res["role"] == "Sales User"

    details = CRMProcessor.get_crm_details("test_crm_bot")
    assert details["onboarding_status"] == CRMOnboardingStatus.USER_CREATED.value


# FastAPI endpoints tests
client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_auth_dependency():
    from kairon.shared.auth import Authentication
    app.dependency_overrides[Authentication.get_current_user_and_bot] = lambda: mock_user
    yield
    app.dependency_overrides.clear()


@patch("kairon.crm.services.bench_executor.BenchExecutor._database_exists")
@patch("subprocess.run")
@patch("kairon.crm.services.provisioning.ERPNextClient")
@patch("kairon.crm.services.provision_verifier.ProvisionVerifier.verify_health")
@patch("kairon.crm.services.provision_verifier.ProvisionVerifier.verify_provisioning_state")
def test_api_onboard(mock_verify_state, mock_verify_health, mock_erpnext_client, mock_sub_run, mock_db_exists):
    mock_db_exists.return_value = False
    mock_verify_health.return_value = True
    mock_verify_state.return_value = True
    mock_client_instance = MagicMock()
    mock_client_instance.generate_keys_for_user.return_value = {"api_key": "mock_key", "api_secret": "mock_secret"}
    mock_client_instance.ensure_invitation_webhook.return_value = "HOOK-001"
    mock_erpnext_client.return_value = mock_client_instance

    import json
    def mock_run(cmd, *args, **kwargs):
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        res = MagicMock()
        res.returncode = 0
        if "show-config" in cmd_str:
            res.stdout = json.dumps({
                "api_company.localhost": {
                    "db_name": "erpnext_api_company",
                    "db_user": "erpnext_api_company",
                    "db_password": "mock_db_password"
                }
            })
        elif "cat sites/" in cmd_str:
            res.stdout = json.dumps({
                "db_name": "erpnext_api_company",
                "db_user": "erpnext_api_company",
                "db_password": "mock_db_password"
            })
        else:
            res.stdout = ""
        return res
    mock_sub_run.side_effect = mock_run

    CRMClientDetails.drop_collection()
    try:
        bot_settings = BotSettings.objects(bot="test_crm_bot").get()
    except BotSettings.DoesNotExist:
        bot_settings = BotSettings(bot="test_crm_bot", user="test_user")
    bot_settings.enable_crm = True
    bot_settings.save()

    payload = {
        "company_name": "API Company",
        "abbr": "AC",
        "default_currency": "USD",
        "country": "United States",
    }
    response = client.post("/api/bot/test_crm_bot/crm/onboard", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["data"]["status"] == "COMPLETED"


def test_api_get_status():
    response = client.get("/api/bot/test_crm_bot/crm/status")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["data"]["onboarding_status"] == "COMPLETED"


def test_api_get_details():
    response = client.get("/api/bot/test_crm_bot/crm/details")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["data"]["company_name"] == "API Company"
    assert res_data["data"]["abbr"] == "AC"
    assert res_data["data"]["db_name"] == "erpnext_api_company"
    assert res_data["data"]["db_user"] == "erpnext_api_company"


@patch("subprocess.run")
def test_api_create_user(mock_sub_run):
    mock_sub_run.return_value = MagicMock(returncode=0)

    payload = {"email": "apiuser@company.com", "role": "Sales Manager"}
    response = client.post("/api/bot/test_crm_bot/crm/create-user", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["data"]["status"] == "success"
    assert res_data["data"]["email"] == "apiuser@company.com"


def test_api_delete_project():
    response = client.delete(
        "/api/bot/test_crm_bot/crm/project?company_name=API Company"
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["data"]["success"] is True


def test_generate_database_name():
    from kairon.crm.services.bench_executor import BenchExecutor
    executor = BenchExecutor()
    
    # Standard names
    assert executor.generate_database_name("EFG Company") == "erpnext_efg_company"
    assert executor.generate_database_name("ABC Technologies Pvt. Ltd.") == "erpnext_abc_technologies_pvt_ltd"
    assert executor.generate_database_name("John & Sons") == "erpnext_john_sons"
    
    # Length constraint: 63 characters max
    long_name = "A" * 100
    gen_name = executor.generate_database_name(long_name)
    assert len(gen_name) == 63
    assert gen_name.startswith("erpnext_")
    
    # Special character stripping and identifier validity (a-z0-9_)
    special_name = "My-Company #123 @Corp!"
    gen_special = executor.generate_database_name(special_name)
    assert gen_special == "erpnext_my_company_123_corp"
    import re
    assert re.match(r'^[a-z][a-z0-9_]*$', gen_special) is not None


@patch("kairon.crm.services.bench_executor.BenchExecutor._database_exists")
@patch("subprocess.run")
def test_database_name_collision_handling(mock_sub_run, mock_db_exists):
    from kairon.crm.services.bench_executor import BenchExecutor
    # Simulate first database exists, second does not
    mock_db_exists.side_effect = [True, False]
    
    mock_sub_run.return_value = MagicMock(returncode=0)
    
    executor = BenchExecutor()
    
    # Setup mock show-config response to return our expected db details
    import json
    def mock_run(cmd, *args, **kwargs):
        res = MagicMock()
        res.returncode = 0
        res.stdout = json.dumps({
            "efg_company.localhost": {
                "db_name": "erpnext_efg_company_1",
                "db_user": "erpnext_efg_company_1",
                "db_password": "mock_password"
            }
        })
        return res
    mock_sub_run.side_effect = mock_run

    # Create the CRM Client Details document first
    CRMClientDetails.objects(bot="test_collision_bot").delete()
    CRMClientDetails(
        company_name="EFG Company",
        abbr="EFG",
        default_currency="USD",
        country="United States",
        bot="test_collision_bot",
        user="test_user"
    ).save()
    
    executor.provision_site("EFG Company", "EFG", "USD", "United States", "admin_pwd")
    
    # The saved db_name should have suffix _1
    doc = CRMClientDetails.objects(bot="test_collision_bot").first()
    assert doc.db_name == "erpnext_efg_company_1"


# ─────────────────────────────────────────────────────────────
# ERPNext Native User Invitation Tests
# ─────────────────────────────────────────────────────────────

from kairon.crm.models import CRMInvitation, CRMInvitationStatus
from kairon.crm.services.erpnext_client import ERPNextClient
from kairon.crm.services.provision_verifier import ProvisionVerifier
import base64
import hmac
import hashlib


@pytest.fixture
def setup_invite_bot():
    CRMClientDetails.objects(bot="test_crm_bot").delete()
    CRMInvitation.objects(bot="test_crm_bot").delete()

    doc = CRMClientDetails(
        company_name="Invite Corp",
        abbr="IC",
        default_currency="USD",
        country="United States",
        bot="test_crm_bot",
        user="test_user",
        site_name="invite_corp.localhost",
        onboarding_status=CRMOnboardingStatus.COMPLETED.value,
        erpnext_company="Invite Corp",
        kairon_integration_user="kairon-crm@invite_corp.localhost",
        kairon_api_key=Utility.encrypt_message("mock_api_key"),
        kairon_api_secret=Utility.encrypt_message("mock_api_secret"),
        webhook_secret=Utility.encrypt_message("mock_webhook_secret"),
    )
    doc.save()
    yield doc
    CRMClientDetails.objects(bot="test_crm_bot").delete()
    CRMInvitation.objects(bot="test_crm_bot").delete()


@patch.object(ERPNextClient, "check_smtp_configured", return_value=True)
@patch.object(ERPNextClient, "invite_user")
@patch.object(ERPNextClient, "get_invitation_status")
def test_invite_user_success(mock_get_status, mock_invite, mock_smtp, setup_invite_bot):
    mock_invite.return_value = {
        "invited_emails": ["invited@test.com"],
        "pending_invite_emails": [],
        "accepted_invite_emails": [],
        "disabled_user_emails": [],
    }
    mock_get_status.return_value = {"name": "INV-00001", "email": "invited@test.com", "status": "Pending"}

    res = CRMProcessor.invite_erpnext_user(
        bot="test_crm_bot",
        email="invited@test.com",
        roles=["Sales User"],
    )
    assert res["status"] == "invited"
    assert res["email"] == "invited@test.com"
    assert res["company"] == "Invite Corp"

    inv = CRMInvitation.objects(bot="test_crm_bot", email="invited@test.com").first()
    assert inv is not None
    assert inv.invitation_status == CRMInvitationStatus.PENDING.value
    assert inv.erpnext_invitation_id == "INV-00001"


@patch.object(ERPNextClient, "check_smtp_configured", return_value=True)
@patch.object(ERPNextClient, "invite_user")
def test_invite_user_already_pending(mock_invite, mock_smtp, setup_invite_bot):
    mock_invite.return_value = {
        "invited_emails": [],
        "pending_invite_emails": ["pending@test.com"],
        "accepted_invite_emails": [],
        "disabled_user_emails": [],
    }

    res = CRMProcessor.invite_erpnext_user(
        bot="test_crm_bot",
        email="pending@test.com",
        roles=["Sales User"],
    )
    assert res["status"] == "already_pending"
    assert res["email"] == "pending@test.com"


@patch.object(ERPNextClient, "check_smtp_configured", return_value=True)
@patch.object(ERPNextClient, "invite_user")
def test_invite_user_already_accepted(mock_invite, mock_smtp, setup_invite_bot):
    mock_invite.return_value = {
        "invited_emails": [],
        "pending_invite_emails": [],
        "accepted_invite_emails": ["accepted@test.com"],
        "disabled_user_emails": [],
    }

    res = CRMProcessor.invite_erpnext_user(
        bot="test_crm_bot",
        email="accepted@test.com",
        roles=["Sales User"],
    )
    assert res["status"] == "already_accepted"
    assert res["email"] == "accepted@test.com"


@patch.object(ERPNextClient, "check_smtp_configured", return_value=True)
@patch.object(ERPNextClient, "invite_user")
def test_invite_user_disabled_user(mock_invite, mock_smtp, setup_invite_bot):
    mock_invite.return_value = {
        "invited_emails": [],
        "pending_invite_emails": [],
        "accepted_invite_emails": [],
        "disabled_user_emails": ["disabled@test.com"],
    }

    with pytest.raises(AppException, match="User 'disabled@test.com' is disabled in ERPNext"):
        CRMProcessor.invite_erpnext_user(
            bot="test_crm_bot",
            email="disabled@test.com",
            roles=["Sales User"],
        )


@patch.object(ERPNextClient, "check_smtp_configured", return_value=False)
def test_invite_user_smtp_not_configured(mock_smtp, setup_invite_bot):
    with pytest.raises(AppException, match="ERPNext SMTP not configured"):
        CRMProcessor.invite_erpnext_user(
            bot="test_crm_bot",
            email="test@test.com",
            roles=["Sales User"],
        )


def test_invite_user_not_provisioned(setup_invite_bot):
    doc = setup_invite_bot
    doc.onboarding_status = CRMOnboardingStatus.PENDING.value
    doc.save()

    with pytest.raises(AppException, match="ERPNext site is not yet provisioned"):
        CRMProcessor.invite_erpnext_user(
            bot="test_crm_bot",
            email="test@test.com",
            roles=["Sales User"],
        )


def test_invite_user_no_crm_record():
    with pytest.raises(AppException, match="No CRM configuration found for this bot"):
        CRMProcessor.invite_erpnext_user(
            bot="non_existent_bot",
            email="test@test.com",
            roles=["Sales User"],
        )


@patch.object(ERPNextClient, "check_smtp_configured", return_value=True)
@patch.object(ERPNextClient, "invite_user")
def test_invite_user_invalid_role(mock_invite, mock_smtp, setup_invite_bot):
    mock_invite.side_effect = AppException("Invalid role specified: Role 'NonExistentRole' is invalid")

    with pytest.raises(AppException, match="Invalid role specified"):
        CRMProcessor.invite_erpnext_user(
            bot="test_crm_bot",
            email="test@test.com",
            roles=["NonExistentRole"],
        )


@patch.object(ERPNextClient, "check_user_exists", return_value=True)
@patch.object(ERPNextClient, "assign_company_permission")
def test_handle_invitation_webhook_success(mock_assign, mock_user_exists, setup_invite_bot):
    CRMInvitation(
        bot="test_crm_bot",
        site_name="invite_corp.localhost",
        company="Invite Corp",
        email="accepted@test.com",
        roles=["Sales User"],
        invitation_status=CRMInvitationStatus.PENDING.value,
    ).save()

    raw_body = b'{"status": "Accepted", "email": "accepted@test.com", "app_name": "frappe"}'
    signature = base64.b64encode(
        hmac.new(b"mock_webhook_secret", raw_body, hashlib.sha256).digest()
    ).decode("utf-8")

    res = CRMProcessor.handle_invitation_webhook(
        site_name="invite_corp.localhost",
        raw_body=raw_body,
        signature_header=signature,
        payload={"status": "Accepted", "email": "accepted@test.com", "app_name": "frappe"},
    )
    assert res["action"] == "company_permission_assigned"
    mock_assign.assert_called_once_with("accepted@test.com", "Invite Corp")

    inv = CRMInvitation.objects(bot="test_crm_bot", email="accepted@test.com").first()
    assert inv.invitation_status == CRMInvitationStatus.COMPANY_ASSIGNED.value


def test_handle_invitation_webhook_invalid_signature(setup_invite_bot):
    raw_body = b'{"status": "Accepted", "email": "accepted@test.com"}'
    with pytest.raises(AppException, match="Invalid webhook signature"):
        CRMProcessor.handle_invitation_webhook(
            site_name="invite_corp.localhost",
            raw_body=raw_body,
            signature_header="invalid_signature",
            payload={"status": "Accepted", "email": "accepted@test.com"},
        )


@patch.object(ERPNextClient, "get_invitation_status")
@patch.object(ERPNextClient, "check_user_exists", return_value=True)
@patch.object(ERPNextClient, "assign_company_permission")
def test_reconcile_invitations_success(mock_assign, mock_user_exists, mock_get_status, setup_invite_bot):
    CRMInvitation(
        bot="test_crm_bot",
        site_name="invite_corp.localhost",
        company="Invite Corp",
        email="reconcile@test.com",
        roles=["Sales User"],
        invitation_status=CRMInvitationStatus.PENDING.value,
    ).save()

    mock_get_status.return_value = {"status": "Accepted"}

    summary = CRMProcessor.reconcile_invitations(bot="test_crm_bot")
    assert summary["assigned"] == 1
    mock_assign.assert_called_once_with("reconcile@test.com", "Invite Corp")

    inv = CRMInvitation.objects(bot="test_crm_bot", email="reconcile@test.com").first()
    assert inv.invitation_status == CRMInvitationStatus.COMPANY_ASSIGNED.value


@patch.object(ERPNextClient, "get_invitation_status")
def test_reconcile_invitations_expired(mock_get_status, setup_invite_bot):
    CRMInvitation(
        bot="test_crm_bot",
        site_name="invite_corp.localhost",
        company="Invite Corp",
        email="expired@test.com",
        roles=["Sales User"],
        invitation_status=CRMInvitationStatus.PENDING.value,
    ).save()

    mock_get_status.return_value = {"status": "Expired"}

    summary = CRMProcessor.reconcile_invitations(bot="test_crm_bot")
    assert summary["expired"] == 1

    inv = CRMInvitation.objects(bot="test_crm_bot", email="expired@test.com").first()
    assert inv.invitation_status == CRMInvitationStatus.EXPIRED.value


@patch.object(ERPNextClient, "check_smtp_configured", return_value=True)
@patch.object(ERPNextClient, "invite_user")
@patch.object(ERPNextClient, "get_invitation_status")
def test_api_invite_user_endpoint(mock_get_status, mock_invite, mock_smtp, setup_invite_bot):
    mock_invite.return_value = {
        "invited_emails": ["api_invited@test.com"],
        "pending_invite_emails": [],
        "accepted_invite_emails": [],
        "disabled_user_emails": [],
    }
    mock_get_status.return_value = {"name": "INV-00002", "email": "api_invited@test.com", "status": "Pending"}

    payload = {"email": "api_invited@test.com", "roles": ["Sales Manager"]}
    response = client.post("/api/bot/test_crm_bot/crm/invite-user", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"]["status"] == "invited"
    assert res["data"]["email"] == "api_invited@test.com"


def test_api_invite_user_validation():
    # Empty email
    response = client.post("/api/bot/test_crm_bot/crm/invite-user", json={"email": "", "roles": ["Role"]})
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is False
    assert res["error_code"] == 422

    # Empty roles
    response = client.post("/api/bot/test_crm_bot/crm/invite-user", json={"email": "test@test.com", "roles": []})
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is False
    assert res["error_code"] == 422


def test_verify_invitation_success():
    verifier = ProvisionVerifier("http://localhost:8080", "invite_corp.localhost")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{
            "name": "INV-00001",
            "email": "test@test.com",
            "status": "Pending",
            "email_sent_at": "2026-07-20 10:00:00"
        }]
    }
    with patch.object(verifier.session, "get", return_value=mock_resp):
        assert verifier.verify_invitation("test@test.com", "frappe") is True


def test_verify_post_acceptance_success():
    verifier = ProvisionVerifier("http://localhost:8080", "invite_corp.localhost")

    mock_user_resp = MagicMock()
    mock_user_resp.status_code = 200
    mock_user_resp.json.return_value = {
        "data": {
            "email": "test@test.com",
            "enabled": 1,
            "roles": [{"role": "Sales User"}]
        }
    }

    mock_perm_resp = MagicMock()
    mock_perm_resp.status_code = 200
    mock_perm_resp.json.return_value = {
        "data": [{"name": "PERM-00001"}]
    }

    def mock_get(url, *args, **kwargs):
        if "User Permission" in url:
            return mock_perm_resp
        return mock_user_resp

    with patch.object(verifier.session, "get", side_effect=mock_get):
        assert verifier.verify_post_acceptance("test@test.com", "Invite Corp", ["Sales User"]) is True


def test_ensure_invitation_webhook_idempotency():
    client_obj = ERPNextClient("http://localhost:8080", "invite_corp.localhost")

    # 1. Existing webhook case
    mock_check = MagicMock()
    mock_check.status_code = 200
    mock_check.json.return_value = {"data": [{"name": "HOOK-00001"}]}

    with patch.object(client_obj.session, "get", return_value=mock_check):
        name = client_obj.ensure_invitation_webhook("http://localhost:8000", "invite_corp.localhost", "secret")
        assert name == "HOOK-00001"

    # 2. Absent webhook case -> creates new
    mock_absent = MagicMock()
    mock_absent.status_code = 200
    mock_absent.json.return_value = {"data": []}

    mock_create = MagicMock()
    mock_create.status_code = 200
    mock_create.json.return_value = {"data": {"name": "HOOK-00002"}}

    with patch.object(client_obj.session, "get", return_value=mock_absent), \
         patch.object(client_obj.session, "post", return_value=mock_create):
        name = client_obj.ensure_invitation_webhook("http://localhost:8000", "invite_corp.localhost", "secret")
        assert name == "HOOK-00002"


# ─────────────────────────────────────────────────────────────
# Module Provisioning & Validation Unit Tests
# ─────────────────────────────────────────────────────────────

def test_validate_integration_permissions_success():
    client_obj = ERPNextClient("http://localhost:8080", "test_corp.localhost")

    m_ok = MagicMock()
    m_ok.status_code = 200
    m_ok.json.return_value = {"data": [{"name": "Build"}]}

    with patch.object(client_obj.session, "get", return_value=m_ok), \
         patch.object(client_obj.session, "put", return_value=m_ok):
        assert client_obj.validate_integration_permissions() is True


def test_validate_integration_permissions_missing_workspace_permission():
    client_obj = ERPNextClient("http://localhost:8080", "test_corp.localhost")

    m_ok = MagicMock()
    m_ok.status_code = 200
    m_ok.json.return_value = {"data": [{"name": "Build"}]}

    m_forbidden = MagicMock()
    m_forbidden.status_code = 403
    m_forbidden.text = "Permission Denied"

    def mock_get(url, *args, **kwargs):
        if "Workspace" in url:
            return m_forbidden
        return m_ok

    with patch.object(client_obj.session, "get", side_effect=mock_get):
        assert client_obj.validate_integration_permissions() is False


def test_configure_modules_idempotent():
    client_obj = ERPNextClient("http://localhost:8080", "test_corp.localhost")
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch.object(client_obj.session, "put", return_value=mock_resp):
        res1 = client_obj.configure_workspace_visibility(["CRM", "POS"])
        res2 = client_obj.configure_workspace_visibility(["CRM", "POS"])
        assert res1 == res2
        assert res1["CRM"] is False  # visible
        assert res1["HR"] is True   # hidden


def test_reconcile_idempotent():
    client_obj = ERPNextClient("http://localhost:8080", "test_corp.localhost")

    m_mod = MagicMock()
    m_mod.status_code = 200
    m_mod.json.return_value = {
        "data": [
            {"name": "CRM", "app_name": "erpnext"},
            {"name": "HR", "app_name": "erpnext"}
        ]
    }

    m_ws = MagicMock()
    m_ws.status_code = 200
    m_ws.json.return_value = {
        "data": [
            {"name": "CRM", "is_hidden": 0, "public": 1},
            {"name": "HR", "is_hidden": 1, "public": 1}
        ]
    }

    m_prof = MagicMock()
    m_prof.status_code = 200
    m_prof.json.return_value = {
        "data": {
            "module_profile_name": "Kairon Profile",
            "block_modules": [{"module": "HR"}]
        }
    }

    def mock_get(url, *args, **kwargs):
        if "Module Def" in url:
            return m_mod
        if "Workspace" in url:
            return m_ws
        if "Module Profile" in url:
            return m_prof
        return m_ws

    with patch.object(client_obj.session, "get", side_effect=mock_get), \
         patch.object(client_obj.session, "put", return_value=m_ws):
        report1 = client_obj.verify_module_configuration(["CRM"], profile_name="Kairon Profile")
        report2 = client_obj.verify_module_configuration(["CRM"], profile_name="Kairon Profile")
        assert report1.is_fully_consistent is True
        assert report2.is_fully_consistent is True


def test_assign_module_profile_idempotent():
    client_obj = ERPNextClient("http://localhost:8080", "test_corp.localhost")
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch.object(client_obj.session, "put", return_value=mock_resp):
        assert client_obj.assign_module_profile_to_user("owner@test.com", "Kairon Profile") is True
        assert client_obj.assign_module_profile_to_user("owner@test.com", "Kairon Profile") is True


def test_schema_selected_modules_validation():
    from kairon.crm.schemas import CRMOnboardRequest, CRMConfigureModulesRequest, validate_module_selection

    # Deduplication and validity
    cleaned = validate_module_selection(["CRM", "CRM", "POS"])
    assert cleaned == ["CRM", "POS"]

    # Reject empty list
    with pytest.raises(ValueError, match="cannot be an empty list"):
        validate_module_selection([])

    # Reject infrastructure module
    with pytest.raises(ValueError, match="infrastructure module"):
        validate_module_selection(["Accounts"])

    # Reject unknown module
    with pytest.raises(ValueError, match="Invalid business module"):
        validate_module_selection(["NonExistentModule"])

    # CRMOnboardRequest validation
    req = CRMOnboardRequest(
        company_name="Test Co",
        abbr="TC",
        default_currency="USD",
        country="United States",
        selected_modules=["CRM", "POS"]
    )
    assert req.selected_modules == ["CRM", "POS"]

    # CRMConfigureModulesRequest validation
    conf_req = CRMConfigureModulesRequest(selected_modules=["HR"])
    assert conf_req.selected_modules == ["HR"]


def test_api_module_endpoints():
    test_bot = "test_crm_bot"
    BotSettings(bot=test_bot, user="test_user", enable_crm=True).save()

    # Drop existing
    CRMClientDetails.objects(bot=test_bot).delete()

    # 1. Available modules endpoint
    response = client.post("/api/bot/test_crm_bot/crm/invite-user", json={"email": "dummy@test.com", "roles": ["Sales User"]})
    # Now call GET available-modules
    response = client.get("/api/bot/test_crm_bot/crm/available-modules")
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert "modules" in res["data"]
    module_keys = [m["key"] for m in res["data"]["modules"]]
    assert "CRM" in module_keys
    assert "POS" in module_keys

    # Save CRM details
    CRMProcessor.save_crm_details(
        company_name="Module Test Corp",
        abbr="MTC",
        default_currency="USD",
        country="United States",
        bot=test_bot,
        user="test_user",
        selected_modules=["CRM", "POS"]
    )

    # 2. Selected modules endpoint
    response = client.get("/api/bot/test_crm_bot/crm/selected-modules")
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"]["selected_modules"] == ["CRM", "POS"]

    # 3. Configure modules endpoint
    response = client.post("/api/bot/test_crm_bot/crm/configure-modules", json={"selected_modules": ["CRM", "HR"]})
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"]["selected_modules"] == ["CRM", "HR"]

    # Verify updated selected_modules
    details = CRMProcessor.get_crm_details(test_bot)
    assert details["selected_modules"] == ["CRM", "HR"]


