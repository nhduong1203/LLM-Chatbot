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

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Default log level
    format="%(asctime)s [%(levelname)s] %(message)s",  # Log format
    handlers=[
        logging.StreamHandler()  # Log to stdout (container best practice)
    ]
)
logger = logging.getLogger(__name__)

redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=False)



VECTOR_DIMENSION = 384

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

class GenerateRAGAnswer:

    def __init__(self, embedder):
        self.embedder = embedder

    # Existing functions now delegate to the shared `retrieve_data`
    def retrieve_contexts(self, query, user_id="user123", chat_id="chat456", top_k=3):
        index_name = f"reference:{user_id}:{chat_id}"
        try:
            # Check if the index exists
            if not redis_client.ft(index_name).info():
                print(f"Index {index_name} does not exist.")
                return []

            # Embed the query
            encoded_query = self.embedder.embed(query)

            # Define the query
            search_query = (
                Query(f'(*)=>[KNN {top_k} @vector $query_vector AS vector_score]')
                .sort_by('vector_score')
                .return_fields('vector_score', 'text')
                .dialect(2)
            )

            # Perform the search
            results = redis_client.ft(index_name).search(
                search_query,
                {
                    'query_vector': np.array(encoded_query, dtype=np.float32).tobytes()
                }
            )

            return results.docs if results.docs else []

        except Exception as e:
            print(f"Error while retrieving data from {index_name}: {e}")
            return []

    def retrieve_history(self, query, user_id="user123", chat_id="chat456", top_k=3):
        index_name = f"history:{user_id}:{chat_id}"
        try:
            # Check if the index exists
            if not redis_client.ft(index_name).info():
                print(f"Index {index_name} does not exist.")
                return []

            # Embed the query
            encoded_query = self.embedder.embed(query)

            # Define the query
            search_query = (
                Query(f'(*)=>[KNN {top_k} @vector $query_vector AS vector_score]')
                .sort_by('vector_score')
                .return_fields('vector_score', 'message', 'role')
                .dialect(2)
            )

            # Perform the search
            results = redis_client.ft(index_name).search(
                search_query,
                {
                    'query_vector': np.array(encoded_query, dtype=np.float32).tobytes()
                }
            )

            return results.docs if results.docs else []

        except Exception as e:
            print(f"Error while retrieving data from {index_name}: {e}")
            return []


    def gen_prompt(self, query, user_id="user123", chat_id="chat456") -> str:
        """
        Constructs a detailed prompt from the retrieved or searched contexts and chat history
        to be processed by the language model.

        Returns:
            str: A formatted string that serves as a prompt for the language model.
        """
        # Retrieve contexts and chat history
        contexts = self.retrieve_contexts(query, user_id, chat_id)
        history = self.retrieve_history(query, user_id, chat_id)

        # Prepare chat history text
        if history:
            history_texts = [f"{entry['role']}: {entry['message']}" for entry in history]
            chat_history = "\n".join(history_texts)
        else:
            chat_history = "No relevant chat history is available."

        # Check if contexts are available
        if not contexts:
            # If no context is found, create a simpler prompt
            prompt_template = (
                """
                You are a teaching assistant.
                However, here is the recent chat history (if any):
                <chat_history>
                {chat_history}
                </chat_history>
                Please try your best to answer the student's question based on this history and your general knowledge.
                If you cannot answer, ask the student to clarify the question.

                Question: {query}
                Answer: """
            ).format(chat_history=chat_history, query=query)
        else:
            # If contexts are available, construct the detailed prompt
            context_texts = [ctx["text"] for ctx in contexts]
            context = "\n\n".join(context_texts)
            prompt_template = (
                """
                You are a teaching assistant.
                Given a set of relevant information from the teacher's recording during the lesson (delimited by <info></info>)
                and the recent chat history (delimited by <chat_history></chat_history>), please compose an answer to the question of a student.
                Ensure that the answer is accurate, has a friendly tone, and sounds helpful.
                If you cannot answer, ask the student to clarify the question.

                <info>
                {context}
                </info>

                <chat_history>
                {chat_history}
                </chat_history>

                Question: {query}
                Answer: """
            ).format(context=context, chat_history=chat_history, query=query)

        logger.info(prompt_template)
        return prompt_template
    
    async def generate_llm_answer(self, query, user_id="user123", chat_id="chat456"):
        """
        Generates an answer from the language model by streaming content based on the prepared prompt.

        Yields:
            str: Each content chunk generated by the language model.
        """
        query_time = time.time()
        final_prompt = self.gen_prompt(query=query, user_id=user_id, chat_id=chat_id)

        # TODO
        final_respond = ""
        for chunk in run(final_prompt, stream=True):
            final_respond += chunk
            yield json.dumps({"token": chunk}) + "\n"

        self.save_message(message=query, user_id=user_id, chat_id=chat_id, timestamp=query_time, role="User")
        self.save_message(message=final_respond, user_id=user_id, chat_id=chat_id, role="Assistant")


    def save_message(self, message, user_id="user123", chat_id="chat456", timestamp=None, role="User"):
        embedding_message = self.embedder.embed(message)
        # Use the current time if no timestamp is provided
        if timestamp is None:
            timestamp = int(time.time())

        # Redis key format
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

        



if __name__ == "__main__":
    rag = GenerateRAGAnswer()
    query = "How are you"
    promt = rag.gen_prompt(query=query)
    print(promt)