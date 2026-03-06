from datetime import datetime
from loguru import logger 
from ragService.semanticCacheRedis import SemanticCacheRedis as SemanticCache, SessionContextWindow
import random
import requests
import json
import re
from pipeline.tools import tools
from datetime import datetime, timezone
from sessions.conversation_cache import ConversationCacheManager

import os 
from dotenv import load_dotenv
from pipeline.config import *
from pipeline.instruction import system_instruction
from pipeline.instruction import user_instruction
from pipeline.instruction import synthesis_instruction
from pipeline.instruction import (
    deep_search_gating_instruction,
    deep_search_sub_query_instruction,
    deep_search_final_synthesis_instruction,
)
from pipeline.optimized_tool_execution import optimized_tool_execution
from pipeline.utils import format_sse, get_model_server
from pipeline.sse_messages import get_status_message, SSEStatusTracker
from functionCalls.getImagePrompt import generate_prompt_from_image, describe_image, replyFromImage
import asyncio
load_dotenv()

POLLINATIONS_TOKEN = os.getenv("TOKEN")
MODEL = LLM_MODEL
logger.debug(f"Model configured: {MODEL}")

def _scrub_tool_names(text: str) -> str:
    if not text:
        return text
    return LEAKED_TOOL_RE.sub("", text).strip()

def get_user_message(operation: str) -> str:
    return get_status_message(operation)


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

async def _decompose_query_with_llm(query: str, headers: dict, max_parts: int = TOPIC_DECOMPOSITION_MAX_PARTS) -> list[str]:
    decomposition_prompt = [
        {
            "role": "system",
            "content": (
                f"You are a query decomposition engine. Break the following query into "
                f"2 to {max_parts} focused sub-topics for comprehensive research. "
                f"Return ONLY a JSON array of strings, each being a focused sub-question. "
                f'Example: ["What is X?", "How does X compare to Y?", "Recent developments in X"]'
            )
        },
        {
            "role": "user",
            "content": query
        }
    ]

    payload = {
        "model": MODEL,
        "messages": decomposition_prompt,
        "seed": random.randint(1000, 9999),
        "max_tokens": 500,
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
            timeout=float(TOPIC_DECOMPOSITION_TIMEOUT)
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        parts = json.loads(content)
        if isinstance(parts, list) and all(isinstance(p, str) for p in parts):
            valid = [p.strip() for p in parts if 10 <= len(p.strip()) <= 200]
            if valid:
                logger.info(f"[DECOMPOSITION] LLM decomposed query into {len(valid)} sub-topics")
                return valid[:max_parts]
    except Exception as e:
        logger.warning(f"[DECOMPOSITION] LLM decomposition failed: {e}")

    return [query]

async def _evaluate_deep_search_need(query: str, headers: dict) -> bool:
    gating_messages = [
        {"role": "system", "content": "You are a query complexity evaluator. Return only JSON."},
        {"role": "user", "content": deep_search_gating_instruction(query)},
    ]
    payload = {
        "model": MODEL,
        "messages": gating_messages,
        "seed": random.randint(1000, 9999),
        "max_tokens": 200,
        "stream": False,
    }
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                requests.post,
                POLLINATIONS_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=15
            ),
            timeout=18.0
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        result = json.loads(content)
        needs = result.get("needs_deep_search", True)
        reason = result.get("reason", "")
        logger.info(f"[DeepSearch] Gating LLM verdict: needs_deep_search={needs}, reason={reason}")
        return bool(needs)
    except Exception as e:
        logger.warning(f"[DeepSearch] Gating LLM call failed ({e}), defaulting to complexity heuristic")
        return None

