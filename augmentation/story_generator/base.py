from abc import ABC, abstractmethod


class TrainingDataGeneratorBase(ABC):

    """Base class for generating training data from different sources."""

    @abstractmethod
    def extract(self):
        """Retrieve training data from source."""
        raise NotImplementedError("Provider not implemented")
