import pytest

from kairon.api.models import HttpActionConfigRequest, HttpActionParameters


class TestBotModels:

    def test_http_action_params_valid(self):
        assert HttpActionParameters(key="param1", value="param1", parameter_type="slot")
        assert HttpActionParameters(key="param1", value="param1", parameter_type="value")
        HttpActionParameters(key="key", value="", parameter_type="value")
        HttpActionParameters(key="key", value=None, parameter_type="value")
        assert HttpActionParameters(key="param1", value="param1", parameter_type="sender_id")
        assert HttpActionParameters(key="param1", value="", parameter_type="sender_id")
        assert HttpActionParameters(key="param1", parameter_type="sender_id")

    def test_http_action_params_invalid(self):
        with pytest.raises(ValueError, match=r".*key cannot be empty.*"):
            HttpActionParameters(key="", value="param1", parameter_type="slot")
        with pytest.raises(ValueError, match=r".*key cannot be empty.*"):
            HttpActionParameters(key=None, value="param1", parameter_type="slot")
        with pytest.raises(ValueError, match=r".*Provide name of the slot as value.*"):
            HttpActionParameters(key="key", value="", parameter_type="slot")
        with pytest.raises(ValueError, match=r".*Provide name of the slot as value.*"):
            HttpActionParameters(key="key", value=None, parameter_type="slot")
        with pytest.raises(ValueError, match=r".*parameter_type\n  value is not a valid enumeration member.*"):
            HttpActionParameters(key="key", value="value", parameter_type="unknown_type")

    def test_http_action_config_request_valid(self):
        HttpActionConfigRequest(
            auth_token="",
            action_name="test_action",
            response="response",
            http_url="http://www.google.com",
            request_method="GET",
            http_params_list=[]
        )
        HttpActionConfigRequest(
            auth_token=None,
            action_name="test_action",
            response="response",
            http_url="http://www.google.com",
            request_method="GET",
            http_params_list=[]
        )
        HttpActionConfigRequest(
            auth_token=None,
            action_name="test_action",
            response="response",
            http_url="http://www.google.com",
            request_method="GET",
            http_params_list=None
        )

    def test_http_action_config_request_invalid(self):
        with pytest.raises(ValueError, match=r".*none is not an allowed value.*"):
            HttpActionConfigRequest(auth_token="", action_name=None, response="response",
                                    http_url="http://www.google.com",
                                    request_method="GET", http_params_list=[])
        with pytest.raises(ValueError, match=r".*action_name is required*"):
            HttpActionConfigRequest(auth_token="", action_name="", response="response",
                                    http_url="http://www.google.com",
                                    request_method="GET", http_params_list=[])
        with pytest.raises(ValueError, match=r".*none is not an allowed value.*"):
            HttpActionConfigRequest(auth_token="", action_name="http_action", response=None,
                                    http_url="http://www.google.com",
                                    request_method="GET", http_params_list=[])
        with pytest.raises(ValueError, match=r".*URL is malformed.*"):
            HttpActionConfigRequest(auth_token="", action_name="http_action", response="response", http_url="",
                                    request_method="GET", http_params_list=[])
        with pytest.raises(ValueError, match=r".*none is not an allowed value.*"):
            HttpActionConfigRequest(auth_token="", action_name="http_action", response="response", http_url=None,
                                    request_method="GET", http_params_list=[])
        with pytest.raises(ValueError, match=r".URL is malformed.*"):
            HttpActionConfigRequest(auth_token="", action_name="http_action", response="response",
                                    http_url="www.google.com", request_method="GET", http_params_list=[])
        with pytest.raises(ValueError, match=r".*Invalid HTTP method.*"):
            HttpActionConfigRequest(auth_token="", action_name="http_action", response="response",
                                    http_url="http://www.google.com",
                                    request_method="OPTIONS", http_params_list=[])
        with pytest.raises(ValueError, match=r".*Invalid HTTP method.*"):
            HttpActionConfigRequest(auth_token="", action_name="http_action", response="response",
                                    http_url="http://www.google.com",
                                    request_method="", http_params_list=[])
        with pytest.raises(ValueError, match=r".*none is not an allowed value.*"):
            HttpActionConfigRequest(auth_token="", action_name="http_action", response="response",
                                    http_url="http://www.google.com",
                                    request_method=None, http_params_list=[])
