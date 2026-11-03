from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def _mock_error(*args, **kwargs):
    raise JIRAError(status_code=404, url="https://test1-digite.atlassian.net")


def test_add_jira_action_invalid_config(monkeypatch):
    url = "https://test_add_jira_action_invalid_config.net"
    action = {
        "name": "jira_action_new",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }
    monkeypatch.setattr(ActionUtility, "get_jira_client", _mock_error)
    response = client.post(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == "JiraError HTTP 404 url: https://test1-digite.atlassian.net\n\t"
    )


def test_list_jira_action_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/jira",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


@responses.activate
def test_add_jira_action():
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }
    responses.add(
        "GET",
        f"{url}/rest/api/2/serverInfo",
        json={
            "baseUrl": "https://udit-pandey.atlassian.net",
            "version": "1001.0.0-SNAPSHOT",
            "versionNumbers": [1001, 0, 0],
            "deploymentType": "Cloud",
            "buildNumber": 100191,
            "buildDate": "2022-02-11T05:35:40.000+0530",
            "serverTime": "2022-02-15T10:54:09.906+0530",
            "scmInfo": "831671b3b59f40b5108ef3f9491df89a1317ecaa",
            "serverTitle": "Jira",
            "defaultLocale": {"locale": "en_US"},
        },
    )
    responses.add(
        "GET",
        f"{url}/rest/api/2/project/HEL",
        json={
            "expand": "description,lead,issueTypes,url,projectKeys,permissions,insight",
            "self": "https://udit-pandey.atlassian.net/rest/api/2/project/10000",
            "id": "10000",
            "key": "HEL",
            "description": "",
            "lead": {
                "self": "https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f",
                "accountId": "6205e1585d18ad00729aa75f",
                "avatarUrls": {
                    "48x48": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                    "24x24": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                    "16x16": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                    "32x32": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                },
                "displayName": "Udit Pandey",
                "active": True,
            },
            "components": [],
            "issueTypes": [
                {
                    "self": "https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001",
                    "id": "10001",
                    "description": "A small, distinct piece of work.",
                    "iconUrl": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium",
                    "name": "Task",
                    "subtask": False,
                    "avatarId": 10318,
                    "hierarchyLevel": 0,
                },
                {
                    "self": "https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002",
                    "id": "10002",
                    "description": "A collection of related bugs, stories, and tasks.",
                    "iconUrl": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium",
                    "name": "Epic",
                    "subtask": False,
                    "avatarId": 10307,
                    "hierarchyLevel": 1,
                },
                {
                    "self": "https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003",
                    "id": "10003",
                    "description": "Subtasks track small pieces of work that are part of a larger task.",
                    "iconUrl": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium",
                    "name": "Bug",
                    "subtask": True,
                    "avatarId": 10316,
                    "hierarchyLevel": -1,
                },
            ],
            "assigneeType": "UNASSIGNED",
            "versions": [],
            "name": "helicopter",
            "roles": {
                "atlassian-addons-project-access": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007",
                "Administrator": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004",
                "Viewer": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006",
                "Member": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005",
            },
            "avatarUrls": {
                "48x48": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408",
                "24x24": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small",
                "16x16": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall",
                "32x32": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium",
            },
            "projectTypeKey": "software",
            "simplified": True,
            "style": "next-gen",
            "isPrivate": False,
            "properties": {},
            "entityId": "8a851ebf-72eb-461d-be68-4c2c28805440",
            "uuid": "8a851ebf-72eb-461d-be68-4c2c28805440",
        },
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


@patch("kairon.shared.actions.utils.ActionUtility.get_jira_client", autospec=True)
@patch("kairon.shared.actions.utils.ActionUtility.validate_jira_action", autospec=True)
def test_add_jira_action_different_parameter_type(mock_jira_client, mock_validate):
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action_slot",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL", "parameter_type": "slot"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"

    action = {
        "name": "jira_action_key_vault",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


@patch("kairon.shared.actions.data_objects.JiraAction.validate", autospec=True)
def test_add_jira_action_invalid_parameter_type(moack_jira):
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action_slot",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL", "parameter_type": "user_message"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_list_jira_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/jira",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    [action.pop("_id") for action in actual["data"]]
    assert actual["data"] == [
        {
            "name": "jira_action",
            "url": "https://test-digite.atlassian.net",
            "user_name": "test@digite.com",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "ASDFGHJKL",
                "parameter_type": "value",
            },
            "project_key": "HEL",
            "issue_type": "Bug",
            "summary": "new user",
            "response": "We have logged a ticket",
        },
        {
            "name": "jira_action_slot",
            "url": "https://test-digite.atlassian.net",
            "user_name": "test@digite.com",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "ASDFGHJKL",
                "parameter_type": "slot",
            },
            "project_key": "HEL",
            "issue_type": "Bug",
            "summary": "new user",
            "response": "We have logged a ticket",
        },
        {
            "name": "jira_action_key_vault",
            "url": "https://test-digite.atlassian.net",
            "user_name": "test@digite.com",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "AWS_KEY",
                "parameter_type": "key_vault",
            },
            "project_key": "HEL",
            "issue_type": "Bug",
            "summary": "new user",
            "response": "We have logged a ticket",
        },
    ]


