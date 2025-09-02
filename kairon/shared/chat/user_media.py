import asyncio
import base64
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from markdown_pdf import MarkdownPdf, Section
from loguru import logger
from fastapi import File
import requests
from mongoengine import DoesNotExist, NotUniqueError
from pathy import ClientError
from uuid6 import uuid7

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import Actions, PromptAction
from kairon.shared.actions.models import ActionType
from kairon.shared.chat.agent.agent_flow import AgenticFlow
from kairon.shared.cloud.utils import CloudUtility
from kairon.shared.data.data_objects import UserMediaData, Rules, Intents
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import UserMediaUploadType, UserMediaUploadStatus, FlowTagType
import fitz


class UserMedia:
    MEDIA_EXTRACTION_FLOW_NAME = "k_media_extraction"
    @staticmethod
    def create_user_media_data(bot: str, media_id: str, filename: str, sender_id: str, upload_type: str = UserMediaUploadType.user_uploaded.value):
        """
        Create user media data in processing state.
        Call mark_user_media_data_upload_done() to mark the upload as done or mark_user_media_data_upload_failed() to mark the upload as failed.
        """
        extension = str(Path(filename).suffix).lower()
        user_media_data = UserMediaData(
            media_id=media_id,
            filename=filename,
            extension=extension,
            upload_type=upload_type,
            upload_status=UserMediaUploadStatus.processing.value,
            sender_id=sender_id,
            bot=bot,
            timestamp=datetime.utcnow()
        )
        user_media_data.save()

    @staticmethod
    def mark_user_media_data_upload_done(media_id:str, media_url: str, output_filename: str, filesize: int):
        """
        Mark user media data upload as done.
        """
        user_media_data = UserMediaData.objects(media_id=media_id).first()
        if user_media_data:
            user_media_data.media_url = media_url
            user_media_data.output_filename = output_filename
            user_media_data.filesize = filesize
            user_media_data.upload_status = UserMediaUploadStatus.completed.value
            user_media_data.save()

    @staticmethod
    def mark_user_media_data_upload_failed(media_id:str, reason: str):
        user_media_data = UserMediaData.objects(media_id=media_id).first()
        if user_media_data:
            user_media_data.upload_status = UserMediaUploadStatus.failed.value
            user_media_data.additional_log = reason
            user_media_data.save()



    @staticmethod
    def save_media_content(
                bot: str,
                sender_id: str,
                media_id: str,
                binary_data: bytes = None,
                filename: str = None,
                ):
        """
        Save media content to cloud storage.
        :param bot: bot name
        :param sender_id: sender id
        :param media_id: media id
        :param binary_data: binary data of the file
        :param filename: name of the file
        """

        if not filename:
            raise AppException('filename must be provided for binary data')

        bucket = Utility.environment["storage"]["user_media"].get("bucket")
        root_dir = Utility.environment["storage"]["user_media"].get("root_dir")
        fpath = Path(filename)
        extension = str(fpath.suffix).lower()
        base_filename = fpath.stem
        filesize = len(binary_data)

        if extension not in Utility.environment["storage"]["user_media"].get(
                "allowed_extensions"
        ):
            raise AppException(
                f'Only {Utility.environment["storage"]["user_media"].get("allowed_extensions")} type files allowed'
            )

        output_filename = os.path.join(root_dir, bot, f"{sender_id.replace('@', '_')}_{media_id}_{base_filename}{extension}")
        try:
            url = CloudUtility.upload_file_bytes(binary_data, bucket, output_filename)
            UserMedia.mark_user_media_data_upload_done(media_id=media_id,
                                                       media_url=url,
                                                       output_filename=output_filename,
                                                       filesize=filesize)
            logger.info(f"saved {media_id} successfully")
        except ClientError as e:
            logger.exception(e)
            UserMedia.mark_user_media_data_upload_failed(media_id=media_id, reason=str(e))
            raise AppException(f"File upload for {media_id} failed")
        except Exception as e:
            logger.exception(e)
            UserMedia.mark_user_media_data_upload_failed(media_id=media_id, reason=str(e))
            raise AppException(f"File upload for {media_id} failed")

    @staticmethod
    def save_whatsapp_media_content(bot: str, sender_id: str, whatsapp_media_id:str, config: dict):
        """
        Download media from 360 dialog or meta and save it to cloud storage via background task.
        :param bot: bot name
        :param sender_id: sender id
        :param whatsapp_media_id: whatsapp media id
        :param config: configuration for 360 dialog or meta
        :return: list of media ids
        """
        download_url = None
        file_path = None
        headers = {}
        provider = config.get("bsp_type", "meta")
        if provider == '360dialog':
            endpoint = f'https://waba-v2.360dialog.io/{whatsapp_media_id}'
            headers = {
                'D360-API-KEY': config.get('api_key'),
            }
            resp = requests.get(endpoint, headers=headers, stream=True)
            if resp.status_code != 200:
                raise AppException(f"Failed to download media from 360 dialog: {resp.status_code} - {resp.text}")
            json_resp = resp.json()
            download_url = json_resp.get("url")
            download_url = download_url.replace('https://lookaside.fbsbx.com', 'https://waba-v2.360dialog.io')
            mime_type = json_resp.get("mime_type")
            extension = mimetypes.guess_extension(mime_type) or ''
            file_path = f"whataspp_360_{whatsapp_media_id}{extension}"
        elif provider == 'meta':
            endpoint = f'https://graph.facebook.com/v22.0/{whatsapp_media_id}'
            access_token = config.get('access_token')
            headers = {'Authorization': f'Bearer {access_token}'}
            media_info_resp = requests.get(
                endpoint,
                params={"fields": "url", "access_token": access_token},
                timeout=10
            )
            if media_info_resp.status_code != 200:
                raise AppException(f"Failed to get url from meta for media: {whatsapp_media_id}")
            json_resp = media_info_resp.json()
            download_url = json_resp.get("url")
            mime_type = json_resp.get("mime_type")
            extension = mimetypes.guess_extension(mime_type) or ''
            file_path = f"whatsapp_meta_{whatsapp_media_id}{extension}"

        media_resp = requests.get(
            download_url,
            headers=headers,
            stream=True,
            timeout=10
        )
        if media_resp.status_code != 200:
            raise AppException(f"Failed to download media: {whatsapp_media_id}")
        buffer = bytearray()
        for chunk in media_resp.iter_content(chunk_size=8192):
            if chunk:
                buffer.extend(chunk)
        file_buffer = bytes(buffer)

        media_id = uuid7().hex
        UserMedia.create_user_media_data(
            bot=bot,
            media_id=media_id,
            filename=file_path,
            sender_id=sender_id,
            upload_type=UserMediaUploadType.user_uploaded.value)

        def background_task():
            try:
                asyncio.run(UserMedia.save_media_content_task(
                    bot=bot,
                    sender_id=sender_id,
                    media_id=media_id,
                    binary_data=file_buffer,
                    filename=file_path
                ))
            except Exception as e:
                logger.exception(f"Background task failed for media_id {media_id}: {e}")

        asyncio.create_task(asyncio.to_thread(background_task))

        return [media_id]


    @staticmethod
    async def save_media_content_task(
            bot: str,
            sender_id: str,
            media_id: str,
            binary_data: bytes,
            filename: str,
            execute_summarizarion: bool = True
    ):
        await asyncio.to_thread(
            UserMedia.save_media_content,
            bot,
            sender_id,
            media_id,
            binary_data,
            filename
        )
        if execute_summarizarion:
            await UserMedia.extract_media_information(bot, media_id, sender_id)

    @staticmethod
    async def upload_media_contents(
            bot: str,
            sender_id: str,
            files: list[File],
    ):
        """
        Upload media contents to cloud storage via background task.
        :param bot: bot name
        :param sender_id: sender id
        :param files: list of files to upload
        :return: list of media ids
        """
        media_ids = []
        file_names = []
        read_tasks = [asyncio.create_task(file.read()) for file in files]
        binary_datas = await asyncio.gather(*read_tasks)

        for file, binary_data in zip(files, binary_datas):
            filename = file.filename
            file_names.append(filename)
            media_id = uuid7().hex
            media_ids.append(media_id)
            UserMedia.create_user_media_data(
                bot=bot,
                media_id=media_id,
                filename=filename,
                sender_id=sender_id
            )
            asyncio.create_task(UserMedia.save_media_content_task(
                bot=bot,
                sender_id=sender_id,
                media_id=media_id,
                binary_data=binary_data,
                filename=filename
            ))
        return media_ids, file_names

    @staticmethod
    async def upload_media_content_sync(
            bot: str,
            sender_id: str,
            files: list[File],
    ):
        media_ids = []
        file_names = []
        read_tasks = [asyncio.create_task(file.read()) for file in files]
        binary_datas = await asyncio.gather(*read_tasks)
        tasks = []

        for file, binary_data in zip(files, binary_datas):
            filename = file.filename
            file_names.append(filename)
            media_id = uuid7().hex
            media_ids.append(media_id)
            UserMedia.create_user_media_data(
                bot=bot,
                media_id=media_id,
                filename=filename,
                sender_id=sender_id
            )
            tasks.append(
                UserMedia.save_media_content_task(
                    bot=bot,
                    sender_id=sender_id,
                    media_id=media_id,
                    binary_data=binary_data,
                    filename=filename,
                    execute_summarizarion=False
                )
            )

        await asyncio.gather(*tasks)
        return media_ids, file_names


    @staticmethod
    async def get_media_content_buffer(media_id: str, base64_encode: bool = False) -> tuple[BinaryIO|str, str, str]:
        try:
            media_doc = UserMediaData.objects.get(media_id=media_id)
            media_data = media_doc.to_mongo().to_dict()
            media_data['id'] = str(media_doc.id)
            media_data.pop('bot')
            media_data.pop('sender_id')
            bucket = Utility.environment["storage"]["user_media"].get("bucket")
            file_buffer = CloudUtility.download_file_to_memory(bucket, media_doc.output_filename)
            download_name = f"media_{media_id}{media_doc.extension}"
            if base64_encode:
                file_buffer.seek(0)
                encoded_string = base64.b64encode(file_buffer.read()).decode('utf-8')
                return encoded_string, download_name, media_doc.extension
            return file_buffer, download_name, media_doc.extension
        except DoesNotExist:
            raise AppException("Document not found")

    custom_markdown_css = """
        body {
            font-family: "Segoe UI", "Helvetica Neue", sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #333;
            margin: 1cm;
        }

        h1, h2, h3, h4 {
            font-weight: bold;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
            padding-bottom: 0.2em;
        }

        h1 { font-size: 24pt; text-align: center; }
        h2 { font-size: 16pt; color: #2a4b8d; border-bottom: 1px solid #ccc;}
        h3 { font-size: 14pt; color: #222; }
        h4 { font-size: 12pt; }

        p { margin: 0.8em 0; }

        ul, ol {
            margin-left: 1.5em;
            margin-top: 0.5em;
            margin-bottom: 0.5em;
        }

        pre {
            background-color: #f4f4f4;
            border: 1px solid #ddd;
            padding: 0.8em;
            overflow-x: auto;
            font-family: "Courier New", monospace;
            font-size: 10pt;
        }

        code {
            background-color: #f4f4f4;
            padding: 0.1em 0.3em;
            border-radius: 3px;
            font-family: "Courier New", monospace;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin: 1em 0;
        }

        th, td {
            border: 1px solid #ccc;
            padding: 0.5em;
            text-align: left;
        }

        th {
            background-color: #f0f0f0;
        }

        img {
            max-width: 100%;
            display: block;
            margin: 1em auto;
        }

        blockquote {
            border-left: 4px solid #ccc;
            padding-left: 1em;
            color: #555;
            font-style: italic;
        }

        hr {
            border: none;
            border-top: 1px solid #ccc;
            margin: 2em 0;
        }
        """

    @staticmethod
    def save_markdown_as_pdf(bot: str, sender_id: str, text: str, filepath: str= "report.pdf"):
        if Path(filepath).suffix.lower() != ".pdf":
            raise AppException("Provided filepath must have a .pdf extension")
        pdf = MarkdownPdf(toc_level=0, mode='commonmark')
        pdf.add_section(Section(text, toc=False), user_css=UserMedia.custom_markdown_css)
        pdf.writer.close()
        pdf.out_file.seek(0)
        doc = fitz.Story.add_pdf_links(pdf.out_file, pdf.hrefs)
        doc.set_metadata(pdf.meta)
        binary_data = doc.write()
        doc.close()
        media_id = uuid7().hex
        UserMedia.create_user_media_data(
            bot=bot,
            media_id=media_id,
            filename=filepath,
            sender_id=sender_id,
            upload_type=UserMediaUploadType.system_uploaded.value
        )
        UserMedia.save_media_content(
                bot=bot,
                sender_id=sender_id,
                media_id=media_id,
                binary_data=binary_data,
                filename=filepath
            )
        return binary_data, media_id

    @staticmethod
    def add_media_extraction_flow_if_not_exist( bot: str):
        try:
            instructions = ['Extract all relevant information from the media file and return as a markdown']

            llm_prompts = [
                {'name': 'System Prompt',
                 'instructions': f'{instructions[0]}',
                 'type': 'system',
                 'data': 'Extract information',
                 },
            ]

            action_name = f"{UserMedia.MEDIA_EXTRACTION_FLOW_NAME}_prompt_action"
            if not Actions.objects(bot=bot, name=action_name).first():
                action = Actions(
                    bot=bot,
                    name=action_name,
                    type=ActionType.prompt_action.value,
                    status=True,
                    user="system",
                )
                action.save()


            if not PromptAction.objects(bot=bot, name=action_name).first():
                prompt_action = PromptAction(
                    name=action_name,
                    instructions=instructions,
                    llm_prompts=llm_prompts,
                    dispatch_response=True,
                    process_media=True,
                    bot=bot,
                    status=True,
                    user="system",
                )
                prompt_action.save()
            MULTIMEDIA_INTENT_NAME = "k_multimedia_msg"

            if not Rules.objects(block_name=UserMedia.MEDIA_EXTRACTION_FLOW_NAME, bot=bot).first():
                rule_data = {
                    "block_name": UserMedia.MEDIA_EXTRACTION_FLOW_NAME,
                    "condition_events_indices": [],
                    "start_checkpoints": ["STORY_START"],
                    "end_checkpoints": [],
                    "events": [
                        {"name": "...", "type": "action"},
                        {"name": "k_multimedia_msg", "type": "user"},
                        {"name": action_name, "type": "action"}
                    ],
                    "bot": bot,
                    "user": "system",
                    "timestamp": datetime.utcnow(),
                    "status": True,
                    "template_type": "CUSTOM",
                    "flow_tags": [FlowTagType.agentic_flow.value]
                }
                Rules(**rule_data).save()

        except Exception as e:
            logger.exception(e)
            raise AppException(f"Failed to add media extraction flow: {e}")

    @staticmethod
    async def extract_media_information(bot:str, media_id: str, sender_id: str):
        try:
            UserMedia.add_media_extraction_flow_if_not_exist(bot)
            slot_data = {
                "media_ids": [media_id],
            }
            flow = AgenticFlow(bot, slot_vals=slot_data, sender_id=sender_id)
            responses, errors = await flow.execute_rule(UserMedia.MEDIA_EXTRACTION_FLOW_NAME)
            if errors:
                raise AppException(f"Failed to extract media information: {errors}")
            if not responses:
                raise AppException(f"extraction prompt action execution failed: {media_id}")

            user_media_data = UserMediaData.objects(media_id=media_id).get()

            user_media_data.summary = responses[0].get("text")
            user_media_data.save()

        except Exception as e:
            logger.exception(e)
            raise AppException(f"Failed to extract media information: {e}")

    def get_media_ids(bot: str):
        try:
            media_data = UserMediaData.objects(
                bot=bot,
                upload_status=UserMediaUploadStatus.completed.value,
                media_id__ne="",
            ).only("filename", "media_id")

            if not media_data:
                return []

            return [{"filename": doc.filename, "media_id": doc.media_id} for doc in media_data]

        except Exception as e:
            raise AppException(f"Error while fetching media ids for bot '{bot}': {str(e)}")

    @staticmethod
    def create_media_doc(
            bot: str,
            sender_id: str,
            filename: str,
            extension: str,
            filesize: int,
    ) -> UserMediaData:
        """
        Create a media document in pending state, return the instance so it can be updated later.
        """
        media_doc = UserMediaData(
            media_id = "",
            media_url = "",
            filename = filename,
            extension = extension,
            output_filename = "",
            summary = "",
            upload_status = UserMediaUploadStatus.processing.value,
            upload_type = UserMediaUploadType.broadcast.value,
            filesize = filesize,
            additional_log = "Upload initiated",
            sender_id = sender_id,
            bot = bot,
            external_upload_info = {
                "bsp": "360dialog",
                "external_media_id": "",
                "error": "",
            },
        )
        media_doc.save()
        return media_doc
