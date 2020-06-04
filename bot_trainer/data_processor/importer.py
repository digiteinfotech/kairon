from typing import Optional, Text, Dict

from rasa.importers.importer import TrainingDataImporter
from rasa.nlu.training_data import TrainingData
from rasa.core.domain import Domain
from rasa.core.training.structures import StoryGraph
from .processor import MongoProcessor
from rasa.core.interpreter import RegexInterpreter, NaturalLanguageInterpreter
from bot_trainer.exceptions import AppException


class MongoDataImporter(TrainingDataImporter):
    """ This class defines the functions that are used to load data
        from the bot files """
    def __init__(self, bot: str):
        self.bot = bot
        self.processor = MongoProcessor()

    async def get_nlu_data(self, language: Optional[Text] = "en") -> TrainingData:
        """ Loads the data from the nlu file of the bot """
        training_data = self.processor.load_nlu(self.bot)
        if not training_data.training_examples:
            raise AppException("Training data does not exists!")
        return training_data

    async def get_domain(self) -> Domain:
        """ loads the data from the domain file of the bot """
        return self.processor.load_domain(self.bot)

    async def get_config(self) -> Dict:
        """ loads the data from the config file of the bot """
        return self.processor.load_config(self.bot)

    async def get_stories(
        self,
        interpreter: "NaturalLanguageInterpreter" = RegexInterpreter(),
        template_variables: Optional[Dict] = None,
        use_e2e: bool = False,
        exclusion_percentage: Optional[int] = None,
    ) -> StoryGraph:
        """ Loads the data from the stories file of the bot """
        return self.processor.load_stories(self.bot)
