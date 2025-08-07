"""
Agentic RAG Application with Model Context Protocol (MCP)

This application implements a complete RAG system using MCP for agent communication.
It provides a Flask web API for document upload and query processing.
"""

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
import logging
import time
from werkzeug.utils import secure_filename
from datetime import datetime
from agents.mcp_coordinator import MCPCoordinatorAgent
from utils.document_parser import DocumentParser
from utils.mcp import broker, MessageType
from config import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.system.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(config.system.log_file), logging.StreamHandler()],
)

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Apply Flask configuration
flask_config = config.get_flask_config()
for key, value in flask_config.items():
    app.config[key] = value

# Create uploads directory
os.makedirs(config.system.upload_folder, exist_ok=True)

# Initialize MCP coordinator
try:
    coordinator = MCPCoordinatorAgent()
    logger.info("MCP Agentic RAG system initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize MCP coordinator: {str(e)}")
    coordinator = None

# Allowed file extensions
ALLOWED_EXTENSIONS = config.system.allowed_extensions


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.errorhandler(413)
def too_large(e):
    return jsonify(
        {
            "error": f"File too large. Maximum size is {config.system.max_file_size_mb}MB."
        }
    ), 413


@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {str(e)}")
    return jsonify({"error": "Internal server error occurred"}), 500


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    return app.send_static_file("icon.png")


@app.route("/health", methods=["GET"])
def health_check():
    """System health check endpoint with MCP support"""
    if not coordinator:
        return jsonify(
            {"status": "error", "message": "MCP Coordinator not initialized"}
        ), 503

    try:
        # Get coordinator health
        coordinator_health = coordinator.health_check()

        # Get broker stats
        broker_stats = broker.get_stats()

        return jsonify(
            {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "system_health": {
                    "coordinator": coordinator_health,
                    "broker": broker_stats,
                    "registered_agents": broker.get_registered_agents(),
                    "active_workflows": len(coordinator.get_active_workflows()),
                },
            }
        )

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify(
            {"status": "error", "message": "Health check failed", "error": str(e)}
        ), 503