async def _execute_deep_search_sub_query(
    sub_query: str,
    original_query: str,
    sub_query_index: int,
    total_sub_queries: int,
    headers: dict,
    memoized_results: dict,
    emit_event,
    core_service,
    current_utc_time,
):
    collected_sources = []
    collected_images = []

    rag_context = ""
    if core_service:
        try:
            retrieval_result = core_service.retrieve(sub_query, top_k=3)
            if retrieval_result.get("count", 0) > 0:
                rag_context = "\n".join(
                    [r["metadata"]["text"] for r in retrieval_result.get("results", [])]
                )
        except Exception:
            pass

    messages = [
        {
            "role": "system",
            "name": "elixposearch-agent-system",
            "content": system_instruction(rag_context, current_utc_time, is_detailed=True),
        },
        {
            "role": "user",
            "content": deep_search_sub_query_instruction(
                sub_query, original_query, sub_query_index, total_sub_queries
            ),
        },
    ]

    final_content = None
    tool_call_count = 0

    for iteration in range(1, DEEP_SEARCH_MAX_ITERATIONS_PER_SUB + 1):
        if len(messages) > 8:
            messages = messages[:2] + messages[-6:]

        for m in messages:
            if m.get("role") == "assistant" and not m.get("content"):
                if m.get("tool_calls"):
                    m["content"] = f"Executing {len(m['tool_calls'])} tool(s)..."
                else:
                    m["content"] = "Researching..."

        payload = {
            "model": MODEL,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "seed": random.randint(1000, 9999),
            "max_tokens": DEEP_SEARCH_MAX_TOKENS_PER_SUB,
        }

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    requests.post,
                    POLLINATIONS_ENDPOINT,
                    json=payload,
                    headers=headers,
                    timeout=45
                ),
                timeout=50.0,
            )
            response.raise_for_status()
            response_data = response.json()
        except Exception as e:
            logger.error(f"[DeepSearch:Sub{sub_query_index}] API error at iteration {iteration}: {e}")
            break

        assistant_message = response_data["choices"][0]["message"]
        if not assistant_message.get("content"):
            if assistant_message.get("tool_calls"):
                assistant_message["content"] = "Gathering information..."
            else:
                assistant_message["content"] = "Researching..."

        messages.append(assistant_message)
        tool_calls = assistant_message.get("tool_calls")

        if not tool_calls:
            final_content = assistant_message.get("content")
            logger.info(f"[DeepSearch:Sub{sub_query_index}] Iteration {iteration}: no tool calls, final content ready ({len(final_content or '')} chars)")
            break

        logger.info(f"[DeepSearch:Sub{sub_query_index}] Iteration {iteration}: {len(tool_calls)} tool calls")
        tool_outputs = []
        fetch_calls = []
        web_search_calls = []
        other_calls = []

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            if fn_name == "fetch_full_text":
                fetch_calls.append(tc)
            elif fn_name == "web_search":
                web_search_calls.append(tc)
            else:
                other_calls.append(tc)

        fetch_calls = fetch_calls[:DEEP_SEARCH_MAX_LINKS_PER_SUB]
        tool_call_count += len(tool_calls)

        if web_search_calls:
            async def _exec_ws(idx, tc):
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                logger.info(f"[DeepSearch:Sub{sub_query_index}] WebSearch #{idx+1}: {fn_args.get('query', '')[:50]}")
                tool_result = None
                async for result in optimized_tool_execution(fn_name, fn_args, memoized_results, emit_event):
                    if isinstance(result, tuple):
                        tool_result = result[0]
                    elif isinstance(result, str) and not result.startswith("event:"):
                        tool_result = result
                return {"tool_call_id": tc["id"], "name": fn_name, "result": tool_result}

            ws_results = await asyncio.gather(
                *[_exec_ws(idx, tc) for idx, tc in enumerate(web_search_calls)],
                return_exceptions=True,
            )
            for r in ws_results:
                if not isinstance(r, Exception):
                    if "current_search_urls" in memoized_results:
                        collected_sources.extend(memoized_results["current_search_urls"][:3])
                    tool_outputs.append({
                        "role": "tool",
                        "tool_call_id": r["tool_call_id"],
                        "name": r["name"],
                        "content": str(r["result"]) if r["result"] else "No result",
                    })

        for tc in other_calls:
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"])
            logger.info(f"[DeepSearch:Sub{sub_query_index}] Tool: {fn_name}")
            tool_result = None
            image_urls = []
            tool_result_gen = optimized_tool_execution(fn_name, fn_args, memoized_results, emit_event)
            if hasattr(tool_result_gen, '__aiter__'):
                async for result in tool_result_gen:
                    if isinstance(result, tuple):
                        tool_result, image_urls = result
                    elif isinstance(result, str) and not result.startswith("event:"):
                        tool_result = result
            if fn_name == "image_search" and image_urls:
                collected_images.extend(image_urls)
            tool_outputs.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": fn_name,
                "content": str(tool_result) if tool_result else "No result",
            })

        if fetch_calls:
            async def _exec_fetch(idx, tc):
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                url = fn_args.get("url", "")
                logger.info(f"[DeepSearch:Sub{sub_query_index}] Fetch #{idx+1}: {url[:60]}")
                tool_result = None
                async for result in optimized_tool_execution(fn_name, fn_args, memoized_results, emit_event):
                    if not isinstance(result, str) or not result.startswith("event:"):
                        tool_result = result
                return {"tool_call_id": tc["id"], "url": url, "result": tool_result}

            try:
                fetch_results = await asyncio.wait_for(
                    asyncio.gather(
                        *[_exec_fetch(idx, tc) for idx, tc in enumerate(fetch_calls)],
                        return_exceptions=True,
                    ),
                    timeout=8.0,
                )
            except (asyncio.TimeoutError, TimeoutError):
                logger.warning(f"[DeepSearch:Sub{sub_query_index}] Fetch timeout")
                fetch_results = []

            for fr in fetch_results:
                if isinstance(fr, Exception):
                    continue
                url = fr.get("url", "")
                if url and len(collected_sources) < 6:
                    collected_sources.append(url)
                tool_outputs.append({
                    "role": "tool",
                    "tool_call_id": fr["tool_call_id"],
                    "name": "fetch_full_text",
                    "content": str(fr["result"])[:500] if fr["result"] else "No result",
                })

        messages.extend(tool_outputs)

    if not final_content:
        logger.info(f"[DeepSearch:Sub{sub_query_index}] Forcing synthesis after {DEEP_SEARCH_MAX_ITERATIONS_PER_SUB} iterations")
        synthesis_messages = messages[:2] + messages[-4:] if len(messages) > 6 else messages
        synthesis_messages.append({
            "role": "user",
            "content": synthesis_instruction(sub_query, is_detailed=True),
        })
        try:
            resp = await asyncio.wait_for(
                asyncio.to_thread(
                    requests.post,
                    POLLINATIONS_ENDPOINT,
                    json={
                        "model": MODEL,
                        "messages": synthesis_messages,
                        "seed": random.randint(1000, 9999),
                        "max_tokens": DEEP_SEARCH_MAX_TOKENS_PER_SUB,
                        "stream": False,
                    },
                    headers=headers,
                    timeout=20,
                ),
                timeout=22.0,
            )
            resp.raise_for_status()
            final_content = resp.json()["choices"][0]["message"].get("content", "").strip()
        except Exception as e:
            logger.error(f"[DeepSearch:Sub{sub_query_index}] Forced synthesis failed: {e}")
            final_content = f"Research on '{sub_query}' gathered {len(collected_sources)} sources."

    logger.info(
        f"[DeepSearch:Sub{sub_query_index}] Complete: {len(final_content or '')} chars, "
        f"{len(collected_sources)} sources, {tool_call_count} tool calls"
    )
    return final_content or "", collected_sources, collected_images

