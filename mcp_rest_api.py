#!/usr/bin/env python3
"""
Model Context Protocol (MCP) REST API

This script implements a REST API for MCP communication between distributed agents.
It allows agents to send and receive MCP messages over HTTP.
"""

from flask import Flask, request, jsonify
import logging
import time
from typing import Dict, List
from utils.mcp import MCPMessage, broker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Message queue for each agent
message_queues: Dict[str, List[MCPMessage]] = {}

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "message_queues": {agent: len(queue) for agent, queue in message_queues.items()}
    })

@app.route("/send", methods=["POST"])
def send_message():
    """Send an MCP message"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Create message from JSON
        message = MCPMessage.from_dict(data)
        
        # Add to receiver's queue
        receiver = message.receiver
        if receiver not in message_queues:
            message_queues[receiver] = []
        
        message_queues[receiver].append(message)
        
        # Also send to broker for local processing
        broker.send(message)
        
        logger.info(f"Message queued: {message.sender} → {message.receiver} ({message.type})")
        
        return jsonify({
            "status": "success",
            "trace_id": message.trace_id,
            "timestamp": time.time()
        })
        
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return jsonify({
            "error": f"Failed to send message: {str(e)}"
        }), 500

@app.route("/receive/<agent_id>", methods=["GET"])
def receive_messages(agent_id: str):
    """Receive messages for a specific agent"""
    try:
        # Check if agent has a queue
        if agent_id not in message_queues:
            message_queues[agent_id] = []
            return jsonify({
                "status": "success",
                "messages": []
            })
        
        # Get messages for agent
        messages = message_queues[agent_id]
        
        # Convert to dictionaries
        message_dicts = [msg.to_dict() for msg in messages]
        
        # Clear queue
        message_queues[agent_id] = []
        
        logger.info(f"Delivered {len(messages)} messages to {agent_id}")
        
        return jsonify({
            "status": "success",
            "messages": message_dicts
        })
        
    except Exception as e:
        logger.error(f"Error receiving messages: {str(e)}")
        return jsonify({
            "error": f"Failed to receive messages: {str(e)}"
        }), 500

@app.route("/peek/<agent_id>", methods=["GET"])
def peek_messages(agent_id: str):
    """Peek at messages for a specific agent without removing them"""
    try:
        # Check if agent has a queue
        if agent_id not in message_queues:
            message_queues[agent_id] = []
            return jsonify({
                "status": "success",
                "messages": []
            })
        
        # Get messages for agent
        messages = message_queues[agent_id]
        
        # Convert to dictionaries
        message_dicts = [msg.to_dict() for msg in messages]
        
        logger.info(f"Peeked at {len(messages)} messages for {agent_id}")
        
        return jsonify({
            "status": "success",
            "messages": message_dicts
        })
        
    except Exception as e:
        logger.error(f"Error peeking at messages: {str(e)}")
        return jsonify({
            "error": f"Failed to peek at messages: {str(e)}"
        }), 500

@app.route("/history", methods=["GET"])
def get_history():
    """Get message history"""
    try:
        limit = request.args.get("limit", default=10, type=int)
        history = broker.get_recent_messages(limit=limit)
        
        return jsonify({
            "status": "success",
            "history": history
        })
        
    except Exception as e:
        logger.error(f"Error getting history: {str(e)}")
        return jsonify({
            "error": f"Failed to get history: {str(e)}"
        }), 500

@app.route("/stats", methods=["GET"])
def get_stats():
    """Get MCP statistics"""
    try:
        stats = {
            "queue_sizes": {agent: len(queue) for agent, queue in message_queues.items()},
            "total_queued_messages": sum(len(queue) for queue in message_queues.values()),
            "history_size": len(broker.message_history),
            "registered_handlers": {
                receiver: list(msg_types.keys()) 
                for receiver, msg_types in broker.handlers.items()
            }
        }
        
        return jsonify({
            "status": "success",
            "stats": stats
        })
        
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return jsonify({
            "error": f"Failed to get stats: {str(e)}"
        }), 500

@app.route("/clear/<agent_id>", methods=["POST"])
def clear_queue(agent_id: str):
    """Clear message queue for a specific agent"""
    try:
        if agent_id in message_queues:
            queue_size = len(message_queues[agent_id])
            message_queues[agent_id] = []
            logger.info(f"Cleared {queue_size} messages for {agent_id}")
        else:
            logger.info(f"No queue found for {agent_id}")
            message_queues[agent_id] = []
        
        return jsonify({
            "status": "success",
            "agent_id": agent_id,
            "cleared_messages": queue_size if 'queue_size' in locals() else 0
        })
        
    except Exception as e:
        logger.error(f"Error clearing queue: {str(e)}")
        return jsonify({
            "error": f"Failed to clear queue: {str(e)}"
        }), 500

def register_agent_handler(agent_id: str, msg_type: str, handler_function):
    """Register a handler for a specific agent and message type"""
    broker.register_handler(agent_id, msg_type, handler_function)

if __name__ == "__main__":
    logger.info("Starting MCP REST API server on port 8001")
    app.run(debug=True, port=8009, host='0.0.0.0')