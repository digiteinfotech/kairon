import csv
import os
from typing import Text, List

from kairon import Utility
from kairon.shared.content_importer.content_processor import ContentImporterLogProcessor
from kairon.shared.data.processor import MongoProcessor


class ContentImporter:
    """
    Class to import document content into kairon. A validation is run over content
    before initiating the import process.
    """
    processor = MongoProcessor()

    def __init__(self, path: Text, bot: Text, user: Text, file_received: Text, table_name: Text, overwrite: bool = True):
        """Initialize content importer"""

        self.path = path
        self.bot = bot
        self.user = user
        self.file_received = file_received
        self.table_name = table_name
        self.overwrite = overwrite
        self.data = []

    def validate(self):
        """
        Validates the document content
        Returns a summary of the validation results and number of rows in original csv.
        """
        file_path = os.path.join(self.path, self.file_received)
        def csv_to_dict_list(csv_file_path: str) -> List[dict]:
            with open(csv_file_path, mode='r') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                data = []
                for row in csv_reader:
                    row = {key.lower(): value for key, value in row.items()}
                    row.pop('kairon_error_description', None)
                    data.append(row)
                return data

        column_dict = MongoProcessor().get_column_datatype_dict(self.bot, self.table_name)
        self.data = csv_to_dict_list(file_path)
        original_row_count = len(self.data)

        summary = ContentImporter.processor.validate_doc_content(column_dict= column_dict, doc_content= self.data)
        if summary:
            summary_dir = os.path.join('content_upload_summary', self.bot)
            Utility.make_dirs(summary_dir)
            event_id = ContentImporterLogProcessor.get_event_id_for_latest_event(self.bot)
            summary_file_path = os.path.join(summary_dir, f'failed_rows_with_errors_{event_id}.csv')

            headers = list(self.data[0].keys()) + ['kairon_error_description']

            with open(summary_file_path, mode='w', newline='') as file:
                csv_writer = csv.DictWriter(file, fieldnames=headers)
                csv_writer.writeheader()
                failed_row_indices = []
                for row_number, error_list in summary.items():
                    row_index = int(row_number.split()[-1]) - 2
                    failed_row_indices.append(row_index)
                    failed_row = self.data[row_index]

                    error_description = "; ".join([f"{error['column_name']}: {error['status']}" for error in error_list])

                    failed_row_with_error = {**failed_row, 'kairon_error_description': error_description}
                    csv_writer.writerow(failed_row_with_error)

                for index in sorted(failed_row_indices, reverse=True):
                    self.data.pop(index)

        return original_row_count, summary

    def import_data(self):
        """
        Saves document content into the database.
        """
        if self.data:
            MongoProcessor().save_doc_content(self.bot, self.user, self.data, self.table_name, self.overwrite)



