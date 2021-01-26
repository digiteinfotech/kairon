from typing import Optional, Text, Dict

from rasa.shared.importers.importer import TrainingDataImporter
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.shared.core.domain import Domain
from rasa.shared.nlu.interpreter import NaturalLanguageInterpreter, RegexInterpreter
from rasa.shared.core.training_data.structures import StoryGraph
from .processor import MongoProcessor
from kairon.exceptions import AppException


class MongoDataImporter(TrainingDataImporter):
    """Class overrides the TrainingDataImporter functionality required for training bot"""

    def __init__(self, bot: str):
        self.bot = bot
        self.processor = MongoProcessor()

    async def get_nlu_data(self, language: Optional[Text] = "en") -> TrainingData:
        """
        loads training examples
        """
        training_data = self.processor.load_nlu(self.bot)
        if not training_data.training_examples:
            raise AppException("Training data does not exists!")
        return training_data

    async def get_domain(self) -> Domain:
        """
        loads domain data
        """
        return self.processor.load_domain(self.bot)

    async def get_config(self) -> Dict:
        """
        loads bot training configuration
        """
        return self.processor.load_config(self.bot)

    async def get_stories(
        self,
        interpreter: "NaturalLanguageInterpreter" = RegexInterpreter(),
        template_variables: Optional[Dict] = None,
        use_e2e: bool = False,
        exclusion_percentage: Optional[int] = None,
    ) -> StoryGraph:
        """
        loads stories
        """
        return self.processor.load_stories(self.bot)
