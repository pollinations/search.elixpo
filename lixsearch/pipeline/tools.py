tools = [
    {
        "type": "function",
        "function": {
            "name": "cleanQuery",
            "description": "Clean and extract URLs from a search query",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to clean"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current/real-time information. MANDATORY for weather, time-sensitive data, news, prices, events, and scores. When called, you MUST fetch 3-6 URLs from results using fetch_full_text. This is not optional - all web_search calls require comprehensive URL extraction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query. For weather: include location and 'weather' or 'temperature'. For time: include location and 'time'. For news: be specific about topic/date."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_full_text",
            "description": "Fetch full text content from a URL with AI-driven intelligent caching. SMART CACHING: System detects whether content is ephemeral (weather, prices, news - always fetch fresh) or stable (articles, docs - cache 24h for performance). Detection is AI-based aspect analysis, not heuristic. Stable content hit returns instantly from cache; ephemeral always bypasses cache for freshness. When web_search is executed, you MUST call this for 3-6 of the returned URLs. Minimum 3 URLs must be fetched.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch. Select from web_search results. System automatically determines if content should be cached or fetched fresh."
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "transcribe_audio",
            "description": "Transcribe audio from a YouTube URL, optionally using a provided transcript or extracting relevant information based on a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The YouTube URL"
                    },
                    "full_transcript": {
                        "type": "boolean",
                        "description": "Optional boolean, if user wants full transcript or some part of it based on query",
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional query to extract relevant information from the transcript",
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_local_time",
            "description": "Get CURRENT local time for a specific location (MANDATORY for any time/timezone query). Always use this when user asks 'what time is it in [location]'. If user also asks about other current info (weather), follow with web_search to avoid incomplete responses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location_name": {
                        "type": "string",
                        "description": "The location name (city, region, country). Extract from user query. Required."
                    }
                },
                "required": ["location_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_prompt_from_image",
            "description": "Generate a search prompt from an image URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "imageURL": {
                        "type": "string",
                        "description": "The image URL to analyze"
                    }
                },
                "required": ["imageURL"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "replyFromImage",
            "description": "Reply to a query based on an image",
            "parameters": {
                "type": "object",
                "properties": {
                    "imageURL": {
                        "type": "string",
                        "description": "The image URL"
                    },
                    "query": {
                        "type": "string",
                        "description": "The query about the image"
                    }
                },
                "required": ["imageURL", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "image_search",
            "description": "Search for images based on a query",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_query": {
                        "type": "string",
                        "description": "The image search query"
                    },
                    "max_images": {
                        "type": "integer",
                        "description": "Maximum number of images to return",
                        "default": 10
                    }
                },
                "required": ["image_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_image",
            "description": "Generate an image from a text prompt using AI image generation. Use when the user explicitly asks to create/generate/draw an image, or when a visual diagram/illustration would significantly help explain a concept. Returns a URL to the generated image. Do NOT use for image search - use image_search instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "A detailed, descriptive prompt for image generation. Be specific about subjects, style, colors, composition, and mood."
                    }
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "youtubeMetadata",
            "description": "Fetch metadata (title, description, duration, views) from a YouTube URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The YouTube URL"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_conversation_cache",
            "description": "Query cached conversation history using semantic similarity. Use FIRST before any other tools. If cache returns match (>0.85 similarity), check if query is TIME-SENSITIVE. If time-sensitive (weather/time/news), IGNORE cache and proceed with web_search. Only use cached answer for evergreen content (definitions, general knowledge, history).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user query to search in conversation cache"
                    },
                    "use_window": {
                        "type": "boolean",
                        "description": "Always true for fastest lookup"
                    },
                    "similarity_threshold": {
                        "type": "number",
                        "description": "Use 0.85 for high confidence matches"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_session_conversation_history",
            "description": "Retrieve FULL conversation history for the current session. Use this when user asks for summary, recap, or 'what have we discussed'. Returns all messages in chronological order from the session context window. CRITICAL: Always use this before summarizing to ensure you have the complete conversation context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "The session ID to retrieve conversation history for. This is passed by the system - use current session_id."
                    },
                    "include_metadata": {
                        "type": "boolean",
                        "description": "Include timestamps and role information for each message",
                        "default": True
                    }
                },
                "required": ["session_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_query_complexity",
            "description": "Analyze query complexity and determine if it should be decomposed into sub-queries. Returns complexity assessment, detected aspects, and decomposition recommendation with confidence score.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user query to analyze for complexity and decomposition suitability"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_response_quality",
            "description": "Evaluate the quality of a response based on completeness, factuality, and freshness. Analyzes whether the response adequately addresses the query with cited sources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The original user query"
                    },
                    "response": {
                        "type": "string",
                        "description": "The generated response to evaluate"
                    },
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of URLs/sources used to generate the response"
                    }
                },
                "required": ["query", "response", "sources"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sanitize_output",
            "description": "Check output safety and sanitize it to prevent prompt injection attacks. Detects injection patterns, removes dangerous content, and reports any security issues found.",
            "parameters": {
                "type": "object",
                "properties": {
                    "output": {
                        "type": "string",
                        "description": "The output text to sanitize and check for security issues"
                    },
                    "source": {
                        "type": "string",
                        "description": "The source of the output (e.g., 'web_search', 'fetch_full_text')",
                        "default": "unknown"
                    }
                },
                "required": ["output"]
            }
        }
    }
]