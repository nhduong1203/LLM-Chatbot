from fastapi import FastAPI, UploadFile, Form
from typing import List, Optional
import redis
from embedder import Embedder
from utils import save_message
import os
import uvicorn
import logging
from generate_answer import GenerateRAGAnswer
from fastapi.responses import StreamingResponse

app = FastAPI()
embedder = Embedder()
rag = GenerateRAGAnswer()

redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=False)

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Default log level
    format="%(asctime)s [%(levelname)s] %(message)s",  # Log format
    handlers=[
        logging.StreamHandler()  # Log to stdout (container best practice)
    ]
)

logger = logging.getLogger(__name__)
@app.post("/message")
async def handle_upload(
    user_id: str = Form(...),
    chat_id: str = Form(...),
    message: str = Form(...),
    time: float = Form(...),
):
    """Handle upload requests for URLs or files."""
    save_message(user_id=user_id, chat_id=chat_id, message=message, time=time, role="User")

    return StreamingResponse(
        rag.generate_llm_answer(query=message, user_id=user_id, chat_id=chat_id),
        media_type="text/event-stream"
    )

def main():
    # Run web server with uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("CHAT_FASTAPI_HOST", "127.0.0.1"),
        port=int(os.getenv("CHAT_FASTAPI_PORT", 8002)),
    )


if __name__ == "__main__":
    main()