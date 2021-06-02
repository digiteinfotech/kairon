import os
from typing import Text

from rasa.shared.constants import DEFAULT_DOMAIN_PATH, DEFAULT_CONFIG_PATH, DEFAULT_DATA_PATH

from .validator.file_validator import TrainingDataValidator


class DataImporter:
    """
    Class to import training data into kairon. A validation is run over training data
    before initiating the import process.
    """

    def __init__(self, path: Text, bot: Text, user: Text, save_data: bool = True, overwrite: bool = True):
        """Initialize data importer"""

        self.path = path
        self.bot = bot
        self.user = user
        self.save_data = save_data
        self.overwrite = overwrite

    async def validate(self):
        """
        Validates domain and data files to check for possible mistakes and logs them into collection.
        """
        data_path = os.path.join(self.path, DEFAULT_DATA_PATH)
        config_path = os.path.join(self.path, DEFAULT_CONFIG_PATH)
        domain_path = os.path.join(self.path, DEFAULT_DOMAIN_PATH)
        self.validator = await TrainingDataValidator.from_training_files(data_path, domain_path,
                                                                         config_path, self.path)
        self.validator.validate_training_data(False)
        return self.validator.summary

    def import_data(self):
        """
        Saves training data into database.
        """
        if self.save_data:
            if self.validator.config and self.validator.domain and self.validator.story_graph and self.validator.intents:
                from kairon.data_processor.processor import MongoProcessor

                processor = MongoProcessor()
                processor.save_training_data(self.validator.config,
                                             self.validator.domain,
                                             self.validator.story_graph,
                                             self.validator.intents,
                                             self.validator.http_actions, self.bot, self.user,
                                             self.overwrite)
