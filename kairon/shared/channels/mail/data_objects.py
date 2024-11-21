import time
from mongoengine import Document, StringField, ListField, FloatField, BooleanField
from kairon.exceptions import AppException




class MailClassificationConfig(Document):
    intent: str = StringField(required=True)
    entities: list[str] = ListField(StringField())
    subjects: list[str] = ListField(StringField())
    classification_prompt: str = StringField()
    reply_template: str = StringField()
    bot: str = StringField(required=True)
    user: str = StringField()
    timestamp: float = FloatField()
    status: bool = BooleanField(default=True)


    @staticmethod
    def create_doc(
            intent: str,
            entities: list[str],
            subjects: list[str],
            classification_prompt: str,
            reply_template: str,
            bot: str,
            user: str
    ):
        mail_config = None
        try:
            exists = MailClassificationConfig.objects(bot=bot, intent=intent).first()
            if exists and exists.status:
                raise AppException(f"Mail configuration already exists for intent [{intent}]")
            elif exists and not exists.status:
                exists.update(
                    entities=entities,
                    subjects=subjects,
                    classification_prompt=classification_prompt,
                    reply_template=reply_template,
                    timestamp=time.time(),
                    status=True,
                    user=user
                )
                mail_config = exists
            else:
                mail_config = MailClassificationConfig(
                    intent=intent,
                    entities=entities,
                    subjects=subjects,
                    classification_prompt=classification_prompt,
                    reply_template=reply_template,
                    bot=bot,
                    timestamp=time.time(),
                    status=True,
                    user=user
                )
                mail_config.save()

        except Exception as e:
            raise AppException(str(e))

        return mail_config

    @staticmethod
    def get_docs(bot: str):
        try:
            objs =  MailClassificationConfig.objects(bot=bot, status=True)
            return_data = []
            for obj in objs:
                data = obj.to_mongo().to_dict()
                data.pop('_id')
                data.pop('timestamp')
                data.pop('status')
                data.pop('user')
                return_data.append(data)
            return return_data
        except Exception as e:
            raise AppException(str(e))

    @staticmethod
    def get_doc(bot: str, intent: str):
        try:
            obj = MailClassificationConfig.objects(bot=bot, intent=intent, status=True).first()
            if not obj:
                raise AppException(f"Mail configuration does not exist for intent [{intent}]")
            data = obj.to_mongo().to_dict()
            data.pop('_id')
            data.pop('timestamp')
            data.pop('status')
            data.pop('user')
            return data
        except Exception as e:
            raise AppException(str(e))


    @staticmethod
    def delete_doc(bot: str, intent: str):
        try:
            MailClassificationConfig.objects(bot=bot, intent=intent).delete()
        except Exception as e:
            raise AppException(str(e))

    @staticmethod
    def soft_delete_doc(bot: str, intent: str):
        try:
            MailClassificationConfig.objects(bot=bot, intent=intent).update(status=False)
        except Exception as e:
            raise AppException(str(e))

    @staticmethod
    def update_doc(bot: str, intent: str, **kwargs):
        keys = ['entities', 'subjects', 'classification_prompt', 'reply_template']
        for key in kwargs.keys():
            if key not in keys:
                raise AppException(f"Invalid  key [{key}] provided for updating mail config")
        try:
            MailClassificationConfig.objects(bot=bot, intent=intent).update(**kwargs)
        except Exception as e:
            raise AppException(str(e))





