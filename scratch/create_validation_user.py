import asyncio
from kairon.shared.utils import Utility
from kairon.shared.account.processor import AccountProcessor
from pydantic import SecretStr
from mongoengine import connect

async def main():
    connect('conversations', host='mongodb://localhost:27017/conversations')
    Utility.load_environment()
    
    email = "final_test@kairon.ai"
    password = "Password@123"
    
    # 1. Cleanup existing user if any to make it truly fresh
    try:
        from kairon.shared.account.data_objects import User as MongoUser
        MongoUser.objects(email=email).delete()
        print("Cleaned up existing user 'final_test@kairon.ai' to ensure fresh creation.")
    except Exception as e:
        print("Cleanup user error:", e)
        
    import time
    # 2. Setup the fresh account
    account_setup = {
        "account": f"ValAcc{int(time.time())}",
        "email": email,
        "first_name": "Validation",
        "last_name": "User",
        "password": SecretStr(password)
    }
    user_details, mail_to, link = await AccountProcessor.account_setup(account_setup)
    print("Created User details:", user_details)
    account_id = user_details["account"]

    # 3. Create the bot
    bot_id = AccountProcessor.add_bot(
        name="FinalBot",
        account=int(account_id),
        user=email,
        is_new_account=False,
        add_default_data=False
    )
    print(f"Bot 'FinalBot' created successfully with ID: {bot_id}")
    
    # 4. Set active bot on user
    MongoUser._get_collection().update_one({"email": email}, {"$set": {"active_bot": str(bot_id)}})
    print("Updated active_bot for user.")
    
    # 5. Reset bot settings
    from kairon.shared.data.data_objects import BotSettings
    BotSettings.objects(bot=bot_id).delete()
    print("CRM successfully disabled/reset for the new bot.")

if __name__ == "__main__":
    asyncio.run(main())
