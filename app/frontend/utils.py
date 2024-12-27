import requests
import io
from PyPDF2 import PdfReader
import time
from minio import Minio
from minio.error import S3Error
import os

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Default log level
    format="%(asctime)s [%(levelname)s] %(message)s",  # Log format
    handlers=[
        logging.StreamHandler()  # Log to stdout (container best practice)
    ]
)

logger = logging.getLogger(__name__)

# Initialize MinIO client
minio_host = os.getenv("MINIO_HOST", "localhost")
minio_port = os.getenv("MINIO_PORT", "9000")
minio_access_key = os.getenv("MINIO_ACCESS_KEY", "admin")
minio_secret_key = os.getenv("MINIO_SECRET_KEY", "admin123")
minio_secure = False

minio_client = Minio(
    f"{minio_host}:{minio_port}",
    access_key=minio_access_key,
    secret_key=minio_secret_key,
    secure=minio_secure
)


async def upload_to_minio(bucket_name, user_id, chat_id, upload_option, url=None, uploaded_files=None):
    """Save data to MinIO."""

    # Ensure the bucket exists
    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)

    if upload_option == "Website URL" and url:
        # Append URL to url.txt
        object_name = f"users/{user_id}/chats/{chat_id}/reference-documents/urls/url.txt"
        try:
            # Fetch the existing URL file
            try:
                response = minio_client.get_object(bucket_name, object_name)
                existing_data = response.read().decode("utf-8")
                response.close()
            except S3Error:
                existing_data = ""  # No existing file

            # Append the new URL
            updated_data = existing_data + url + "\n"

            # Upload the updated file
            data = io.BytesIO(updated_data.encode("utf-8"))
            minio_client.put_object(bucket_name, object_name, data, length=data.getbuffer().nbytes)
            print(f"URL {url} added successfully to url.txt in MinIO.")
        except Exception as e:
            print(f"Failed to update url.txt: {e}")

    elif upload_option == "Upload Files" and uploaded_files:
        for uploaded_file in uploaded_files:
            file_content = None
            file_type = "txt" if uploaded_file.type == "text/plain" else "pdf"

            # Extract content from PDF or text file
            if file_type == "pdf":
                reader = PdfReader(uploaded_file)
                file_content = "".join(page.extract_text() for page in reader.pages).encode("utf-8")
            elif file_type == "txt":
                file_content = uploaded_file.getvalue()

            # Upload the file content to MinIO
            object_name = f"users/{user_id}/chats/{chat_id}/reference-documents/{uploaded_file.name}"
            data = io.BytesIO(file_content)
            minio_client.put_object(bucket_name, object_name, data, length=data.getbuffer().nbytes)
            print(f"File {uploaded_file.name} uploaded successfully to MinIO.")


import requests


async def process_document(user_id, chat_id, upload_option, url=None, uploaded_files=None):
    """
    Sends a request to the upload endpoint to process documents or URLs.

    Args:
        user_id (str): The user ID.
        chat_id (str): The chat ID.
        upload_option (str): The type of upload (URL or File).
        url (str, optional): The URL to be processed.
        uploaded_files (list, optional): List of uploaded file objects.

    Returns:
        dict: The API response in JSON format.
    """
    DOC_VECTORDB_API_URL = f'{os.getenv("DOC_API_URL")}/upload'

    files = []
    if uploaded_files:
        for uploaded_file in uploaded_files:
            files.append(("uploaded_files", (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)))

    # logger.info(f"files: {files}")
    data = {
        "user_id": user_id,
        "chat_id": chat_id,
        "url": url if upload_option == "Website URL" else None,
    }

    headers = {"Accept": "application/json"}

    # Send the POST request
    try:
        r = requests.post(DOC_VECTORDB_API_URL, data=data, files=files, headers=headers)
        r.raise_for_status()  # Raise exception for HTTP errors
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": str(e)}
    
async def send_message(user_id, chat_id, message):
    """
    Sends a request to the upload endpoint to process documents or URLs.

    Args:
        user_id (str): The user ID.
        chat_id (str): The chat ID.
        upload_option (str): The type of upload (URL or File).
        url (str, optional): The URL to be processed.
        uploaded_files (list, optional): List of uploaded file objects.

    Returns:
        dict: The API response in JSON format.
    """
    CHAT_API_URL = f'{os.getenv("DOC_API_URL")}/message'

    # logger.info(f"files: {files}")
    data = {
        "user_id": user_id,
        "chat_id": chat_id,
        "message": message,
        # "timestamp": time.time(),
    }

    headers = {"Accept": "application/json"}

    # Send the POST request
    try:
        r = requests.post(CHAT_API_URL, data=data, headers=headers)
        r.raise_for_status()  # Raise exception for HTTP errors
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": str(e)}



import asyncio

def sync_upload_to_minio(bucket_name, user_id, chat_id, upload_option, url=None, uploaded_files=None):
    asyncio.run(upload_to_minio(bucket_name, user_id, chat_id, upload_option, url=url, uploaded_files=uploaded_files))

def sync_process_document(user_id, chat_id, upload_option, url=None, uploaded_files=None):
    asyncio.run(process_document(user_id, chat_id, upload_option, url=url, uploaded_files=uploaded_files))


