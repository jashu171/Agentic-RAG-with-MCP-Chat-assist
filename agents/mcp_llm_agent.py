"""
MCP-enabled LLM Response Agent

This module implements an LLM agent that uses the Model Context Protocol (MCP)
for generating responses using Google Gemini with retrieved context.
"""

import logging
import time
import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import google.generativeai as genai
from utils.mcp import MessageType, broker
from utils.mcp_client import MCPAgent

load_dotenv()
logger = logging.getLogger(__name__)


class MCPLLMAgent(MCPAgent):
    """
    LLM agent that uses MCP for communication

    Handles response generation using Google Gemini
    """

    def __init__(self, api_url: Optional[str] = None):
        """
        Initialize LLM agent

        Args:
            api_url: URL of MCP REST API (None for in-memory only)
        """
        super().__init__("LLMResponseAgent", api_url)

        # Initialize Gemini
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

        # Enhanced stats
        self.stats.update(
            {
                "responses_generated": 0,
                "rag_responses": 0,
                "general_responses": 0,
                "processing_errors": 0,
                "total_tokens_used": 0,
                "average_response_time": 0.0,
            }
        )

        # Modern Response templates with structured format
        self.templates = {
            "rag_prompt": """You are an AI assistant that provides well-structured, modern responses based on uploaded documents. 

CONTEXT FROM UPLOADED FILES:
{context}

SOURCES: {sources}

USER QUERY: {query}

RESPONSE FORMAT REQUIREMENTS:
1. Start with a brief definition/summary (2-3 sentences max)
2. Provide key important context from the documents
3. Use bullet points for lists and key information
4. Create tables when data is structured (use markdown table format)
5. Use clear headings and sections
6. Keep paragraphs short and readable

STRUCTURE YOUR RESPONSE EXACTLY LIKE THIS:

## 📋 Quick Answer
[Brief 1-2 sentence definition/summary of what the query is asking]

## 🔍 Key Context
[2-3 sentences of the most important context from the uploaded documents]

## 📊 Main Points
• [Key point 1]
• [Key point 2] 
• [Key point 3]

## 📈 Data/Details
[If there's numerical data, create a table using markdown format:
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Data 1   | Data 2   | Data 3   |

If no tabular data, use bullet points for details]

## 💡 Summary
[Brief conclusion or key takeaway]

Remember: Keep it concise, well-structured, and easy to scan. Use emojis sparingly for section headers only.""",

            "general_prompt": """You are an AI assistant providing general knowledge responses.

USER QUERY: {query}

RESPONSE FORMAT REQUIREMENTS:
1. Start with a brief definition/summary (2-3 sentences max)
2. Provide key important context
3. Use bullet points for lists and key information
4. Create tables when data is structured
5. Use clear headings and sections
6. Keep paragraphs short and readable

STRUCTURE YOUR RESPONSE EXACTLY LIKE THIS:

## 📋 Quick Answer
[Brief 1-2 sentence definition/summary]

## 🔍 Key Context
[2-3 sentences of important background information]

## 📊 Main Points
• [Key point 1]
• [Key point 2] 
• [Key point 3]

## 📈 Additional Details
[More detailed information, use tables if applicable]

## 💡 Summary
[Brief conclusion or key takeaway]

Note: This response is based on general knowledge. Upload relevant documents for more specific, document-based answers.""",

            "error_response": """## ❌ Error Processing Request

Something went wrong while handling your request.

## 🔍 Error Details
{error}

## 📊 What You Can Try
• Rephrase your question more clearly
• Ensure any referenced file is uploaded properly
• Check if the file contains readable text content
• Try again in a few moments

## 💡 Need Help?
If the problem persists, please contact support or try uploading your documents again.""",

            "no_documents_response": """## 📋 General Knowledge Response

I couldn't find any relevant uploaded documents for this query, so I'm providing a general response.

## 🔍 Response Based on General Knowledge
{answer}

## 📊 To Get Better Results
• Upload files that directly relate to your question
• Ensure documents contain readable, extractable content
• Use keywords or phrases found in your files when asking questions

## 💡 Tip
Upload your documents to get more tailored, document-specific answers with exact references and data."""
        }

        # Register message handlers
        self._register_handlers()

        # Register with broker
        broker.register_agent(self.agent_id, {
            "type": "llm_response",
            "capabilities": ["response_generation", "context_processing"],
            "model": "gemini-2.0-flash"
        })

        logger.info("MCP LLM Agent initialized successfully")

    def _register_handlers(self):
        """Register message handlers"""
        self.mcp.register_handler(MessageType.RETRIEVAL_RESULT.value, self.handle_retrieval_result)

    def handle_retrieval_result(self, message):
        """
        Handle retrieval result messages

        Args:
            message: MCP message with retrieval results
        """
        try:
            if message.is_error():
                logger.error(f"Received error from retrieval: {message.error}")
                self.reply_to(
                    original_msg=message,
                    msg_type=MessageType.ERROR.value,
                    payload={"error": f"Cannot generate response due to retrieval error: {message.error}"}
                )
                return

            # Extract data from message
            chunks = message.payload.get("top_chunks", [])
            chunk_metadata = message.payload.get("chunk_metadata", [])
            query = message.payload.get("query", "")
            collection_size = message.payload.get("collection_size", 0)

            if not query:
                error_msg = "No query provided in retrieval result"
                logger.error(error_msg)
                self.reply_to(
                    original_msg=message,
                    msg_type=MessageType.ERROR.value,
                    payload={"error": error_msg}
                )
                return

            logger.info(f"Generating response for query: {query[:50]}... with {len(chunks)} chunks")

            start_time = time.time()

            # Determine response mode
            use_rag = chunks and len(chunks) > 0

            if use_rag:
                response_data = self._generate_rag_response(chunks, chunk_metadata, query)
                response_type = "rag"
                self.stats["rag_responses"] += 1
            else:
                response_data = self._generate_general_response_data(query)
                response_type = "general"
                self.stats["general_responses"] += 1

            # Calculate processing time
            processing_time = time.time() - start_time

            # Update stats
            self.stats["responses_generated"] += 1
            self._update_average_response_time(processing_time)

            logger.info(f"Generated {response_type} response in {processing_time:.2f}s")

            # Send response back to coordinator
            self.send_message(
                receiver="CoordinatorAgent",
                msg_type=MessageType.RESPONSE_GENERATED.value,
                payload={
                    **response_data,
                    "query": query,
                    "response_type": response_type,
                    "collection_size": collection_size,
                    "processing_time_seconds": processing_time,
                    "generation_stats": self.stats.copy(),
                },
                metadata={
                    "model_used": "gemini-2.0-flash",
                    "response_length": len(response_data.get("answer", "")),
                    "sources_used": len(chunks) if chunks else 0,
                    "workflow_id": getattr(message, 'workflow_id', None),
                    "parent_trace_id": message.trace_id
                }
            )

        except Exception as e:
            error_msg = f"Error generating response: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stats["processing_errors"] += 1

            self.reply_to(
                original_msg=message,
                msg_type=MessageType.ERROR.value,
                payload={"error": error_msg}
            )

    def _generate_rag_response(
        self, chunks: List[str], metadata: List[Dict], query: str
    ) -> Dict[str, Any]:
        """Generate RAG response with context"""
        try:
            # Build context with source information
            context_parts = []
            sources = []

            for i, (chunk, meta) in enumerate(
                zip(chunks[:3], metadata[:3] if metadata else [])
            ):
                source_info = f"Document {i + 1}"
                if meta:
                    file_name = meta.get("file_name", "unknown")
                    source_info = f"Document {i + 1} ({file_name})"
                    sources.append(file_name)

                context_parts.append(f"[{source_info}]\n{chunk}")

            context = "\n\n".join(context_parts)
            sources_text = ", ".join(set(sources)) if sources else "uploaded documents"

            # Build prompt
            prompt = self.templates["rag_prompt"].format(
                context=context, sources=sources_text, query=query
            )

            # Generate response
            response = self.model.generate_content(prompt)
            raw_answer = response.text

            # Enhance formatting
            enhanced_answer = self._enhance_response_formatting(raw_answer, "rag")

            # Add formatted sources section
            sources_section = self._format_sources_section(sources, len(chunks))
            final_answer = enhanced_answer + sources_section

            # Update token stats if available
            if hasattr(response, "usage_metadata"):
                self.stats["total_tokens_used"] += getattr(
                    response.usage_metadata, "total_token_count", 0
                )

            return {
                "answer": final_answer,
                "context_chunks": chunks[:3],
                "sources_used": len(chunks),
            }

        except Exception as e:
            logger.error(f"Error in RAG response generation: {str(e)}")
            # Fallback to general response
            return self._generate_general_response_data(query)

    def _generate_general_response_data(self, query: str) -> Dict[str, Any]:
        """Generate general response without context"""
        try:
            prompt = self.templates["general_prompt"].format(query=query)

            # Generate response
            response = self.model.generate_content(prompt)
            raw_answer = response.text

            # Enhance formatting
            enhanced_answer = self._enhance_response_formatting(raw_answer, "general")
            
            # Format with no documents template to clearly indicate this is from general knowledge
            final_answer = self.templates["no_documents_response"].format(answer=enhanced_answer)

            # Update token stats if available
            if hasattr(response, "usage_metadata"):
                self.stats["total_tokens_used"] += getattr(
                    response.usage_metadata, "total_token_count", 0
                )

            return {
                "answer": final_answer,
                "context_chunks": [],
                "sources_used": 0,
            }

        except Exception as e:
            logger.error(f"Error in general response generation: {str(e)}")
            return {
                "answer": self.templates["error_response"].format(error=str(e)),
                "context_chunks": [],
                "sources_used": 0,
            }

    def _enhance_response_formatting(self, text: str, response_type: str) -> str:
        """Enhance response formatting with better structure"""
        # The new templates already provide good structure
        # Just ensure proper line breaks and formatting
        enhanced = text.strip()
        
        # Ensure proper spacing around headers
        enhanced = enhanced.replace("##", "\n##")
        enhanced = enhanced.replace("\n\n##", "\n##")
        
        # Clean up extra whitespace
        lines = enhanced.split('\n')
        cleaned_lines = []
        for line in lines:
            cleaned_lines.append(line.rstrip())
        
        return '\n'.join(cleaned_lines)

    def _format_sources_section(self, sources: List[str], total_chunks: int) -> str:
        """Format sources section"""
        if not sources:
            return ""

        sources_section = "\n\n---\n\n## 📚 Sources\n"
        unique_sources = list(set(sources))
        
        for source in unique_sources:
            sources_section += f"📄 **{source}**\n"
        
        if total_chunks > 3:
            sources_section += f"\n*Note: Showing top 3 of {total_chunks} relevant sections*"
        
        return sources_section

    def _send_general_response(self, original_message, query: str):
        """Send a general response when no context is available"""
        response_data = self._generate_general_response_data(query)

        self.send_message(
            receiver="CoordinatorAgent",
            msg_type=MessageType.RESPONSE_GENERATED.value,
            payload={
                **response_data,
                "query": query,
                "response_type": "general",
                "collection_size": 0,
                "processing_time_seconds": 0.0,
            },
            metadata={
                "workflow_id": getattr(original_message, 'workflow_id', None),
                "parent_trace_id": original_message.trace_id
            }
        )

        self.stats["general_responses"] += 1
        self.stats["responses_generated"] += 1

    def _update_average_response_time(self, processing_time: float):
        """Update average response time"""
        if self.stats["responses_generated"] > 0:
            total_time = self.stats["average_response_time"] * (self.stats["responses_generated"] - 1)
            self.stats["average_response_time"] = (total_time + processing_time) / self.stats["responses_generated"]

    def generate_response(
        self,
        query: str,
        context_chunks: List[str] = None,
        chunk_metadata: List[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Generate response (direct method for backward compatibility)

        Args:
            query: Query string
            context_chunks: Retrieved context chunks
            chunk_metadata: Metadata for chunks

        Returns:
            Generated response
        """
        start_time = time.time()

        try:
            if not query.strip():
                return {"status": "error", "error": "Empty query provided"}

            # Determine response mode
            use_rag = context_chunks and len(context_chunks) > 0

            if use_rag:
                response_data = self._generate_rag_response(
                    context_chunks, chunk_metadata or [], query
                )
                response_type = "rag"
                self.stats["rag_responses"] += 1
            else:
                response_data = self._generate_general_response_data(query)
                response_type = "general"
                self.stats["general_responses"] += 1

            # Calculate processing time
            processing_time = time.time() - start_time

            # Update stats
            self.stats["responses_generated"] += 1
            self._update_average_response_time(processing_time)

            return {
                "status": "success",
                **response_data,
                "query": query,
                "response_type": response_type,
                "processing_time_seconds": processing_time,
            }

        except Exception as e:
            error_msg = f"Error generating response: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stats["processing_errors"] += 1

            return {"status": "error", "error": error_msg}

    def health_check(self) -> Dict[str, Any]:
        """Get agent health status"""
        try:
            # Test Gemini API connection
            test_response = self.model.generate_content("Test connection")
            api_status = "healthy" if test_response else "degraded"
        except Exception as e:
            logger.warning(f"Gemini API health check failed: {str(e)}")
            api_status = "degraded"

        return {
            "status": "healthy" if api_status == "healthy" else "degraded",
            "agent_id": self.agent_id,
            "stats": self.get_stats(),
            "api_status": api_status,
            "model": "gemini-2.0-flash"
        }