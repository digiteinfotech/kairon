from loguru import logger

from .utility import TrainingDataGeneratorUtil
from ..document_parser import DocumentParser
from ..training_data_generator import TrainingDataGenerator


# file deepcode ignore W0703: Any Exception should be updated as status for Training Data processor
def parse_document_and_generate_training_data(kairon_url: str, user: str, token: str):
    """
    Function to parse pdf or docx documents and retrieve intents, responses and training examples from it

    :param kairon_url: http url to access kairon APIs
    :param user: user id
    :param token: token for user authentication
    :return: None
    """
    try:
        status = {"status": "In progress"}
        logger.debug("setting status in progress")
        TrainingDataGeneratorUtil.set_training_data_status(kairon_url, status, user, token)
        logger.debug("fetch kg status")
        kg_info = TrainingDataGeneratorUtil.fetch_latest_data_generator_status(kairon_url, user, token)
        logger.debug(kg_info)
        if kg_info is None or kg_info.get('document_path') is None:
            raise Exception("Document not found!")
        doc_path = kg_info['document_path']
        logger.debug("starting parsing")
        doc_structure, sentences = DocumentParser.parse(doc_path)
        logger.debug("generating intent")
        training_data = TrainingDataGenerator.generate_intent(doc_structure, sentences)
        status = {
            "status": "Completed",
            "response": training_data
        }
        logger.debug("set training data status")
        TrainingDataGeneratorUtil.set_training_data_status(kairon_url, status, user, token)
    except Exception as e:
        logger.debug("set training data status: "+str(e))
        status = {
            "status": "Fail",
            "exception": str(e)
        }
        TrainingDataGeneratorUtil.set_training_data_status(kairon_url, status, user, token)
