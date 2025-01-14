import os
import redis
from redis.commands.search.field import TextField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.exceptions import ResponseError
from opentelemetry import trace

class RedisVectorIndexManager:
    def __init__(self, redis_host=None, redis_port=None, vector_dimension=384):
        self.redis_host = redis_host or os.getenv("REDIS_HOST", "localhost")
        self.redis_port = redis_port or int(os.getenv("REDIS_PORT", 6379))
        self.vector_dimension = vector_dimension
        self.redis_client = redis.Redis(host=self.redis_host, port=self.redis_port, decode_responses=False)
        self.tracer = trace.get_tracer(__name__)

    def create_index(self, index_name):
        try:
            # Check if the index already exists
            if self.redis_client.ft(index_name).info():
                print(f"Index '{index_name}' already exists. Skipping creation.")
                return
        except ResponseError:
            # If _info() raises a ResponseError, the index does not exist
            pass

        # Define the schema for the index
        schema = (
            TextField("$.text", no_stem=True, as_name="text"),
            TextField("$.metadata", no_stem=True, as_name="metadata"),
            VectorField(
                "$.embedding",
                "FLAT",
                {
                    "TYPE": "FLOAT32",
                    "DIM": self.vector_dimension,
                    "DISTANCE_METRIC": "COSINE",
                },
                as_name="vector",
            ),
        )

        definition = IndexDefinition(prefix=[index_name], index_type=IndexType.JSON)

        try:
            # Create the index
            self.redis_client.ft(index_name).create_index(fields=schema, definition=definition)
            print(f"Index '{index_name}' created successfully.")
        except ResponseError as e:
            print(f"Error creating index '{index_name}': {e}")
            raise

    def store_chunks(self, doc_id, chunks_and_embeddings):
        with self.tracer.start_as_current_span("store_chunks_in_redis") as span:
            span.set_attribute("doc_id", doc_id)
            try:
                pipeline = self.redis_client.pipeline()
                for idx, (chunk, embedding) in enumerate(chunks_and_embeddings):
                    key = f"reference:{doc_id}:chunk:{idx}"
                    data_dict = {
                        "metadata": doc_id,
                        "text": chunk,
                        "embedding": embedding.tolist()
                    }
                    pipeline.json().set(key, "$", data_dict)
                    span.add_event(f"Prepared chunk {idx} for doc_id {doc_id}")

                # Execute the pipeline
                pipeline.execute()
                span.add_event(f"Stored all chunks for doc_id {doc_id}")

                # Split the doc_id by ':'
                parts = doc_id.split(':')
                user_id = parts[0]
                chat_id = parts[1]

                # Create an index
                index_name = f"reference:{user_id}:{chat_id}"
                span.add_event(f"Creating Redis index {index_name}")
                self.create_index(index_name)
            except Exception as e:
                span.record_exception(e)
                raise

# Example Usage
if __name__ == "__main__":
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    vector_dimension = 384

    manager = RedisVectorIndexManager(redis_host, redis_port, vector_dimension)

    # Example document ID and chunks
    doc_id = "user123:chat456"
    chunks_and_embeddings = [
        ("Chunk 1 text", [0.1, 0.2, 0.3]),
        ("Chunk 2 text", [0.4, 0.5, 0.6]),
    ]

    manager.store_chunks(doc_id, chunks_and_embeddings)