async def _deep_search_final_synthesis(
    original_query: str,
    sub_results: list,
    headers: dict,
) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are lixSearch. Combine multiple research findings into a single "
                "comprehensive, well-structured answer. Never mention sub-queries, "
                "research threads, or internal processes. "
                "NEVER mention internal tool names, function calls, or cache operations."
            ),
        },
        {
            "role": "user",
            "content": deep_search_final_synthesis_instruction(original_query, sub_results),
        },
    ]

    payload = {
        "model": MODEL,
        "messages": messages,
        "seed": random.randint(1000, 9999),
        "max_tokens": DEEP_SEARCH_FINAL_SYNTHESIS_MAX_TOKENS,
        "stream": False,
    }

    response = await asyncio.wait_for(
        asyncio.to_thread(
            requests.post,
            POLLINATIONS_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=30,
        ),
        timeout=35.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"].get("content", "").strip()

async def _run_deep_search_pipeline(
    user_query: str,
    user_image: str,
    event_id: str,
    session_id: str,
    emit_event,
):
    logger.info(f"[DeepSearch] Starting deep search for: '{user_query[:80]}'")

    current_utc_time = datetime.now(timezone.utc)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {POLLINATIONS_TOKEN}",
    }

    core_service = None
    try:
        from ipcService.coreServiceManager import get_core_embedding_service
        core_service = get_core_embedding_service()
    except Exception as e:
        logger.warning(f"[DeepSearch] IPC CoreEmbeddingService unavailable: {e}")

    session_context = None
    if session_id:
        try:
            session_context = SessionContextWindow(session_id=session_id)
            session_context.add_message(role="user", content=user_query)
        except Exception as e:
            logger.warning(f"[DeepSearch] SessionContextWindow init failed: {e}")

    memoized_results = {
        "timezone_info": {},
        "web_searches": {},
        "fetched_urls": {},
        "youtube_metadata": {},
        "youtube_transcripts": {},
        "base64_cache": {},
        "context_sufficient": False,
        "cache_hit": False,
        "cached_response": None,
        "session_id": session_id or "",
        "generated_images": [],
    }

    _embed_fn = core_service.embed_single_text if core_service else None
    conversation_cache = ConversationCacheManager(
        window_size=CACHE_WINDOW_SIZE,
        max_entries=CACHE_MAX_ENTRIES,
        ttl_seconds=CACHE_TTL_SECONDS,
        compression_method=CACHE_COMPRESSION_METHOD,
        embedding_model=CACHE_EMBEDDING_MODEL,
        similarity_threshold=CACHE_SIMILARITY_THRESHOLD,
        cache_dir=CONVERSATION_CACHE_DIR,
        embed_fn=_embed_fn,
    )
    memoized_results["conversation_cache"] = conversation_cache
    if session_id:
        try:
            conversation_cache.load_from_disk(session_id=session_id)
        except Exception as e:
            logger.warning(f"[DeepSearch] Failed to load conversation cache: {e}")

    semantic_cache = None
    try:
        semantic_cache = SemanticCache(
            session_id=session_id or "pipeline",
            ttl_seconds=SEMANTIC_CACHE_TTL_SECONDS,
            similarity_threshold=SEMANTIC_CACHE_SIMILARITY_THRESHOLD,
            redis_host=SEMANTIC_CACHE_REDIS_HOST,
            redis_port=SEMANTIC_CACHE_REDIS_PORT,
            redis_db=SEMANTIC_CACHE_REDIS_DB,
        )
        if session_id:
            semantic_cache.load_for_request(session_id)
    except Exception as e:
        logger.warning(f"[DeepSearch] Semantic cache init failed: {e}")

    decompose_event = emit_event("INFO", "<TASK>Analyzing query for deep search</TASK>")
    if decompose_event:
        yield decompose_event

    sub_queries = await _decompose_query_with_llm(
        user_query, headers, max_parts=DEEP_SEARCH_MAX_SUB_QUERIES
    )
    logger.info(f"[DeepSearch] Decomposed into {len(sub_queries)} sub-queries: {sub_queries}")

    if len(sub_queries) <= 1:
        from pipeline.queryDecomposition import QueryAnalyzer
        analyzer = QueryAnalyzer()
        proposed = analyzer.propose_decomposition(user_query)
        if len(proposed) > 1:
            sub_queries = [sq.text for sq in proposed[:DEEP_SEARCH_MAX_SUB_QUERIES]]
            logger.info(f"[DeepSearch] Aspect-based fallback: {len(sub_queries)} sub-queries")

    plan_event = emit_event(
        "INFO",
        f"<TASK>Deep searching {len(sub_queries)} aspects of your question</TASK>",
    )
    if plan_event:
        yield plan_event

    all_sub_results = []
    all_collected_sources = []
    all_collected_images = []

    for sq_idx, sub_query in enumerate(sub_queries, 1):
        logger.info(f"[DeepSearch] Sub-query {sq_idx}/{len(sub_queries)}: '{sub_query[:80]}'")

        sq_event = emit_event(
            "INFO",
            f"<TASK>Researching ({sq_idx}/{len(sub_queries)}): {sub_query[:60]}</TASK>",
        )
        if sq_event:
            yield sq_event

        try:
            sq_response, sq_sources, sq_images = await asyncio.wait_for(
                _execute_deep_search_sub_query(
                    sub_query=sub_query,
                    original_query=user_query,
                    sub_query_index=sq_idx,
                    total_sub_queries=len(sub_queries),
                    headers=headers,
                    memoized_results=memoized_results,
                    emit_event=emit_event,
                    core_service=core_service,
                    current_utc_time=current_utc_time,
                ),
                timeout=float(DEEP_SEARCH_TIMEOUT_PER_SUB),
            )

            if sq_response:
                sq_response = _scrub_tool_names(sq_response)
                all_sub_results.append((sub_query, sq_response, sq_sources))
                all_collected_sources.extend(sq_sources)
                all_collected_images.extend(sq_images)

                if event_id:
                    yield format_sse("RESPONSE", sq_response)
                else:
                    yield sq_response

                logger.info(
                    f"[DeepSearch] Sub-query {sq_idx} complete: "
                    f"{len(sq_response)} chars, {len(sq_sources)} sources"
                )
            else:
                logger.warning(f"[DeepSearch] Sub-query {sq_idx} returned empty response")

        except asyncio.TimeoutError:
            logger.error(f"[DeepSearch] Sub-query {sq_idx} timed out after {DEEP_SEARCH_TIMEOUT_PER_SUB}s")
            timeout_event = emit_event(
                "INFO",
                f"<TASK>Research thread {sq_idx} timed out, continuing</TASK>",
            )
            if timeout_event:
                yield timeout_event
        except Exception as e:
            logger.error(f"[DeepSearch] Sub-query {sq_idx} failed: {e}", exc_info=True)

    if len(all_sub_results) > 1:
        synth_event = emit_event("INFO", "<TASK>Combining all research into final answer</TASK>")
        if synth_event:
            yield synth_event

        try:
            final_response = await _deep_search_final_synthesis(
                original_query=user_query,
                sub_results=all_sub_results,
                headers=headers,
            )

            if final_response:
                final_response = _scrub_tool_names(final_response)

                if all_collected_sources:
                    unique_sources = sorted(set(all_collected_sources))[:8]
                    source_block = "\n\n---\n**Sources:**\n"
                    for i, src in enumerate(unique_sources, 1):
                        source_block += f"{i}. [{src}]({src})\n"
                    final_response += source_block

                if event_id:
                    yield format_sse("RESPONSE", final_response)
                else:
                    yield final_response

        except Exception as e:
            logger.error(f"[DeepSearch] Final synthesis failed: {e}", exc_info=True)

    elif len(all_sub_results) == 1:
        _sq, _resp, _srcs = all_sub_results[0]
        if _srcs:
            unique_sources = sorted(set(_srcs))[:5]
            source_block = "\n\n---\n**Sources:**\n"
            for i, src in enumerate(unique_sources, 1):
                source_block += f"{i}. [{src}]({src})\n"
            source_response = _resp + source_block
            if event_id:
                yield format_sse("RESPONSE", source_response)
            else:
                yield source_response

    combined_content = "\n\n".join(r[1] for r in all_sub_results) if all_sub_results else None
    if combined_content:
        memoized_results["final_response"] = combined_content
        try:
            cache_metadata = {
                "sources": all_collected_sources[:8],
                "deep_search": True,
                "sub_queries": len(all_sub_results),
            }
            _cache_embedding = None
            if core_service:
                try:
                    _cache_embedding = core_service.embed_single_text(user_query)
                except Exception:
                    pass
            conversation_cache.add_to_cache(
                query=user_query,
                response=combined_content,
                metadata=cache_metadata,
                query_embedding=_cache_embedding,
            )
        except Exception as e:
            logger.warning(f"[DeepSearch] Cache save failed: {e}")

        if session_context:
            try:
                session_context.add_message(role="assistant", content=combined_content)
                memoized_results["_assistant_response_saved"] = True
            except Exception as e:
                logger.warning(f"[DeepSearch] Session context save failed: {e}")

    if session_id and semantic_cache is not None:
        try:
            semantic_cache.save_for_request(session_id)
        except Exception:
            pass

    if session_id:
        try:
            conversation_cache.save_to_disk(session_id=session_id)
        except Exception:
            pass

    done_event = emit_event("INFO", "<TASK>DONE</TASK>")
    if done_event:
        yield done_event

    logger.info(
        f"[DeepSearch] Complete: {len(all_sub_results)} sub-queries answered, "
        f"{len(all_collected_sources)} total sources"
    )

