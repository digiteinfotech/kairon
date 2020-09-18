import torch
from transformers import PegasusForConditionalGeneration, PegasusTokenizer


class ParaPhrasing:
    model_name = 'tuner007/pegasus_paraphrase'
    torch_device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tokenizer = PegasusTokenizer.from_pretrained(model_name)
    model = PegasusForConditionalGeneration.from_pretrained(model_name).to(torch_device)

    @staticmethod
    def paraphrases(input_text, num_return_sequences=10, num_beams=10):
        batch = ParaPhrasing.tokenizer.prepare_seq2seq_batch([input_text], truncation=True, padding='longest',
                                                             max_length=60).to(
            ParaPhrasing.torch_device)
        translated = ParaPhrasing.model.generate(**batch, max_length=60, num_beams=num_beams,
                                                 num_return_sequences=num_return_sequences, temperature=1.5)
        tgt_text = ParaPhrasing.tokenizer.batch_decode(translated, skip_special_tokens=True)
        return tgt_text
