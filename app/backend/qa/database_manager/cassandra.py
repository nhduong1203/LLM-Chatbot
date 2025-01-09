from cassandra.cluster import Cluster
from datetime import datetime, timezone
from uuid import uuid1
from datetime import datetime
from opentelemetry import trace
import os
import logging

logging.basicConfig(
    level=logging.INFO,  # Default log level
    format="%(asctime)s [%(levelname)s] %(message)s",  # Log format
    handlers=[
        logging.StreamHandler()  # Log to stdout (container best practice)
    ]
)
logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

class CassandraMessageStore:
    def __init__(self, cassandra_host=None, cassandra_port=None, keyspace="mlops"):
        # CASSANDRA_IP_ADDRESS or CASSANDRA_HOST
        self.cassandra_host = cassandra_host or os.getenv("CASSANDRA_HOST", "localhost")
        self.cassandra_port = cassandra_port or int(os.getenv("CASSANDRA_PORT", 9042))
        self.cluster = Cluster([self.cassandra_host], port=self.cassandra_port)
        self.session = self.cluster.connect()
        self.initialize_schema(cql_file_path="./init.cql")
        # self.session.set_keyspace(keyspace)

    def initialize_schema(self, cql_file_path):
        """Executes the schema initialization script from the provided CQL file."""
        try:
            logger.info(f"Initializing schema from {cql_file_path}")
            with open(cql_file_path, 'r') as file:
                commands = file.read()
            
            # Split commands to execute them separately
            for command in commands.split(';'):
                command = command.strip()
                if command:  # Ignore empty commands
                    logger.info(f"Executing CQL: {command}")
                    self.session.execute(command)
            
            logger.info("Schema initialization complete.")
            self.session.set_keyspace("mlops")
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            raise
    
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
                VALUES (?, ?, ?, ?, ?)
                """
                prepared = self.session.prepare(insert_query)

                # Execute the query
                self.session.execute(prepared, (user_id, conversation_id, role, message, timestamp))
                logger.info(f"Message saved: user_id={user_id}, conversation_id={conversation_id}")
            except Exception as e:
                span.record_exception(e)
                logger.info(f"Failed to save message: {e}")
    
    def close(self):
        self.cluster.shutdown()
