from loguru import logger

from .utility import WebsiteTrainingDataGeneratorUtil
from ..utils.website_qna_generator import WebsiteQnAGenerator


# file deepcode ignore W0703: Any Exception should be updated as status for Training Data processor
def parse_website_and_generate_training_data(kairon_url: str, user: str, token: str):
    """Function to parse website and generate QnA data. This function is called from the main file in augmentation folder.
    :param kairon_url: http url to access kairon APIs
    :param user: user id
    :param token: token for user authentication
    :return: None
    """
    try:
        status = {"status": "In progress"}
        logger.debug("setting status in progress")
        WebsiteTrainingDataGeneratorUtil.set_training_data_status(kairon_url, status, user, token)
        logger.debug("fetch kg status")
        kg_info = WebsiteTrainingDataGeneratorUtil.fetch_latest_data_generator_status(kairon_url, user, token)
        logger.debug(kg_info)
        if kg_info is None or kg_info.get('website_url') is None:
            raise Exception("Website not found!")
        elif kg_info is None or kg_info.get('max_pages') is None:
             raise Exception("Please provide maximum number of pages to scrape.")
        website_url = kg_info['website_url']
        max_pages = kg_info['max_pages']
        logger.debug("starting qna generation")
        training_data = WebsiteQnAGenerator.get_qa_data(website_url,max_pages)
        status = {
            "status": "Completed",
            "response": training_data
        }
        logger.debug("set training data status")
        WebsiteTrainingDataGeneratorUtil.set_training_data_status(kairon_url, status, user, token)
    except Exception as e:
        logger.debug("set training data status: "+str(e))
        status = {
            "status": "Fail",
            "exception": str(e)
        }
        WebsiteTrainingDataGeneratorUtil.set_training_data_status(kairon_url, status, user, token)