from typing import Text
import os
import pandas as pd
from bson import json_util
import json

from kairon.shared.data.collection_processor import DataProcessor


class FileImporter:

    def __init__(self, path: Text, bot: Text, user: Text, file_received: Text, collection_name : Text, overwrite: bool = True):

        """Initialize file importer"""

        self.path = path
        self.bot = bot
        self.user = user
        self.file_received = file_received
        self.overwrite = overwrite
        self.collection_name=collection_name

    def validate(self):
        pass

    def preprocess(self):
        file_path = os.path.join(self.path, self.file_received)

        try:
            df = pd.read_csv(file_path)
            df.columns = df.columns.str.strip()
            df = df.astype(object).where(pd.notna(df), None)

            records = df.to_dict(orient="records")
            normalized_records = json.loads(json_util.dumps(records))

            data = []
            for record in normalized_records:
                data.append({
                    "is_secure": [],
                    "is_non_editable": [],
                    "data": record
                })

        except pd.errors.EmptyDataError:
            raise ValueError("CSV file is empty")
        except UnicodeDecodeError as e:
            raise ValueError(f"File encoding error. Please ensure the file is UTF-8 encoded: {str(e)}")

        if not data:
            raise ValueError("CSV file is empty or contains no valid data")

        return {"payload": data}


    def import_data(self, collections_data):
        if collections_data:
            DataProcessor.save_bulk_collection_data(
                payloads=[collection for collection in collections_data["payload"]],
                user=self.user,
                bot=self.bot,
                collection_name=self.collection_name
            )


