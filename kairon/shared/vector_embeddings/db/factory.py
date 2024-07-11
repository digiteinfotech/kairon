from kairon.exceptions import AppException
from kairon.shared.constants import VectorEmbeddingsDatabases
from kairon.shared.vector_embeddings.db.qdrant import Qdrant


class DatabaseFactory:

    __implementations = {
        VectorEmbeddingsDatabases.qdrant.value: Qdrant
    }

    @staticmethod
    def get_instance(db_type):
        if db_type not in DatabaseFactory.__implementations.keys():
            raise AppException("Database not yet implemented!")
        return DatabaseFactory.__implementations[db_type]
