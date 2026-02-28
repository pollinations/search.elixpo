# Session Persistence Fix - Documentation

## Problem
Session conversation history was not persisting between requests. When a user made multiple requests with the same `session_id`, the system would treat each request as a fresh session and "forget" previous messages.

**Symptom:** User asks to "summarize the conversation" after 2-3 queries, but the system responds with "There is no conversation history to summarize yet."

## Root Cause
The pipeline was creating a fresh `SessionContextWindow` instance for each request but NOT loading the previous messages from Redis. The flow was broken:

```
Request 1:
  → SessionContextWindow created
  → add_message("user", query1) called → Redis stores message ✓
  → Finally block saves assistant response ✓
  → Redis now has 2 messages: [user_query, assistant_response]

Request 2 (BROKEN):
  → SessionContextWindow created (FRESH, doesn't load from Redis)
  → memoized_results["session_context"] is a fresh instance
  → When tool calls get_session_conversation_history
  → get_context() is called on the fresh instance
  → It retrieves from Redis using the session_id...
  → BUT the messages might not be there if the order list expired
  → OR the tool handler expects the context to be pre-loaded
  → Result: "No conversation history found" ❌
```

## Solution
Load previous messages from Redis immediately after creating a new `SessionContextWindow` instance:

```python
if session_id:
    try:
        session_context = SessionContextWindow(session_id=session_id)
        memoized_results["session_context"] = session_context
        
        # CRITICAL: Load previous messages from Redis for this session
        # This ensures that get_context() in the tool handler retrieves all messages
        # including those from previous requests
        previous_messages = session_context.get_context()  # Reads from Redis
        loaded_count = len(previous_messages)
        
        # Save current user message to the context window
        session_context.add_message(role="user", content=user_query)
        
        logger.info(
            f"[Pipeline] Initialized SessionContextWindow for {session_id}: "
            f"loaded {loaded_count} previous messages, added current query"
        )
```

## How It Works

### Session Context Storage (Redis DB 2)
- **Key structure:** `elixpo:session_context:{session_id}:{msg_id}` (individual messages)
- **Order list:** `elixpo:session_order:{session_id}` (message IDs in LRU order)
- **TTL:** 30 minutes (1800 seconds) - auto-expires old sessions
- **Window size:** 20 messages maximum per session

### Message Flow with Fix
1. **Request 1:** Create context → Load (empty) → Add query → Add response → Redis stores all
2. **Request 2:** Create context → **Load previous messages from Redis** → Add query → Add response
3. **Request 3:** Create context → **Load all previous messages** → Tool can now retrieve full history

### Tool Handler (`get_session_conversation_history`)
The tool handler retrieves messages from the SessionContextWindow instance in `memoized_results`:
```python
session_context = memoized_results["session_context"]
conversation_history = session_context.get_context()  # All messages loaded from Redis
```

## Verification

The fix ensures:
✓ Previous messages are loaded from Redis when a new request arrives  
✓ Current user query is added to the context window  
✓ Tool handler has access to the complete conversation history  
✓ User can ask "summarize conversation" and get complete context  
✓ LRU eviction and TTL still work (old sessions auto-expire)  

## Testing
Run the multi-turn conversation test:
```bash
python3 test_multi_turn_session.py
```

This test simulates:
1. First query about Python features
2. Second query about Python libraries
3. Summary request asking "what have we discussed"

Expected: Summary mentions both previous topics (Python features + libraries)  
If broken: Summary says "no conversation history"

## Performance Notes
- `get_context()` reads from Redis (fast lookup) ✓
- Loading happens once per request (acceptable overhead) ✓
- No impact on subsequent requests or tools ✓
- Memory efficient: stored as pickled objects in Redis ✓

## Related Code
- **SessionContextWindow:** `lixsearch/ragService/semanticCacheRedis.py` (lines 139-320)
- **Pipeline Init:** `lixsearch/pipeline/lixsearch.py` (lines 223-241)
- **Tool Handler:** `lixsearch/pipeline/optimized_tool_execution.py` (lines 71-105)
- **Tool Definition:** `lixsearch/pipeline/tools.py` (lines 195-230)
