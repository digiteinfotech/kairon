import os
from typing import Text

from rasa.shared.constants import DEFAULT_DOMAIN_PATH, DEFAULT_CONFIG_PATH, DEFAULT_DATA_PATH
from kairon.shared.data.constant import REQUIREMENTS
from kairon.shared.data.processor import MongoProcessor
from .validator.file_validator import TrainingDataValidator


class DataImporter:
    """
    Class to import training data into kairon. A validation is run over training data
    before initiating the import process.
    """
    processor = MongoProcessor()

    def __init__(self, path: Text, bot: Text, user: Text, files_to_save: set, save_data: bool = True,
                 overwrite: bool = True):
        """Initialize data importer"""

        self.path = path
        self.bot = bot
        self.user = user
        self.save_data = save_data
        self.overwrite = overwrite
        self.files_to_save = files_to_save

    async def validate(self):
        """
        Validates domain and data files to check for possible mistakes and logs them into collection.
        """
        DataImporter.processor.prepare_training_data_for_validation(self.bot, self.path,
                                                                    REQUIREMENTS - self.files_to_save)
        data_path = os.path.join(self.path, DEFAULT_DATA_PATH)
        config_path = os.path.join(self.path, DEFAULT_CONFIG_PATH)
        domain_path = os.path.join(self.path, DEFAULT_DOMAIN_PATH)
        TrainingDataValidator.validate_domain(domain_path)
        self.validator = await TrainingDataValidator.from_training_files(data_path, domain_path,
                                                                         config_path, self.path)
        self.validator.validate_training_data(False, self.bot, self.user, self.save_data, self.overwrite)
        return self.validator.summary, self.validator.component_count

    def import_data(self):
        """
        Saves training data into database.
        """
        if self.save_data and self.files_to_save:
            if self.validator.config and self.validator.domain and self.validator.story_graph and self.validator.intents:
                DataImporter.processor.save_training_data(self.bot, self.user,
                                                          self.validator.config,
                                                          self.validator.domain,
                                                          self.validator.story_graph,
                                                          self.validator.intents,
                                                          self.validator.actions,
                                                          self.validator.multiflow_stories,
                                                          self.validator.bot_content,
                                                          self.validator.chat_client_config.get('config'),
                                                          self.validator.other_collections,
                                                          self.overwrite, self.files_to_save,
                                                          file_upload=True)
