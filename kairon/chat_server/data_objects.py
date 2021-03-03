from datetime import datetime

from mongoengine import Document, StringField, DateTimeField, BooleanField, DictField, LongField, EmbeddedDocument, \
    EmbeddedDocumentField, ValidationError

from kairon.chat_server.channels.channels import KaironChannels


class ChannelCredentials(Document):
    bot = StringField(required=True)
    user = StringField(required=True)
    channel = StringField(required=True)
    credentials = DictField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if self.channel not in [channel for channel in KaironChannels]:
            raise ValidationError("Channel not supported!")


# class User(Document):
#     email = StringField(required=True)
#     first_name = StringField(required=True)
#     last_name = StringField(required=True)
#     password = StringField(required=True)
#     role = StringField(required=True, default="trainer")
#     is_integration_user = BooleanField(default=False)
#     account = LongField(required=True)
#     bot = StringField(required=True)
#     user = StringField(required=True)
#     timestamp = DateTimeField(default=datetime.utcnow)
#     status = BooleanField(default=True)
#
#
# class Bot(Document):
#     name = StringField(required=True)
#     account = LongField(required=True)
#     user = StringField(required=True)
#     timestamp = DateTimeField(default=datetime.utcnow)
#     status = BooleanField(default=True)
#
#
# class UserEmailConfirmation(Document):
#     email = StringField(required=True, primary_key=True)
#     timestamp = DateTimeField(default=datetime.utcnow)
#
#
# class EndPointTracker(EmbeddedDocument):
#     type = StringField(required=True, default="mongo")
#     url = StringField(required=True)
#     db = StringField(required=True)
#     username = StringField()
#     password = StringField()
#     auth_source = StringField()
#
#
# class EndPointAction(EmbeddedDocument):
#     url = StringField(required=True)
#
#
# class EndPointBot(EmbeddedDocument):
#     url = StringField(required=True)
#     token = StringField()
#     token_type = StringField()
#
#
# class Endpoints(Document):
#     bot_endpoint = EmbeddedDocumentField(EndPointBot)
#     action_endpoint = EmbeddedDocumentField(EndPointAction)
#     tracker_endpoint = EmbeddedDocumentField(EndPointTracker)
#     bot = StringField(required=True)
#     user = StringField(required=True)
#     timestamp = DateTimeField(default=datetime.utcnow)
