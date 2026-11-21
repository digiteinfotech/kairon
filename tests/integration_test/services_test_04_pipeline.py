from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training




@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_create_pipeline_event_cron(mock_event_server):

    data = {
        "bot": pytest.bot,
        "name": "callback_test",
        "pyscript_code": "print('Hello, World!')",
    }
    result = CallbackConfig.create_entry(**data)
    payload = {
        "pipeline_name": "daily_analytics_pipeline",
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "32 11 * * *",
            "timezone": "Asia/Kolkata"
        },
        "data_deletion_policy": [],
        "triggers": []
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Event scheduled!"
    assert "event_id" in actual["data"]
    pytest.analytics_event_id = actual["data"]["event_id"]



@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_create_pipeline_event_epoch(mock_event_server):
    future_epoch = int(time.time()) + 3600
    timezone = "Asia/Kolkata"

    payload = {
        "pipeline_name": "one_time_pipeline",
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z",
        "scheduler_config": {
            "expression_type": "epoch",
            "schedule": future_epoch,
            "timezone": timezone
        },
        "data_deletion_policy": [],
        "triggers": []
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Event scheduled!"
    assert "event_id" in actual["data"]

    event_id = actual["data"]["event_id"]
    saved_event = AnalyticsPipelineConfig.objects(id=event_id).get()
    saved_schedule = saved_event.scheduler_config["schedule"]

    expected_dt = datetime.fromtimestamp(
        future_epoch,
        ZoneInfo(timezone)
    ).isoformat()

    assert saved_schedule == expected_dt

    mock_event_server.assert_called_once()
    _, kwargs = mock_event_server.call_args
    assert kwargs["run_at"] == expected_dt
    assert kwargs["timezone"] == timezone


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_create_pipeline_event_without_scheduler(mock_event_server):
    payload = {
        "pipeline_name": "instant_pipeline",
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z",
        "data_deletion_policy": [],
        "triggers": []
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Event scheduled!"
    assert "event_id" in actual["data"]

def test_create_pipeline_event_missing_pipeline_name():
    payload = {
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z"
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    assert data["message"][0]["loc"] == ["body", "pipeline_name"]
    assert data["message"][0]["msg"] == "field required"


def test_create_pipeline_event_missing_callback_name():
    payload = {
        "pipeline_name": "daily_pipeline",
        "timestamp": "2025-11-25T14:30:00Z"
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    assert data["message"][0]["loc"] == ["body", "callback_name"]
    assert data["message"][0]["msg"] == "field required"


def test_create_pipeline_event_invalid_expression_type():
    payload = {
        "pipeline_name": "daily_pipeline",
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z",
        "scheduler_config": {
            "expression_type": "unknown",
            "schedule": "10 10 * * *",
            "timezone": "Asia/Kolkata"
        }
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = response.json()
    assert response["error_code"] == 422
    errors = response["message"]
    assert any("expression_type must be either cron or epoch" in err["msg"] for err in errors)


def test_scheduler_config_missing_timezone():
    payload = {
        "pipeline_name": "daily_pipeline",
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "10 10 * * *",
            "timezone": ""
        }
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    data = response.json()
    assert data["error_code"] == 422
    assert any("timezone is required for all schedules" in err["msg"] for err in data["message"])


def test_scheduler_config_missing_schedule():
    payload = {
        "pipeline_name": "daily_pipeline",
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "",
            "timezone": "Asia/Kolkata"
        }
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    data = response.json()
    assert data["error_code"] == 422
    assert any("schedule time is required for all schedules" in err["msg"] for err in data["message"])


def test_scheduler_config_invalid_cron_expression():
    payload = {
        "pipeline_name": "daily_pipeline",
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "invalid_cron",
            "timezone": "Asia/Kolkata"
        }
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    data = response.json()
    assert data["error_code"] == 422
    assert any("Invalid cron expression" in err["msg"] for err in data["message"])


def test_scheduler_config_cron_interval_too_small():
    payload = {
        "pipeline_name": "daily_pipeline",
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "* * * * *",
            "timezone": "Asia/Kolkata"
        }
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    data = response.json()
    assert data["error_code"] == 422
    assert any("Recurrence interval must be at least" in err["msg"] for err in data["message"])


def test_scheduler_config_epoch_invalid_integer():
    payload = {
        "pipeline_name": "daily_pipeline",
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z",
        "scheduler_config": {
            "expression_type": "epoch",
            "schedule": "invalid",
            "timezone": "Asia/Kolkata"
        }
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    data = response.json()
    assert data["error_code"] == 422
    assert any("schedule must be a valid integer epoch time" in err["msg"] for err in data["message"])


def test_scheduler_config_epoch_unknown_timezone():
    future_epoch = int(datetime.now().timestamp()) + 5000
    payload = {
        "pipeline_name": "daily_pipeline",
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z",
        "scheduler_config": {
            "expression_type": "epoch",
            "schedule": str(future_epoch),
            "timezone": "Invalid/XYZ"
        }
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    data = response.json()
    assert data["error_code"] == 422
    assert any("Unknown timezone" in err["msg"] for err in data["message"])


def test_scheduler_config_epoch_not_in_future():
    past_epoch = int(datetime.now().timestamp()) - 100
    payload = {
        "pipeline_name": "daily_pipeline",
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z",
        "scheduler_config": {
            "expression_type": "epoch",
            "schedule": str(past_epoch),
            "timezone": "Asia/Kolkata"
        }
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    data = response.json()
    assert data["error_code"] == 422
    assert any("epoch time (schedule) must be in the future" in err["msg"] for err in data["message"])


def test_list_pipeline_events_success():
    response = client.get(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Events fetched"


def test_get_pipeline_event_success():
    response = client.get(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events/{pytest.analytics_event_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Event retrieved"
    assert actual["data"]


def test_get_pipeline_event_not_found():
    response = client.get(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events/invalid-id-123",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is False


@patch("kairon.shared.utils.Utility.execute_http_request", autospec=True)
def test_delete_pipeline_event_success(mock_http):
    mock_http.return_value = {"success": True}

    response = client.delete(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events/{pytest.analytics_event_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Event deleted"
    mock_http.assert_called_once()



@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_delete_pipeline_event_failure(mock_event_server):
    mock_event_server.side_effect = Exception("Delete failure")
    response = client.delete(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events/fake-id-123",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is False


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_update_pipeline_event_success(mock_event_server):
    payload = {
        "pipeline_name": "daily_analytics_pipeline",
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "32 11 * * *",
            "timezone": "Asia/Kolkata"
        },
        "data_deletion_policy": [],
        "triggers": []
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    pytest.analytics_event_id = actual["data"]["event_id"]

    payload = {
        "pipeline_name": "updated_pipeline",
        "callback_name": "callback_test",
        "timestamp": "2025-11-25T14:30:00Z",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "10 12 * * *",
            "timezone": "Asia/Kolkata"
        },
        "data_deletion_policy": [],
        "triggers": []
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events/{pytest.analytics_event_id}",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Event updated"
    assert actual["data"]["event_id"] == pytest.analytics_event_id


def test_update_pipeline_event_validation_error():
    payload = {
        "pipeline_name": "",
        "callback_name": "cb_test",
        "timestamp": "invalid-ts"
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/pipeline_analytics/events/{pytest.analytics_event_id}",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()
    assert response['error_code'] == 422

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/callback/callback_test",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()


def test_search_and_list_analytics_pipeline_logs():

    now = utc_now().replace(tzinfo=pytz.UTC)

    entries = [
        {
            "status": "Completed",
            "start_offset": 0,
            "end_offset": 2,
        },
        {
            "status": "Completed",
            "start_offset": -30,
            "end_offset": -27,
        },
        {
            "status": "Fail",
            "exception": "Execution error: Expecting value: line 1 column 1 (char 0)",
            "start_offset": -40,
            "end_offset": -38,
        },
        {
            "status": "Completed",
            "start_offset": -60,
            "end_offset": -57,
        },
    ]

    for e in entries:
        AnalyticsPipelineLogs(
            event_id="6938ff94e22b4ae6c225fa18",
            status=e["status"],
            pipeline_name="daily_analytics_pipeline",
            callback_name="callback_test",
            exception=e.get("exception"),
            bot=pytest.bot,
            bot_response={"message": "Record Saved!"},
            user = "integration@demo.ai",
            start_timestamp=now + timedelta(minutes=e["start_offset"]),
            end_timestamp=now + timedelta(minutes=e["end_offset"]),
        ).save()


    list_resp = client.get(
        f"/api/bot/{pytest.bot}/logs/analytics_pipeline",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    list_data = list_resp.json()
    assert list_data["success"]
    assert list_data["error_code"] == 0
    assert list_data["data"]["total"] == 4
    assert len(list_data["data"]["logs"]) == 4

    for log in list_data["data"]["logs"]:
        assert log["event_id"]
        assert log["status"]
        assert log["pipeline_name"] == "daily_analytics_pipeline"
        assert log["callback_name"] == "callback_test"
        assert log["bot_response"] == {"message": "Record Saved!"}
        assert log.get("start_time") or log.get("start_timestamp")
        assert log.get("end_time") or log.get("end_timestamp")
        assert log["user"] == "integration@demo.ai"


    from_date = (now - timedelta(days=1)).date()
    to_date = (now + timedelta(days=1)).date()

    search_url = (
        f"/api/bot/{pytest.bot}/logs/analytics_pipeline/search"
        f"?from_date={from_date}&to_date={to_date}"
        f"&start_idx=0&page_size=10&pipeline_name=daily_analytics_pipeline"
    )

    search_resp = client.get(
        search_url,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    search_data = search_resp.json()
    assert search_data["success"]
    assert search_data["error_code"] == 0
    assert search_data["data"]["total"] == 4
    assert len(search_data["data"]["logs"]) == 4

    for log in search_data["data"]["logs"]:
        assert log["event_id"]
        assert log["status"]
        assert log["pipeline_name"] == "daily_analytics_pipeline"
        assert log["callback_name"] == "callback_test"
        assert log["start_timestamp"]
        assert log["end_timestamp"]
        assert log["user"] == "integration@demo.ai"
        if log["status"] == "Fail":
            assert "Execution error" in log["exception"]
