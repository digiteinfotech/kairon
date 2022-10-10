from transformers import T5ForConditionalGeneration, T5TokenizerFast


class QuestionGenerator:

    """Class loads pipeline for generating questions from text"""
    model = T5ForConditionalGeneration.from_pretrained("mrm8488/t5-base-e2e-question-generation")
    tokenizer = T5TokenizerFast.from_pretrained("mrm8488/t5-base-e2e-question-generation")

    @staticmethod
    def generate(text: str):
        """
        generates questions
        for given text

        :param text: sentence or paragraph for question generation
        :return: list of questions
        """
        try:
            if len(text) < 50:
                raise Exception("input too small")
            generator_args = {'temperature': 1, 'max_length': 100}
            text = "generate questions: " + text + " </s>"
            input_ids = QuestionGenerator.tokenizer.encode(text, return_tensors="pt")
            res = QuestionGenerator.model.generate(input_ids, **generator_args)
            output = QuestionGenerator.tokenizer.batch_decode(res, skip_special_tokens=True)
            return output
        except Exception as ex:
            raise ex
