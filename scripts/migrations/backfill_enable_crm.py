import os
import sys
import logging
from mongoengine import connect

# Ensure the root of the project is in the path to import kairon modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from kairon.shared.utils import Utility
from kairon.shared.data.data_objects import BotSettings

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_migration():
    logger.info("Starting backfill migration for 'enable_crm' in bot_settings...")
    
    try:
        # Load environment configuration
        Utility.load_environment()
        
        # Establish MongoDB connection using the existing utility
        config = Utility.mongoengine_connection(Utility.environment['database']["url"])
        connect(**config)
        
        # Get the underlying PyMongo collection for raw operations
        collection = BotSettings._get_collection()
        
        # We want to find documents where 'enable_crm' does NOT exist
        query = {"enable_crm": {"$exists": False}}
        
        # Count how many need updating
        total_docs = collection.count_documents({})
        docs_to_update = collection.count_documents(query)
        docs_skipped = total_docs - docs_to_update
        
        logger.info(f"Total documents in bot_settings: {total_docs}")
        logger.info(f"Documents already having 'enable_crm' (skipped): {docs_skipped}")
        logger.info(f"Documents to update: {docs_to_update}")
        
        if docs_to_update > 0:
            # Perform bulk update for efficiency and safety
            result = collection.update_many(
                query,
                {"$set": {"enable_crm": False}}
            )
            logger.info(f"Successfully updated {result.modified_count} documents.")
        else:
            logger.info("No documents required updating. Migration is complete.")
            
    except Exception as e:
        logger.error(f"Migration failed during execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
