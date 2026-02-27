from datetime import datetime
from loguru import logger 
from ragService.semanticCacheRedis import SemanticCacheRedis as SemanticCache
import random
import requests
import json
import re
from pipeline.tools import tools
from datetime import datetime, timezone
from sessions.conversation_cache import ConversationCacheManager
from pipeline.config import LOG_MESSAGE_QUERY_TRUNCATE, LOG_MESSAGE_CONTEXT_TRUNCATE, LOG_MESSAGE_PREVIEW_TRUNCATE, ERROR_MESSAGE_TRUNCATE
import os 
from dotenv import load_dotenv
from pipeline.config import (POLLINATIONS_ENDPOINT, 
                             CACHE_WINDOW_SIZE, CACHE_MAX_ENTRIES, CACHE_TTL_SECONDS, 
                             CACHE_SIMILARITY_THRESHOLD, CACHE_COMPRESSION_METHOD, 
                             CACHE_EMBEDDING_MODEL,
                             SEMANTIC_CACHE_DIR, CONVERSATION_CACHE_DIR, SEMANTIC_CACHE_TTL_SECONDS,
                             SEMANTIC_CACHE_SIMILARITY_THRESHOLD, REDIS_URL,
                             MIN_LINKS_TO_TAKE, MAX_LINKS_TO_TAKE, SEARCH_MAX_RESULTS, RETRIEVAL_TOP_K)
from pipeline.instruction import system_instruction, user_instruction, synthesis_instruction
from pipeline.optimized_tool_execution import optimized_tool_execution
from pipeline.utils import format_sse, get_model_server
from functionCalls.getImagePrompt import generate_prompt_from_image
import asyncio
load_dotenv()

POLLINATIONS_TOKEN = os.getenv("TOKEN")
MODEL = os.getenv("MODEL")
logger.debug(f"Model configured: {MODEL}")

INTERNAL_LEAK_PATTERNS = [
    r"\bthe user wants to know\b",
    r"\bi should\b",
    r"\blet me\b",
    r"\bfirst priority\b",
    r"\bquery_conversation_cache\b",
    r"\btool(?:s)?\b.*\b(use|call|execute)\b",
]

USER_FRIENDLY_MESSAGES = {
    "processing": "<TASK>Processing your request</TASK>",
    "analyzing": "<TASK>Analyzing your input</TASK>",
    "searching": "<TASK>Searching for information</TASK>",
    "fetching": "<TASK>Gathering relevant data</TASK>",
    "synthesizing": "<TASK>Preparing your answer</TASK>",
    "image_analysis": "<TASK>Analyzing provided content</TASK>",
    "generating": "<TASK>Generating results</TASK>",
    "finalizing": "<TASK>Finalizing response</TASK>",
    "complete": "<TASK>Done</TASK>",
}

def get_user_message(operation: str) -> str:
    return USER_FRIENDLY_MESSAGES.get(operation, "<TASK>Processing</TASK>")


def _decompose_query(query: str) -> list[str]:
    if not query or len(query) < 50:
        return [query]
    
    parts = re.split(r'\s+(?:and|or|also|additionally|furthermore)\s+', query, maxsplit=2)
    if len(parts) > 1:
        logger.info(f"[DECOMPOSITION] Split query into {len(parts)} parts")
        return [p.strip() for p in parts if p.strip()]
    
    if '?' in query:
        parts = query.split('?')
        if len(parts) > 1:
            questions = [p.strip() + '?' for p in parts[:-1] if p.strip()]
            if len(questions) > 1:
                logger.info(f"[DECOMPOSITION] Found {len(questions)} questions in query")
                return questions
    
    return [query]


def _looks_like_internal_reasoning(content: str) -> bool:
    if not content:
        return False
    probe = content[:2500].lower()
    matches = sum(1 for p in INTERNAL_LEAK_PATTERNS if re.search(p, probe))
    return matches >= 2


def _strip_internal_lines(content: str) -> str:
    if not content:
        return ""
    cleaned = []
    for line in content.splitlines():
        low = line.strip().lower()
        if (
            low.startswith("the user wants")
            or low.startswith("i should")
            or low.startswith("let me")
            or re.match(r"^\d+\.\s+(first|second|third|then|finally)\b", low)
        ):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


