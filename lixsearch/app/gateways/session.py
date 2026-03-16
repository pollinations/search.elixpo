import logging
import uuid
from datetime import datetime
from quart import request, jsonify
from sessions.main import get_session_manager
from ragService.main import get_retrieval_system
from pipeline.config import X_REQ_ID_SLICE_SIZE
from app.utils import validate_session_id

logger = logging.getLogger("lixsearch-api")


async def create_session():
    try:
        data = await request.get_json()
        query = data.get("query", "").strip()

        if not query:
            return jsonify({"error": "Query is required"}), 400

        session_manager = get_session_manager()
        session_id = session_manager.create_session(query)

        logger.info(f"[API] Session: {session_id}")

        return jsonify({
            "session_id": session_id,
            "query": query,
            "created_at": datetime.utcnow().isoformat()
        }), 201

    except Exception as e:
        logger.error(f"[API] Session creation error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


async def get_session_info(session_id: str):
    if not validate_session_id(session_id):
        return jsonify({"error": "Invalid session_id"}), 400

    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:X_REQ_ID_SLICE_SIZE])

    try:
        logger.info(f"[{request_id}] get_session_info session={session_id}")
        session_manager = get_session_manager()
        session_data = session_manager.get_session(session_id)

        if not session_data:
            logger.warning(f"[{request_id}] session={session_id} not found")
            return jsonify({"error": "Session not found"}), 404

        rag_stats = {}
        try:
            retrieval_system = get_retrieval_system()
            rag_engine = retrieval_system.get_rag_engine(session_id)
            rag_stats = rag_engine.get_stats() if rag_engine else {}
        except Exception:
            pass

        return jsonify({
            "session_id": session_id,
            "query": session_data.query,
            "summary": session_manager.get_session_summary(session_id),
            "rag_stats": rag_stats,
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat()
        })

    except Exception as e:
        logger.error(f"[{request_id}] get_session_info session={session_id} error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


async def get_session_kg(session_id: str):
    if not validate_session_id(session_id):
        return jsonify({"error": "Invalid session_id"}), 400

    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:X_REQ_ID_SLICE_SIZE])

    try:
        logger.info(f"[{request_id}] Getting KG for session: {session_id}")
        session_manager = get_session_manager()
        if not session_manager.get_session(session_id):
            return jsonify({"error": "Session not found"}), 404

        retrieval_system = get_retrieval_system()
        rag_engine = retrieval_system.get_rag_engine(session_id)
        context = rag_engine.get_full_context(session_id) if rag_engine else {}

        if isinstance(context, dict) and "error" in context:
            logger.warning(f"[{request_id}] KG fetch error for session: {session_id}")
            return jsonify(context), 404

        return jsonify({
            **(context if isinstance(context, dict) else {"context": context}),
            "request_id": request_id
        })

    except Exception as e:
        logger.error(f"[{request_id}] KG fetch error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


async def query_session_kg(session_id: str):
    if not validate_session_id(session_id):
        return jsonify({"error": "Invalid session_id"}), 400

    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:X_REQ_ID_SLICE_SIZE])

    try:
        logger.info(f"[{request_id}] Querying KG for session: {session_id}")
        session_manager = get_session_manager()
        if not session_manager.get_session(session_id):
            return jsonify({"error": "Session not found"}), 404

        data = await request.get_json()
        query = data.get("query", "").strip()
        top_k = data.get("top_k", 10)

        if not query:
            return jsonify({"error": "Query is required"}), 400

        retrieval_system = get_retrieval_system()
        rag_engine = retrieval_system.get_rag_engine(session_id)
        results = rag_engine.retrieve_context(query, top_k=top_k) if rag_engine else []

        return jsonify({
            "query": query,
            "session_id": session_id,
            "results": results if isinstance(results, list) else [],
            "request_id": request_id
        })

    except Exception as e:
        logger.error(f"[{request_id}] KG query error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


async def get_entity_evidence(session_id: str, entity: str):
    if not validate_session_id(session_id):
        return jsonify({"error": "Invalid session_id"}), 400

    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:X_REQ_ID_SLICE_SIZE])

    try:
        logger.info(f"[{request_id}] Getting entity evidence: {entity} for session: {session_id}")
        session_manager = get_session_manager()
        if not session_manager.get_session(session_id):
            return jsonify({"error": "Session not found"}), 404

        retrieval_system = get_retrieval_system()
        rag_engine = retrieval_system.get_rag_engine(session_id)
        results = rag_engine.retrieve_context(entity, url=session_id, top_k=3) if rag_engine else []

        if isinstance(results, dict) and "error" in results:
            logger.warning(f"[{request_id}] Entity not found: {entity}")
            return jsonify(results), 404

        return jsonify({
            "entity": entity,
            "evidence": results,
            "request_id": request_id
        })

    except Exception as e:
        logger.error(f"[{request_id}] Entity evidence error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


async def get_session_summary(session_id: str):
    if not validate_session_id(session_id):
        return jsonify({"error": "Invalid session_id"}), 400

    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:X_REQ_ID_SLICE_SIZE])

    try:
        logger.info(f"[{request_id}] Getting summary for session: {session_id}")
        session_manager = get_session_manager()
        session_data = session_manager.get_session(session_id)
        if not session_data:
            return jsonify({"error": "Session not found"}), 404

        rag_stats = {}
        try:
            retrieval_system = get_retrieval_system()
            rag_engine = retrieval_system.get_rag_engine(session_id)
            rag_stats = rag_engine.get_stats() if rag_engine else {}
        except Exception:
            pass

        return jsonify({
            "session_id": session_id,
            "summary": session_manager.get_session_summary(session_id),
            "stats": rag_stats,
            "request_id": request_id
        })

    except Exception as e:
        logger.error(f"[{request_id}] Summary error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


async def delete_session(session_id: str):
    if not validate_session_id(session_id):
        return jsonify({"error": "Invalid session_id"}), 400

    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:X_REQ_ID_SLICE_SIZE])

    try:
        logger.info(f"[{request_id}] Deleting session: {session_id}")
        session_manager = get_session_manager()
        session_manager.cleanup_session(session_id)

        logger.info(f"[{request_id}] Session deleted: {session_id}")

        return jsonify({
            "message": "Session deleted",
            "session_id": session_id,
            "request_id": request_id
        }), 200

    except Exception as e:
        logger.error(f"[{request_id}] Session deletion error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
