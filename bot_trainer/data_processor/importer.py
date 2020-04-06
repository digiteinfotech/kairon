from typing import Optional, Text, Dict

from rasa.importers.importer import TrainingDataImporter
from rasa.nlu.training_data import TrainingData
from rasa.core.domain import Domain
from rasa.core.training.structures import StoryGraph
from .processor import MongoProcessor
from rasa.core.interpreter import RegexInterpreter, NaturalLanguageInterpreter


class MongoDataImporter(TrainingDataImporter):

        def __init__(self, bot: str, account: int):
            self.bot = bot
            self.account = account
            self.processor = MongoProcessor()

        def get_nlu_data(self, language: Optional[Text] = "en") -> TrainingData:
            return self.processor.load_nlu(self.bot, self.account)

        def get_domain(self) -> Domain:
            return self.processor.load_domain(self.bot, self.account)

        def get_config(self) -> Dict:
            return self.processor.load_config(self.bot, self.account)

        def get_stories(
        self,
        interpreter: "NaturalLanguageInterpreter" = RegexInterpreter(),
        template_variables: Optional[Dict] = None,
        use_e2e: bool = False,
        exclusion_percentage: Optional[int] = None,
    ) -> StoryGraph:
            self.processor.load_stories(self.bot, self.account)