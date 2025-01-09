import os
import requests
import time
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

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

endpoint_id = os.environ["RUNPOD_ENDPOINT_ID"]
URI = f"https://api.runpod.ai/v2/{endpoint_id}/run"
api_key =os.environ['RUNPOD_AI_API_KEY']

def run(prompt, stream=True):
    with tracer.start_as_current_span("run") as span:
        span.set_attribute("prompt", prompt)

        request = {
            'prompt': prompt,
            "sampling_params": {
                "max_tokens": 500
            },
            "apply_chat_template": True,
            'stream': stream
        }

        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        try:
            response = requests.post(URI, json=dict(input=request), headers=headers)
            span.set_attribute("response_status", response.status_code)

            if response.status_code == 200:
                data = response.json()
                task_id = data.get('id')
                span.set_attribute("task_id", task_id)
                return stream_output(task_id, stream=stream)
            else:
                span.set_attribute("error", response.text)
                response.raise_for_status()
        except Exception as e:
            span.record_exception(e)
            raise

def stream_output(task_id, stream=False):
    with tracer.start_as_current_span("stream_output") as span:
        span.set_attribute("task_id", task_id)
        span.set_attribute("stream", stream)

        url = f"https://api.runpod.ai/v2/{endpoint_id}/stream/{task_id}"
        headers = {
            "Authorization": f"Bearer {os.environ['RUNPOD_AI_API_KEY']}"
        }

        try:
            while True:
                response = requests.get(url, headers=headers)
                span.set_attribute("response_status", response.status_code)

                if response.status_code == 200:
                    data = response.json()
                    if len(data['stream']) > 0:
                        for word in data["stream"][0]["output"]["choices"][0]["tokens"]:
                            yield word
                    if data.get('status') == 'COMPLETED':
                        span.add_event("Stream completed")
                        break
                else:
                    response.raise_for_status()

                time.sleep(0.1 if stream else 1)
        except Exception as e:
            span.record_exception(e)
            cancel_task(task_id)
            raise

def cancel_task(task_id):
    with tracer.start_as_current_span("cancel_task") as span:
        span.set_attribute("task_id", task_id)

        url = f"https://api.runpod.ai/v2/{endpoint_id}/cancel/{task_id}"
        headers = {
            "Authorization": f"Bearer {os.environ['RUNPOD_AI_API_KEY']}"
        }

        try:
            response = requests.get(url, headers=headers)
            span.set_attribute("response_status", response.status_code)
            return response
        except Exception as e:
            span.record_exception(e)
            raise


def standalone_question(query="What is a spotlist?", q="", chat_history="", max_tokens=1000): 
    prompt= f"""Create a SINGLE standalone question. The question should be based on the New question plus the Chat history. 
    If the New question can stand on its own you should return the New question. New question: \"{q}\", Chat history: \"{chat_history}\".""",
    with tracer.start_as_current_span("standalone question") as span:
        span.set_attribute("prompt", prompt)
        try:
            URI = f"https://api.runpod.ai/v2/{endpoint_id}/runsync"
            headers = {
                "Authorization": f"Bearer {api_key}"
            }
            q="What is a spotlist?"
            chat_history=""
            max_tokens=1000
            # prompt= f"""Create a SINGLE standalone question. The question should be based on the New question plus the Chat history. 
            #     If the New question can stand on its own you should return the New question. New question: \"{q}\", Chat history: \"{chat_history}\".""",
            prompt="Just send me a random quote"
            request = {
                'prompt': prompt,
                "sampling_params": {
                    "max_tokens": max_tokens
                }
            }
            response = requests.post(URI, json=dict(input=request), headers=headers)
            response_data = response.json()
            output_text = response_data['output'][0]['choices'][0]['tokens'][0]
            return output_text

        except Exception as e:
            span.record_exception(e)
            raise

if __name__ == '__main__':
    standalone_question()
