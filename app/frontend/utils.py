import requests
import time
import os
import json
import httpx
import streamlit as st
import logging
import asyncio
from typing import AsyncGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Default log level
    format="%(asctime)s [%(levelname)s] %(message)s",  # Log format
    handlers=[
        logging.StreamHandler()  # Log to stdout (container best practice)
    ]
)

logger = logging.getLogger(__name__)

NGINX_URL = os.getenv("NGINX_URL")

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
    DOC_VECTORDB_API_URL = f'http://{NGINX_URL}/upload'

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
    
async def delete_document(user_id, chat_id, upload_option, document_name=None):
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
    DOC_VECTORDB_API_URL = f'http://{NGINX_URL}/remove_document'
    data = {
        "user_id": user_id,
        "chat_id": chat_id,
        "upload_option": upload_option,
        "document_name": document_name
    }
    # upload_option: str, document_name

    headers = {"Accept": "application/json"}

    # Send the POST request
    try:
        r = requests.post(DOC_VECTORDB_API_URL, data=data, headers=headers)
        r.raise_for_status()  # Raise exception for HTTP errors
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": str(e)}
    
def sync_process_document(user_id, chat_id, upload_option, url=None, uploaded_files=None):
    asyncio.run(process_document(user_id, chat_id, upload_option, url=url, uploaded_files=uploaded_files))

def sync_delete_document(user_id, chat_id, upload_option, document_name):
    asyncio.run(process_document(user_id, chat_id, upload_option, document_name))

def send_message(ws_connection, user_id, chat_id, message):
    """
    Sends a message via WebSocket to the server and streams the response.

    Args:
        user_id (str): The user ID.
        chat_id (str): The chat ID.
        message (str): The message to send.

    Yields:
        str: The server's response as it is received.
    """

    try:
    
        payload = {
            "type": "ms",
            "user_id": user_id,
            "chat_id": chat_id,
            "message": message
        }
        ws_connection.send(json.dumps(payload))

        # Stream the response without closing the connection
        while True:
            response = ws_connection.recv()
            if response == "/end":  # End marker, exit the loop but keep the connection alive
                break
            yield response
    except Exception as e:
        # Log the error and reset the connection
        st.session_state.ws_connection = None  # Clear the connection to force reconnection
        raise Exception(f"WebSocket error: {e}")

def testing():
    CHAT_API_URL = f'http://{NGINX_URL}/test'
    headers = {"Accept": "application/json"}

    with httpx.stream('POST', CHAT_API_URL, headers=headers, timeout=None) as r:
        if r.status_code != 200:
            raise Exception(f"Error: {r.status_code}, {r.text}")
        
        for line in r.iter_text():
            yield line  # Yield token for further processing (if needed)
            time.sleep(0.05)


