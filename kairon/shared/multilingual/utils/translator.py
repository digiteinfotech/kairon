from loguru import logger
from google.cloud import translate_v3 as translate
from google.oauth2 import service_account
from typing import List, Text

from kairon.exceptions import AppException
from kairon.shared.utils import Utility


class Translator:

    """Class containing code for Google Cloud translate"""

    @staticmethod
    def translate_text_bulk(text: List[Text], s_lang: Text, d_lang: Text, mime_type: Text = "text/plain"):
        """
        Translates text in bulk by google cloud api
        :param text: text to translate
        :param s_lang: source language
        :param d_lang: destination language
        :param mime_type: type of document for translation
        :return: translations: translated text
        """
        try:
            service_account_info_json = {
                "type": Utility.environment['multilingual']['service_account_creds'].get('type', "service_account"),
                "project_id": Utility.environment['multilingual']['project_id'],
                "private_key_id": Utility.environment['multilingual']['service_account_creds']['private_key_id'],
                "private_key": Utility.environment['multilingual']['service_account_creds']['private_key'],
                "client_email": Utility.environment['multilingual']['service_account_creds']['client_email'],
                "client_id": Utility.environment['multilingual']['service_account_creds']['client_id'],
                "auth_uri": Utility.environment['multilingual']['service_account_creds']['auth_uri'],
                "token_uri": Utility.environment['multilingual']['service_account_creds']['token_uri'],
                "auth_provider_x509_cert_url": Utility.environment['multilingual']['service_account_creds']['auth_provider_x509_cert_url'],
                "client_x509_cert_url": Utility.environment['multilingual']['service_account_creds']['client_x509_cert_url']
            }
            logger.debug(service_account_info_json)
            credentials = service_account.Credentials.from_service_account_info(service_account_info_json)
            client = translate.TranslationServiceClient(credentials=credentials)

            location = "global"
            parent = f"projects/{Utility.environment['multilingual']['project_id']}/locations/{location}"

            # Translate text from Source Language to Destination Language

            logger.info('Fetching translations...')

            response = client.translate_text(
                request={
                    "parent": parent,
                    "contents": text,
                    "mime_type": mime_type,
                    "source_language_code": s_lang,
                    "target_language_code": d_lang,
                }
            )

            # Display the translation for each input text provided
            translations = []
            for translation in response.translations:
                trans = translation.translated_text
                translations.append(trans)
        except Exception as e:
            logger.exception(e)
            raise AppException(f'Cloud Translation failed with exception: {str(e)}')

        logger.info('Translations completed successfully.')
        return translations

    @staticmethod
    def get_supported_languages():
        multilingual_env = Utility.environment.get('multilingual', {})
        service_account_creds = multilingual_env.get('service_account_creds', {})

        service_account_info_json = {
            "type": service_account_creds.get('type', "service_account"),
            "project_id": multilingual_env.get('project_id'),
            "private_key_id": service_account_creds.get('private_key_id'),
            "private_key": service_account_creds.get('private_key'),
            "client_email": service_account_creds.get('client_email'),
            "client_id": service_account_creds.get('client_id'),
            "auth_uri": service_account_creds.get('auth_uri'),
            "token_uri": service_account_creds.get('token_uri'),
            "auth_provider_x509_cert_url": service_account_creds.get('auth_provider_x509_cert_url'),
            "client_x509_cert_url": service_account_creds.get('client_x509_cert_url')
        }
        logger.debug(service_account_info_json)
        credentials = service_account.Credentials.from_service_account_info(service_account_info_json)
        client = translate.TranslationServiceClient(credentials=credentials)

        location = "global"
        parent = f"projects/{multilingual_env.get('project_id')}/locations/{location}"
        response = client.get_supported_languages(parent=parent, display_language_code="en")
        result = {language.language_code: language.display_name for language in response.languages}
        return result

