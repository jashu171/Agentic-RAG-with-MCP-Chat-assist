"""
MCP-enabled Retrieval Agent

This module implements a retrieval agent that uses the Model Context Protocol (MCP)
for communication with other agents in the system.
"""

import logging
from typing import List, Dict, Any, Optional
from utils.vector_store import VectorStore
from utils.mcp import MessageType
from utils.mcp_client import MCPAgent

logger = logging.getLogger(__name__)

class MCPRetrievalAgent(MCPAgent):
    """
    Retrieval agent that uses MCP for communication
    
    Handles document indexing and context retrieval
    """
    
    def __init__(self, api_url: Optional[str] = None):
        """
        Initialize retrieval agent
        
        Args:
            api_url: URL of MCP REST API (None for in-memory only)
        """
        super().__init__("RetrievalAgent", api_url)
        self.vector_store = VectorStore()
        
        # Enhanced stats
        self.stats.update({
            "documents_indexed": 0,
            "queries_processed": 0,
            "total_chunks": 0,
            "errors": 0
        })
        
        # Register message handlers
        self._register_handlers()
        
        logger.info("MCP Retrieval Agent initialized successfully")
    
    def _register_handlers(self):
        """Register message handlers"""
        self.mcp.register_handler(MessageType.DOCUMENT_PROCESSED.value, self.handle_document_processed)
        self.mcp.register_handler(MessageType.QUERY_REQUEST.value, self.handle_query_request)
    
    def handle_document_processed(self, message):
        """
        Handle document processed messages
        
        Args:
            message: MCP message with processed document chunks
        """
        try:
            if message.is_error():
                logger.error(f"Received error message: {message.error}")
                self.send_message(
                    receiver="CoordinatorAgent",
                    msg_type=MessageType.ERROR.value,
                    payload={"error": f"Cannot index documents due to upstream error: {message.error}"}
                )
                return
            
            chunks = message.payload.get("chunks", [])
            file_path = message.payload.get("file_path", "unknown")
            
            if not chunks:
                error_msg = "No chunks provided for indexing"
                logger.warning(error_msg)
                self.stats["errors"] += 1
                self.send_message(
                    receiver="CoordinatorAgent",
                    msg_type=MessageType.ERROR.value,
                    payload={"error": error_msg}
                )
                return
            
            # Add documents with metadata
            metadata = {
                "file_path": file_path,
                "file_name": message.metadata.get("file_name", "unknown"),
                "file_type": message.payload.get("file_type", "unknown"),
                "processing_time": message.get_age_seconds()
            }
            
            self.vector_store.add_documents(chunks, metadata)
            
            # Update stats
            self.stats["documents_indexed"] += 1
            self.stats["total_chunks"] += len(chunks)
            
            logger.info(f"Successfully indexed {len(chunks)} chunks from {file_path}")
            
            # Send success response to coordinator
            self.send_message(
                receiver="CoordinatorAgent",
                msg_type=MessageType.DOCUMENTS_INDEXED.value,
                payload={
                    "status": "success",
                    "chunks_added": len(chunks),
                    "file_path": file_path,
                    "total_documents": self.vector_store.get_collection_info()["count"],
                    "indexing_stats": self.stats.copy()
                },
                metadata={
                    "processing_time_seconds": getattr(message, 'get_age_seconds', lambda: 0)()
                }
            )
            
        except Exception as e:
            error_msg = f"Error indexing documents: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stats["errors"] += 1
            self.send_message(
                receiver="CoordinatorAgent",
                msg_type=MessageType.ERROR.value,
                payload={"error": error_msg},
                workflow_id=message.workflow_id,
                parent_trace_id=message.trace_id
            )
    
    def handle_query_request(self, message):
        """
        Handle query request messages
        
        Args:
            message: MCP message with query request
        """
        try:
            query = message.payload.get("query", "")
            k = message.payload.get("search_k", 5)
            similarity_threshold = message.payload.get("similarity_threshold", 0.7)
            
            if not query.strip():
                error_msg = "Empty query provided"
                logger.warning(error_msg)
                self.send_message(
                    receiver="LLMResponseAgent",
                    msg_type=MessageType.ERROR.value,
                    payload={"error": error_msg, "query": query}
                )
                return
            
            # Enhanced search with metadata
            search_results = self.vector_store.search_with_metadata(query, k=k)
            
            if not search_results:
                logger.info(f"No relevant documents found for query: {query}")
                relevant_chunks = []
                metadata_list = []
            else:
                relevant_chunks = [result["document"] for result in search_results]
                metadata_list = [result["metadata"] for result in search_results]
            
            # Update stats
            self.stats["queries_processed"] += 1
            
            logger.info(f"Retrieved {len(relevant_chunks)} chunks for query: {query[:50]}...")
            
            # Send retrieval result to LLM agent
            self.send_message(
                receiver="LLMResponseAgent",
                msg_type=MessageType.RETRIEVAL_RESULT.value,
                payload={
                    "top_chunks": relevant_chunks,
                    "chunk_metadata": metadata_list,
                    "query": query,
                    "total_results": len(relevant_chunks),
                    "collection_size": self.vector_store.get_collection_info()["count"],
                    "retrieved_context": relevant_chunks  # For compatibility with example format
                },
                metadata={
                    "search_k": k,
                    "similarity_threshold": similarity_threshold,
                    "query_length": len(query)
                }
            )
            
        except Exception as e:
            error_msg = f"Error retrieving context for query '{query}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stats["errors"] += 1
            self.send_message(
                receiver="LLMResponseAgent",
                msg_type=MessageType.ERROR.value,
                payload={"error": error_msg, "query": query}
            )
    
    def add_documents(self, chunks: List[str], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add documents to vector store
        
        Args:
            chunks: Document chunks to add
            metadata: Document metadata
            
        Returns:
            Result of indexing operation
        """
        try:
            self.vector_store.add_documents(chunks, metadata)
            
            # Update stats
            self.stats["documents_indexed"] += 1
            self.stats["total_chunks"] += len(chunks)
            
            logger.info(f"Successfully indexed {len(chunks)} chunks")
            
            return {
                "status": "success",
                "chunks_added": len(chunks),
                "total_documents": self.vector_store.get_collection_info()["count"]
            }
            
        except Exception as e:
            error_msg = f"Error indexing documents: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stats["errors"] += 1
            
            return {
                "status": "error",
                "error": error_msg
            }
    
    def retrieve_context(self, query: str, k: int = 5, similarity_threshold: float = 0.7) -> Dict[str, Any]:
        """
        Retrieve context for a query
        
        Args:
            query: Query string
            k: Number of results to return
            similarity_threshold: Minimum similarity score
            
        Returns:
            Retrieved context and metadata
        """
        try:
            if not query.strip():
                return {
                    "status": "error",
                    "error": "Empty query provided",
                    "top_chunks": [],
                    "chunk_metadata": []
                }
            
            # Enhanced search with metadata
            search_results = self.vector_store.search_with_metadata(query, k=k)
            
            if not search_results:
                logger.info(f"No relevant documents found for query: {query}")
                relevant_chunks = []
                metadata_list = []
            else:
                relevant_chunks = [result["document"] for result in search_results]
                metadata_list = [result["metadata"] for result in search_results]
            
            # Update stats
            self.stats["queries_processed"] += 1
            
            logger.info(f"Retrieved {len(relevant_chunks)} chunks for query: {query[:50]}...")
            
            return {
                "status": "success",
                "top_chunks": relevant_chunks,
                "chunk_metadata": metadata_list,
                "query": query,
                "total_results": len(relevant_chunks),
                "collection_size": self.vector_store.get_collection_info()["count"]
            }
            
        except Exception as e:
            error_msg = f"Error retrieving context for query '{query}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stats["errors"] += 1
            
            return {
                "status": "error",
                "error": error_msg,
                "top_chunks": [],
                "chunk_metadata": []
            }
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get vector store collection information"""
        return self.vector_store.get_collection_info()
    
    def clear_collection(self) -> Dict[str, Any]:
        """Clear vector store collection"""
        try:
            result = self.vector_store.clear_collection()
            return {
                "status": "success",
                "result": result
            }
        except Exception as e:
            error_msg = f"Error clearing collection: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "status": "error",
                "error": error_msg
            }