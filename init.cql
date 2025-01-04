CREATE KEYSPACE IF NOT EXISTS mlops 
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
USE mlops;
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY, 
    username TEXT,
    email TEXT,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY,
    user_id UUID,
    started_at TIMESTAMP,
    ended_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    session_id UUID,
    message_id TIMEUUID,
    sender TEXT,  // 'user' hoặc 'bot'
    message TEXT,
    timestamp TIMESTAMP,
    PRIMARY KEY (session_id, message_id)
);

CREATE TABLE IF NOT EXISTS user_sessions (
    user_id UUID,
    session_id UUID,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    PRIMARY KEY (user_id, session_id)
) WITH CLUSTERING ORDER BY (session_id DESC);
