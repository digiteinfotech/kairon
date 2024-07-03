import unittest
import responses
from kairon.shared.verification.email import QuickEmailVerification
from urllib.parse import urlencode
from unittest import mock
from kairon.shared.utils import Utility
import os


class VerificationTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()

    @responses.activate
    def test_quick_email_verification(self):
        email_address = "test@test.com"
        api_key = "test"
        with mock.patch.dict(Utility.environment, {'verify': {"email": {"type": "quickemail", "key": api_key, "enable": True}}}):
            verification = QuickEmailVerification()
            responses.add(responses.GET,
                          verification.url + "?" + urlencode({"apikey": verification.key, "email": email_address}),
                          json={
                              "result": "valid",
                              "reason": "rejected_email",
                              "disposable": "false",
                              "accept_all": "false",
                              "role": "false",
                              "free": "false",
                              "email": "test@test.com",
                              "user": "test",
                              "domain": "quickemailverification.com",
                              "mx_record": "us2.mx1.mailhostbox.com",
                              "mx_domain": "mailhostbox.com",
                              "safe_to_send": "false",
                              "did_you_mean": "",
                              "success": "true",
                              "message": None
                          })
            self.assertTrue(verification.verify(email_address))

    @responses.activate
    def test_quick_email_verification_disposable(self):
        email_address = "test@test.com"
        api_key = "test"
        with mock.patch.dict(Utility.environment, {'verify': {"email": {"type": "quickemail", "key": api_key, "enable": True}}}):
            verification = QuickEmailVerification()
            responses.add(responses.GET,
                          verification.url + "?" + urlencode({"apikey": verification.key, "email": email_address}),
                          json={
                              "result": "valid",
                              "reason": "rejected_email",
                              "disposable": "true",
                              "accept_all": "false",
                              "role": "false",
                              "free": "false",
                              "email": "test@test.com",
                              "user": "test",
                              "domain": "quickemailverification.com",
                              "mx_record": "us2.mx1.mailhostbox.com",
                              "mx_domain": "mailhostbox.com",
                              "safe_to_send": "false",
                              "did_you_mean": "",
                              "success": "true",
                              "message": None
                          })
            self.assertFalse(verification.verify(email_address))

    @responses.activate
    def test_quick_email_verification_invalid(self):
        email_address = "test@test.com"
        api_key = "test"
        with mock.patch.dict(Utility.environment, {'verify': {"email": {"type": "quickemail", "key": api_key, "enable": True}}}):
            verification = QuickEmailVerification()
            responses.add(responses.GET,
                          verification.url + "?" + urlencode({"apikey": verification.key, "email": email_address}),
                          json={
                              "result": "invalid",
                              "reason": "rejected_email",
                              "disposable": "true",
                              "accept_all": "false",
                              "role": "false",
                              "free": "false",
                              "email": "test@test.com",
                              "user": "test",
                              "domain": "quickemailverification.com",
                              "mx_record": "us2.mx1.mailhostbox.com",
                              "mx_domain": "mailhostbox.com",
                              "safe_to_send": "false",
                              "did_you_mean": "",
                              "success": "true",
                              "message": None
                          })
            self.assertFalse(verification.verify(email_address))
