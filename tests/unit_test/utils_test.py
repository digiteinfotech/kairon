from bot_trainer.utils import Utility
import pytest
from bot_trainer.exceptions import AppException
import os
import yaml
from loguru import logger

class TestUtility:

    def test_load_configuration_yaml_invalid(self):
        with pytest.raises(AppException):
            Utility.load_configuration_yaml('demo.ini')

    def test_load_configuration_no_env(self):
        data = Utility.load_configuration_yaml("./tests/testing_data/sample.yaml")
        assert data['system'] == 'testing'
        assert data['testing']['demo'] == 'default'
        assert data['plain'] == "value"

    def test_load_configuration_env(self):
        os.environ['SYSTEM'] = "env_value"
        os.environ['ENVIRONMENT_VARIABLE'] = "value"
        data = Utility.load_configuration_yaml("./tests/testing_data/sample.yaml")
        assert data['system'] == 'env_value'
        assert data['testing']['demo'] == 'value'
        assert data['plain'] == "value"
        del os.environ['SYSTEM']
        del os.environ['ENVIRONMENT_VARIABLE']

    def test_load_configuration_invalid_value(self):
        old_data = yaml.safe_load(open('./tests/testing_data/sample.yaml'))
        logger.info(old_data)
        sample = {'system': "${SYSTEM:testing"}
        yaml.safe_dump(sample, open('./tests/testing_data/sample.yaml', mode='w+'))
        with pytest.raises(AppException):
            Utility.load_configuration_yaml("./tests/testing_data/sample.yaml")
        yaml.safe_dump(old_data, open('./tests/testing_data/sample.yaml', mode='w+'))
        data = Utility.load_configuration_yaml("./tests/testing_data/sample.yaml")
        assert data['system'] == 'testing'
        assert data['testing']['demo'] == 'default'
        assert data['plain'] == "value"
        sample = {'system': "SYSTEM:testing}"}
        yaml.safe_dump(sample, open('./tests/testing_data/sample.yaml', mode='w+'))
        with pytest.raises(AppException):
            Utility.load_configuration_yaml("./tests/testing_data/sample.yaml")
        yaml.safe_dump(old_data, open('./tests/testing_data/sample.yaml', mode='w+'))