async def _synthesize_subtopic(
    subtopic: str,
    original_query: str,
    messages_context: list,
    headers: dict,
    max_tokens: int,
    rag_context: str = "",
) -> str:
    synthesis_messages = messages_context[:2]

    focused_prompt = {
        "role": "user",
        "content": (
            f"Focus specifically on this aspect of the query '{original_query}':\n\n"
            f"Sub-topic: {subtopic}\n\n"
            f"Provide a focused, detailed response for this specific aspect. "
            f"Use markdown formatting with \\n for line breaks. "
            f"Do not repeat information that would belong to other sub-topics. "
            f"Be thorough but concise for this specific angle.\n"
            f"NEVER mention internal tool names, function calls, or cache operations."
        )
    }
    synthesis_messages.append(focused_prompt)

    payload = {
        "model": MODEL,
        "messages": synthesis_messages,
        "seed": random.randint(1000, 9999),
        "max_tokens": max_tokens,
        "stream": False,
    }

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
    data = response.json()
    content = data["choices"][0]["message"]["content"].strip()
    return content

def _looks_like_internal_reasoning(content: str) -> bool:
    if not content:
        return False
    probe = content[:2500].lower()
    matches = sum(1 for p in INTERNAL_LEAK_PATTERNS if re.search(p, probe, re.MULTILINE))
    if matches >= 2:
        return True
    first_line = content.strip().split("\n")[0].lower()
    strong_starts = (
        "the user wants", "the user is asking", "i should", "i need to",
        "let me", "based on the", "step 1", "first,",
    )
    if any(first_line.startswith(s) for s in strong_starts):
        return True
    return False

def _strip_internal_lines(content: str) -> str:
    if not content:
        return ""
    cleaned = []
    for line in content.splitlines():
        low = line.strip().lower()
        if (
            low.startswith("the user wants")
            or low.startswith("the user is asking")
            or low.startswith("i should")
            or low.startswith("i need to")
            or low.startswith("i will search")
            or low.startswith("i will fetch")
            or low.startswith("i will look")
            or low.startswith("let me")
            or low.startswith("based on the rag")
            or low.startswith("based on the web search")
            or low.startswith("based on the search results")
            or re.match(r"^\d+\.\s+(first|second|third|then|next|finally)\b", low)
            or re.match(r"^(first,|second,|next,|finally,|step \d+)", low)
        ):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()

_FETCH_FAIL_PATTERNS = re.compile(
    r"^\[(?:TIMEOUT|ERROR|CACHED)\]|^No result$|^\[No content fetched",
    re.IGNORECASE,
)

def _evaluate_fetch_quality(tool_outputs: list) -> tuple[int, int]:
    total = 0
    good = 0
    for out in tool_outputs:
        if out.get("name") != "fetch_full_text":
            continue
        total += 1
        content = out.get("content", "")
        if not content or _FETCH_FAIL_PATTERNS.match(content) or len(content) < FETCH_MIN_USEFUL_CHARS:
            continue
        good += 1
    return good, total

