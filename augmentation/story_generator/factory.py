from typing import Text

from augmentation.story_generator.website import WebsiteTrainingDataGenerator
from kairon.exceptions import AppException
from kairon.shared.data.constant import TrainingDataSourceType


class TrainingDataGeneratorFactory:

    __implementations = {
        TrainingDataSourceType.website.value: WebsiteTrainingDataGenerator
    }

    @staticmethod
    def get_instance(source: Text):
        if not TrainingDataGeneratorFactory.__implementations.get(source):
            raise AppException(f'{source} data extraction not supported yet!')
        return TrainingDataGeneratorFactory.__implementations[source]
