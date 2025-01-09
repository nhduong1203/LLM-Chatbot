import torch
import os
from database_manager import RedisManager, CassandraMessageStore
from endpoint_request import run, standalone_question
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

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class GenerateRAGAnswer:
    def __init__(self):
        self.redis_manager = RedisManager()
        self.cassandra_manager = CassandraMessageStore()

    def gen_prompt(self, query, contexts=None) -> str:
        with tracer.start_as_current_span("gen_prompt") as span:
            span.set_attribute("query", query)
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
            contexts = self.redis_manager.retrieve_contexts(query, user_id, chat_id)
            final_query = standalone_question(query=query)
            final_prompt = self.gen_prompt(query=final_query, contexts=contexts, user_id=user_id, chat_id=chat_id)

            final_response = ""
            for chunk in run(final_prompt, stream=True):
                yield chunk
                final_response += chunk
            self.cassandra_manager.save_message(user_id=user_id, conversation_id=chat_id, message=query, role="User", timestamp=query_time)
            self.cassandra_manager.save_message(user_id=user_id, conversation_id=chat_id, message=final_response, role="Bot")

