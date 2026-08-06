"""Separate FastMCP agents: document_process_mcp + voice_process_mcp."""

from document_processing_agenticflow.mcp.base import BaseAgentMCPServer
from document_processing_agenticflow.mcp.client import MCPAgentClient, tool_result_payload
from document_processing_agenticflow.mcp.document_process_mcp import DocumentProcessMCP
from document_processing_agenticflow.mcp.voice_process_mcp import VoiceProcessMCP

__all__ = [
    "BaseAgentMCPServer",
    "DocumentProcessMCP",
    "VoiceProcessMCP",
    "MCPAgentClient",
    "tool_result_payload",
]
