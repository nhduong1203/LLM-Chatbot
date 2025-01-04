import numpy as np
import torch
import os
import redis
from utils import create_redis_index
import json
from redis.commands.search.query import Query
from endpoint_request import run
import time
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Default log level
    format="%(asctime)s [%(levelname)s] %(message)s",  # Log format
    handlers=[
        logging.StreamHandler()  # Log to stdout (container best practice)
    ]
)
logger = logging.getLogger(__name__)

# Configure OpenTelemetry Tracer
resource = Resource(attributes={SERVICE_NAME: "rag-system"})
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

redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=False)

VECTOR_DIMENSION = 384
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


from redis.exceptions import ResponseError

def check_index_exists(index_name):
    try:
        # Try to fetch info about the index
        redis_client.execute_command("FT.INFO", index_name)
        return True  # If no error, the index exists
    except ResponseError:
        return False  # If a ResponseError occurs, the index doesn't exist


class GenerateRAGAnswer:
    def __init__(self, embedder):
        self.embedder = embedder

    def retrieve_contexts(self, query, user_id="user123", chat_id="chat456", top_k=3):
        index_name = f"reference:{user_id}:{chat_id}"
        with tracer.start_as_current_span("retrieve_contexts") as span:
            span.set_attribute("index_name", index_name)
            span.set_attribute("query", query)

            try:
                if not check_index_exists(index_name):
                    logger.info(f"Index {index_name} does not exist.")
                    return None

                encoded_query = self.embedder.embed(query)
                search_query = (
                    Query(f'(*)=>[KNN {top_k} @vector $query_vector AS vector_score]')
                    .sort_by('vector_score')
                    .return_fields('vector_score', 'text')
                    .dialect(2)
                )
                results = redis_client.ft(index_name).search(
                    search_query,
                    {'query_vector': np.array(encoded_query, dtype=np.float32).tobytes()}
                )
                return results.docs if results.docs else []

            except Exception as e:
                span.record_exception(e)
                logger.error(f"Error while retrieving data from {index_name}: {e}")
                return []

    def gen_prompt(self, query, user_id="user123", chat_id="chat456") -> str:
        with tracer.start_as_current_span("gen_prompt") as span:
            span.set_attribute("query", query)
            contexts = self.retrieve_contexts(query, user_id, chat_id)

            if contexts:
                context_texts = [ctx["text"] for ctx in contexts]
                context = "\n\n".join(context_texts)
                prompt_template = (
                    """
                    You are a powerful chatbot designed to assist students by answering their questions.
                    Given the following relevant information from the provided context (delimited by <info></info>):

                    <info>
                    {context}
                    </info>

                    Please ensure the answer is friendly, helpful, and accurate. If the information provided is insufficient to answer the question, request clarification or specify what additional details are needed.

                    Question: {query}
                    Answer:
                    """
                ).format(context=context, query=query)
            else:
                prompt_template = (
                    """
                    You are a powerful chatbot designed to assist students by answering their questions.

                    Please answer the question below using your general knowledge. If the question cannot be answered based on the given information, kindly ask the student for clarification or specify what additional details are required.

                    Question: {query}
                    Answer:
                    """
                ).format(query=query)


            span.set_attribute("prompt_length", len(prompt_template))
            logger.info(prompt_template)
            return prompt_template

    def generate_llm_answer(self, query, user_id="user123", chat_id="chat456"):
        with tracer.start_as_current_span("generate_llm_answer") as span:
            span.set_attribute("query", query)
            query_time = time.time()
            final_prompt = self.gen_prompt(query=query, user_id=user_id, chat_id=chat_id)

            final_response = ""
            for chunk in run(final_prompt, stream=True):
                yield chunk
                final_response += chunk

            self.save_message(message=query, user_id=user_id, chat_id=chat_id, timestamp=query_time, role="User")
            self.save_message(message=final_response, user_id=user_id, chat_id=chat_id, role="Assistant")

    def save_message(self, message, user_id="user123", chat_id="chat456", timestamp=None, role="User"):
        with tracer.start_as_current_span("save_message") as span:
            span.set_attribute("message", message)
            span.set_attribute("user_id", user_id)
            span.set_attribute("chat_id", chat_id)
            span.set_attribute("role", role)

            embedding_message = self.embedder.embed(message)
            if timestamp is None:
                timestamp = int(time.time())

            key = f"history:{user_id}:{chat_id}:{timestamp}"
            data_dict = {
                "message": message,
                "time": timestamp,
                "role": role,
                "embedding": embedding_message.tolist()
            }
            redis_client.json().set(key, "$", data_dict)
            INDEX_NAME = f"history:{user_id}:{chat_id}"
            create_redis_index(redis_client, VECTOR_DIMENSION, INDEX_NAME)
