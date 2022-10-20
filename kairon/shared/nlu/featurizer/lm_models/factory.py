from kairon.shared.nlu.featurizer.lm_models.transformers.bert import BertModel
from kairon.shared.nlu.featurizer.lm_models.transformers.distilbert import DistilBertModel
from kairon.shared.nlu.featurizer.lm_models.transformers.xlm_roberta import XLMRobertaModel
from kairon.shared.nlu.featurizer.lm_models.transformers.roberta import RobertaModel


class ModelFactory:

    models = {
        "bert": BertModel,
        "distilbert": DistilBertModel,
        "xlm-roberta": XLMRobertaModel,
        "roberta": RobertaModel
    }

    @staticmethod
    def get_instance(model_name: str,
                     model_weights: str,
                     cache_dir: str = None,
                     from_pt: bool = False,
                     local_files: bool = False):
        return ModelFactory.models[model_name](model_weights, cache_dir, from_pt, local_files)