async def run_elixposearch_pipeline(user_query: str, user_image: str, event_id: str = None, request_id: str = None, session_id: str = None):
    """
    Main search pipeline with full caching and RAG support.
    
    Args:
        user_query: User search query
        user_image: Optional image URL for image-based search
        event_id: Optional event ID for SSE streaming
        request_id: Optional request ID for logging (generated if not provided)
        session_id: REQUIRED for cache isolation - unique session identifier
        
    Note:
        session_id is used throughout for cache isolation and conversation context.
        Each session maintains its own semantic cache and context window.
    """
    logger.info(
        f"[pipeline] session={session_id} Starting ElixpoSearch: "
        f"query='{user_query[:LOG_MESSAGE_QUERY_TRUNCATE]}...' image={bool(user_image)} "
        f"request_id={request_id}"
    )
    def emit_event(event_type, message):
        if event_id:
            return format_sse(event_type, message)
        return None

    original_user_query = user_query or ""
    image_only_mode = bool(user_image and not original_user_query.strip())

    initial_event = emit_event("INFO", get_user_message("processing"))
    if initial_event:
        yield initial_event
    try:
        current_utc_time = datetime.now(timezone.utc)
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {POLLINATIONS_TOKEN}"}

        async def sanitize_final_response(content: str, query: str, sources: list[str]) -> str:
            if not _looks_like_internal_reasoning(content):
                return content

            logger.warning("[FINAL] Detected internal reasoning leakage; rewriting final response")
            rewrite_prompt = [
                {
                    "role": "system",
                    "content": (
                        "You are lixSearch. Rewrite drafts into final user-facing answers only. "
                        "Never reveal internal reasoning, planning, tool strategy, cache logic, or step-by-step deliberation."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"User query: {query}\n\n"
                        "Draft response (contains internal notes, remove them):\n"
                        f"{content}\n\n"
                        "Return only the final answer in markdown."
                    ),
                },
            ]
            if sources:
                rewrite_prompt.append({
                    "role": "user",
                    "content": "Optional sources:\n" + "\n".join(sources[:5])
                })

            payload = {
                "model": MODEL,
                "messages": rewrite_prompt,
                "seed": random.randint(1000, 9999),
                "max_tokens": 1600,
                "stream": False,
            }
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        requests.post,
                        POLLINATIONS_ENDPOINT,
                        json=payload,
                        headers=headers,
                        timeout=20
                    ),
                    timeout=22.0
                )
                response.raise_for_status()
                response_data = response.json()
                rewritten = response_data["choices"][0]["message"].get("content", "").strip()
                if rewritten and not _looks_like_internal_reasoning(rewritten):
                    return rewritten
            except Exception as e:
                logger.warning(f"[FINAL] Rewrite failed, applying local sanitization fallback: {e}")

            stripped = _strip_internal_lines(content)
            if stripped and not _looks_like_internal_reasoning(stripped):
                return stripped

            fallback = f"Here is a concise update on '{query}'."
            if sources:
                fallback += "\n\n**Sources:**\n" + "\n".join([f"- {s}" for s in sources[:3]])
            return fallback
        
        try:
            from ipcService.coreServiceManager import get_core_embedding_service
            core_service = get_core_embedding_service()
            logger.info("[Pipeline] Connected to shared CoreEmbeddingService singleton via IPC")
        except Exception as e:
            logger.warning(f"[Pipeline] Could not connect to IPC CoreEmbeddingService: {e}")
            core_service = None
                   
        memoized_results = {
            "timezone_info": {},
            "web_searches": {},
            "fetched_urls": {},
            "youtube_metadata": {},
            "youtube_transcripts": {},
            "base64_cache": {},
            "context_sufficient": False,  
            "cache_hit": False,
            "cached_response": None
        }
        
        conversation_cache = ConversationCacheManager(
            window_size=CACHE_WINDOW_SIZE,
            max_entries=CACHE_MAX_ENTRIES,
            ttl_seconds=CACHE_TTL_SECONDS,
            compression_method=CACHE_COMPRESSION_METHOD,
            embedding_model=CACHE_EMBEDDING_MODEL,
            similarity_threshold=CACHE_SIMILARITY_THRESHOLD,
            cache_dir=CONVERSATION_CACHE_DIR
        )
        memoized_results["conversation_cache"] = conversation_cache
        logger.info(f"[Pipeline] Initialized Conversation Cache Manager (window_size={CACHE_WINDOW_SIZE}, max_entries={CACHE_MAX_ENTRIES})")
        
        if request_id:
            if conversation_cache.load_from_disk(session_id=request_id):
                logger.info(f"[Pipeline] Loaded conversation cache from disk (session: {request_id})")
        
        # Parse Redis URL for semantic cache initialization
        redis_host = "localhost"
        redis_port = 6379
        redis_db = 0
        if REDIS_URL:
            try:
                url_parts = REDIS_URL.replace("redis://", "").split("/")
                host_port = url_parts[0].split(":")
                redis_host = host_port[0]
                redis_port = int(host_port[1]) if len(host_port) > 1 else 6379
                redis_db = int(url_parts[1]) if len(url_parts) > 1 else 0
            except Exception as e:
                logger.warning(f"[Pipeline] Failed to parse REDIS_URL, using defaults: {e}")
        
        semantic_cache = SemanticCache(
            session_id=request_id or "pipeline",
            ttl_seconds=SEMANTIC_CACHE_TTL_SECONDS, 
            similarity_threshold=SEMANTIC_CACHE_SIMILARITY_THRESHOLD,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db
        )
        if request_id:
            semantic_cache.load_for_request(request_id)
            logger.info(f"[Pipeline] Loaded persistent Redis cache for request {request_id}")
        
        image_context_provided = False
        if image_only_mode:
            logger.info(f"[Pipeline] Image-only query detected. Generating search query from image...")
            try:
                image_event = emit_event("INFO", get_user_message("image_analysis"))
                if image_event:
                    yield image_event
                
                generated_query = await generate_prompt_from_image(user_image)
                user_query = generated_query
                image_context_provided = True
                logger.info(f"[Pipeline] Generated query from image: '{user_query}'")
                
                query_event = emit_event("INFO", get_user_message("analyzing"))
                if query_event:
                    yield query_event
            except Exception as e:
                logger.warning(f"[Pipeline] Failed to generate query from image, continuing with empty query: {e}")
                image_context_provided = False
        elif user_image and user_query.strip():
            logger.info(f"[Pipeline] Image + Query mode: Will analyze image in context of query")
            image_context_provided = True
        
        max_iterations = 3 
        current_iteration = 0
        collected_sources = []
        collected_images_from_web = []
        collected_similar_images = []
        final_message_content = None
        tool_call_count = 0
        
        query_components = _decompose_query(user_query)
        if len(query_components) > 1:
            logger.info(f"[DECOMPOSITION] Query decomposed into {len(query_components)} components for parallel processing")
            for i, component in enumerate(query_components, 1):
                logger.info(f"[DECOMPOSITION] Component {i}: {component[:80]}")
            memoized_results["query_components"] = query_components
        else:
            logger.info(f"[DECOMPOSITION] Query is single component, no decomposition needed")
            memoized_results["query_components"] = [user_query]
        rag_context = ""
        if core_service:
            try:
                retrieval_result = core_service.retrieve(user_query, top_k=3)
                if retrieval_result.get("count", 0) > 0:
                    rag_context = "\n".join([r["metadata"]["text"] for r in retrieval_result.get("results", [])])
                    logger.info(f"[Pipeline] Retrieved {retrieval_result.get('count', 0)} chunks from vector store")
            except Exception as e:
                logger.warning(f"[Pipeline] Vector store retrieval failed, continuing without context: {e}")
        else:
            logger.info("[Pipeline] Skipping vector store retrieval (model_server unavailable)")
        
        logger.info(f"[Pipeline] RAG context prepared: {len(rag_context)} chars")
        
        messages = [
            {
                "role": "system",
                "name": "elixposearch-agent-system",
                "content": system_instruction(rag_context, current_utc_time)
            },
            {
                "role": "user",
                "content": user_instruction(user_query, user_image)
            }
        ]

        while current_iteration < max_iterations:
            current_iteration += 1
            if messages and len(messages) > 0:
                for m in messages:
                    if m.get("role") == "assistant":
                        if m.get("content") is None or m.get("content") == "":
                            if "tool_calls" in m and len(m.get("tool_calls", [])) > 0:
                                m["content"] = f"Executing {len(m['tool_calls'])} tool(s)..."
                            else:
                                m["content"] = "Processing your request..."

            iteration_event = emit_event("INFO", get_user_message("searching"))
            if iteration_event:
                yield iteration_event
            if len(messages) > 8:
                trimmed = messages[:2] + messages[-6:]
                logger.info(f"[OPTIMIZATION] Trimmed messages from {len(messages)} to {len(trimmed)}")
                messages = trimmed
            
            payload = {
                "model": MODEL,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "seed": random.randint(1000, 9999),
                "max_tokens": 2000,
            }

            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        requests.post,
                        POLLINATIONS_ENDPOINT,
                        json=payload,
                        headers=headers,
                        timeout=120
                    ),
                    timeout=125.0
                )
                response.raise_for_status()
                response_data = response.json()
            except asyncio.TimeoutError:
                logger.error(f"API timeout at iteration {current_iteration}")
                if event_id:
                    yield format_sse("INFO", get_user_message("processing"))
                break
            except requests.exceptions.HTTPError as http_err:
                print(f"\n{'='*80}")
                print(f"[HTTP ERROR] Status Code: {http_err.response.status_code}")
                print(f"[HTTP ERROR] URL: {http_err.response.url}")
                print(f"[HTTP ERROR] Headers: {http_err.response.headers}")
                print(f"[HTTP ERROR] Response Text:\n{http_err.response.text}")
                print(f"{'='*80}\n")
                logger.error(f"Pollinations API HTTP error at iteration {current_iteration}: {http_err}")
                logger.error(f"Response content: {http_err.response.text}")
                if event_id:
                    yield format_sse("INFO", get_user_message("processing"))
                break
            except requests.exceptions.RequestException as e:
                print(f"\n{'='*80}")
                print(f"[REQUEST ERROR] Type: {type(e).__name__}")
                print(f"[REQUEST ERROR] Message: {str(e)}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"[REQUEST ERROR] Status Code: {e.response.status_code}")
                    print(f"[REQUEST ERROR] Response: {e.response.text}")
                print(f"{'='*80}\n")
                logger.error(f"Pollinations API request failed at iteration {current_iteration}: {e}")
                if event_id:
                    yield format_sse("INFO", get_user_message("processing"))
                break
            except Exception as e:
                print(f"\n{'='*80}")
                print(f"[UNEXPECTED ERROR] Type: {type(e).__name__}")
                print(f"[UNEXPECTED ERROR] Message: {str(e)}")
                print(f"{'='*80}\n")
                logger.error(f"Unexpected API error at iteration {current_iteration}: {e}", exc_info=True)
                if event_id:
                    yield format_sse("INFO", get_user_message("processing"))
                break
            assistant_message = response_data["choices"][0]["message"]
            
            if not assistant_message.get("content"):
                if assistant_message.get("tool_calls"):
                    assistant_message["content"] = "I'll help you with that. Let me gather the information you need."
                else:
                    assistant_message["content"] = "Processing your request..."
            
            if assistant_message.get("content") is None:
                assistant_message["content"] = ""
                
            messages.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls")
            logger.info(f"Tool calls suggested by model: {len(tool_calls) if tool_calls else 0} tools")
            if not tool_calls:
                final_message_content = assistant_message.get("content")
                logger.info(f"[COMPLETION] No tool calls found, setting final message: {final_message_content[:LOG_MESSAGE_PREVIEW_TRUNCATE] if final_message_content else 'EMPTY'}")
                break
            tool_outputs = []
            print(tool_calls)
            logger.info(f"Processing {len(tool_calls)} tool call(s):")
            
            fetch_calls = []
            web_search_calls = []
            other_calls = []
            for tool_call in tool_calls:
                fn_name = tool_call["function"]["name"]
                if fn_name == "fetch_full_text":
                    fetch_calls.append(tool_call)
                elif fn_name == "web_search":
                    web_search_calls.append(tool_call)
                else:
                    other_calls.append(tool_call)
            
            if web_search_calls and len(fetch_calls) < MIN_LINKS_TO_TAKE:
                urls_needed = MIN_LINKS_TO_TAKE - len(fetch_calls)
                logger.info(f"[URL-LIMITS] Web search detected but only {len(fetch_calls)} URLs to fetch. Need {urls_needed} more to meet minimum of {MIN_LINKS_TO_TAKE}")
                if event_id:
                    yield format_sse("INFO", get_user_message("fetching"))
            
            if len(fetch_calls) > MAX_LINKS_TO_TAKE:
                logger.info(f"[URL-LIMITS] Capping fetch_calls from {len(fetch_calls)} to {MAX_LINKS_TO_TAKE} (MAX_LINKS_TO_TAKE)")
                fetch_calls = fetch_calls[:MAX_LINKS_TO_TAKE]
            
            logger.info(f"[URL-LIMITS] Final URL fetch plan: {len(fetch_calls)} URLs (min={MIN_LINKS_TO_TAKE}, max={MAX_LINKS_TO_TAKE})")
            
            async def execute_tool_async(idx, tool_call, is_web_search=False):
                function_name = tool_call["function"]["name"]
                function_args = json.loads(tool_call["function"]["arguments"])
                logger.info(f"[Async Tool #{idx+1}] {function_name}")
                
                tool_result_gen = optimized_tool_execution(function_name, function_args, memoized_results, emit_event)
                tool_result = None
                image_urls = []
                if hasattr(tool_result_gen, '__aiter__'):
                    async for result in tool_result_gen:
                        if isinstance(result, str) and result.startswith("event:"):
                            pass
                        elif isinstance(result, tuple):
                            tool_result, image_urls = result
                        else:
                            tool_result = result
                else:
                    tool_result = await tool_result_gen if asyncio.iscoroutine(tool_result_gen) else tool_result_gen
                
                return {
                    "tool_call_id": tool_call["id"],
                    "name": function_name,
                    "result": tool_result,
                    "image_urls": image_urls
                }
            
            if web_search_calls:
                emit_sse = emit_event("INFO", get_user_message("fetching"))
                if emit_sse:
                    yield emit_sse
                web_search_results = await asyncio.gather(
                    *[execute_tool_async(idx, tc, True) for idx, tc in enumerate(web_search_calls)],
                    return_exceptions=True
                )
                for result in web_search_results:
                    if not isinstance(result, Exception):
                        if result["name"] == "web_search" and "current_search_urls" in memoized_results:
                            collected_sources.extend(memoized_results["current_search_urls"][:3])
                        tool_outputs.append({
                            "role": "tool",
                            "tool_call_id": result["tool_call_id"],
                            "name": result["name"],
                            "content": str(result["result"]) if result["result"] else "No result"
                        })
            
            for idx, tool_call in enumerate(other_calls):
                function_name = tool_call["function"]["name"]
                function_args = json.loads(tool_call["function"]["arguments"])
                logger.info(f"[Sequential Tool #{idx+1}] {function_name}")
                if event_id:
                    yield format_sse("INFO", get_user_message("processing"))
                
                tool_result_gen = optimized_tool_execution(function_name, function_args, memoized_results, emit_event)
                if hasattr(tool_result_gen, '__aiter__'):
                    tool_result = None
                    image_urls = []
                    async for result in tool_result_gen:
                        if isinstance(result, str) and result.startswith("event:"):
                            yield result
                        elif isinstance(result, tuple):
                            tool_result, image_urls = result
                        else:
                            tool_result = result
                    if function_name == "image_search" and image_urls:
                        if image_only_mode:
                            collected_similar_images.extend(image_urls)
                        else:
                            collected_images_from_web.extend(image_urls)
                else:
                    tool_result = await tool_result_gen if asyncio.iscoroutine(tool_result_gen) else tool_result_gen
                
                if function_name in ["transcribe_audio"]:
                    collected_sources.append(function_args.get("url"))
                
                tool_outputs.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": function_name,
                    "content": str(tool_result) if tool_result else "No result"
                })
            
            tool_call_count += len(tool_calls)
            
            if event_id:
                yield format_sse("INFO", get_user_message("processing"))
            
            if fetch_calls:
                logger.info(f"Executing {len(fetch_calls)} fetch_full_text calls in PARALLEL")
                if event_id:
                    yield format_sse("INFO", get_user_message("fetching"))
                
                async def execute_fetch(idx, tool_call):
                    function_name = tool_call["function"]["name"]
                    function_args = json.loads(tool_call["function"]["arguments"])
                    url = function_args.get('url', 'N/A')
                    logger.info(f"[PARALLEL FETCH #{idx+1}] {url[:60]}")
                    
                    tool_result_gen = optimized_tool_execution(function_name, function_args, memoized_results, emit_event)
                    tool_result = None
                    async for result in tool_result_gen:
                        if not isinstance(result, str) or not result.startswith("event:"):
                            tool_result = result
                    
                    return {
                        "tool_call_id": tool_call["id"],
                        "function_name": function_name,
                        "url": url,
                        "result": tool_result
                    }
                
                fetch_results = await asyncio.wait_for(
                    asyncio.gather(
                        *[execute_fetch(idx, tc) for idx, tc in enumerate(fetch_calls)],
                        return_exceptions=True
                    ),
                    timeout=8.0
                )
                
                ingest_tasks = []
                for fetch_result in fetch_results:
                    if isinstance(fetch_result, Exception):
                        logger.error(f"Fetch failed: {fetch_result}")
                        continue
                    
                    url = fetch_result["url"]
                    tool_result = fetch_result["result"]
                    
                    if len(collected_sources) < 5:
                        collected_sources.append(url)
                    
                    if core_service:
                        async def ingest_url_async(url_to_ingest):
                            try:
                                from ipcService.coreServiceManager import get_core_embedding_service
                                core_svc = get_core_embedding_service()
                                ingest_result = await asyncio.wait_for(
                                    asyncio.to_thread(core_svc.ingest_url, url_to_ingest),
                                    timeout=3.0
                                )
                                chunks = ingest_result.get('chunks_ingested', 0)
                                logger.info(f"[INGEST] {chunks} chunks from {url_to_ingest[:40]}")
                            except asyncio.TimeoutError:
                                logger.warning(f"[INGEST TIMEOUT] {url_to_ingest[:40]}")
                            except Exception as e:
                                logger.warning(f"[INGEST FAILED] {url_to_ingest[:40]}: {e}")
                        
                        ingest_tasks.append(ingest_url_async(url))
                    
                    tool_outputs.append({
                        "role": "tool",
                        "tool_call_id": fetch_result["tool_call_id"],
                        "name": "fetch_full_text",
                        "content": str(tool_result)[:500] if tool_result else "No result"
                    })
                
                if ingest_tasks:
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*ingest_tasks, return_exceptions=True),
                            timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        logger.warning("[INGESTION] Timeout reached, continuing anyway")
            messages.extend(tool_outputs)
            logger.info(f"Completed iteration {current_iteration}. Messages: {len(messages)}, Total tools: {tool_call_count}")
            if event_id:
                yield format_sse("INFO", get_user_message("processing"))
            

        if not final_message_content and current_iteration >= max_iterations:
            logger.info(f"[SYNTHESIS CONDITION MET] final_message_content={bool(final_message_content)}, current_iteration={current_iteration}, max_iterations={max_iterations}")
            if event_id:
                yield format_sse("INFO", get_user_message("synthesizing"))
            
            # RE-RETRIEVE from vector store AFTER ingesting all URLs
            logger.info("[SYNTHESIS] Re-retrieving context from vector store after ingestion...")
            try:
                from searching.main import retrieve_from_vector_store
                updated_rag_context = retrieve_from_vector_store(user_query, top_k=RETRIEVAL_TOP_K)
                if updated_rag_context:
                    rag_context_str = "\n".join([
                        f"- {item.get('text', '')[:200]}" 
                        for item in updated_rag_context if item.get('text')
                    ])
                    logger.info(f"[SYNTHESIS] Retrieved {len(updated_rag_context)} chunks after ingestion ({len(rag_context_str)} chars)")
                    if rag_context_str:
                        rag_context = rag_context_str
                else:
                    logger.warning("[SYNTHESIS] No additional context retrieved from vector store")
            except Exception as e:
                logger.warning(f"[SYNTHESIS] Failed to re-retrieve context: {e}")
            
            query_components = memoized_results.get("query_components", [user_query])
            if len(query_components) > 1:
                logger.info(f"[SYNTHESIS] Multi-component query synthesis:")
                for i, component in enumerate(query_components, 1):
                    logger.info(f"[SYNTHESIS] Component {i}: {component[:LOG_MESSAGE_PREVIEW_TRUNCATE]}")
                logger.info(f"[SYNTHESIS] Synthesizing {len(collected_sources)} total sources across {len(query_components)} components")
            
            logger.info("[SYNTHESIS] Starting synthesis of gathered information")
            synthesis_prompt = {
                "role": "user",
                "content": synthesis_instruction(user_query, image_context=image_context_provided)
            }
            
            original_msg_count = len(messages)
            if len(messages) > 6:
                messages = messages[:2] + messages[-4:]
                logger.info(f"[SYNTHESIS] Trimmed messages from {original_msg_count} to {len(messages)}")
            else:
                logger.info(f"[SYNTHESIS] Messages count: {len(messages)} (no trim needed)")
            
            messages.append(synthesis_prompt)
            payload = {
                "model": MODEL,
                "messages": messages,
                "seed": random.randint(1000, 9999),
                "max_tokens": 2500,
                "stream": False,
            }

            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        requests.post,
                        POLLINATIONS_ENDPOINT,
                        json=payload,
                        headers=headers,
                        timeout=20
                    ),
                    timeout=22.0
                )
                response.raise_for_status()
                response_data = response.json()
                logger.info(f"[SYNTHESIS] Raw API response status: {response.status_code}, response keys: {response_data.keys() if isinstance(response_data, dict) else 'unknown'}")
                logger.debug(f"[SYNTHESIS] Full response data: {json.dumps(response_data, indent=2)[:500]}")
                try:
                    message = response_data["choices"][0]["message"]
                    logger.debug(f"[SYNTHESIS] Message keys: {message.keys()}")
                    logger.debug(f"[SYNTHESIS] Content value: {repr(message.get('content'))}")
                    logger.debug(f"[SYNTHESIS] Tool calls: {message.get('tool_calls')}")
                    
                    final_message_content = message.get("content", "").strip()
                    
                    if not final_message_content and "reasoning_content" in message:
                        final_message_content = message.get("reasoning_content", "").strip()
                        logger.info("[SYNTHESIS] Using reasoning_content as fallback")
                    
                    if not final_message_content and message.get("tool_calls"):
                        logger.warning(f"[SYNTHESIS] Model returned tool_calls instead of content in synthesis")
                        final_message_content = f"I searched for information about '{user_query}' and gathered {len(collected_sources)} relevant sources."
                        if collected_sources:
                            final_message_content += f"\n\nKey sources:\n" + "\n".join([f"- {src}" for src in collected_sources[:5]])
                    
                    if not final_message_content:
                        logger.error(f"[SYNTHESIS] API returned empty content after all fallbacks. Full response: {response_data}")
                        final_message_content = f"I processed your query about '{user_query}'."
                        if collected_sources:
                            final_message_content += f"\n\nRelevant sources found:\n" + "\n".join([f"- {src}" for src in collected_sources[:5]])
                    else:
                        logger.info(f"[SYNTHESIS] Successfully extracted content. Length: {len(final_message_content)}")
                except (KeyError, IndexError, TypeError) as e:
                    logger.error(f"[SYNTHESIS] Failed to extract content from response. Expected structure not found. Error: {e}")
                    logger.error(f"[SYNTHESIS] Response data keys: {response_data.keys() if isinstance(response_data, dict) else 'Not a dict'}")
                    logger.error(f"[SYNTHESIS] Full response: {response_data}")
                    final_message_content = f"I gathered {len(collected_sources)} relevant sources about '{user_query}'."
                    if collected_sources:
                        final_message_content += f"\n\nRelevant sources:\n" + "\n".join([f"- {src}" for src in collected_sources[:5]])
            except asyncio.TimeoutError:
                logger.error("[SYNTHESIS TIMEOUT] Request timed out")
                logger.warning(f"[SYNTHESIS FALLBACK] Using collected information as response")
                final_message_content = f"I found relevant information about '{user_query}':"
                if collected_sources:
                    final_message_content += f"\n\n{', '.join(collected_sources[:3])}"
            except requests.exceptions.HTTPError as http_err:
                logger.error(f"[SYNTHESIS HTTP ERROR] Status Code: {http_err.response.status_code} - {str(http_err)[:ERROR_MESSAGE_TRUNCATE]}")
                final_message_content = f"I found relevant information about '{user_query}':"
                if collected_sources:
                    final_message_content += f"\n\n{', '.join(collected_sources[:3])}"
            except requests.exceptions.RequestException as e:
                logger.error(f"[SYNTHESIS REQUEST ERROR] {type(e).__name__}: {str(e)[:ERROR_MESSAGE_TRUNCATE]}")
                final_message_content = f"I found relevant information about '{user_query}':"
                if collected_sources:
                    final_message_content += f"\n\n{', '.join(collected_sources[:3])}"
            except Exception as e:
                logger.error(f"[SYNTHESIS ERROR] {type(e).__name__}: {str(e)[:ERROR_MESSAGE_TRUNCATE]}", exc_info=True)
                final_message_content = f"I found relevant information about '{user_query}':"
                if collected_sources:
                    final_message_content += f"\n\n{', '.join(collected_sources[:5])}"

        if final_message_content:
            final_message_content = await sanitize_final_response(final_message_content, user_query, collected_sources)
            logger.info(f"Preparing optimized final response")
            logger.info(f"[FINAL] final_message_content starts with: {final_message_content[:LOG_MESSAGE_PREVIEW_TRUNCATE] if final_message_content else 'None'}")
            logger.info(f"[FINAL] final_message_content starts with: {final_message_content[:LOG_MESSAGE_PREVIEW_TRUNCATE] if final_message_content else 'None'}")
            
            if (collected_images_from_web or collected_similar_images) and final_message_content in ["Processing your request...", "I'll help you with that. Let me gather the information you need."]:
                logger.info(f"[FINAL] Detected placeholder content with collected images. Triggering synthesis...")
                synthesis_prompt = {
                    "role": "user",
                    "content": f"Based on the image analysis and search results, provide a final comprehensive answer to: {user_query}"
                }
                messages.append(synthesis_prompt)
                
                payload = {
                    "model": MODEL,
                    "messages": messages,
                    "seed": random.randint(1000, 9999),
                    "max_tokens": 2500,
                    "stream": False,
                }
                
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            requests.post,
                            POLLINATIONS_ENDPOINT,
                            json=payload,
                            headers=headers,
                            timeout=120
                        ),
                        timeout=125.0
                    )
                    response.raise_for_status()
                    response_data = response.json()
                    synthesis_response = response_data["choices"][0]["message"].get("content", "")
                    if synthesis_response:
                        final_message_content = synthesis_response
                        logger.info(f"[FINAL] Synthesis generated new content, length: {len(final_message_content)}")
                except Exception as e:
                    logger.warning(f"[FINAL] Synthesis generation failed: {e}, using existing content")
            
            has_image_markdown = bool(re.search(r'!\[([^\]]*)\]\(https?://[^\)]+\)', final_message_content))
            image_count_in_synthesis = len(re.findall(r'!\[', final_message_content))
            logger.info(f"[FINAL] Synthesis content has embedded images: {has_image_markdown} ({image_count_in_synthesis} found)")
            existing_image_urls = set(re.findall(r'!\[[^\]]*\]\((https?://[^\)]+)\)', final_message_content))
            
            response_parts = [final_message_content]
            images_added = 0
            
            image_pool = collected_similar_images if (image_only_mode and collected_similar_images) else collected_images_from_web
            if image_pool:
                deduped_pool = []
                seen_urls = set()
                for img in image_pool:
                    if img and img.startswith("http") and img not in seen_urls:
                        seen_urls.add(img)
                        deduped_pool.append(img)

                missing_images = [img for img in deduped_pool if img not in existing_image_urls]
                if missing_images:
                    desired_total = min(10, max(4, len(deduped_pool)))
                    images_to_add = max(0, desired_total - len(existing_image_urls))
                    if images_to_add > 0:
                        title = "Similar Images" if image_only_mode else "Related Images"
                        label = "Similar Image" if image_only_mode else "Image"
                        response_parts.append(f"\n\n**{title}:**\n")
                        for img in missing_images[:images_to_add]:
                            response_parts.append(f"![{label}]({img})\n")
                            images_added += 1
                logger.info(f"[FINAL] Added {images_added} images from collected results (existing in synthesis: {len(existing_image_urls)})")
            elif has_image_markdown:
                logger.info(f"[FINAL] No collected image pool; using {image_count_in_synthesis} image references from synthesis")
            if collected_sources:
                response_parts.append("\n\n---\n**Sources:**\n")
                unique_sources = sorted(list(set(collected_sources)))[:5]
                for i, src in enumerate(unique_sources):
                    response_parts.append(f"{i+1}. [{src}]({src})\n")
            response_with_sources = "".join(response_parts)
            
            try:
                cache_metadata = {
                    "sources": collected_sources[:5],
                    "tool_calls": tool_call_count,
                    "iteration": current_iteration,
                    "had_cache_hit": memoized_results.get("cache_hit", False)
                }
                conversation_cache.add_to_cache(
                    query=user_query, 
                    response=final_message_content,
                    metadata=cache_metadata
                )
                cache_stats = conversation_cache.get_cache_stats()
                logger.info(f"[Pipeline] Saved to conversation cache. Stats: {cache_stats}")
            except Exception as e:
                logger.warning(f"[Pipeline] Failed to save to conversation cache: {e}")
            
            if event_id:
                yield format_sse("INFO", get_user_message("finalizing"))
                yield format_sse("final", response_with_sources)
            else:
                yield response_with_sources
            return
        else:
            error_msg = f"[ERROR] ElixpoSearch failed - no final content after {max_iterations} iterations (tool_calls: {tool_call_count})"
            logger.error(error_msg)
            logger.error(f"[DIAGNOSTIC] final_message_content is: {repr(final_message_content)}, type: {type(final_message_content)}")
            logger.error(f"[DIAGNOSTIC] collected_sources: {collected_sources}, tool_call_count: {tool_call_count}")
            if collected_sources or tool_call_count > 0:
                logger.warning(f"[FALLBACK] Generating response from {len(collected_sources)} sources and {tool_call_count} tools")
                final_message_content = f"I found relevant information about '{user_query}':"
                if collected_sources:
                    final_message_content += f"\n\n{', '.join(collected_sources[:3])}"
                
                response_parts = [final_message_content]
                if collected_sources:
                    response_parts.append("\n\n---\n**Sources:**\n")
                    unique_sources = sorted(list(set(collected_sources)))[:5]
                    for i, src in enumerate(unique_sources):
                        response_parts.append(f"{i+1}. [{src}]({src})\n")
                response_with_fallback = "".join(response_parts)
                
                if event_id:
                    yield format_sse("INFO", get_user_message("finalizing"))
                    chunk_size = 8000
                    for i in range(0, len(response_with_fallback), chunk_size):
                        chunk = response_with_fallback[i:i+chunk_size]
                        event_name = "final" if i + chunk_size >= len(response_with_fallback) else "final-part"
                        yield format_sse(event_name, chunk)
                else:
                    yield response_with_fallback
                return
            else:
                if event_id:
                    yield format_sse("INFO", get_user_message("complete"))
                return
    except Exception as e:
        error_msg = str(e) if str(e) else f"Empty exception: {type(e).__name__}"
        logger.error(f"Pipeline error: {error_msg}", exc_info=True)
        logger.error(f"[DEBUG] Exception type: {type(e).__name__}, Args: {e.args}")
        if event_id:
            yield format_sse("INFO", get_user_message("complete"))
    finally:
        if request_id:
            semantic_cache.save_for_request(request_id)
            logger.info(f"[Pipeline] Saved persistent cache for request {request_id}")
            
            try:
                if "conversation_cache" in memoized_results:
                    conversation_cache.save_to_disk(session_id=request_id)
                    cache_stats = conversation_cache.get_cache_stats()
                    logger.info(f"[Pipeline] Saved conversation cache to disk: {cache_stats}")
            except Exception as e:
                logger.warning(f"[Pipeline] Failed to save conversation cache: {e}")
        
        logger.info("Optimized Search Completed")
