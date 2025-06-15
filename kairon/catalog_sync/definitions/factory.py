from kairon.events.definitions.petpooja_sync import PetpoojaSync
from kairon.exceptions import AppException
from kairon.shared.constants import CatalogSyncClass


class CatalogSyncFactory:

    __provider_implementations = {
        CatalogSyncClass.petpooja: PetpoojaSync,
    }

    @staticmethod
    def get_instance(provider: str):
        """
        Factory to retrieve catalog provider implementation for execution.
        :param provider: catalog provider name (e.g., "petpooja")
        :return: Corresponding Sync class
        """
        try:
            provider_enum = CatalogSyncClass(provider.lower())
        except ValueError:
            valid_syncs = [sync.value for sync in CatalogSyncClass]
            raise AppException(f"'{provider}' is not a valid catalog sync provider. Accepted types: {valid_syncs}")

        sync_class = CatalogSyncFactory.__provider_implementations.get(provider_enum)
        if not sync_class:
            raise AppException(f"No implementation found for provider '{provider}'.")

        return sync_class