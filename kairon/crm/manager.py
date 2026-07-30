from .processor import CRMProcessor


class CRMManager:

    @staticmethod
    def get_processor() -> CRMProcessor:
        return CRMProcessor()
