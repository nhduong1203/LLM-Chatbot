from fastapi import FastAPI, UploadFile, Form
from typing import List, Optional
from minio import Minio
from PyPDF2 import PdfReader
from embedder import Embedder
from semantic_chunking import SemanticChunker
import redis
from redis_vectordb import store_chunks_in_redis
from embedder import Embedder
from utils import crawl_website, convert_html_to_text
import os
import uvicorn
import logging
from utils import upload_to_minio

from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import get_tracer_provider, set_tracer_provider

# Configure Jaeger tracing
set_tracer_provider(
    TracerProvider(resource=Resource.create({SERVICE_NAME: "file-upload-service"}))
)
tracer = get_tracer_provider().get_tracer("file_upload_tracer")
local = True
if local:
    jaeger_exporter = JaegerExporter(
        agent_host_name=os.getenv("JAEGER_AGENT_HOST", "localhost"),
        agent_port=int(os.getenv("JAEGER_AGENT_PORT", 6831)),
    )
else:
    jaeger_exporter = JaegerExporter(
        agent_host_name="jaeger-agent.observability.svc.cluster.local",
        agent_port=6831,
    )
span_processor = BatchSpanProcessor(jaeger_exporter)
get_tracer_provider().add_span_processor(span_processor)

# Initialize other components
embedder = Embedder()
chunker = SemanticChunker(embedder.model)

app = FastAPI()
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=False)

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
    with tracer.start_as_current_span("ensure_bucket_exists") as span:
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)

# Configure logging
logging.basicConfig(
    level=logging.INFO,  
    format="%(asctime)s [%(levelname)s] %(message)s",  
    handlers=[
        logging.StreamHandler()  
    ]
)

logger = logging.getLogger(__name__)

@app.post("/upload")
async def handle_upload(
    user_id: str = Form(...),
    chat_id: str = Form(...),
    url: Optional[str] = Form(None),
    uploaded_files: Optional[List[UploadFile]] = None
):
    """Handle upload requests for URLs or files."""
    with tracer.start_as_current_span("handle_upload") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("chat_id", chat_id)
        bucket_name = "my-bucket"
        ensure_bucket_exists(bucket_name)
        

        if url:
            with tracer.start_as_current_span("process_url") as url_span:
                url_span.set_attribute("url", url)
                await upload_to_minio(minio_client, bucket_name, user_id, chat_id, "Website URL", url=url)
                crawl_result = crawl_website(url)
                if crawl_result['status'] == 'success':
                    plain_text = convert_html_to_text(crawl_result['content'])
                    chunks = chunker.process_file(plain_text)
                    chunks_and_embeddings = embedder.embed_chunks(chunks)
                    doc_id = f"{user_id}:{chat_id}:url:{hash(url)}"
                    store_chunks_in_redis(redis_client, doc_id, chunks_and_embeddings)
                    return {"status": "success", "message": "URL processed and stored successfully."}
                else:
                    url_span.record_exception(Exception(crawl_result['error']))
                    return {"status": "error", "message": crawl_result['error']}

        results = []

        if uploaded_files:
            await upload_to_minio(minio_client, bucket_name, user_id, chat_id, "Upload Files", uploaded_files=uploaded_files)
            for uploaded_file in uploaded_files:
                with tracer.start_as_current_span("process_file") as file_span:
                    file_span.set_attribute("filename", uploaded_file.filename)
                    try:
                        file_content = None
                        if uploaded_file.content_type == "application/pdf":
                            file_span.set_attribute("content_type", "application/pdf")
                            try:
                                reader = PdfReader(uploaded_file.file)
                                file_content = ""
                                for i, page in enumerate(reader.pages):
                                    try:
                                        text = page.extract_text()
                                        if text:
                                            file_content += text
                                    except Exception as e:
                                        logger.error(f"Error extracting text from page {i + 1}: {e}")
                            except Exception as e:
                                file_span.record_exception(e)
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
                        file_span.record_exception(e)
                        results.append({"filename": uploaded_file.filename, "status": "error", "message": str(e)})

        if results:
            return {"status": "success", "results": results}
        else:
            span.record_exception(ValueError("No valid input provided."))
            return {"status": "error", "message": "No valid input provided."}


