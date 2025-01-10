import requests
import time
import os
import json
import httpx
import streamlit as st
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

import asyncio
import requests

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
    DOC_VECTORDB_API_URL = f'{NGINX_URL}/upload'

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
    
import asyncio
import websockets
import time
import json

import websockets
import asyncio

async def send_message(user_id, chat_id, message):
    """
    Sends a message via WebSocket to the server and streams the response.

    Args:
        user_id (str): The user ID.
        chat_id (str): The chat ID.
        message (str): The message to send.

    Yields:
        str: The server's response as it is received.
    """
    uri = f"{NGINX_URL}/ws/{user_id}"  # Ensure NGINX_URL is properly defined
    try:
        async with websockets.connect(uri) as websocket:
            # Send the message as a JSON payload
            payload = {
                "chat_id": chat_id,
                "message": message
            }
            await websocket.send(json.dumps(payload))

            # Listen for server responses
            full_response = ""
            while True:
                try:
                    # Receive the next token from the server
                    token = await websocket.recv()
                    
                    if token == "/end":
                        break  # End of message stream
                    
                    full_response += token  # Accumulate tokens
                    yield full_response  # Yield the accumulated response incrementally
                except websockets.ConnectionClosedError:
                    st.error("WebSocket connection closed unexpectedly.")
                    break
    except Exception as e:
        # Log error for debugging
        st.error(f"An error occurred: {e}")


from typing import AsyncGenerator
def to_sync_generator(async_gen: AsyncGenerator):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        while True:
            try:
                yield loop.run_until_complete(anext(async_gen))
            except StopAsyncIteration:
                break
    finally:
        loop.close()

def testing():
    CHAT_API_URL = f'{NGINX_URL}/test'
    headers = {"Accept": "application/json"}

    with httpx.stream('POST', CHAT_API_URL, headers=headers, timeout=None) as r:
        if r.status_code != 200:
            raise Exception(f"Error: {r.status_code}, {r.text}")
        
        for line in r.iter_text():
            yield line  # Yield token for further processing (if needed)
            time.sleep(0.05)

def sync_process_document(user_id, chat_id, upload_option, url=None, uploaded_files=None):
    asyncio.run(process_document(user_id, chat_id, upload_option, url=url, uploaded_files=uploaded_files))


