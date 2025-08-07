"""
MCP-enabled Coordinator Agent

This module implements a coordinator agent that uses the Model Context Protocol (MCP)
for orchestrating the entire RAG pipeline with proper message passing.
"""

import logging
import time
import uuid
from typing import Dict, List, Any, Optional
from utils.mcp import MessageType, broker
from utils.mcp_client import MCPAgent
from .mcp_ingestion_agent import MCPIngestionAgent
from .mcp_retrieval_agent import MCPRetrievalAgent
from .mcp_llm_agent import MCPLLMAgent

logger = logging.getLogger(__name__)

class MCPCoordinatorAgent(MCPAgent):
    """
    Coordinator agent that orchestrates the RAG pipeline using MCP
    
    Handles:
    - Document processing workflows
    - Query processing workflows
    - System health monitoring
    - Agent coordination
    """
    
    def __init__(self, api_url: Optional[str] = None):
        """
        Initialize coordinator agent
        
        Args:
            api_url: URL of MCP REST API (None for in-memory only)
        """
        super().__init__("CoordinatorAgent", api_url)
        
        # Initialize sub-agents
        self.ingestion_agent = MCPIngestionAgent(api_url)
        self.retrieval_agent = MCPRetrievalAgent(api_url)
        self.llm_agent = MCPLLMAgent(api_url)
        
        # Enhanced stats
        self.stats.update({
            "documents_processed": 0,
            "queries_answered": 0,
            "workflows_started": 0,
            "workflows_completed": 0,
            "total_processing_time": 0.0,
            "average_response_time": 0.0
        })
        
        # Active workflows
        self.active_workflows: Dict[str, Dict[str, Any]] = {}
        
        # Register message handlers
        self._register_handlers()
        
        # Register with broker
        broker.register_agent(self.agent_id, {
            "type": "coordinator",
            "capabilities": ["document_processing", "query_processing", "workflow_management"],
            "sub_agents": ["IngestionAgent", "RetrievalAgent", "LLMResponseAgent"]
        })
        
        logger.info("MCP Coordinator Agent initialized successfully")
    
    def _register_handlers(self):
        """Register message handlers"""
        # Document processing
        self.mcp.register_handler(MessageType.INGESTION_REQUEST.value, self.handle_ingestion_request)
        
        # Query processing
        self.mcp.register_handler(MessageType.QUERY_REQUEST.value, self.handle_query_request)
        
        # Workflow responses
        self.mcp.register_handler(MessageType.DOCUMENTS_INDEXED.value, self.handle_documents_indexed)
        self.mcp.register_handler(MessageType.RESPONSE_GENERATED.value, self.handle_response_generated)
        
        # System messages
        self.mcp.register_handler(MessageType.SYSTEM_STATUS.value, self.handle_system_status_request)
    
    def handle_ingestion_request(self, message):
        """
        Handle document ingestion requests
        
        Workflow:
        1. Start workflow
        2. Send to ingestion agent
        3. Wait for processing
        4. Send to retrieval agent for indexing
        5. Complete workflow
        """
        try:
            file_path = message.payload.get("file_path")
            if not file_path:
                self.mcp.send_error(message.sender, "No file_path provided in ingestion request")
                return
            
            # Start workflow
            workflow_id = str(uuid.uuid4())
            self.active_workflows[workflow_id] = {
                "id": workflow_id,
                "type": "document_processing",
                "file_path": file_path,
                "started_at": time.time(),
                "status": "processing",
                "steps": ["ingestion", "indexing"],
                "current_step": "ingestion",
                "original_sender": message.sender,
                "original_trace_id": message.trace_id
            }
            
            logger.info(f"Starting document processing workflow: {workflow_id} for {file_path}")
            
            # Send workflow start notification
            self.mcp.send(
                receiver="*",
                msg_type=MessageType.WORKFLOW_START.value,
                payload={
                    "workflow_id": workflow_id,
                    "workflow_type": "document_processing",
                    "file_path": file_path
                },
                trace_id=workflow_id
            )
            
            # Forward to ingestion agent
            self.mcp.send(
                receiver="IngestionAgent",
                msg_type=MessageType.INGESTION_REQUEST.value,
                payload=message.payload,
                trace_id=workflow_id
            )
            
            self.stats["workflows_started"] += 1
            
        except Exception as e:
            error_msg = f"Error handling ingestion request: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.mcp.send_error(message.sender, error_msg)
    
    def handle_query_request(self, message):
        """
        Handle query processing requests
        
        Workflow:
        1. Start workflow
        2. Send to retrieval agent for context
        3. Send context to LLM agent
        4. Return response to sender
        5. Complete workflow
        """
        try:
            query = message.payload.get("query")
            if not query:
                self.mcp.send_error(message.sender, "No query provided in request")
                return
            
            # Start workflow
            workflow_id = str(uuid.uuid4())
            self.active_workflows[workflow_id] = {
                "id": workflow_id,
                "type": "query_processing",
                "query": query,
                "started_at": time.time(),
                "status": "processing",
                "steps": ["retrieval", "generation"],
                "current_step": "retrieval",
                "original_sender": message.sender,
                "original_trace_id": message.trace_id
            }
            
            logger.info(f"Starting query processing workflow: {workflow_id} for query: {query[:50]}...")
            
            # Send workflow start notification
            self.mcp.send(
                receiver="*",
                msg_type=MessageType.WORKFLOW_START.value,
                payload={
                    "workflow_id": workflow_id,
                    "workflow_type": "query_processing",
                    "query": query
                },
                trace_id=workflow_id
            )
            
            # Forward to retrieval agent
            self.mcp.send(
                receiver="RetrievalAgent",
                msg_type=MessageType.QUERY_REQUEST.value,
                payload=message.payload,
                trace_id=workflow_id
            )
            
            self.stats["workflows_started"] += 1
            
        except Exception as e:
            error_msg = f"Error handling query request: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.mcp.send_error(message.sender, error_msg)
    
    def handle_documents_indexed(self, message):
        """Handle documents indexed response from retrieval agent"""
        try:
            workflow_id = message.workflow_id
            if not workflow_id or workflow_id not in self.active_workflows:
                logger.warning(f"Received documents indexed message without valid workflow: {workflow_id}")
                return
            
            workflow = self.active_workflows[workflow_id]
            
            if message.is_error():
                # Handle error in workflow
                workflow["status"] = "failed"
                workflow["error"] = message.error
                workflow["completed_at"] = time.time()
                
                # Send error to original sender
                self.mcp.send_error(
                    receiver=workflow["original_sender"],
                    error_msg=f"Document processing failed: {message.error}"
                )
                
                # Clean up workflow
                del self.active_workflows[workflow_id]
                return
            
            # Update workflow
            workflow["status"] = "completed"
            workflow["completed_at"] = time.time()
            processing_time = workflow["completed_at"] - workflow["started_at"]
            
            # Update stats
            self.stats["documents_processed"] += 1
            self.stats["workflows_completed"] += 1
            self.stats["total_processing_time"] += processing_time
            
            logger.info(f"Document processing workflow completed: {workflow_id} in {processing_time:.2f}s")
            
            # Send success response to original sender
            self.mcp.send(
                receiver=workflow["original_sender"],
                msg_type=MessageType.DOCUMENTS_INDEXED.value,
                payload={
                    **message.payload,
                    "workflow_id": workflow_id,
                    "total_processing_time": processing_time
                },
                trace_id=workflow["original_trace_id"]
            )
            
            # Send workflow completion notification
            self.mcp.send(
                receiver="*",
                msg_type=MessageType.WORKFLOW_COMPLETE.value,
                payload={
                    "workflow_id": workflow_id,
                    "workflow_type": "document_processing",
                    "status": "completed",
                    "processing_time": processing_time
                },
                trace_id=workflow_id
            )
            
            # Clean up workflow
            del self.active_workflows[workflow_id]
            
        except Exception as e:
            error_msg = f"Error handling documents indexed: {str(e)}"
            logger.error(error_msg, exc_info=True)
    
    def handle_response_generated(self, message):
        """Handle response generated from LLM agent"""
        try:
            workflow_id = message.workflow_id
            if not workflow_id or workflow_id not in self.active_workflows:
                logger.warning(f"Received response generated message without valid workflow: {workflow_id}")
                return
            
            workflow = self.active_workflows[workflow_id]
            
            if message.is_error():
                # Handle error in workflow
                workflow["status"] = "failed"
                workflow["error"] = message.error
                workflow["completed_at"] = time.time()
                
                # Send error to original sender
                self.mcp.send_error(
                    receiver=workflow["original_sender"],
                    error_msg=f"Query processing failed: {message.error}"
                )
                
                # Clean up workflow
                del self.active_workflows[workflow_id]
                return
            
            # Update workflow
            workflow["status"] = "completed"
            workflow["completed_at"] = time.time()
            processing_time = workflow["completed_at"] - workflow["started_at"]
            
            # Update stats
            self.stats["queries_answered"] += 1
            self.stats["workflows_completed"] += 1
            self.stats["total_processing_time"] += processing_time
            self._update_average_response_time()
            
            logger.info(f"Query processing workflow completed: {workflow_id} in {processing_time:.2f}s")
            
            # Send response to original sender
            self.mcp.send(
                receiver=workflow["original_sender"],
                msg_type=MessageType.RESPONSE_GENERATED.value,
                payload={
                    **message.payload,
                    "workflow_id": workflow_id,
                    "total_processing_time": processing_time
                },
                trace_id=workflow["original_trace_id"]
            )
            
            # Send workflow completion notification
            self.mcp.send(
                receiver="*",
                msg_type=MessageType.WORKFLOW_COMPLETE.value,
                payload={
                    "workflow_id": workflow_id,
                    "workflow_type": "query_processing",
                    "status": "completed",
                    "processing_time": processing_time
                },
                trace_id=workflow_id
            )
            
            # Clean up workflow
            del self.active_workflows[workflow_id]
            
        except Exception as e:
            error_msg = f"Error handling response generated: {str(e)}"
            logger.error(error_msg, exc_info=True)
    
    def handle_system_status_request(self, message):
        """Handle system status requests"""
        try:
            # Get health status from all agents
            health_checks = {}
            
            # Check sub-agents
            for agent_name, agent in [
                ("IngestionAgent", self.ingestion_agent),
                ("RetrievalAgent", self.retrieval_agent),
                ("LLMResponseAgent", self.llm_agent)
            ]:
                health_info = agent.health_check()
                health_checks[agent_name] = health_info
            
            # Determine overall status
            overall_status = "healthy"
            for agent_health in health_checks.values():
                if agent_health.get("status") != "healthy":
                    overall_status = "degraded"
                    break
            
            # Send system status response
            self.reply_to(
                original_msg=message,
                msg_type=MessageType.SYSTEM_STATUS.value,
                payload={
                    "overall_status": overall_status,
                    "agent_health": health_checks,
                    "coordinator_stats": self.get_stats(),
                    "active_workflows": len(self.active_workflows),
                    "broker_stats": broker.get_stats()
                }
            )
            
        except Exception as e:
            error_msg = f"Error getting system status: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.mcp.send_error(message.sender, error_msg)
    
    def _update_average_response_time(self):
        """Update average response time"""
        if self.stats["queries_answered"] > 0:
            self.stats["average_response_time"] = (
                self.stats["total_processing_time"] / self.stats["queries_answered"]
            )
    
    def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific workflow"""
        return self.active_workflows.get(workflow_id)
    
    def get_active_workflows(self) -> List[Dict[str, Any]]:
        """Get all active workflows"""
        return list(self.active_workflows.values())
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get comprehensive pipeline statistics"""
        return {
            "coordinator": self.get_stats(),
            "ingestion": self.ingestion_agent.get_stats(),
            "retrieval": self.retrieval_agent.get_stats(),
            "llm": self.llm_agent.get_stats(),
            "broker": broker.get_stats()
        }
    
    def process_document(self, file_path: str) -> Dict[str, Any]:
        """
        Process a document (legacy method for backward compatibility)
        
        Args:
            file_path: Path to the document to process
            
        Returns:
            Processing result
        """
        # Create ingestion request message
        message = self.mcp.send(
            receiver=self.agent_id,
            msg_type=MessageType.INGESTION_REQUEST.value,
            payload={"file_path": file_path}
        )
        
        return {
            "status": "started",
            "trace_id": message.trace_id,
            "file_path": file_path
        }
    
    def answer_query(self, query: str, search_k: int = 5) -> Dict[str, Any]:
        """
        Answer a query (legacy method for backward compatibility)
        
        Args:
            query: Query string
            search_k: Number of search results
            
        Returns:
            Query result
        """
        # Create query request message
        message = self.mcp.send(
            receiver=self.agent_id,
            msg_type=MessageType.QUERY_REQUEST.value,
            payload={
                "query": query,
                "search_k": search_k
            }
        )
        
        return {
            "status": "started",
            "trace_id": message.trace_id,
            "query": query
        }