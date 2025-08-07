"""
MCP-enabled Ingestion Agent

This module implements an ingestion agent that uses the Model Context Protocol (MCP)
for document processing and communication with other agents.
"""

import logging
import os
from typing import Optional, Dict, Any
from utils.document_parser import DocumentParser
from utils.mcp import MessageType, broker
from utils.mcp_client import MCPAgent

logger = logging.getLogger(__name__)

class MCPIngestionAgent(MCPAgent):
    """
    Ingestion agent that uses MCP for communication
    
    Handles document parsing and chunk extraction
    """
    
    def __init__(self, api_url: Optional[str] = None):
        """
        Initialize ingestion agent
        
        Args:
            api_url: URL of MCP REST API (None for in-memory only)
        """
        super().__init__("IngestionAgent", api_url)
        
        # Enhanced stats
        self.stats.update({
            "files_processed": 0,
            "total_chunks": 0,
            "processing_errors": 0,
            "supported_formats": len(DocumentParser.get_supported_extensions())
        })
        
        self.processed_files = set()
        
        # Register message handlers
        self._register_handlers()
        
        # Register with broker
        broker.register_agent(self.agent_id, {
            "type": "ingestion",
            "capabilities": ["document_parsing", "chunk_extraction"],
            "supported_formats": DocumentParser.get_supported_extensions()
        })
        
        logger.info("MCP Ingestion Agent initialized successfully")
    
    def _register_handlers(self):
        """Register message handlers"""
        self.mcp.register_handler(MessageType.INGESTION_REQUEST.value, self.handle_ingestion_request)
    
    def handle_ingestion_request(self, message):
        """
        Handle document ingestion requests
        
        Args:
            message: MCP message with ingestion request
        """
        try:
            file_path = message.payload.get("file_path")
            chunk_size = message.payload.get("chunk_size", 1000)
            chunk_overlap = message.payload.get("chunk_overlap", 200)
            
            if not file_path:
                error_msg = "No file_path provided in ingestion request"
                logger.error(error_msg)
                self.stats["processing_errors"] += 1
                self.reply_to(
                    original_msg=message,
                    msg_type=MessageType.ERROR.value,
                    payload={"error": error_msg}
                )
                return
            
            # Validate file exists
            if not os.path.exists(file_path):
                error_msg = f"File not found: {file_path}"
                logger.error(error_msg)
                self.stats["processing_errors"] += 1
                self.reply_to(
                    original_msg=message,
                    msg_type=MessageType.ERROR.value,
                    payload={"error": error_msg}
                )
                return
            
            # Check if file type is supported
            if not DocumentParser.is_supported_file(file_path):
                error_msg = f"Unsupported file type: {file_path}"
                logger.error(error_msg)
                self.stats["processing_errors"] += 1
                self.reply_to(
                    original_msg=message,
                    msg_type=MessageType.ERROR.value,
                    payload={"error": error_msg}
                )
                return
            
            logger.info(f"Processing document: {file_path}")
            
            # Parse document
            chunks = DocumentParser.parse_file(file_path, chunk_size, chunk_overlap)
            
            if not chunks:
                error_msg = f"No content extracted from file: {file_path}"
                logger.warning(error_msg)
                self.stats["processing_errors"] += 1
                self.reply_to(
                    original_msg=message,
                    msg_type=MessageType.ERROR.value,
                    payload={"error": error_msg}
                )
                return
            
            # Update stats
            self.processed_files.add(file_path)
            self.stats["files_processed"] += 1
            self.stats["total_chunks"] += len(chunks)
            
            # Get file metadata
            file_stats = os.stat(file_path)
            file_size = file_stats.st_size
            file_ext = os.path.splitext(file_path)[1].lower()
            
            logger.info(f"Successfully processed {file_path}: {len(chunks)} chunks extracted")
            
            # Send processed document to retrieval agent
            self.send_message(
                receiver="RetrievalAgent",
                msg_type=MessageType.DOCUMENT_PROCESSED.value,
                payload={
                    "chunks": chunks,
                    "file_path": file_path,
                    "chunk_count": len(chunks),
                    "file_size": file_size,
                    "file_type": file_ext,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "processing_stats": self.stats.copy()
                },
                metadata={
                    "file_name": os.path.basename(file_path),
                    "file_extension": file_ext,
                    "file_size_mb": round(file_size / (1024 * 1024), 2),
                    "workflow_id": getattr(message, 'workflow_id', None),
                    "parent_trace_id": message.trace_id
                }
            )
            
        except Exception as e:
            error_msg = f"Error processing document {file_path}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stats["processing_errors"] += 1
            self.reply_to(
                original_msg=message,
                msg_type=MessageType.ERROR.value,
                payload={"error": error_msg}
            )
    
    def process_document(self, file_path: str, chunk_size: int = 1000, 
                        chunk_overlap: int = 200) -> Dict[str, Any]:
        """
        Process a document (direct method for backward compatibility)
        
        Args:
            file_path: Path to the document to process
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
            
        Returns:
            Processing result
        """
        try:
            # Validate file exists
            if not os.path.exists(file_path):
                return {
                    "status": "error",
                    "error": f"File not found: {file_path}"
                }
            
            # Check if file type is supported
            if not DocumentParser.is_supported_file(file_path):
                return {
                    "status": "error",
                    "error": f"Unsupported file type: {file_path}"
                }
            
            logger.info(f"Processing document: {file_path}")
            
            # Parse document
            chunks = DocumentParser.parse_file(file_path, chunk_size, chunk_overlap)
            
            if not chunks:
                return {
                    "status": "error",
                    "error": f"No content extracted from file: {file_path}"
                }
            
            # Update stats
            self.processed_files.add(file_path)
            self.stats["files_processed"] += 1
            self.stats["total_chunks"] += len(chunks)
            
            # Get file metadata
            file_stats = os.stat(file_path)
            file_size = file_stats.st_size
            file_ext = os.path.splitext(file_path)[1].lower()
            
            logger.info(f"Successfully processed {file_path}: {len(chunks)} chunks extracted")
            
            return {
                "status": "success",
                "chunks": chunks,
                "file_path": file_path,
                "chunk_count": len(chunks),
                "file_size": file_size,
                "file_type": file_ext,
                "processing_stats": self.stats.copy()
            }
            
        except Exception as e:
            error_msg = f"Error processing document {file_path}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stats["processing_errors"] += 1
            
            return {
                "status": "error",
                "error": error_msg
            }
    
    def get_processed_files(self) -> list:
        """Get list of processed files"""
        return list(self.processed_files)
    
    def get_supported_formats(self) -> list:
        """Get list of supported file formats"""
        return DocumentParser.get_supported_extensions()
    
    def health_check(self) -> Dict[str, Any]:
        """Get agent health status"""
        return {
            "status": "healthy",
            "agent_id": self.agent_id,
            "stats": self.get_stats(),
            "processed_files_count": len(self.processed_files),
            "supported_formats": self.get_supported_formats()
        }