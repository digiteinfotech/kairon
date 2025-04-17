import asyncio
import base64
import io
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import markdown
from loguru import logger
from fastapi import File
from mongoengine import DoesNotExist
from pathy import ClientError
from uuid6 import uuid7

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.cloud.utils import CloudUtility
from kairon.shared.data.data_objects import UserMediaData


class UserMedia:



    @staticmethod
    def save_media_content(
                bot: str,
                sender_id: str,
                media_id: str,
                binary_data: bytes = None,
                filename: str = None,
                ):

        if not filename:
            raise AppException('filename must be provided for binary data')

        temp_path = tempfile.mkdtemp()
        file_path = os.path.join(temp_path, filename)
        Utility.write_to_file(file_path, binary_data)
        bucket = Utility.environment["storage"]["user_media"].get("bucket")
        root_dir = Utility.environment["storage"]["user_media"].get("root_dir")
        fpath = Path(file_path)
        extension = fpath.suffix
        base_filename = fpath.stem
        filesize = len(binary_data)

        if extension not in Utility.environment["storage"]["user_media"].get(
                "allowed_extensions"
        ):
            raise AppException(
                f'Only {Utility.environment["storage"]["user_media"].get("allowed_extensions")} type files allowed'
            )

        output_filename = os.path.join(root_dir, bot, f"{sender_id}_{base_filename}{extension}")
        try:
            url = CloudUtility.upload_file(file_path, bucket, output_filename)
            user_media_data = UserMediaData(
                media_id=media_id,
                media_url=url,
                filename=filename,
                extension=extension,
                output_filename=output_filename,
                filesize=filesize,
                sender_id=sender_id,
                bot=bot,
                timestamp=datetime.utcnow()
            )
            user_media_data.save()
            logger.info(f"saved {media_id}")
        except ClientError as e:
            logger.exception(e)
            raise AppException("File upload failed")
        except Exception as e:
            logger.exception(e)
            raise AppException("File upload failed")

    @staticmethod
    async def save_media_content_task(
            bot: str,
            sender_id: str,
            media_id: str,
            binary_data: bytes,
            filename: str,
    ):
        await asyncio.to_thread(
            UserMedia.save_media_content,
            bot,
            sender_id,
            media_id,
            binary_data,
            filename
        )

    @staticmethod
    async def upload_media_contents(
            bot: str,
            sender_id: str,
            files: list[File],
    ):
        media_ids = []
        read_tasks = [asyncio.create_task(file.read()) for file in files]
        binary_datas = await asyncio.gather(*read_tasks)

        for file, binary_data in zip(files, binary_datas):
            filename = file.filename
            media_id = uuid7().hex
            media_ids.append(media_id)
            asyncio.create_task(UserMedia.save_media_content_task(
                bot=bot,
                sender_id=sender_id,
                media_id=media_id,
                binary_data=binary_data,
                filename=filename
            ))
        return media_ids


    @staticmethod
    async def get_media_content_buffer(media_id: str, base64_encode: bool = False) -> tuple[BinaryIO|str, str]:
        try:
            media_doc = UserMediaData.objects.get(media_id=media_id)
            media_data = media_doc.to_mongo().to_dict()
            media_data['id'] = str(media_doc.id)
            media_data.pop('bot')
            media_data.pop('sender_id')
            bucket = Utility.environment["storage"]["user_media"].get("bucket")
            file_buffer = CloudUtility.download_file_to_memory(bucket, media_doc.output_filename)
            download_name = f"{media_doc.bot}_{media_doc.sender_id}_{media_doc.filename}{media_doc.extension}"
            if base64_encode:
                file_buffer.seek(0)
                encoded_string = base64.b64encode(file_buffer.read()).decode('utf-8')
                return encoded_string, download_name
            return file_buffer, download_name
        except DoesNotExist:
            raise AppException("Document not found")


    @staticmethod
    def save_markdown_as_pdf(bot: str, sender_id: str, text: str, filepath: str= "report.pdf"):
        from weasyprint import HTML
        if Path(filepath).suffix.lower() != ".pdf":
            raise AppException("Provided filepath must have a .pdf extension")
        html_content: str = markdown.markdown(text)
        pdf_buffer= io.BytesIO()
        HTML(string=html_content).write_pdf(pdf_buffer)
        pdf_buffer.seek(0)
        binary_data =  pdf_buffer.read()
        media_id = uuid7().hex
        UserMedia.save_media_content(
                bot=bot,
                sender_id=sender_id,
                media_id=media_id,
                binary_data=binary_data,
                filename=filepath
            )
        return pdf_buffer, media_id


