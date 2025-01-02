import requests
from bs4 import BeautifulSoup
import html2text
from minio.error import S3Error
import asyncio
import io
from PyPDF2 import PdfReader


def crawl_website(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        return {"status": "success", "content": soup.get_text()}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def convert_html_to_text(html_content):
    text_maker = html2text.HTML2Text()
    text_maker.ignore_links = True
    return text_maker.handle(html_content)


# def sync_upload_to_minio(minio_client, bucket_name, user_id, chat_id, upload_option, url=None, uploaded_files=None):
#     asyncio.run(upload_to_minio(minio_client, bucket_name, user_id, chat_id, upload_option, url=url, uploaded_files=uploaded_files))

async def upload_to_minio(minio_client, bucket_name, user_id, chat_id, upload_option, url=None, uploaded_files=None):
    """
    Save data to MinIO.

    Args:
        minio_client: MinIO client instance.
        bucket_name: Name of the MinIO bucket.
        user_id: ID of the user uploading the content.
        chat_id: ID of the chat associated with the upload.
        upload_option: Type of upload (e.g., "Upload Files" or "Website URL").
        url: URL to be processed, if applicable.
        uploaded_files: List of uploaded file objects, if applicable.
    """
    # Ensure the bucket exists
    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)

    if upload_option == "Website URL" and url:
        # Handle URL uploads
        object_name = f"users/{user_id}/chats/{chat_id}/reference-documents/url.txt"
        try:
            # Write URL to MinIO as a text file
            url_content = url.encode("utf-8")
            data = io.BytesIO(url_content)
            minio_client.put_object(bucket_name, object_name, data, length=len(url_content))
            print(f"URL '{url}' saved successfully to MinIO.")
        except Exception as e:
            print(f"Failed to upload URL to MinIO: {e}")
            raise

    elif upload_option == "Upload Files" and uploaded_files:
        # Handle file uploads
        for uploaded_file in uploaded_files:
            try:
                file_content = None
                file_type = "txt" if uploaded_file.content_type == "text/plain" else "pdf"

                # Extract content from PDF or text file
                if file_type == "pdf":
                    with io.BytesIO(await uploaded_file.read()) as file_stream:
                        reader = PdfReader(file_stream)
                        file_content = "".join(page.extract_text() for page in reader.pages).encode("utf-8")
                elif file_type == "txt":
                    file_content = await uploaded_file.read()

                if not file_content:
                    raise ValueError(f"Unable to extract content from file: {uploaded_file.filename}")

                # Upload the file content to MinIO
                object_name = f"users/{user_id}/chats/{chat_id}/reference-documents/{uploaded_file.filename}"
                data = io.BytesIO(file_content)
                minio_client.put_object(bucket_name, object_name, data, length=data.getbuffer().nbytes)
                print(f"File '{uploaded_file.filename}' uploaded successfully to MinIO.")
            except Exception as e:
                print(f"Failed to upload file '{uploaded_file.filename}' to MinIO: {e}")
                raise
    else:
        print("No valid upload option or data provided.")
        raise ValueError("Invalid upload option or no data to upload.")