async def run_elixposearch_pipeline(user_query: str, user_image: str, event_id: str = None, session_id: str = None, deep_search: bool = False):
    logger.info(
        f"[pipeline] session={session_id} Starting ElixpoSearch: "
        f"query='{user_query[:LOG_MESSAGE_QUERY_TRUNCATE]}...' image={bool(user_image)} "
        f"deep_search={deep_search}"
    )
    def emit_event(event_type, message):
        if event_id:
            return format_sse(event_type, message)
        return None

    original_user_query = user_query or ""
    image_only_mode = bool(user_image and not original_user_query.strip())

    is_deep_search = deep_search and not image_only_mode
    if is_deep_search:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {POLLINATIONS_TOKEN}",
        }

        llm_verdict = await _evaluate_deep_search_need(original_user_query, headers)

        if llm_verdict is False:
            logger.info(f"[DeepSearch] LLM gating DOWNGRADE: query too simple for deep search")
            is_deep_search = False
            downgrade_event = emit_event(
                "INFO",
                "<TASK>Query is straightforward — using standard search</TASK>",
            )
            if downgrade_event:
                yield downgrade_event
        elif llm_verdict is None:
            from pipeline.queryDecomposition import QueryAnalyzer, QueryComplexity
            gate_analyzer = QueryAnalyzer()
            gate_complexity = gate_analyzer.detect_query_complexity(original_user_query)
            complexity_rank = {
                QueryComplexity.SIMPLE: 0,
                QueryComplexity.MODERATE: 1,
                QueryComplexity.COMPLEX: 2,
                QueryComplexity.HIGHLY_COMPLEX: 3,
            }
            min_rank = complexity_rank.get(
                QueryComplexity(DEEP_SEARCH_GATING_MIN_COMPLEXITY.lower()), 1
            )
            if complexity_rank.get(gate_complexity, 0) < min_rank:
                logger.info(
                    f"[DeepSearch] Heuristic gating DOWNGRADE: complexity={gate_complexity.value} "
                    f"below minimum={DEEP_SEARCH_GATING_MIN_COMPLEXITY}"
                )
                is_deep_search = False
                downgrade_event = emit_event(
                    "INFO",
                    "<TASK>Query is straightforward — using standard search</TASK>",
                )
                if downgrade_event:
                    yield downgrade_event
            else:
                logger.info(f"[DeepSearch] Heuristic gating PASS: complexity={gate_complexity.value}")
        else:
            logger.info(f"[DeepSearch] LLM gating PASS: proceeding with deep search")

    if is_deep_search:
        async for event in _run_deep_search_pipeline(
            user_query=original_user_query,
            user_image=user_image,
            event_id=event_id,
            session_id=session_id,
            emit_event=emit_event,
        ):
            yield event
        return

    _detail_keywords = re.compile(
        r"\b(detail(?:ed|s)?|comprehensive|in[- ]?depth|thorough|extensive|elaborate|full|complete|everything about|deep dive|lengthy|long)\b",
        re.IGNORECASE,
    )
    is_detailed_mode = bool(_detail_keywords.search(original_user_query))
    active_min_links = MIN_LINKS_TO_TAKE_DETAILED if is_detailed_mode else MIN_LINKS_TO_TAKE
    active_max_links = MAX_LINKS_TO_TAKE_DETAILED if is_detailed_mode else MAX_LINKS_TO_TAKE
    active_max_tokens = LLM_MAX_TOKENS_DETAILED if is_detailed_mode else LLM_MAX_TOKENS
    if is_detailed_mode:
        logger.info(f"[Pipeline] Detailed mode ON: links={active_min_links}-{active_max_links}, max_tokens={active_max_tokens}")

    initial_event = emit_event("INFO", get_user_message("processing"))
    if initial_event:
        yield initial_event
    status_tracker = SSEStatusTracker(emit_fn=emit_event, stale_threshold=10.0)
    semantic_cache = None
    memoized_results = {}
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
            "cached_response": None,
            "session_id": session_id or "",
            "generated_images": [],
        }
        session_context = None
        if session_id:
            try:
                session_context = SessionContextWindow(session_id=session_id)
                memoized_results["session_context"] = session_context
                previous_messages = session_context.get_context()
                loaded_count = len(previous_messages)
                session_context.add_message(role="user", content=user_query)

                logger.info(
                    f"[Pipeline] Initialized SessionContextWindow for {session_id}: "
                    f"loaded {loaded_count} hot messages, added current query"
                )
            except Exception as e:
                logger.warning(f"[Pipeline] Failed to initialize SessionContextWindow: {e}")
                session_context = None
        
        _embed_fn = core_service.embed_single_text if core_service else None
        conversation_cache = ConversationCacheManager(
            window_size=CACHE_WINDOW_SIZE,
            max_entries=CACHE_MAX_ENTRIES,
            ttl_seconds=CACHE_TTL_SECONDS,
            compression_method=CACHE_COMPRESSION_METHOD,
            embedding_model=CACHE_EMBEDDING_MODEL,
            similarity_threshold=CACHE_SIMILARITY_THRESHOLD,
            cache_dir=CONVERSATION_CACHE_DIR,
            embed_fn=_embed_fn,
        )
        memoized_results["conversation_cache"] = conversation_cache
        logger.info(f"[Pipeline] Initialized Conversation Cache Manager (window_size={CACHE_WINDOW_SIZE}, max_entries={CACHE_MAX_ENTRIES}, embed={'ipc' if _embed_fn else 'local'})")
        
        if session_id:
            if conversation_cache.load_from_disk(session_id=session_id):
                logger.info(f"[Pipeline] Loaded conversation cache from disk (session: {session_id})")
        

        semantic_cache = SemanticCache(
            session_id=session_id or "pipeline",
            ttl_seconds=SEMANTIC_CACHE_TTL_SECONDS,
            similarity_threshold=SEMANTIC_CACHE_SIMILARITY_THRESHOLD,
            redis_host=SEMANTIC_CACHE_REDIS_HOST,
            redis_port=SEMANTIC_CACHE_REDIS_PORT,
            redis_db=SEMANTIC_CACHE_REDIS_DB
        )
        if session_id:
            semantic_cache.load_for_request(session_id)
            logger.info(f"[Pipeline] Loaded persistent Redis cache for session {session_id}")
        
        image_context_provided = False
        image_analysis_result = None
        if image_only_mode:
            logger.info(f"[Pipeline] Image-only mode: describing image directly via vision model")
            try:
                image_event = emit_event("INFO", "<TASK>Analyzing image</TASK>")
                if image_event:
                    yield image_event

                image_description = await describe_image(user_image)
                logger.info(f"[Pipeline] Image description generated: {len(image_description)} chars")

                # Yield description directly as RESPONSE and return
                if event_id:
                    chunk_size = 80
                    for i in range(0, len(image_description), chunk_size):
                        chunk = image_description[i:i+chunk_size]
                        yield format_sse("RESPONSE", chunk)
                    yield format_sse("INFO", "<TASK>DONE</TASK>")
                else:
                    yield image_description

                # Save to session context
                memoized_results["final_response"] = image_description
                if session_id and semantic_cache is not None:
                    semantic_cache.save_for_request(session_id)
                return
            except Exception as e:
                logger.warning(f"[Pipeline] Failed to describe image: {e}")
                # Fall through to normal pipeline with empty query
                user_query = "describe this image"
                image_context_provided = False
        elif user_image and user_query.strip():
            logger.info(f"[Pipeline] Image + Query mode: analyzing image in context of query")
            try:
                image_event = emit_event("INFO", "<TASK>Analyzing image</TASK>")
                if image_event:
                    yield image_event

                image_analysis_result = await replyFromImage(user_image, user_query)
                image_context_provided = True
                logger.info(f"[Pipeline] Image analysis done: {len(image_analysis_result)} chars")
            except Exception as e:
                logger.warning(f"[Pipeline] Failed to analyze image: {e}")
                image_context_provided = False
        
        max_iterations = 3
        current_iteration = 0
        fetch_retry_done = False
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

        # RAG retrieval — run async with timeout so it never blocks the main pipeline
        rag_context = ""
        if core_service:
            try:
                retrieval_result = await asyncio.wait_for(
                    asyncio.to_thread(core_service.retrieve, user_query, 3),
                    timeout=3.0
                )
                if retrieval_result.get("count", 0) > 0:
                    rag_context = "\n".join([r["metadata"]["text"] for r in retrieval_result.get("results", [])])
                    logger.info(f"[Pipeline] Retrieved {retrieval_result.get('count', 0)} chunks from vector store")
            except asyncio.TimeoutError:
                logger.warning("[Pipeline] Vector store retrieval timed out (3s), continuing without context")
            except Exception as e:
                logger.warning(f"[Pipeline] Vector store retrieval failed, continuing without context: {e}")
        else:
            logger.info("[Pipeline] Skipping vector store retrieval (model_server unavailable)")
        
        logger.info(f"[Pipeline] RAG context prepared: {len(rag_context)} chars")
        
        # Build user message — include image analysis if vision model already processed it
        user_msg_content = user_instruction(user_query, user_image if not image_analysis_result else None, is_detailed=is_detailed_mode)
        if image_analysis_result:
            user_msg_content += f"\n\n[Image Analysis]\n{image_analysis_result}"

        messages = [
            {
                "role": "system",
                "name": "elixposearch-agent-system",
                "content": system_instruction(rag_context, current_utc_time, is_detailed=is_detailed_mode)
            },
            {
                "role": "user",
                "content": user_msg_content
            }
        ]
        force_synthesis = False

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

            if len(messages) > 8:
                trimmed = messages[:2] + messages[-6:]
                logger.info(f"[OPTIMIZATION] Trimmed messages from {len(messages)} to {len(trimmed)}")
                messages = trimmed
            
            payload = {
                "model": MODEL,
                "messages": messages,
                "seed": random.randint(1000, 9999),
                "max_tokens": active_max_tokens,
            }
            if not force_synthesis:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            # Refresh stale SSE status before potentially long LLM call
            _stale_event = status_tracker.refresh_if_stale()
            if _stale_event:
                yield _stale_event

            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        requests.post,
                        POLLINATIONS_ENDPOINT,
                        json=payload,
                        headers=headers,
                        timeout=55
                    ),
                    timeout=60.0
                )
                response.raise_for_status()
                response_data = response.json()
                status_tracker.touch()
            except asyncio.TimeoutError:
                logger.error(f"API timeout at iteration {current_iteration}")
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
                break
            except Exception as e:
                print(f"\n{'='*80}")
                print(f"[UNEXPECTED ERROR] Type: {type(e).__name__}")
                print(f"[UNEXPECTED ERROR] Message: {str(e)}")
                print(f"{'='*80}\n")
                logger.error(f"Unexpected API error at iteration {current_iteration}: {e}", exc_info=True)
                break
            choice = response_data.get("choices", [{}])[0]
            assistant_message = choice.get("message") or choice.get("delta")
            if not assistant_message:
                logger.error(f"Unexpected API response structure: {response_data}")
                break

            # Strip reasoning_content — it's internal model thinking, never user-facing
            assistant_message.pop("reasoning_content", None)

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
                raw_content = assistant_message.get("content", "")
                is_reasoning_leak = _looks_like_internal_reasoning(raw_content)
                is_placeholder = raw_content.strip() in (
                    "Processing your request...",
                    "I'll help you with that. Let me gather the information you need.",
                    "",
                )
                has_useful_context = bool(collected_sources) or tool_call_count > 0

                if (is_reasoning_leak or is_placeholder) and has_useful_context and current_iteration < max_iterations:
                    logger.warning(
                        f"[COMPLETION] Iteration {current_iteration}: LLM returned reasoning/placeholder text "
                        f"(leak={is_reasoning_leak}, placeholder={is_placeholder}). Forcing synthesis instead of using raw content."
                    )
                    if event_id:
                        yield format_sse("INFO", get_user_message("synthesizing"))
                        status_tracker.touch()
                    _has_images = image_context_provided or bool(collected_images_from_web) or bool(collected_similar_images)
                    messages.append({
                        "role": "user",
                        "content": synthesis_instruction(user_query, image_context=_has_images, is_detailed=is_detailed_mode)
                    })
                    force_synthesis = True
                    continue

                final_message_content = raw_content
                logger.info(f"[COMPLETION] No tool calls found, setting final message: {final_message_content[:LOG_MESSAGE_PREVIEW_TRUNCATE] if final_message_content else 'EMPTY'}")
                break
            tool_outputs = []
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
                    try:
                        _ws_args = json.loads(tool_call["function"]["arguments"])
                        _depth = _ws_args.get("search_depth")
                        if _depth and not is_detailed_mode:
                            _bounds = SEARCH_DEPTH_BOUNDS.get(_depth)
                            if _bounds:
                                active_min_links = _bounds["min"]
                                active_max_links = _bounds["max"]
                                logger.info(f"[URL-LIMITS] search_depth='{_depth}' -> links={active_min_links}-{active_max_links}")
                    except (json.JSONDecodeError, KeyError):
                        pass
                else:
                    other_calls.append(tool_call)
            
            if web_search_calls and len(fetch_calls) < active_min_links:
                urls_needed = active_min_links - len(fetch_calls)
                logger.info(f"[URL-LIMITS] Web search detected but only {len(fetch_calls)} URLs to fetch. Need {urls_needed} more to meet minimum of {active_min_links}")

            if len(fetch_calls) > active_max_links:
                logger.info(f"[URL-LIMITS] Capping fetch_calls from {len(fetch_calls)} to {active_max_links}")
                fetch_calls = fetch_calls[:active_max_links]

            logger.info(f"[URL-LIMITS] Final URL fetch plan: {len(fetch_calls)} URLs (min={active_min_links}, max={active_max_links})")
            
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
                search_count = len(web_search_calls)
                emit_sse = emit_event("INFO", f"<TASK>Running {search_count} web search{'es' if search_count > 1 else ''}</TASK>")
                if emit_sse:
                    yield emit_sse
                status_tracker.touch()
                web_search_results = await asyncio.gather(
                    *[execute_tool_async(idx, tc, True) for idx, tc in enumerate(web_search_calls)],
                    return_exceptions=True
                )
                successful_searches = 0
                for result in web_search_results:
                    if not isinstance(result, Exception):
                        successful_searches += 1
                        if result["name"] == "web_search" and "current_search_urls" in memoized_results:
                            collected_sources.extend(memoized_results["current_search_urls"][:3])
                        tool_outputs.append({
                            "role": "tool",
                            "tool_call_id": result["tool_call_id"],
                            "name": result["name"],
                            "content": str(result["result"]) if result["result"] else "No result"
                        })
                logger.info(f"[Pipeline] Web search complete: {successful_searches} successful, {len(collected_sources)} sources")
            
            for idx, tool_call in enumerate(other_calls):
                function_name = tool_call["function"]["name"]
                function_args = json.loads(tool_call["function"]["arguments"])
                logger.info(f"[Sequential Tool #{idx+1}] {function_name}")

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

            if fetch_calls:
                _stale_event = status_tracker.refresh_if_stale()
                if _stale_event:
                    yield _stale_event
                logger.info(f"[Pipeline] Fetching {len(fetch_calls)} sources in parallel")

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
                
                try:
                    fetch_results = await asyncio.wait_for(
                        asyncio.gather(
                            *[execute_fetch(idx, tc) for idx, tc in enumerate(fetch_calls)],
                            return_exceptions=True
                        ),
                        timeout=8.0
                    )
                except (asyncio.TimeoutError, TimeoutError):
                    logger.warning(f"[PARALLEL FETCH] Timeout after 8s – continuing with results collected so far")
                    fetch_results = []

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

                good_fetches, total_fetches = _evaluate_fetch_quality(tool_outputs)
                if total_fetches > 0:
                    logger.info(f"[FETCH QUALITY] {good_fetches}/{total_fetches} fetches returned usable content")

            messages.extend(tool_outputs)
            logger.info(f"Completed iteration {current_iteration}. Messages: {len(messages)}, Total tools: {tool_call_count}")

        if not final_message_content and current_iteration >= max_iterations:
            logger.info(f"[SYNTHESIS CONDITION MET] final_message_content={bool(final_message_content)}, current_iteration={current_iteration}, max_iterations={max_iterations}")
            if event_id:
                yield format_sse("INFO", get_user_message("synthesizing"))
                status_tracker.touch()
            logger.info("[SYNTHESIS] Re-retrieving context from vector store after ingestion...")
            try:
                from searching.main import retrieve_from_vector_store
                updated_rag_context = await asyncio.wait_for(
                    asyncio.to_thread(retrieve_from_vector_store, user_query, top_k=RETRIEVAL_TOP_K),
                    timeout=5.0
                )
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
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"[SYNTHESIS] Failed to re-retrieve context: {e}")
            
            query_components = memoized_results.get("query_components", [user_query])
            if len(query_components) > 1:
                logger.info(f"[SYNTHESIS] Multi-component query synthesis:")
                for i, component in enumerate(query_components, 1):
                    logger.info(f"[SYNTHESIS] Component {i}: {component[:LOG_MESSAGE_PREVIEW_TRUNCATE]}")
                logger.info(f"[SYNTHESIS] Synthesizing {len(collected_sources)} total sources across {len(query_components)} components")

            if is_detailed_mode:
                if event_id:
                    yield format_sse("INFO", "<TASK>Decomposing topic</TASK>")

                subtopics = await _decompose_query_with_llm(user_query, headers, max_parts=TOPIC_DECOMPOSITION_MAX_PARTS)
                logger.info(f"[SYNTHESIS] Decomposed into {len(subtopics)} sub-topics: {subtopics}")

                original_msg_count = len(messages)
                if len(messages) > 6:
                    messages = messages[:2] + messages[-4:]
                    logger.info(f"[SYNTHESIS] Trimmed messages from {original_msg_count} to {len(messages)}")

                all_subtopic_responses = []
                per_part_tokens = max(800, active_max_tokens // len(subtopics))

                for idx, subtopic in enumerate(subtopics, 1):
                    if event_id:
                        yield format_sse("INFO", f"<TASK>Researching part {idx} of {len(subtopics)}</TASK>")

                    try:
                        subtopic_response = await _synthesize_subtopic(
                            subtopic=subtopic,
                            original_query=user_query,
                            messages_context=messages,
                            headers=headers,
                            max_tokens=per_part_tokens,
                            rag_context=rag_context,
                        )

                        if subtopic_response:
                            subtopic_response = await sanitize_final_response(subtopic_response, subtopic, collected_sources)
                            subtopic_response = _scrub_tool_names(subtopic_response)
                            all_subtopic_responses.append(subtopic_response)

                            if idx == len(subtopics) and collected_sources:
                                source_block = "\n\n---\n**Sources:**\n"
                                unique_sources = sorted(list(set(collected_sources)))[:5]
                                for si, src in enumerate(unique_sources):
                                    source_block += f"{si+1}. [{src}]({src})\n"
                                subtopic_response += source_block

                            if event_id:
                                yield format_sse("RESPONSE", subtopic_response)
                            else:
                                yield subtopic_response

                    except Exception as e:
                        logger.error(f"[SYNTHESIS] Sub-topic {idx} failed: {e}")

                final_message_content = "\n\n".join(all_subtopic_responses) if all_subtopic_responses else None
                if final_message_content:
                    try:
                        cache_metadata = {
                            "sources": collected_sources[:5],
                            "tool_calls": tool_call_count,
                            "iteration": current_iteration,
                            "had_cache_hit": memoized_results.get("cache_hit", False),
                            "decomposed": True,
                        }
                        _cache_embedding = None
                        if core_service:
                            try:
                                _cache_embedding = core_service.embed_single_text(user_query)
                            except Exception:
                                pass
                        conversation_cache.add_to_cache(
                            query=user_query,
                            response=final_message_content,
                            metadata=cache_metadata,
                            query_embedding=_cache_embedding,
                        )
                    except Exception as e:
                        logger.warning(f"[Pipeline] Failed to save decomposed response to cache: {e}")

                    if session_context:
                        try:
                            session_context.add_message(role="assistant", content=final_message_content)
                            memoized_results["_assistant_response_saved"] = True
                        except Exception as e:
                            logger.warning(f"[Pipeline] Failed to store decomposed reply in hybrid cache: {e}")

                    memoized_results["final_response"] = final_message_content

                if event_id:
                    yield format_sse("INFO", "<TASK>DONE</TASK>")
                return

            logger.info("[SYNTHESIS] Starting synthesis of gathered information")
            _has_images = image_context_provided or bool(collected_images_from_web) or bool(collected_similar_images)
            synthesis_prompt = {
                "role": "user",
                "content": synthesis_instruction(user_query, image_context=_has_images, is_detailed=is_detailed_mode)
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
                "max_tokens": active_max_tokens,
                "stream": False,
            }

            # Refresh stale SSE status before synthesis LLM call
            _stale_event = status_tracker.refresh_if_stale()
            if _stale_event:
                yield _stale_event

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

                    # Never use reasoning_content — it's the model's internal thinking, not for the user
                    if not final_message_content and "reasoning_content" in message:
                        logger.warning("[SYNTHESIS] Model returned reasoning_content but empty content — ignoring internal reasoning")

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
            final_message_content = _scrub_tool_names(final_message_content)
            logger.info(f"Preparing optimized final response")
            logger.info(f"[FINAL] final_message_content starts with: {final_message_content[:LOG_MESSAGE_PREVIEW_TRUNCATE] if final_message_content else 'None'}")
            logger.info(f"[FINAL] final_message_content starts with: {final_message_content[:LOG_MESSAGE_PREVIEW_TRUNCATE] if final_message_content else 'None'}")
            
            _is_placeholder_or_fallback = (
                final_message_content in [
                    "Processing your request...",
                    "I'll help you with that. Let me gather the information you need.",
                ]
                or final_message_content.startswith("I found relevant information about")
                or final_message_content.startswith("I gathered")
                or final_message_content.startswith("I searched for information about")
                or final_message_content.startswith("I processed your query about")
            )
            if (collected_images_from_web or collected_similar_images) and _is_placeholder_or_fallback:
                logger.info(f"[FINAL] Detected placeholder/fallback content with collected images. Triggering synthesis...")
                _image_pool = collected_similar_images if (image_only_mode and collected_similar_images) else collected_images_from_web
                _image_list = "\n".join(f"![Image]({url})" for url in _image_pool[:10] if url and url.startswith("http"))
                synthesis_prompt = {
                    "role": "user",
                    "content": (
                        f"Based on the search results, provide a final comprehensive answer to: {user_query}\n\n"
                        f"Include these images in your response using markdown:\n{_image_list}"
                    )
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
                            timeout=55
                        ),
                        timeout=60.0
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

            generated_images = memoized_results.get("generated_images", [])
            if generated_images:
                gen_deduped = [img for img in generated_images if img not in existing_image_urls]
                if gen_deduped:
                    response_parts.append("\n\n**Generated Images:**\n")
                    for img in gen_deduped:
                        response_parts.append(f"![Generated Image]({img})\n")
                    logger.info(f"[FINAL] Added {len(gen_deduped)} generated images")

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
                _cache_embedding = None
                if core_service:
                    try:
                        _cache_embedding = core_service.embed_single_text(user_query)
                    except Exception:
                        pass
                conversation_cache.add_to_cache(
                    query=user_query,
                    response=final_message_content,
                    metadata=cache_metadata,
                    query_embedding=_cache_embedding,
                )
                cache_stats = conversation_cache.get_cache_stats()
                logger.info(f"[Pipeline] Saved to conversation cache. Stats: {cache_stats}")
            except Exception as e:
                logger.warning(f"[Pipeline] Failed to save to conversation cache: {e}")

            if session_context:
                try:
                    session_context.add_message(role="assistant", content=final_message_content)
                    memoized_results["_assistant_response_saved"] = True
                    logger.debug(f"[Pipeline] Stored assistant reply in hybrid cache for session={session_id}")
                except Exception as e:
                    logger.warning(f"[Pipeline] Failed to store assistant reply in hybrid cache: {e}")

            memoized_results["final_response"] = response_with_sources
            
            if event_id:
                yield format_sse("RESPONSE", response_with_sources)
                yield format_sse("INFO", "<TASK>DONE</TASK>")
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

                image_pool = collected_similar_images if (image_only_mode and collected_similar_images) else collected_images_from_web
                if image_pool:
                    deduped_pool = []
                    seen_urls = set()
                    for img in image_pool:
                        if img and img.startswith("http") and img not in seen_urls:
                            seen_urls.add(img)
                            deduped_pool.append(img)
                    if deduped_pool:
                        title = "Similar Images" if image_only_mode else "Related Images"
                        label = "Similar Image" if image_only_mode else "Image"
                        response_parts.append(f"\n\n**{title}:**\n")
                        for img in deduped_pool[:10]:
                            response_parts.append(f"![{label}]({img})\n")
                        logger.info(f"[FALLBACK] Added {min(len(deduped_pool), 10)} images to fallback response")

                generated_images = memoized_results.get("generated_images", [])
                if generated_images:
                    response_parts.append("\n\n**Generated Images:**\n")
                    for img in generated_images:
                        response_parts.append(f"![Generated Image]({img})\n")

                if collected_sources:
                    response_parts.append("\n\n---\n**Sources:**\n")
                    unique_sources = sorted(list(set(collected_sources)))[:5]
                    for i, src in enumerate(unique_sources):
                        response_parts.append(f"{i+1}. [{src}]({src})\n")
                response_with_fallback = "".join(response_parts)

                memoized_results["final_response"] = response_with_fallback

                if event_id:
                    yield format_sse("INFO", get_user_message("finalizing"))
                    chunk_size = 8000
                    for i in range(0, len(response_with_fallback), chunk_size):
                        chunk = response_with_fallback[i:i+chunk_size]
                        yield format_sse("RESPONSE", chunk)
                    yield format_sse("INFO", "<TASK>DONE</TASK>")
                else:
                    yield response_with_fallback
                return
            else:
                if event_id:
                    yield format_sse("INFO", "<TASK>DONE</TASK>")
                return
    except Exception as e:
        error_msg = str(e) if str(e) else f"Empty exception: {type(e).__name__}"
        logger.error(f"Pipeline error: {error_msg}", exc_info=True)
        logger.error(f"[DEBUG] Exception type: {type(e).__name__}, Args: {e.args}")
        if event_id:
            yield format_sse("INFO", "<TASK>DONE</TASK>")
    finally:
        if session_id and "session_context" in memoized_results and memoized_results["session_context"]:
            try:
                session_context = memoized_results["session_context"]
                if "final_response" in memoized_results and memoized_results["final_response"]:
                    if not memoized_results.get("_assistant_response_saved"):
                        session_context.add_message(role="assistant", content=memoized_results["final_response"])
                        logger.info(f"[Pipeline] Saved assistant response to SessionContextWindow for {session_id} (finally)")
            except Exception as e:
                logger.warning(f"[Pipeline] Failed to save response to SessionContextWindow: {e}")
        
        if session_id and semantic_cache is not None:
            semantic_cache.save_for_request(session_id)
            logger.info(f"[Pipeline] Saved persistent cache for session {session_id}")

            try:
                if "conversation_cache" in memoized_results:
                    conversation_cache.save_to_disk(session_id=session_id)
                    cache_stats = conversation_cache.get_cache_stats()
                    logger.info(f"[Pipeline] Saved conversation cache to disk: {cache_stats}")
            except Exception as e:
                logger.warning(f"[Pipeline] Failed to save conversation cache: {e}")
        
        logger.info("Optimized Search Completed")
