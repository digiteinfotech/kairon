import asyncio
import re

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger
from pydantic.schema import timedelta
from pydantic.validators import datetime
from imap_tools import MailBox, AND
from kairon.exceptions import AppException
from kairon.shared.account.data_objects import Bot
from kairon.shared.channels.mail.constants import MailConstants
from kairon.shared.channels.mail.data_objects import MailClassificationConfig
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import ChannelTypes
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.llm.processor import LLMProcessor
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib



class MailProcessor:
    def __init__(self, bot):
        self.config = ChatDataProcessor.get_channel_config(ChannelTypes.MAIL, bot, False)['config']
        self.llm_type = self.config.get('llm_type', "openai")
        self.hyperparameters = self.config.get('hyperparameters', MailConstants.DEFAULT_HYPERPARAMETERS)
        self.bot = bot
        bot_info = Bot.objects.get(id=bot)
        self.account = bot_info.account
        self.llm_processor = LLMProcessor(self.bot, self.llm_type)
        self.mail_configs = list(MailClassificationConfig.objects(bot=self.bot))
        self.mail_configs_dict = {item.intent: item for item in self.mail_configs}
        self.bot_settings = BotSettings.objects(bot=self.bot).get()
        self.mailbox = None
        self.smtp = None


    def login_imap(self):
        if self.mailbox:
            return
        email_account = self.config['email_account']
        email_password = self.config['email_password']
        imap_server = self.config.get('imap_server', MailConstants.DEFAULT_IMAP_SERVER)
        self.mailbox = MailBox(imap_server).login(email_account, email_password)

    def logout_imap(self):
        if self.mailbox:
            self.mailbox.logout()
            self.mailbox = None

    def login_smtp(self):
        if self.smtp:
            return
        email_account = self.config['email_account']
        email_password = self.config['email_password']
        smtp_server = self.config.get('smtp_server', MailConstants.DEFAULT_SMTP_SERVER)
        smtp_port = self.config.get('smtp_port', MailConstants.DEFAULT_SMTP_PORT)
        smtp_port = int(smtp_port)
        self.smtp = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
        self.smtp.starttls()
        self.smtp.login(email_account, email_password)

    def logout_smtp(self):
        if self.smtp:
            self.smtp.quit()
            self.smtp = None

    async def send_mail(self, to: str, subject: str, body: str):
        try:
            email_account = self.config['email_account']
            msg = MIMEMultipart()
            msg['From'] = email_account
            msg['To'] = to
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'html'))
            self.smtp.sendmail(email_account, to, msg.as_string())
        except Exception as e:
            logger.error(f"Error sending mail to {to}: {str(e)}")

    def process_mail(self, intent: str, rasa_chat_response: dict):
        slots = rasa_chat_response.get('slots', [])
        slots = {key.strip(): value.strip() for slot_str in slots
                    for split_result in [slot_str.split(":", 1)]
                    if len(split_result) == 2
                    for key, value in [split_result]}


        responses = '<br/><br/>'.join(response.get('text', '') for response in rasa_chat_response.get('response', []))
        slots['bot_response'] = responses
        mail_template = self.mail_configs_dict.get(intent, None)
        if mail_template and mail_template.reply_template:
            mail_template = mail_template.reply_template
        else:
            mail_template = MailConstants.DEFAULT_TEMPLATE

        return mail_template.format(**{key: str(value) for key, value in slots.items()})

    async def classify_messages(self, messages: [dict]) -> [dict]:
        if self.bot_settings.llm_settings['enable_faq']:
            try:
                system_prompt = self.config.get('system_prompt', MailConstants.DEFAULT_SYSTEM_PROMPT)
                system_prompt += '\n return json format: [{"intent": "intent_name", "entities": {"entity_name": "value"}, "mail_id": "mail_id", "subject": "subject"}], if not classifiable set intent and not-found entity values as null'
                context_prompt = self.get_context_prompt()
                messages = json.dumps(messages)
                info = await self.llm_processor.predict(messages,
                                                        self.bot_settings.user,
                                                        system_prompt=system_prompt,
                                                        context_prompt=context_prompt,
                                                        similarity_prompt=[],
                                                        hyperparameters=self.hyperparameters)
                classifications = MailProcessor.extract_jsons_from_text(info["content"])[0]
                return classifications
            except Exception as e:
                logger.error(str(e))
                raise AppException(str(e))


    @staticmethod
    async def process_messages(bot: str, batch: [dict]):
        """
        classify and respond to a batch of messages
        """
        try:
            from kairon.chat.utils import ChatUtils
            mp = MailProcessor(bot)
            classifications = await mp.classify_messages(batch)
            user_messages: [str] = []
            responses = []
            intents = []
            for classification in classifications:
                try:
                    intent = classification['intent']
                    if not intent or intent == 'null':
                        continue
                    entities = classification['entities']
                    sender_id = classification['mail_id']
                    subject = f"{classification['subject']}"

                    # mail_id is in the format "name <email>" or "email"
                    if '<' in sender_id:
                        sender_id = sender_id.split('<')[1].split('>')[0]

                    entities_str = ', '.join([f'"{key}": "{value}"' for key, value in entities.items() if value and value != 'null'])
                    user_msg = f'/{intent}{{{entities_str}}}'
                    logger.info(user_msg)

                    user_messages.append(user_msg)
                    responses.append({
                        'to': sender_id,
                        'subject': subject,
                    })
                    intents.append(intent)
                except Exception as e:
                    logger.exception(e)
            logger.info(responses)

            chat_responses = await ChatUtils.process_messages_via_bot(user_messages,
                                                                mp.account,
                                                                bot,
                                                                mp.bot_settings.user,
                                                                False,
                                                                {
                                                                    'channel': ChannelTypes.MAIL.value
                                                                })
            logger.info(chat_responses)

            for index, response in enumerate(chat_responses):
                responses[index]['body'] = mp.process_mail(intents[index], response)

            mp.login_smtp()
            tasks = [mp.send_mail(**response) for response in responses]
            await asyncio.gather(*tasks)
            mp.logout_smtp()

        except Exception as e:
            raise AppException(str(e))

    def get_context_prompt(self) -> str:
        context_prompt = ""
        for item in self.mail_configs:
            context_prompt += f"intent: {item['intent']} \n"
            context_prompt += f"entities: {item['entities']} \n"
            context_prompt += "\nclassification criteria: \n"
            context_prompt += f"subjects: {item['subjects']} \n"
            context_prompt += f"rule: {item['classification_prompt']} \n"
            context_prompt += "\n\n"
        return context_prompt


    @staticmethod
    def process_message_task(bot: str, message_batch: [dict]):
        """
        Process a batch of messages
        used for execution by executor
        """
        asyncio.run(MailProcessor.process_messages(bot, message_batch))


    @staticmethod
    def read_mails(bot: str) -> ([dict], str, int):
        """
        Read mails from the mailbox
        Parameters:
        - bot: str - bot id
        Returns:
        - list of messages - each message is a dict with the following
            - mail_id
            - subject
            - date
            - body
        - user
        - time_shift

        """
        mp = MailProcessor(bot)
        time_shift = int(mp.config.get('interval', 20 * 60))
        last_read_timestamp = datetime.now() - timedelta(seconds=time_shift)
        messages = []
        is_logged_in = False
        try:
            mp.login_imap()
            is_logged_in = True
            msgs = mp.mailbox.fetch(AND(seen=False, date_gte=last_read_timestamp.date()))
            for msg in msgs:
                subject = msg.subject
                sender_id = msg.from_
                date = msg.date
                body = msg.text or msg.html or ""
                logger.info(subject, sender_id, date)
                message_entry = {
                    'mail_id': sender_id,
                    'subject': subject,
                    'date': str(date),
                    'body': body
                }
                messages.append(message_entry)
            mp.logout_imap()
            is_logged_in = False
            return messages, mp.bot_settings.user, time_shift
        except Exception as e:
            logger.exception(e)
            if is_logged_in:
                mp.logout_imap()
            return [], mp.bot_settings.user, time_shift

    @staticmethod
    def extract_jsons_from_text(text) -> list:
        """
        Extract json objects from text as a list
        """
        json_pattern = re.compile(r'(\{.*?\}|\[.*?\])', re.DOTALL)
        jsons = []
        for match in json_pattern.findall(text):
            try:
                json_obj = json.loads(match)
                jsons.append(json_obj)
            except json.JSONDecodeError:
                continue
        return jsons
