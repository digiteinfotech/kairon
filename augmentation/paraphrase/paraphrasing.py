import torch
from transformers import PegasusForConditionalGeneration, PegasusTokenizer


class ParaPhrasing:

    """Class loads pegasus model for text augmentation"""
    model_name = 'tuner007/pegasus_paraphrase'
    torch_device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tokenizer = PegasusTokenizer.from_pretrained(model_name)
    model = PegasusForConditionalGeneration.from_pretrained(model_name).to(torch_device)

    @staticmethod
    def paraphrases(input_text, num_return_sequences=10, num_beams=20):
        """
        generates variations for
        a given sentence/text

        :param input_text: sentence or text
        :param num_return_sequences: Number of variations to be returned
        :param num_beams: Number of beams for beam search. 1 means no beam search
        :return: list of variations of the input text
        """
        if isinstance(input_text, str):
            input_text = [input_text]
        batch = ParaPhrasing.tokenizer.prepare_seq2seq_batch(input_text, truncation=True, padding='longest',
                                                             max_length=60, return_tensors="pt").to(
            ParaPhrasing.torch_device)
        translated = ParaPhrasing.model.generate(**batch, max_length=60, num_beams=num_beams,
                                                 num_return_sequences=num_return_sequences, top_k=90)
        tgt_text = ParaPhrasing.tokenizer.batch_decode(translated, skip_special_tokens=True)
        return list(set(tgt_text))
