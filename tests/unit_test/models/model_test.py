import pytest
from mongoengine import ValidationError

from kairon.api.models import HttpActionConfigRequest, HttpActionParameters, ActionResponseEvaluation
from kairon.shared.data.data_objects import Slots, SlotMapping


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
            response=ActionResponseEvaluation(value="response"),
            http_url="http://www.google.com",
            request_method="GET",
            http_params_list=[]
        )
        HttpActionConfigRequest(
            auth_token=None,
            action_name="test_action",
            response=ActionResponseEvaluation(value="response"),
            http_url="http://www.google.com",
            request_method="GET",
            http_params_list=[]
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
        HttpActionConfigRequest(auth_token="", action_name="http_action", response=None, http_url="http://www.google.com",
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

    def test_slot(self):
        with pytest.raises(ValueError, match="Slot name and type cannot be empty or blank spaces"):
            Slots(name='email_id', type=' ', auto_fill=True).save()
        with pytest.raises(ValueError, match="Slot name and type cannot be empty or blank spaces"):
            Slots(name=' ', type='text', auto_fill=True).save()

    def test_validate_slot_mapping(self):
        with pytest.raises(ValueError, match="Slot name cannot be empty or blank spaces"):
            SlotMapping(slot=' ', mapping=[{"type": "from_value"}]).save()
        with pytest.raises(ValidationError,
                           match="Your form 'form_name' uses an invalid slot mapping of type 'from_value' for slot 'email_id'. Please see https://rasa.com/docs/rasa/forms for more information."):
            SlotMapping(slot='email_id', mapping=[{"type": "from_value"}]).save()
        assert not SlotMapping(
            slot='email_id', mapping=[{"type": "from_intent", "value": 'uditpandey@hotmail.com'}]
        ).validate()
