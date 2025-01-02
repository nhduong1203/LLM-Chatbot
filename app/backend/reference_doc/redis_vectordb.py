from redis.commands.search.field import TextField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.exceptions import ResponseError

from opentelemetry import trace

tracer = trace.get_tracer(__name__)

VECTOR_DIMENSION = 384

def create_redis_index(redis_client, vector_dimension, index_name):
    try:
        # Check if the index already exists
        if redis_client.ft(index_name).info():
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
                "DIM": vector_dimension,
                "DISTANCE_METRIC": "COSINE",
            },
            as_name="vector",
        ),
    )

    definition = IndexDefinition(prefix=[index_name], index_type=IndexType.JSON)

    try:
        # Create the index
        redis_client.ft(index_name).create_index(fields=schema, definition=definition)
        print(f"Index '{index_name}' created successfully.")
    except ResponseError as e:
        print(f"Error creating index '{index_name}': {e}")
        raise


def store_chunks_in_redis(redis_client, doc_id, chunks_and_embeddings):
    with tracer.start_as_current_span("store_chunks_in_redis") as span:
        span.set_attribute("doc_id", doc_id)
        try:
            pipeline = redis_client.pipeline()
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
            INDEX_NAME = f"reference:{user_id}:{chat_id}"
            span.add_event(f"Creating Redis index {INDEX_NAME}")
            create_redis_index(redis_client, VECTOR_DIMENSION, INDEX_NAME)
        except Exception as e:
            span.record_exception(e)
            raise