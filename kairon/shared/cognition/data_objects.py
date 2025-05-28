from datetime import datetime

from mongoengine import EmbeddedDocument, StringField, BooleanField, ValidationError, ListField, EmbeddedDocumentField, \
    DateTimeField, SequenceField, DynamicField, DictField

from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import push_notification, auditlogger
from kairon.shared.models import CognitionMetadataType, CognitionDataType


class ColumnMetadata(EmbeddedDocument):
    column_name = StringField(required=True)
    data_type = StringField(required=True, default=CognitionMetadataType.str.value,
                            choices=[CognitionMetadataType.str.value, CognitionMetadataType.int.value, CognitionMetadataType.float.value])
    enable_search = BooleanField(default=True)
    create_embeddings = BooleanField(default=True)

    def validate(self, clean=True):
        from kairon import Utility

        if clean:
            self.clean()
        if self.data_type not in [CognitionMetadataType.str.value, CognitionMetadataType.int.value, CognitionMetadataType.float.value]:
            raise ValidationError("Only str,int and float data types are supported")
        if Utility.check_empty_string(self.column_name):
            raise ValidationError("Column name cannot be empty")

    def clean(self):
        from kairon import Utility

        if not Utility.check_empty_string(self.column_name):
            self.column_name = self.column_name.strip().lower()


@auditlogger.log
@push_notification.apply
class CognitionSchema(Auditlog):
    metadata = ListField(EmbeddedDocumentField(ColumnMetadata, default=None))
    collection_name = StringField(required=True)
    user = StringField(required=True)
    bot = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    activeStatus = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot"]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        if self.metadata:
            for metadata_dict in self.metadata:
                metadata_dict.validate()

    def clean(self):
        self.collection_name = self.collection_name.strip().lower()


@auditlogger.log
@push_notification.apply
class CognitionData(Auditlog):
    vector_id = SequenceField(required=True)
    data = DynamicField(required=True)
    content_type = StringField(default=CognitionDataType.text.value, choices=[CognitionDataType.text.value,
                                                                              CognitionDataType.json.value])
    collection = StringField(default=None)
    user = StringField(required=True)
    bot = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["$data", "bot"]}]}

    def validate(self, clean=True):
        from kairon import Utility

        if clean:
            self.clean()

        if isinstance(self.data, dict) and self.content_type != CognitionDataType.json.value:
            raise ValidationError("content type and type of data do not match!")
        if not self.data or (isinstance(self.data, str) and Utility.check_empty_string(self.data)):
            raise ValidationError("data cannot be empty")

    def clean(self):
        if self.collection:
            self.collection = self.collection.strip().lower()


class CollectionData(Auditlog):
    collection_name = StringField(required=True)
    is_secure = ListField(StringField(), default=[])
    is_non_editable = ListField(StringField(), default=[])
    data = DictField()
    user = StringField(required=True)
    bot = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot"]}]}

    def validate(self, clean=True):
        from kairon import Utility

        if clean:
            self.clean()

        if Utility.check_empty_string(self.collection_name):
            raise ValidationError("collection_name should not be empty")

        if not isinstance(self.is_secure, list):
            raise ValidationError("is_secure should be list of keys")

        if self.is_secure:
            if not self.data or not isinstance(self.data, dict):
                raise ValidationError("data cannot be empty and should be of type dict")
            data_keys = set(self.data.keys())
            is_secure_set = set(self.is_secure)

            if not is_secure_set.issubset(data_keys):
                raise ValidationError("is_secure contains keys that are not present in data")

    def clean(self):
        if self.collection_name:
            self.collection_name = self.collection_name.strip().lower()
