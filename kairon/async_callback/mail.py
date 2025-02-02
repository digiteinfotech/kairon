from email.mime.multipart import MIMEMultipart


from email.mime.text import MIMEText
from typing import Text, List
import boto3
from pymongo import MongoClient
import os
from smtplib import SMTP

from kairon import Utility

ssm = boto3.client('ssm')
# client = MongoClient(
#     ssm.get_parameter(Name=os.getenv('DATABASE_URL'), WithDecryption=True).get('Parameter', {}).get('Value'))
# platform_db = client.get_database()

database_url = Utility.environment["database"]["url"]
# database_url = "mongodb://localhost:27017/conversations"
client = MongoClient(database_url)
platform_db = client.get_database()

# client = MongoClient("mongodb://localhost:27017/")
# platform_db = client.get_database("conversations")

email_config = platform_db.get_collection("email_action_config")

def send_email(email_action: Text,
               from_email: Text,
               to_email: Text,
               subject:  Text,
               body: Text,
               bot: Text):
    if not bot:
        raise Exception("Missing bot id")

    action_config = email_config.find_one({"bot": bot, 'action_name': email_action})

    smtp_password = action_config.get('smtp_password').get("value")
    smtp_userid = action_config.get('smtp_userid').get("value")

    trigger_email(email=[to_email],
                  subject=subject,
                  body=body,
                  smtp_url=action_config['smtp_url'],
                  smtp_port=action_config['smtp_port'],
                  sender_email=from_email,
                  smtp_password=smtp_password,
                  smtp_userid=smtp_userid,
                  tls=action_config['tls']
                  )

def trigger_email(
        email: List[str],
        subject: str,
        body: str,
        smtp_url: str,
        smtp_port: int,
        sender_email: str,
        smtp_password: str,
        smtp_userid: str = None,
        tls: bool = False,
        content_type="html",
):
    """
    Sends an email to the mail id of the recipient

    :param smtp_userid:
    :param sender_email:
    :param tls:
    :param smtp_port:
    :param smtp_url:
    :param email: the mail id of the recipient
    :param smtp_password:
    :param subject: the subject of the mail
    :param body: the body of the mail
    :param content_type: "plain" or "html" content
    :return: None
    """
    smtp = SMTP(smtp_url, port=smtp_port, timeout=10)
    smtp.connect(smtp_url, smtp_port)
    if tls:
        smtp.starttls()
    smtp.login(smtp_userid if smtp_userid else sender_email, smtp_password)
    from_addr = sender_email
    body = MIMEText(body, content_type)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ",".join(email)
    msg.attach(body)
    smtp.sendmail(from_addr, email, msg.as_string())
    smtp.quit()
