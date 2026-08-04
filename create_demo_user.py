import os
import sys
import argparse

# Ensure Kairon codebase directory is in path
KAIRON_DIR = "/home/geet_more/Desktop/kairon"
if os.path.exists(KAIRON_DIR):
    os.chdir(KAIRON_DIR)
    sys.path.insert(0, KAIRON_DIR)

from kairon.shared.utils import Utility
from mongoengine import connect, disconnect
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.account.data_objects import User, Account, BotAccess
from kairon.shared.data.data_objects import BotSettings

# Bypass strict schema validation during script updates
BotSettings._meta['strict'] = False


def create_user_and_bot(email: str, password: str, bot_name: str):
    """
    Provisions a new Kairon user account and bot instance, ensuring
    that enable_crm is set to False so it can be manually enabled via Streamlit.
    """
    # 1. Connect to MongoDB
    disconnect()
    Utility.load_environment()
    config = Utility.mongoengine_connection(Utility.environment['database']['url'])
    connect(**config)

    # 2. Check or Create Account & User
    user_obj = User.objects(email=email).first()
    if not user_obj:
        account_name = f"Account_{email.split('@')[0]}"
        acc_doc = Account.objects(name=account_name).first()
        if acc_doc:
            account_id = acc_doc.account
        else:
            acc_res = AccountProcessor.add_account(account_name, email)
            account_id = acc_res.get("_id") if isinstance(acc_res, dict) else acc_res

        AccountProcessor.add_user(
            email=email,
            password=password,
            first_name=email.split("@")[0].capitalize(),
            last_name="User",
            account=account_id,
            user=email
        )
        user_obj = User.objects(email=email).first()

    # Enable user & save password hash
    user_obj.password = Utility.get_password_hash(password)
    user_obj.status = True
    user_obj.is_confirmed = True
    user_obj.save()

    # 3. Check or Create Bot
    existing_access = BotAccess.objects(user=email).first()
    if existing_access:
        bot_id = str(existing_access.bot)
    else:
        bot_res = AccountProcessor.add_bot(
            name=bot_name,
            account=user_obj.account,
            user=user_obj.email
        )
        if isinstance(bot_res, dict):
            bot_id = str(bot_res.get("_id"))
        else:
            bot_id = str(bot_res)

    # 4. Set BotSettings enable_crm = False
    settings = BotSettings.objects(bot=str(bot_id)).first()
    if settings:
        settings.update(set__enable_crm=False)
    else:
        BotSettings(bot=str(bot_id), user=email, enable_crm=False).save()

    # 5. Retrieve enable_crm directly from MongoDB database for verification
    db_settings = BotSettings.objects(bot=str(bot_id)).first()
    db_enable_crm = db_settings.enable_crm if db_settings else False

    print("\n=======================================================")
    print("      PROVISIONED DEMO USER & BOT SUCCESSFULLY         ")
    print("=======================================================")
    print(f" User Email       : {email}")
    print(f" Password         : {password}")
    print(f" Bot Name         : {bot_name}")
    print(f" Bot ID           : {bot_id}")
    print(f" DB enable_crm    : {db_enable_crm}")
    print("=======================================================\n")
    print("You can now log into Streamlit with these credentials and enable CRM!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create Kairon User and Bot with enable_crm = False")
    parser.add_argument("--email", type=str, help="User email address")
    parser.add_argument("--password", type=str, help="User password")
    parser.add_argument("--bot-name", type=str, help="Bot name")

    args = parser.parse_args()

    email = args.email or input("Enter Email: ").strip()
    while not email:
        email = input("Email cannot be empty. Enter Email: ").strip()

    password = args.password or input("Enter Password: ").strip()
    while not password:
        password = input("Password cannot be empty. Enter Password: ").strip()

    bot_name = args.bot_name or input("Enter Bot Name: ").strip()
    while not bot_name:
        bot_name = input("Bot Name cannot be empty. Enter Bot Name: ").strip()

    create_user_and_bot(email, password, bot_name)
