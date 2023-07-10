from kairon.exceptions import AppException
from kairon.shared.constants import VectorEmbeddingsDatabases
from kairon.shared.vector_embeddings.db.qdrant import Qdrant


class VectorEmbeddingsDbFactory:

    __implementations = {
        VectorEmbeddingsDatabases.qdrant.value: Qdrant
    }

    @staticmethod
    def get_instance(db_type):
        if db_type not in VectorEmbeddingsDbFactory.__implementations.keys():
            raise AppException("Database not yet implemented!")
        return VectorEmbeddingsDbFactory.__implementations[db_type]
