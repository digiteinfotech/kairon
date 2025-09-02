from kairon.events.definitions.crud_file_upload import CrudFileUploader
from kairon.exceptions import AppException
from kairon.shared.constants import UploadHandlerClass


class UploadHandlerFactory:

    upload_handler = {
        UploadHandlerClass.crud_data: CrudFileUploader
    }

    @staticmethod
    def get_instance(upload_class: str):
        """
        Factory to retrieve uploadFile implementation for execution.

        :param upload_class: valid uploadFile class
        """
        if upload_class not in UploadHandlerFactory.upload_handler.keys():
            valid_events = [ev.value for ev in UploadHandlerClass]
            raise AppException(f"{upload_class} is not a valid event. Accepted event types: {valid_events}")
        return UploadHandlerFactory.upload_handler[upload_class]
