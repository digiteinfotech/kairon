from mongoengine import Document, EmbeddedDocument, EmbeddedDocumentField, StringField, LongField, ListField, ValidationError, DateTimeField, BooleanField, DictField
from datetime import datetime

class Entity(EmbeddedDocument):
    start = LongField(required=True)
    end = LongField(required=True)
    value = StringField(required=True)
    entity = StringField(required=True)

class TrainingExamples(Document):
    intent = StringField(required=True)
    text = StringField(required=True)
    bot = StringField(required=True)
    account = LongField(required=True)
    entities = ListField(EmbeddedDocumentField(Entity))
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {'indexes': [{'fields': ['$text']}]}

    def validate(self, clean=True):
        if self.entities:
            for ent in self.entities:
                extracted_ent = self.text[ent.start:ent.end]
                if extracted_ent != ent.value:
                    raise ValidationError("Invalid entity: "+ent.entity+", value: "+ent.value+" does not match with the position in the text "+extracted_ent)


class EntitySynonyms(Document):
    bot = StringField(required=True)
    account = LongField(required=True)
    synonym = StringField(required=True)
    value = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {'indexes': [{'fields': ['$value']}]}

class LookupTables(Document):
    name = StringField(required=True)
    value = StringField(required=True)
    bot = StringField(required=True)
    account = LongField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {'indexes': [{'fields': ['$value']}]}

class RegexFeatures(Document):
    name = StringField(required=True)
    pattern = StringField(required=True)
    bot = StringField(required=True)
    account = LongField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {'indexes': [{'fields': ['$text']}]}

class Intents(Document):
    value = StringField(required=True)
    bot = StringField(required=True, unique_with="value")
    account = LongField(required=True, unique_with="bot")
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)


class Entities(Document):
    name = StringField(required=True)
    bot = StringField(required=True, unique_with="name")
    account = LongField(required=True, unique_with="bot")
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

class Form(Document):
    name = StringField(required=True)
    bot = StringField(required=True, unique_with="name")
    account = LongField(required=True, unique_with="bot")
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

class ResponseButton(EmbeddedDocument):
    title = StringField(required=True)
    payload = StringField(required=True)

class ResponseText(EmbeddedDocument):
    text = StringField(required=True)
    image: StringField()
    channel: StringField(required=True)
    buttons: ListField(EmbeddedDocumentField(ResponseButton))

class ResponseCustom(EmbeddedDocument):
    text = DictField(required=True)

class Responses(Document):
    name = StringField(required=True)
    texts = ListField(EmbeddedDocumentField(ResponseText))
    customs = ListField(EmbeddedDocumentField(ResponseCustom))
    bot = StringField(required=True, unique_with="name")
    account = LongField(required=True, unique_with="bot")
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if not self.texts and not self.customs:
            raise ValidationError("Either Text or Custom response must be present!")


class Actions(Document):
    name = StringField(required=True)
    bot = StringField(required=True, unique_with="name")
    account = LongField(required=True, unique_with="bot")
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

class SessionConfig(Document):
    sesssionExpirationTime = LongField(required=True, default=60)
    carryOverSlots = BooleanField(required=True, default=True)
    bot = StringField(required=True)
    account = LongField(required=True, unique_with="bot")
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

class SlotConfig(Document):
    name = StringField(required=True)
    datatype = StringField(required=True)
    fields = ListField(DictField())
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)