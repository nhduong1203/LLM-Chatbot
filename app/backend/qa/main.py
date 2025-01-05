from fastapi import FastAPI, UploadFile, Form
from typing import List, Optional
import os
import logging
from generate_answer import GenerateRAGAnswer
from fastapi.responses import StreamingResponse
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Configure OpenTelemetry Tracer
resource = Resource(attributes={SERVICE_NAME: "chat-service"})
provider = TracerProvider(resource=resource)
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
provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

app = FastAPI()
rag = GenerateRAGAnswer()

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
async def message_response(
    user_id: str = Form(...),
    chat_id: str = Form(...),
    message: str = Form(...),
    timestamp: float = Form(...),
):
    with tracer.start_as_current_span("message") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("chat_id", chat_id)
        span.set_attribute("message", message)
        span.set_attribute("timestamp", timestamp)

        try:
            # Generate an LLM answer using RAG
            # The generator end when the function that create the generator end.
            generator = rag.generate_llm_answer(query=message, user_id=user_id, chat_id=chat_id)
            return StreamingResponse(generator, media_type="text/event-stream")
        except Exception as e:
            span.record_exception(e)
            logger.error(f"Error generating response: {e}")
            raise


