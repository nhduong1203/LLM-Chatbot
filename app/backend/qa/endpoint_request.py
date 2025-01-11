import os
import requests
import time
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
import openai





# Configure OpenTelemetry Tracer
resource = Resource(attributes={SERVICE_NAME: "runpod-client"})
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

# endpoint_id = os.environ["RUNPOD_ENDPOINT_ID"]
# URI = f"https://api.runpod.ai/v2/{endpoint_id}/run"
# api_key =os.environ['RUNPOD_AI_API_KEY']

api_key = os.environ.get("OPENAI_API_KEY")
model = "gpt-3.5-turbo"
openai.api_key = api_key

def get_openai_stream_response(message, max_tokens=150):
    """
    Sends a request to OpenAI's API and retrieves the response in streaming mode for chat models.

    Parameters:
        api_key (str): Your OpenAI API key.
        model (str): The model to use (e.g., 'gpt-4', 'gpt-3.5-turbo').
        messages (list): A list of messages for the chat model in the format [{"role": "user", "content": "Your message"}].
        max_tokens (int): The maximum number of tokens to generate (default is 150).

    Returns:
        None: Prints the response in a streaming manner.
    """

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": message}
    ]

    try:
        # Sending request to OpenAI's API
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            stream=True  # Enable streaming response
        )

        print("Response:")
        for chunk in response:
            if 'choices' in chunk:
                # Extract content from the stream response
                delta = chunk['choices'][0]['delta']
                if 'content' in delta:
                    yield delta['content']

    except openai.error.OpenAIError as e:
        print(f"An error occurred: {e}")


def standalone_question(query="", chat_history="", max_tokens=1000):
    """
    Create a SINGLE standalone question based on a new question and chat history.
    If the new question can stand on its own, return it directly.

    Parameters:
        query (str): The query string (default: "What is a spotlist?").
        q (str): The new question.
        chat_history (str): The chat history.
        max_tokens (int): The maximum number of tokens to generate (default: 1000).

    Returns:
        str: The standalone question or response text.
    """
    prompt = f"""Create a SINGLE standalone question. The question should be based on the New question plus the Chat history. \
    If the New question can stand on its own you should return the New question. New question: \"{query}\", Chat history: \"{chat_history}\"."""

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an assistant that reformulates questions."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens
        )

        output_text = response["choices"][0]["message"]["content"].strip()
        return output_text

    except openai.error.OpenAIError as e:
        raise Exception(f"An error occurred: {e}")

if __name__ == '__main__':
    standalone_question()
