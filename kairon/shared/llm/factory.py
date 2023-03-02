from typing import Text
from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from kairon.shared.llm.gpt3 import GPT3FAQEmbedding

class LLMFactory:
    __implementations = {
        "GPT3_FAQ_EMBED": GPT3FAQEmbedding
    }

    @staticmethod
    def get_instance(bot_id: Text, _type: Text):
        llm_type = Utility.environment['llm'][_type]
        if not LLMFactory.__implementations.get(llm_type):
            raise AppException(f'{llm_type} type LLM is not supported')
        return LLMFactory.__implementations[llm_type](bot_id)
