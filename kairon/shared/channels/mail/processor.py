import asyncio
import time

from loguru import logger
from pydantic.schema import timedelta
from pydantic.validators import datetime
from imap_tools import MailBox, AND, OR, NOT

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.account.data_objects import Bot
from kairon.shared.channels.mail.constants import MailConstants
from kairon.shared.channels.mail.data_objects import MailResponseLog, MailStatus, MailChannelStateData
from kairon.shared.chat.agent.agent_flow import AgenticFlow
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import ChannelTypes
from kairon.shared.data.data_objects import BotSettings
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib



class MailProcessor:
    def __init__(self, bot):
        self.bot = bot
        self.config = ChatDataProcessor.get_channel_config(ChannelTypes.MAIL, bot, False)['config']
        self.intent = self.config.get('intent')
        if not self.intent:
            self.intent = self.config.get('flowname')
        self.mail_template = self.config.get('mail_template')
        if not self.mail_template or len(self.mail_template) == 0:
            self.mail_template = MailConstants.DEFAULT_TEMPLATE
        self.bot_settings = BotSettings.objects(bot=self.bot).get()
        self.state = MailProcessor.get_mail_channel_state_data(bot)
        bot_info = Bot.objects.get(id=bot)
        self.account = bot_info.account
        self.mailbox = None
        self.smtp = None

    def update_event_id(self, event_id):
        self.state.event_id = event_id
        self.state.save()


    @staticmethod
    def get_mail_channel_state_data(bot:str):
        """
        Get mail channel state data
        """
        try:
            state = MailChannelStateData.objects(bot=bot).first()
            if not state:
                state = MailChannelStateData(bot=bot)
                state.save()
            return state
        except Exception as e:
            raise AppException(str(e))

    @staticmethod
    def check_email_config_exists(bot: str, config_dict: dict) -> bool:
        """
        Check if email configuration already exists
        :param bot: str - bot id
        :param config_dict: dict - email configuration
        :return status: bool True if configuration exists, False otherwise
        """
        configs = ChatDataProcessor.get_all_channel_configs(ChannelTypes.MAIL, False)
        email_account = config_dict['email_account']
        for config in configs:
            if config['bot'] != bot and config['config']['email_account'] == email_account:
                subjects1 = Utility.string_to_list(config['config'].get('subjects', ''))
                subjects2 = Utility.string_to_list(config_dict.get('subjects', ''))
                if (not subjects1) and (not subjects2):
                    return True
                if len(set(subjects1).intersection(set(subjects2))) > 0:
                    return True

        return False

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


    @staticmethod
    def validate_smtp_connection(bot):
        try:
            mp = MailProcessor(bot)
            mp.login_smtp()
            mp.logout_smtp()
            return True
        except Exception as e:
            logger.error(str(e))
            return False

    @staticmethod
    def validate_imap_connection(bot):
        try:
            mp = MailProcessor(bot)
            mp.login_imap()
            mp.logout_imap()
            return True
        except Exception as e:
            logger.error(str(e))
            return False

    async def send_mail(self, to: str, subject: str, body: str, log_id: str):
        """
        Send mail to a user
        :param to: str - email address
        :param subject: str - email subject
        :param body: str - email body
        :param log_id: str - log id
        """
        exception = None
        try:
            if body and len(body) > 0:
                email_account = self.config['email_account']
                msg = MIMEMultipart()
                msg['From'] = email_account
                msg['To'] = to
                msg['Subject'] = subject
                msg.attach(MIMEText(body, 'html'))
                self.smtp.sendmail(email_account, to, msg.as_string())
        except Exception as e:
            logger.error(f"Error sending mail to {to}: {str(e)}")
            exception = str(e)
        finally:
            mail_log = MailResponseLog.objects.get(id=log_id)
            mail_log.status = MailStatus.FAILED.value if exception else MailStatus.SUCCESS.value
            if exception:
                mail_log.responses.append(exception)
            mail_log.save()

    def process_mail(self, rasa_chat_response: dict, log_id: str) -> str:
        """
        Process mail response from Rasa and return formatted mail
        :param rasa_chat_response: dict - Rasa chat response
        :param log_id: str - log id
        :return: str - formatted mail
        """

        slots = rasa_chat_response.get('slots', {})


        responses = '<br/><br/>'.join(response.get('text', '') for response in rasa_chat_response.get('response', []))
        if len(responses) == 0:
            return ''
        slots['bot_response'] = responses
        mail_template = self.mail_template
        mail_log = MailResponseLog.objects.get(id=log_id)
        mail_log.responses = rasa_chat_response.get('response', [])
        mail_log.slots = slots
        mail_log.save()
        return mail_template.format(**{key: str(value) for key, value in slots.items()})


    @staticmethod
    def get_log(bot_id: str, offset: int, limit: int) -> dict:
        """
        Get logs for a bot
        :param bot_id: str - bot id
        :param offset: int - offset
        :param limit: int - limit
        :return: dict - logs and count
        """
        try:
            count = MailResponseLog.objects(bot=bot_id).count()
            logs = MailResponseLog.objects(bot=bot_id).order_by('-timestamp').skip(offset).limit(limit)
            result = []
            for log in logs:
                log = log.to_mongo().to_dict()
                log.pop('_id')
                log.pop('bot')
                log.pop('user')
                result.append(log)
            return {
                "logs": result,
                "count": count
            }
        except Exception as e:
            raise AppException(str(e))

    @staticmethod
    async def process_messages(bot: str, batch: [dict]):
        """
        Pass messages to bot and send responses
        """
        try:
            flow = AgenticFlow(bot)
            mp = MailProcessor(bot)
            user_messages: [str] = []
            users: [str] = []
            responses = []
            for mail in batch:
                try:
                    entities = {
                        'mail_id': mail['mail_id'],
                        'subject': mail['subject'],
                        'date': mail['date'],
                        'body': mail['body']
                    }
                    user_msg = mp.intent
                    user_messages.append(user_msg)
                    users.append(mail['mail_id'])
                    subject = mail.get('subject', 'Reply')
                    if not subject.startswith('Re:'):
                        subject = f"Re: {subject}"

                    resp, errors = await flow.execute_rule(user_msg, sender_id=mail['mail_id'], slot_vals=entities)
                    chat_response = {
                        'response': resp,
                        'slots': flow.get_non_empty_slots(True)
                    }
                    if errors:
                        raise AppException(f"Failed to execute flow {user_msg}. Errors: {errors}")
                    responses.append({
                        'to': mail['mail_id'],
                        'subject': subject,
                        'body': mp.process_mail(chat_response, log_id=mail['log_id']),
                        'log_id': mail['log_id']
                    })

                except AppException as e:
                    logger.error(str(e))
                except Exception as e:
                    logger.error(str(e))

            mp.login_smtp()
            tasks = [mp.send_mail(**response) for response in responses]
            await asyncio.gather(*tasks)
            mp.logout_smtp()

        except Exception as e:
            raise AppException(str(e))


    @staticmethod
    def process_message_task(bot: str, message_batch: [dict]):
        """
        Process a batch of messages
        used for execution by executor
        """
        asyncio.run(MailProcessor.process_messages(bot, message_batch))

    def generate_criteria(self, subjects=None, ignore_subjects=None, from_addresses=None, ignore_from=None,
                          read_status="all"):
        """
        Generate IMAP criteria for fetching emails.

        Args:
            subjects (list[str], optional): List of subjects to include.
            ignore_subjects (list[str], optional): List of subjects to exclude.
            from_addresses (list[str], optional): List of senders to include.
            ignore_from (list[str], optional): List of senders to exclude.
            read_status (str): Read status filter ('all', 'seen', 'unseen').

        Returns:
            imap_tools.query.AND: IMAP criteria object.
        """
        criteria = []

        if read_status.lower() == "seen":
            criteria.append(AND(seen=True))
        elif read_status.lower() == "unseen":
            criteria.append(AND(seen=False))

        if subjects:
            criteria.append(OR(subject=subjects))

        if ignore_subjects:
            for subject in ignore_subjects:
                criteria.append(NOT(AND(subject=subject)))

        if from_addresses:
            criteria.append(OR(from_=from_addresses))

        if ignore_from:
            for sender in ignore_from:
                criteria.append(NOT(AND(from_=sender)))

        last_processed_uid = self.state.last_email_uid
        base_read_criteria = None
        if last_processed_uid == 0:
            time_shift = int(self.config.get('interval', 20 * 60))
            last_read_timestamp = datetime.now() - timedelta(seconds=time_shift)
            base_read_criteria = AND(date_gte=last_read_timestamp.date())
        else:
            query = f'{int(last_processed_uid) + 1}:*'
            base_read_criteria = AND(uid=query)

        criteria.append(base_read_criteria)

        # Combine all criteria with AND
        return AND(*criteria)


    @staticmethod
    def read_mails(bot: str) -> ([dict], str):
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
            - log_id
        - user
        - time_shift

        """
        logger.info(f"reading mails for {bot}")
        mp = MailProcessor(bot)
        messages = []
        is_logged_in = False
        last_processed_uid = mp.state.last_email_uid
        try:
            mp.login_imap()
            is_logged_in = True
            subject = mp.config.get('subjects', "")
            subject = Utility.string_to_list(subject)
            ignore_subject = mp.config.get('ignore_subjects', "")
            ignore_subject = Utility.string_to_list(ignore_subject)
            from_addresses = mp.config.get('from_emails', "")
            from_addresses = Utility.string_to_list(from_addresses)
            ignore_from = mp.config.get('ignore_from_emails', "")
            ignore_from = Utility.string_to_list(ignore_from)
            read_status = mp.config.get('seen_status', 'all')
            criteria = mp.generate_criteria(subject, ignore_subject, from_addresses, ignore_from, read_status)
            for msg in mp.mailbox.fetch(criteria, mark_seen=False):
                if int(msg.uid) <= last_processed_uid:
                    continue
                last_processed_uid = int(msg.uid)
                subject = msg.subject
                sender_id = msg.from_
                date = msg.date
                body = msg.text or msg.html or ""
                #attachments = msg.attachments
                mail_log = MailResponseLog(sender_id = sender_id,
                                            uid = last_processed_uid,
                                            bot = bot,
                                            user = mp.bot_settings.user,
                                            status=MailStatus.Processing.value,
                                            timestamp = time.time())
                mail_log.save()
                message_entry = {
                    'mail_id': sender_id,
                    'subject': subject,
                    'date': str(date),
                    'body': body,
                    'log_id': str(mail_log.id)
                }
                messages.append(message_entry)
            mp.logout_imap()

            mp.state.last_email_uid = last_processed_uid
            mp.state.save()

            is_logged_in = False
            return messages, mp.bot_settings.user
        except Exception as e:
            logger.exception(e)
            if is_logged_in:
                mp.logout_imap()
            return [], mp.bot_settings.user