@app.route("/stats", methods=["GET"])
def get_stats():
    """System statistics endpoint with MCP metrics"""
    if not coordinator:
        return jsonify({"error": "System not initialized"}), 503

    try:
        # Get comprehensive pipeline stats
        pipeline_stats = coordinator.get_pipeline_stats()

        # Get recent message history
        recent_messages = broker.get_recent_messages(limit=20)

        # Get active workflows
        active_workflows = coordinator.get_active_workflows()

        # Get broker stats
        broker_stats = broker.get_stats()

        return jsonify(
            {
                "pipeline_stats": pipeline_stats,
                "recent_activity": recent_messages,
                "active_workflows": active_workflows,
                "broker_stats": broker_stats,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return jsonify({"error": "Failed to get statistics"}), 500


@app.route("/upload", methods=["POST"])
def upload_files():
    """File upload with MCP workflow tracking"""
    if not coordinator:
        return jsonify({"error": "System not initialized"}), 503

    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400

    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No files selected"}), 400

    results = {"uploaded_files": [], "failed_files": [], "processing_results": []}

    for file in files:
        if not file or file.filename == "":
            continue

        filename = secure_filename(file.filename)
        if not filename:
            results["failed_files"].append(
                {"filename": file.filename, "error": "Invalid filename"}
            )
            continue

        if not allowed_file(filename):
            results["failed_files"].append(
                {
                    "filename": filename,
                    "error": f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
                }
            )
            continue

        try:
            # Save file
            filepath = os.path.join(config.system.upload_folder, filename)
            file.save(filepath)

            # Validate file can be parsed
            if not DocumentParser.is_supported_file(filepath):
                results["failed_files"].append(
                    {"filename": filename, "error": "File type not supported by parser"}
                )
                os.remove(filepath)  # Clean up
                continue

            # Send ingestion request through MCP
            start_time = time.time()
            ingestion_msg = coordinator.send_message(
                receiver=coordinator.agent_id,
                msg_type=MessageType.INGESTION_REQUEST.value,
                payload={
                    "file_path": filepath,
                    "chunk_size": config.agent.chunk_size,
                    "chunk_overlap": config.agent.chunk_overlap,
                },
            )

            processing_time = time.time() - start_time

            results["uploaded_files"].append(filename)
            results["processing_results"].append(
                {
                    "filename": filename,
                    "status": "processing_started",
                    "processing_time": round(processing_time, 2),
                    "trace_id": ingestion_msg.trace_id,
                }
            )

        except Exception as e:
            logger.error(f"Error processing file {filename}: {str(e)}")
            results["failed_files"].append(
                {"filename": filename, "error": f"Processing error: {str(e)}"}
            )

    # Prepare response
    success_count = len(results["uploaded_files"])
    failed_count = len(results["failed_files"])

    if success_count == 0 and failed_count > 0:
        return jsonify(
            {**results, "message": f"All {failed_count} files failed to process"}
        ), 400
    elif failed_count > 0:
        return jsonify(
            {
                **results,
                "message": f"Started processing {success_count} files, {failed_count} failed",
            }
        ), 207  # Multi-status
    else:
        return jsonify(
            {**results, "message": f"Started processing {success_count} files"}
        )


@app.route("/query", methods=["POST"])
def query():
    """Query processing with MCP workflow tracking"""
    if not coordinator:
        return jsonify({"error": "System not initialized"}), 503

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        query_text = data.get("query", "").strip()
        if not query_text:
            return jsonify({"error": "No query provided"}), 400

        # Optional parameters
        search_k = data.get("search_k", config.agent.default_search_k)
        search_k = max(1, min(search_k, 20))  # Limit between 1-20

        # Process query through the MCP workflow
        start_time = time.time()

        # Use the MCP workflow for query processing
        query_msg = coordinator.send_message(
            receiver=coordinator.agent_id,
            msg_type=MessageType.QUERY_REQUEST.value,
            payload={
                "query": query_text,
                "search_k": search_k,
                "similarity_threshold": config.agent.similarity_threshold,
            },
        )

        # For now, fall back to direct method calls since the workflow is async
        # In a production system, you'd want to implement proper async handling
        
        # Step 1: Get context from retrieval agent
        retrieval_result = coordinator.retrieval_agent.retrieve_context(
            query=query_text,
            k=search_k,
            similarity_threshold=config.agent.similarity_threshold,
        )

        if retrieval_result.get("status") == "error":
            logger.error(f"Retrieval failed: {retrieval_result.get('error')}")
            # Continue with empty context for general response
            context_chunks = []
            chunk_metadata = []
        else:
            context_chunks = retrieval_result.get("top_chunks", [])
            chunk_metadata = retrieval_result.get("chunk_metadata", [])

        # Step 2: Generate response using LLM agent
        llm_result = coordinator.llm_agent.generate_response(
            query=query_text,
            context_chunks=context_chunks,
            chunk_metadata=chunk_metadata,
        )

        processing_time = time.time() - start_time

        if llm_result.get("status") == "error":
            logger.error(f"LLM generation failed: {llm_result.get('error')}")
            return jsonify(
                {
                    "error": "Failed to generate response",
                    "details": llm_result.get("error", "Unknown error"),
                }
            ), 500

        # Return successful response
        return jsonify(
            {
                "answer": llm_result.get("answer", "No response generated"),
                "context_chunks": context_chunks[
                    :3
                ],  # Return first 3 chunks for display
                "sources_used": len(context_chunks),
                "response_type": llm_result.get("response_type", "unknown"),
                "collection_size": retrieval_result.get("collection_size", 0),
                "processing_time": round(processing_time, 2),
                "trace_id": query_msg.trace_id,
                "metadata": {
                    "query_length": len(query_text),
                    "search_k": search_k,
                    "timestamp": datetime.now().isoformat(),
                },
            }
        )

    except Exception as e:
        logger.error(f"Error processing query: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to process query", "details": str(e)}), 500


@app.route("/clear", methods=["POST"])
def clear_documents():
    """Clear all documents from the vector store"""
    if not coordinator:
        return jsonify({"error": "System not initialized"}), 503

    try:
        # Clear vector store
        coordinator.retrieval_agent.clear_collection()

        # Clear upload directory
        for filename in os.listdir(config.system.upload_folder):
            file_path = os.path.join(config.system.upload_folder, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)

        logger.info("Document store and uploads cleared")

        return jsonify(
            {
                "message": "All documents cleared successfully",
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Error clearing documents: {str(e)}")
        return jsonify({"error": "Failed to clear documents", "details": str(e)}), 500


if __name__ == "__main__":
    if coordinator:
        logger.info(
            f"Starting MCP Agentic RAG server on {config.system.api_host}:{config.system.api_port}"
        )
        app.run(
            debug=config.system.debug_mode,
            port=config.system.api_port,
            host=config.system.api_host,
        )
    else:
        logger.error("Cannot start server - MCP coordinator initialization failed")
        exit(1)
