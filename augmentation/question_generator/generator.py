from transformers import T5ForConditionalGeneration, T5TokenizerFast

from augmentation.exception import AugmentationException


class QuestionGenerator:
    """Class loads pipeline for generating questions from text"""

    model = T5ForConditionalGeneration.from_pretrained("ThomasSimonini/t5-end2end-question-generation")
    tokenizer = T5TokenizerFast.from_pretrained("t5-base")
    tokenizer.sep_token = '<sep>'
    tokenizer.add_tokens(['<sep>'])

    @staticmethod
    def generate(text: str):
        """
        This function generate questions given an input string.

        :param text: sentence or text
        :return: list of questions
        """
        if len(text) < 50:
            raise AugmentationException("Input too small")
        generator_args = {'temperature': 1.02, 'num_beams': 1, 'max_length': 70}
        text = "generate questions: " + text + " </s>"
        input_ids = QuestionGenerator.tokenizer.encode(text, return_tensors="pt")
        res = QuestionGenerator.model.generate(input_ids, **generator_args)
        output = QuestionGenerator.tokenizer.batch_decode(res, skip_special_tokens=True)
        output = output[0].split("<sep>")
        if len(output[-1]) == 0 or output[-1][-1] != "?":
            output.pop()
        output = [" ".join(i.split()) for i in output]
        return list(set(output))
