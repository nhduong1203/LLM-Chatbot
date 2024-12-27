import os
import requests
import time

endpoint_id = os.environ["RUNPOD_ENDPOINT_ID"]
URI = f"https://api.runpod.ai/v2/{endpoint_id}/run"


def run(prompt, stream=True):
    request = {
        'prompt': prompt,
        "sampling_params": {
            "max_tokens": 500
        },
        # 'max_new_tokens': 1800,
        # 'temperature': 0.3,
        # 'top_k': 50,
        # 'top_p': 0.7,
        # 'repetition_penalty': 1.2,
        'batch_size': 8,
        'stream': stream
    }

    response = requests.post(URI, json=dict(input=request), headers = {
        "Authorization": f"Bearer {os.environ['RUNPOD_AI_API_KEY']}"
    })

    if response.status_code == 200:
        data = response.json()
        
        task_id = data.get('id')
        return stream_output(task_id, stream=stream)


def stream_output(task_id, stream=False):
    # try:
    url = f"https://api.runpod.ai/v2/{endpoint_id}/stream/{task_id}"
    headers = {
        "Authorization": f"Bearer {os.environ['RUNPOD_AI_API_KEY']}"
    }

    try:
        while True:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if len(data['stream']) > 0:
                    for word in data["stream"][0]["output"]["choices"][0]["tokens"]:
                        yield word
                if data.get('status') == 'COMPLETED':
                    break
            time.sleep(0.1 if stream else 1)

    except Exception as e:
        print(e)
        cancel_task(task_id)
    

def cancel_task(task_id):
    url = f"https://api.runpod.ai/v2/{endpoint_id}/cancel/{task_id}"
    headers = {
        "Authorization": f"Bearer {os.environ['RUNPOD_AI_API_KEY']}"
    }
    response = requests.get(url, headers=headers)
    return response


if __name__ == '__main__':
    prompt = "Hello, how are you?"
    start = time.time()

    # Call `run` to initiate the process
    generator = run(prompt)

    # Iterate over the yielded messages and print them
    for message in generator:
        print(message, end='', flush=True)  # Print each chunk as it is streamed

    print("\nTime taken: ", time.time() - start, " seconds")
