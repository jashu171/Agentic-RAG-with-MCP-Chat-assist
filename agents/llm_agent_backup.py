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

        # Response templates
        self.templates = {
            "rag_prompt": """## 📄 Answer Based on Uploaded Files

Your question has been answered using the following uploaded resources:

###  Context Extracted:
{context}

###  Sources Used:
{sources}

---

## Answer to Your Query:  
{query}

### ✅ Formatting Rules:
- Use `##`, `###` for section headings
- Use `-`, `*`, or `1.` for lists and points
- Highlight keywords using `**bold**`
- Use backticks (`code`) for technical terms
- Break long paragraphs into shorter, digestible sections
- Add a sources/reference section if applicable

---

###  Note:
If you’re expecting an answer from a specific file but don’t see it listed above, please ensure the file was uploaded correctly or that it contains content relevant to your question.
""",
            "general_prompt": """## 🤖 General AI Response (No Uploaded Files Used)

Your query was answered using general knowledge, as no specific uploaded file content matched your request.

###  Question:
{query}

---

##  Response:

###  Formatting Rules:
- Use `##`, `###` for section headings
- Use `-`, `*`, or `1.` for lists and points
- Highlight keywords using `**bold**`
- Use backticks (`code`) for technical terms
- Break long paragraphs into shorter, digestible sections
- Add a sources/reference section if applicable

---

###  Tip for Better Answers:
Upload relevant files to get more accurate, document-specific responses. This allows me to reference exact sections and improve answer relevance.
""",
            "error_response": """## ❌ Error While Processing

Something went wrong while handling your request.

###  Error Details:
{error}

---

###  Try This:
- Rephrase your question more clearly
- Ensure any referenced file is uploaded properly
- Retry in a few moments

We're here to help—feel free to ask again or reach out for support.
""",
            "no_documents_response": """##  No Documents Detected or Referenced

I couldn’t find any relevant uploaded documents to use for this query.

---

##  General Guidance:

{answer}

---

###  You Can Try:
1. Uploading files that directly relate to your question
2. Ensuring documents contain readable, extractable content (e.g., text, not scanned images)
3. Using keywords or phrases found in your files when asking questions

Upload your files to get more tailored, document-specific answers.
"""
        }

        # ... [REMAINING CLASS IMPLEMENTATION CONTINUES UNCHANGED]

        # ... [REMAINING CLASS IMPLEMENTATION CONTINUES UNCHANGED]


        # Register message handlers
        self._register_handlers()

        # Register with broker
        broker.register_agent(
            self.agent_id,
            {
                "type": "llm",
                "capabilities": [
                    "response_generation",
                    "rag_responses",
                    "general_responses",
                ],
                "model": "gemini-2.0-flash",
            },
        )

        logger.info("MCP LLM Agent initialized successfully")

    def _register_handlers(self):
        """Register message handlers"""
        self.mcp.register_handler(
            MessageType.CONTEXT_RESPONSE.value, self.handle_context_response
        )
        self.mcp.register_handler(
            MessageType.RETRIEVAL_RESULT.value, self.handle_retrieval_result
        )

    def handle_context_response(self, message):
        """
        Handle context response from retrieval agent

        Args:
            message: MCP message with retrieved context
        """
        self.handle_retrieval_result(message)  # Same handling logic

    def handle_retrieval_result(self, message):
        """
        Handle retrieval results and generate response

        Args:
            message: MCP message with retrieval results
        """
        start_time = time.time()

        try:
            if message.is_error():
                logger.error(f"Received error from retrieval: {message.error}")
                # Generate general response instead
                query = message.payload.get("query", "")
                if query:
                    self._generate_general_response(message, query)
                else:
                    self.reply_to(
                        original_msg=message,
                        msg_type=MessageType.ERROR.value,
                        payload={"error": f"Retrieval failed: {message.error}"},
                    )
                return

            chunks = message.payload.get("top_chunks", [])
            chunk_metadata = message.payload.get("chunk_metadata", [])
            query = message.payload.get("query", "")
            collection_size = message.payload.get("collection_size", 0)

            if not query.strip():
                error_msg = "Empty query provided"
                logger.warning(error_msg)
                self.reply_to(
                    original_msg=message,
                    msg_type=MessageType.ERROR.value,
                    payload={"error": error_msg},
                )
                return

            # Determine response mode
            use_rag = chunks and len(chunks) > 0 and collection_size > 0

            if use_rag:
                response_data = self._generate_rag_response(
                    chunks, chunk_metadata, query
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
                payload={"error": error_msg},
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

            return {"answer": final_answer, "context_chunks": [], "sources_used": 0}

        except Exception as e:
            logger.error(f"Error in general response generation: {str(e)}")
            return {
                "answer": self.templates["error_response"].format(error=str(e)),
                "context_chunks": [],
                "sources_used": 0,
                "error": True,
            }

    def _generate_general_response(self, original_message, query: str):
        """Generate and send general response"""
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
            total_time = self.stats["average_response_time"] * (
                self.stats["responses_generated"] - 1
            )
            self.stats["average_response_time"] = (
                total_time + processing_time
            ) / self.stats["responses_generated"]

    def _enhance_response_formatting(
        self, response_text: str, response_type: str
    ) -> str:
        """
        Enhance response formatting with better structure

        Args:
            response_text: Raw response text
            response_type: Type of response (rag/general)

        Returns:
            Enhanced formatted response
        """
        try:
            # If response already has markdown formatting, return as is
            if any(
                marker in response_text
                for marker in ["##", "###", "**", "- ", "* ", "1. "]
            ):
                return response_text

            # Basic enhancement for unformatted responses
            lines = response_text.strip().split("\n")
            enhanced_lines = []

            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    enhanced_lines.append("")
                    continue

                # Check if line looks like a heading (short line followed by longer content)
                if (
                    len(line) < 60
                    and i < len(lines) - 1
                    and lines[i + 1].strip()
                    and len(lines[i + 1].strip()) > len(line)
                ):
                    enhanced_lines.append(f"## {line}")
                # Check for list-like content
                elif line.startswith(("•", "-", "*")) or any(
                    line.startswith(f"{j}.") for j in range(1, 10)
                ):
                    enhanced_lines.append(line)
                # Check for key-value or definition-like content
                elif ":" in line and len(line.split(":")[0]) < 30:
                    parts = line.split(":", 1)
                    enhanced_lines.append(f"**{parts[0].strip()}:** {parts[1].strip()}")
                else:
                    enhanced_lines.append(line)

            return "\n".join(enhanced_lines)

        except Exception as e:
            logger.warning(f"Error enhancing response formatting: {e}")
            return response_text

    def _format_sources_section(self, sources: List[str], chunks_used: int) -> str:
        """
        Format sources section for RAG responses

        Args:
            sources: List of source document names
            chunks_used: Number of chunks used

        Returns:
            Formatted sources section
        """
        if not sources:
            return ""

        sources_section = "\n\n---\n\n## Sources\n\n"

        unique_sources = list(set(sources))
        if len(unique_sources) == 1:
            sources_section += f"📄 **{unique_sources[0]}** ({chunks_used} section{'s' if chunks_used > 1 else ''})"
        else:
            sources_section += "📄 **Referenced Documents:**\n"
            for i, source in enumerate(unique_sources, 1):
                sources_section += f"{i}. {source}\n"
            sources_section += f"\n*Total sections referenced: {chunks_used}*"

        return sources_section

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
            # Test API connectivity
            test_response = self.model.generate_content("Hello")
            api_status = "healthy" if test_response else "degraded"
        except Exception as e:
            api_status = f"error: {str(e)}"

        return {
            "status": api_status,
            "agent_id": self.agent_id,
            "stats": self.get_stats(),
            "model": "gemini-2.0-flash",
            "api_key_configured": bool(self.api_key),
        }