@responses.activate
def test_edit_jira_action():
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL"},
        "project_key": "HEL",
        "issue_type": "Subtask",
        "parent_key": "HEL-4",
        "summary": "new user",
        "response": "We have logged a ticket",
    }
    responses.add(
        "GET",
        f"{url}/rest/api/2/serverInfo",
        json={
            "baseUrl": "https://udit-pandey.atlassian.net",
            "version": "1001.0.0-SNAPSHOT",
            "versionNumbers": [1001, 0, 0],
            "deploymentType": "Cloud",
            "buildNumber": 100191,
            "buildDate": "2022-02-11T05:35:40.000+0530",
            "serverTime": "2022-02-15T10:54:09.906+0530",
            "scmInfo": "831671b3b59f40b5108ef3f9491df89a1317ecaa",
            "serverTitle": "Jira",
            "defaultLocale": {"locale": "en_US"},
        },
    )
    responses.add(
        "GET",
        f"{url}/rest/api/2/project/HEL",
        json={
            "expand": "description,lead,issueTypes,url,projectKeys,permissions,insight",
            "self": "https://udit-pandey.atlassian.net/rest/api/2/project/10000",
            "id": "10000",
            "key": "HEL",
            "description": "",
            "lead": {
                "self": "https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f",
                "accountId": "6205e1585d18ad00729aa75f",
                "avatarUrls": {
                    "48x48": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                    "24x24": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                    "16x16": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                    "32x32": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                },
                "displayName": "Udit Pandey",
                "active": True,
            },
            "components": [],
            "issueTypes": [
                {
                    "self": "https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001",
                    "id": "10001",
                    "description": "A small, distinct piece of work.",
                    "iconUrl": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium",
                    "name": "Task",
                    "subtask": False,
                    "avatarId": 10318,
                    "hierarchyLevel": 0,
                },
                {
                    "self": "https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002",
                    "id": "10002",
                    "description": "A collection of related bugs, stories, and tasks.",
                    "iconUrl": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium",
                    "name": "Epic",
                    "subtask": False,
                    "avatarId": 10307,
                    "hierarchyLevel": 1,
                },
                {
                    "self": "https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003",
                    "id": "10003",
                    "description": "Subtasks track small pieces of work that are part of a larger task.",
                    "iconUrl": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium",
                    "name": "Subtask",
                    "subtask": True,
                    "avatarId": 10316,
                    "hierarchyLevel": -1,
                },
            ],
            "assigneeType": "UNASSIGNED",
            "versions": [],
            "name": "helicopter",
            "roles": {
                "atlassian-addons-project-access": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007",
                "Administrator": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004",
                "Viewer": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006",
                "Member": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005",
            },
            "avatarUrls": {
                "48x48": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408",
                "24x24": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small",
                "16x16": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall",
                "32x32": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium",
            },
            "projectTypeKey": "software",
            "simplified": True,
            "style": "next-gen",
            "isPrivate": False,
            "properties": {},
            "entityId": "8a851ebf-72eb-461d-be68-4c2c28805440",
            "uuid": "8a851ebf-72eb-461d-be68-4c2c28805440",
        },
    )
    response = client.put(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


@patch("kairon.shared.actions.utils.ActionUtility.get_jira_client", autospec=True)
@patch("kairon.shared.actions.utils.ActionUtility.validate_jira_action", autospec=True)
def test_edit_jira_action_different_parameter_type(mock_jira_client, mock_validate):
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action_slot",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"

    action = {
        "name": "jira_action_key_vault",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL", "parameter_type": "slot"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


@patch("kairon.shared.actions.utils.ActionUtility", autospec=True)
def test_edit_jira_action_invalid_parameter_type(mock_jira):
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action_slot",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL", "parameter_type": "chat_log"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_edit_jira_action_invalid_config(monkeypatch):
    url = "https://test_edit_jira_action_invalid_config.net"
    action = {
        "name": "jira_action",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    monkeypatch.setattr(ActionUtility, "get_jira_client", _mock_error)
    response = client.put(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == "JiraError HTTP 404 url: https://test1-digite.atlassian.net\n\t"
    )


def test_edit_jira_action_not_found():
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action_new",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "jira_action_new" not found'


def test_add_zendesk_action_invalid_config(monkeypatch):
    def __mock_zendesk_error(*args, **kwargs):
        from zenpy.lib.exception import APIException

        raise APIException(
            {"error": {"title": "No help desk at digite751.zendesk.com"}}
        )

    action = {
        "name": "zendesk_action_1",
        "subdomain": "digite751",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy") as mock:
        mock.side_effect = __mock_zendesk_error
        response = client.post(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert (
                actual["message"]
                == "{'error': {'title': 'No help desk at digite751.zendesk.com'}}"
        )


def test_list_zendesk_action_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/zendesk",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_add_zendesk_action():
    action = {
        "name": "zendesk_action",
        "subdomain": "digite751",
        "api_token": {"value": "123456789"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action added"


@patch("kairon.shared.actions.data_objects.ZendeskAction.validate", autospec=True)
def test_add_zendesk_action_different_parameter_type(mock_zedesk):
    action = {
        "name": "zendesk_action_slot",
        "subdomain": "digite751",
        "api_token": {"value": "123456789", "parameter_type": "slot"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action added"

    action = {
        "name": "zendesk_action_key_vault",
        "subdomain": "digite751",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action added"


def test_add_zendesk_action_invalid_parameter_type():
    action = {
        "name": "zendesk_action_intent",
        "subdomain": "digite751",
        "api_token": {"value": "123456789", "parameter_type": "intent"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422


def test_list_zendesk_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/zendesk",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    [action.pop("_id") for action in actual["data"]]
    assert actual["data"] == [
        {
            "name": "zendesk_action",
            "subdomain": "digite751",
            "user_name": "udit.pandey@digite.com",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "123456789",
                "parameter_type": "value",
            },
            "subject": "new ticket",
            "response": "ticket filed",
        },
        {
            "name": "zendesk_action_slot",
            "subdomain": "digite751",
            "user_name": "udit.pandey@digite.com",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "encrypt": False,
                "value": "123456789",
                "parameter_type": "slot",
            },
            "subject": "new ticket",
            "response": "ticket filed",
        },
        {
            "name": "zendesk_action_key_vault",
            "subdomain": "digite751",
            "user_name": "udit.pandey@digite.com",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "encrypt": False,
                "value": "AWS_KEY",
                "parameter_type": "key_vault",
            },
            "subject": "new ticket",
            "response": "ticket filed",
        },
    ]


def test_edit_zendesk_action():
    action = {
        "name": "zendesk_action",
        "subdomain": "digite756",
        "api_token": {"value": "123456789999"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed here",
    }
    with patch("zenpy.Zenpy"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action updated"


@patch("kairon.shared.actions.data_objects.ZendeskAction.validate", autospec=True)
def test_edit_zendesk_action_different_parameter_type(mock_zendesk):
    action = {
        "name": "zendesk_action_slot",
        "subdomain": "digite751",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action updated"

    action = {
        "name": "zendesk_action_key_vault",
        "subdomain": "digite751",
        "api_token": {"value": "123456789", "parameter_type": "slot"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action updated"


def test_edit_zendesk_action_invalid_parameter_type():
    action = {
        "name": "zendesk_action_intent",
        "subdomain": "digite751",
        "api_token": {"value": "123456789", "parameter_type": "intent"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422


def test_edit_zendesk_action_invalid_config(monkeypatch):
    action = {
        "name": "zendesk_action",
        "subdomain": "digite751",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }

    def __mock_zendesk_error(*args, **kwargs):
        from zenpy.lib.exception import APIException

        raise APIException(
            {"error": {"title": "No help desk at digite751.zendesk.com"}}
        )

    with patch("zenpy.Zenpy") as mock:
        mock.side_effect = __mock_zendesk_error
        response = client.put(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert (
                actual["message"]
                == "{'error': {'title': 'No help desk at digite751.zendesk.com'}}"
        )


def test_edit_zendesk_action_not_found():
    action = {
        "name": "zendesk_action_1",
        "subdomain": "digite751",
        "api_token": {"value": "123456789"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/zendesk",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "zendesk_action_1" not found'


def test_add_pipedrive_leads_action_invalid_config(monkeypatch):
    def __mock_exception(*args, **kwargs):
        raise UnauthorizedError("Invalid authentication", {"error_code": 401})

    action = {
        "name": "pipedrive_leads",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }
    with patch("pipedrive.client.Client._request", __mock_exception) as mock:
        response = client.post(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert actual["message"] == "Invalid authentication"


def test_add_pipedrive_leads_name_not_filled(monkeypatch):
    action = {
        "name": "pipedrive_leads",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {"org_name": "organization", "email": "email", "phone": "phone"},
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/pipedrive",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body", "metadata"], "msg": "name is required", "type": "value_error"}
    ]


def test_list_pipedrive_actions_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/pipedrive",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_add_pipedrive_action():
    action = {
        "name": "pipedrive_leads",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }
    with patch("pipedrive.client.Client"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action added"


def test_add_pipedrive_action_different_parameter_types():
    action = {
        "name": "pipedrive_leads_slot",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678", "parameter_type": "slot"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }
    with patch("pipedrive.client.Client"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action added"

    action = {
        "name": "pipedrive_leads_slot_key_vault",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }
    with patch("pipedrive.client.Client"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action added"


def test_add_pipedrive_action_invalid_parameter_types():
    action = {
        "name": "pipedrive_leads_sender_id",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678", "parameter_type": "intent"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }
    with patch("pipedrive.client.Client"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422


def test_list_pipedrive_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/pipedrive",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    [action.pop("_id") for action in actual["data"]]
    assert actual["data"] == [
        {
            "name": "pipedrive_leads",
            "domain": "https://digite751.pipedrive.com/",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "12345678",
                "parameter_type": "value",
            },
            "title": "new lead",
            "metadata": {
                "name": "name",
                "org_name": "organization",
                "email": "email",
                "phone": "phone",
            },
            "response": "I have failed to create lead for you",
        },
        {
            "name": "pipedrive_leads_slot",
            "domain": "https://digite751.pipedrive.com/",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "12345678",
                "parameter_type": "slot",
            },
            "title": "new lead",
            "metadata": {
                "name": "name",
                "org_name": "organization",
                "email": "email",
                "phone": "phone",
            },
            "response": "I have failed to create lead for you",
        },
        {
            "name": "pipedrive_leads_slot_key_vault",
            "domain": "https://digite751.pipedrive.com/",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "AWS_KEY",
                "parameter_type": "key_vault",
            },
            "title": "new lead",
            "metadata": {
                "name": "name",
                "org_name": "organization",
                "email": "email",
                "phone": "phone",
            },
            "response": "I have failed to create lead for you",
        },
    ]


def test_edit_pipedrive_action():
    action = {
        "name": "pipedrive_leads",
        "domain": "https://digite7.pipedrive.com/",
        "api_token": {"value": "1asdfghjklqwertyuio"},
        "title": "new lead generated",
        "response": "Failed to create lead for you",
        "metadata": {"name": "name"},
    }

    with patch("pipedrive.client.Client"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action updated"


@patch(
    "kairon.shared.actions.data_objects.PipedriveLeadsAction.validate", autospec=True
)
def test_edit_pipedrive_action_different_parameter_type(mock_pipedrive):
    action = {
        "name": "pipedrive_leads_slot",
        "domain": "https://digite7.pipedrive.com/",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "title": "new lead generated",
        "response": "Failed to create lead for you",
        "metadata": {"name": "name"},
    }

    with patch("pipedrive.client.Client"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action updated"

    action = {
        "name": "pipedrive_leads_slot_key_vault",
        "domain": "https://digite7.pipedrive.com/",
        "api_token": {"value": "1asdfghjklqwertyuio", "parameter_type": "slot"},
        "title": "new lead generated",
        "response": "Failed to create lead for you",
        "metadata": {"name": "name"},
    }

    with patch("pipedrive.client.Client"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action updated"


def test_edit_pipedrive_action_invalid_parameter_type():
    action = {
        "name": "pipedrive_leads_slot_key_vault",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678", "parameter_type": "intent"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/pipedrive",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_edit_pipedrive_action_invalid_config(monkeypatch):
    action = {
        "name": "pipedrive_leads",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }

    def __mock_exception(*args, **kwargs):
        raise UnauthorizedError("Invalid authentication", {"error_code": 401})

    with patch("pipedrive.client.Client._request", __mock_exception):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert actual["message"] == "Invalid authentication"


def test_edit_pipedrive_action_not_found():
    action = {
        "name": "pipedrive_action",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/pipedrive",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "pipedrive_action" not found'


def test_list_razorpay_actions_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/razorpay",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_add_razorpay_action():
    action_name = "razorpay_action"
    action = {
        "name": action_name,
        "api_key": {"value": "API_KEY", "parameter_type": "key_vault"},
        "api_secret": {"value": "API_SECRET", "parameter_type": "key_vault"},
        "amount": {"value": "amount", "parameter_type": "slot"},
        "currency": {"value": "INR", "parameter_type": "value"},
        "username": {"parameter_type": "sender_id"},
        "email": {"parameter_type": "sender_id"},
        "contact": {"value": "contact", "parameter_type": "slot"},
        "notes": [
            {"key": "order_id", "parameter_type": "slot", "value": "order_id"},
            {"key": "phone_number", "parameter_type": "value", "value": "9876543210"}
        ]
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/razorpay",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"


def test_add_razorpay_action_with_required_values_only():
    action_name = "razorpay_action_required_values_only"
    action = {
        "name": action_name,
        "api_key": {"value": "API_KEY", "parameter_type": "value"},
        "api_secret": {"value": "API_SECRET", "parameter_type": "value"},
        "amount": {"value": "amount", "parameter_type": "value"},
        "currency": {"value": "INR", "parameter_type": "slot"},
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/razorpay",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"


def test_add_razorpay_action_without_required_values():
    action_name = "razorpay_action_required_values_only"
    action = {
        "name": action_name,
        "amount": {"value": "amount", "parameter_type": "value"},
        "currency": {"value": "INR", "parameter_type": "slot"},
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/razorpay",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "api_key"],
            "msg": "field required",
            "type": "value_error.missing",
        },
        {
            "loc": ["body", "api_secret"],
            "msg": "field required",
            "type": "value_error.missing",
        },
    ]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_list_razorpay_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/razorpay",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    [v.pop("timestamp") for v in actual["data"]]
    [action.pop("_id") for action in actual["data"]]
    assert actual["data"] == [
        {
            "name": "razorpay_action",
            "api_key": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_key",
                "encrypt": False,
                "value": "API_KEY",
                "parameter_type": "key_vault",
            },
            "api_secret": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_secret",
                "encrypt": False,
                "value": "API_SECRET",
                "parameter_type": "key_vault",
            },
            "amount": {
                "_cls": "CustomActionRequestParameters",
                "key": "amount",
                "encrypt": False,
                "value": "amount",
                "parameter_type": "slot",
            },
            "currency": {
                "_cls": "CustomActionRequestParameters",
                "key": "currency",
                "encrypt": False,
                "value": "INR",
                "parameter_type": "value",
            },
            "username": {
                "_cls": "CustomActionRequestParameters",
                "key": "username",
                "encrypt": False,
                "parameter_type": "sender_id",
            },
            "email": {
                "_cls": "CustomActionRequestParameters",
                "key": "email",
                "encrypt": False,
                "parameter_type": "sender_id",
            },
            "contact": {
                "_cls": "CustomActionRequestParameters",
                "key": "contact",
                "encrypt": False,
                "value": "contact",
                "parameter_type": "slot",
            },
            "notes": [
                {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'order_id',
                    'encrypt': False,
                    'value': 'order_id',
                    'parameter_type': 'slot'
                },
                {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'phone_number',
                    'encrypt': False,
                    'value': '9876543210',
                    'parameter_type': 'value'
                }
            ]
        },
        {
            "name": "razorpay_action_required_values_only",
            "api_key": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_key",
                "encrypt": False,
                "value": "API_KEY",
                "parameter_type": "value",
            },
            "api_secret": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_secret",
                "encrypt": False,
                "value": "API_SECRET",
                "parameter_type": "value",
            },
            "amount": {
                "_cls": "CustomActionRequestParameters",
                "key": "amount",
                "encrypt": False,
                "value": "amount",
                "parameter_type": "value",
            },
            "currency": {
                "_cls": "CustomActionRequestParameters",
                "key": "currency",
                "encrypt": False,
                "value": "INR",
                "parameter_type": "slot",
            },
            "notes": []
        },
    ]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_edit_razorpay_action():
    action_name = "razorpay_action"
    action = {
        "name": action_name,
        "api_key": {"value": "API_KEY", "parameter_type": "key_vault"},
        "api_secret": {"value": "API_SECRET", "parameter_type": "key_vault"},
        "amount": {"value": "amount", "parameter_type": "value"},
        "currency": {"value": "INR", "parameter_type": "slot"},
        "email": {"parameter_type": "sender_id"},
        "contact": {"value": "contact", "parameter_type": "value"},
        "notes": [
            {"key": "phone_number", "parameter_type": "value", "value": "9876543210"}
        ]
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/razorpay",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated!"


def test_list_razorpay_actions_after_update():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/razorpay",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    [v.pop("timestamp") for v in actual["data"]]
    [action.pop("_id") for action in actual["data"]]
    print(actual["data"])
    assert actual["data"] == [
        {
            "name": "razorpay_action",
            "api_key": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_key",
                "encrypt": False,
                "value": "API_KEY",
                "parameter_type": "key_vault",
            },
            "api_secret": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_secret",
                "encrypt": False,
                "value": "API_SECRET",
                "parameter_type": "key_vault",
            },
            "amount": {
                "_cls": "CustomActionRequestParameters",
                "key": "amount",
                "encrypt": False,
                "value": "amount",
                "parameter_type": "value",
            },
            "currency": {
                "_cls": "CustomActionRequestParameters",
                "key": "currency",
                "encrypt": False,
                "value": "INR",
                "parameter_type": "slot",
            },
            "email": {
                "_cls": "CustomActionRequestParameters",
                "key": "email",
                "encrypt": False,
                "parameter_type": "sender_id",
            },
            "contact": {
                "_cls": "CustomActionRequestParameters",
                "key": "contact",
                "encrypt": False,
                "value": "contact",
                "parameter_type": "value",
            },
            "notes": [
                {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'phone_number',
                    'encrypt': False,
                    'value': '9876543210',
                    'parameter_type': 'value'
                }
            ]
        },
        {
            "name": "razorpay_action_required_values_only",
            "api_key": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_key",
                "encrypt": False,
                "value": "API_KEY",
                "parameter_type": "value",
            },
            "api_secret": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_secret",
                "encrypt": False,
                "value": "API_SECRET",
                "parameter_type": "value",
            },
            "amount": {
                "_cls": "CustomActionRequestParameters",
                "key": "amount",
                "encrypt": False,
                "value": "amount",
                "parameter_type": "value",
            },
            "currency": {
                "_cls": "CustomActionRequestParameters",
                "key": "currency",
                "encrypt": False,
                "value": "INR",
                "parameter_type": "slot",
            },
            "notes": []
        },
    ]
    assert actual["success"]
    assert actual["error_code"] == 0

def test_edit_razorpay_action_required_config_missing():
    action_name = "razorpay_action"
    action = {
        "name": action_name,
        "email": {"parameter_type": "sender_id"},
        "contact": {"value": "contact", "parameter_type": "value"},
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/razorpay",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "api_key"],
            "msg": "field required",
            "type": "value_error.missing",
        },
        {
            "loc": ["body", "api_secret"],
            "msg": "field required",
            "type": "value_error.missing",
        },
        {
            "loc": ["body", "amount"],
            "msg": "field required",
            "type": "value_error.missing",
        },
        {
            "loc": ["body", "currency"],
            "msg": "field required",
            "type": "value_error.missing",
        },
    ]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_edit_razorpay_action_not_found():
    action_name = "new_razorpay_action"
    action = {
        "name": action_name,
        "api_key": {"value": "API_KEY", "parameter_type": "key_vault"},
        "api_secret": {"value": "API_SECRET", "parameter_type": "key_vault"},
        "amount": {"value": "amount", "parameter_type": "value"},
        "currency": {"value": "INR", "parameter_type": "slot"},
        "email": {"parameter_type": "sender_id"},
        "contact": {"value": "contact", "parameter_type": "value"},
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/razorpay",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "new_razorpay_action" not found'


def test_delete_razorpay_action():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/razorpay_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_get_fields_for_integrated_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/fields/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["pipedrive"] == {
        "required_fields": ["name"],
        "optional_fields": ["org_name", "email", "phone"],
    }
