from mongoengine import Document, DynamicField, StringField, FloatField, DateTimeField, DictField


class LLMLogs(Document):
    response = DynamicField()
    start_time = DateTimeField()
    end_time = DateTimeField()
    cost = FloatField()
    llm_call_id = StringField()
    llm_provider = StringField()
    model = StringField()
    model_params = DictField()
    metadata = DictField()
    llm_usage = DictField()