from typing import Text
import os
import csv

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
        data = []
        row_num=0
        try:
            with open(file_path, mode='r', newline='', encoding='utf-8') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                for row_num, row in enumerate(csv_reader, start=1):
                    if not row:
                        continue

                    clean_row = {}
                    for key, value in row.items():
                        norm_key = key.lower().strip() if isinstance(key, str) else key
                        if isinstance(value, str):
                            norm_val = value.strip()
                        elif value is None:
                            norm_val = ""
                        else:
                            norm_val = value
                        clean_row[norm_key] = norm_val


                    data.append({
                        "collection_name": self.collection_name,
                        "is_secure": [],
                        "is_non_editable": [],
                        "data": clean_row
                    })
        except csv.Error as e:
            raise ValueError(f"Error parsing CSV file at line {row_num}: {str(e)}")
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


