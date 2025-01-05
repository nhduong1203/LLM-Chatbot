from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
from datetime import datetime, timezone
from uuid import uuid1
from datetime import datetime
import opentelemetry.trace as tracer


class CassandraMessageStore:
    def __init__(self, cassandra_host, keyspace, username=None, password=None):
        auth_provider = PlainTextAuthProvider(username, password) if username and password else None
        self.cluster = Cluster([cassandra_host], auth_provider=auth_provider)
        self.session = self.cluster.connect()
        self.session.set_keyspace(keyspace)
    
    def save_message(self, user_id, conversation_id, message, role , timestamp=None):
        with tracer.start_as_current_span("save_message") as span:
            try:
                # Generate conversation ID (TIMEUUID) and default timestamp if not provided
                conversation_id = conversation_id or uuid1()  # Generate TIMEUUID
                timestamp = timestamp or datetime.now(timezone.utc)

                # Set tracing attributes
                span.set_attribute("user_id", str(user_id))
                span.set_attribute("conversation_id", str(conversation_id))
                span.set_attribute("role", role)
                span.set_attribute("message", message)
                span.set_attribute("timestamp", str(timestamp))

                # Insert query
                insert_query = """
                INSERT INTO messages (user_id, conversation_id, role, message, timestamp)
                VALUES (%s, %s, %s, %s, %s)
                """
                prepared = self.session.prepare(insert_query)

                # Execute the query
                self.session.execute(prepared, (user_id, conversation_id, role, message, timestamp))
                print(f"Message saved: user_id={user_id}, conversation_id={conversation_id}")
            except Exception as e:
                span.record_exception(e)
                print(f"Failed to save message: {e}")
    
    def close(self):
        self.cluster.shutdown()
