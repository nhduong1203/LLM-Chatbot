from fastapi import FastAPI, UploadFile, Form
from typing import List, Optional
from minio import Minio
from PyPDF2 import PdfReader
from embedder import Embedder
from semantic_chunking import SemanticChunker
import redis
from redis_vectordb import create_redis_index, store_chunks_in_redis
from embedder import Embedder
from utils import crawl_website, convert_html_to_text
import os
import uvicorn

chunker = SemanticChunker()
embedder = Embedder()

app = FastAPI()
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))

redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=False)
VECTOR_DIMENSION = 384
INDEX_NAME = "idx:embedding"
create_redis_index(redis_client, VECTOR_DIMENSION, INDEX_NAME)


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

# Ensure bucket exists
def ensure_bucket_exists(bucket_name: str):
    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)

@app.post("/upload")
async def handle_upload(
    user_id: str = Form(...),
    chat_id: str = Form(...),
    url: Optional[str] = Form(None),
    uploaded_files: Optional[List[UploadFile]] = None
):
    """Handle upload requests for URLs or files."""
    bucket_name = "my-bucket"
    ensure_bucket_exists(bucket_name)

    if url:
        # Crawl the URL and convert to plain text
        crawl_result = crawl_website(url)
        if crawl_result['status'] == 'success':
            plain_text = convert_html_to_text(crawl_result['content'])
            chunks = chunker.process_file(plain_text)
            chunks_and_embeddings = embedder.embed_chunks(chunks)
            doc_id = f"{user_id}:{chat_id}:url:{hash(url)}"
            store_chunks_in_redis(redis_client, doc_id, chunks_and_embeddings)
            return {"status": "success", "message": "URL processed and stored successfully."}
        else:
            return {"status": "error", "message": crawl_result['error']}

    results = []

    if uploaded_files:
        for uploaded_file in uploaded_files:
            try:
                file_content = None
                if uploaded_file.content_type == "application/pdf":
                    try:
                        reader = PdfReader(uploaded_file.file)
                        file_content = ""
                        for i, page in enumerate(reader.pages):
                            try:
                                text = page.extract_text()
                                if text:
                                    file_content += text
                            except Exception as e:
                                print(f"Error extracting text from page {i + 1}: {e}")
                    except Exception as e:
                        results.append({"filename": uploaded_file.filename, "status": "error", "message": f"Failed to process PDF: {e}"})
                        continue
                else:
                    file_content = (await uploaded_file.read()).decode("utf-8")

                if file_content:
                    chunks = chunker.process_file(file_content)
                    chunks_and_embeddings = embedder.embed_chunks(chunks)
                    doc_id = f"{user_id}:{chat_id}:file:{uploaded_file.filename}"
                    store_chunks_in_redis(redis_client, doc_id, chunks_and_embeddings)
                    results.append({"filename": uploaded_file.filename, "status": "success", "message": "File processed and stored successfully."})
                else:
                    results.append({"filename": uploaded_file.filename, "status": "error", "message": "Empty file content."})
            except Exception as e:
                results.append({"filename": uploaded_file.filename, "status": "error", "message": str(e)})

    if results:
        return {"status": "success", "results": results}
    else:
        return {"status": "error", "message": "No valid input provided."}




def main():
    # Run web server with uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("DOC_FASTAPI_HOST", "127.0.0.1"),
        port=int(os.getenv("DOC_FASTAPI_PORT", 8002)),
    )


if __name__ == "__main__":
    main()