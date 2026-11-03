from collections.abc import Callable

from langchain_core.tools import BaseTool

from data_agent.tools.document_analysis import analyze_document
from data_agent.tools.file_statistics import analyze_file_statistics
from data_agent.tools.search import internet_search


class ToolManager:
    """Manager for AI agent tools"""

    def __init__(self) -> None:
        self.tools: dict[str, Callable | BaseTool] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register default tools"""
        self.register_tool("internet_search", internet_search)
        self.register_tool("analyze_document", analyze_document)
        self.register_tool("analyze_file_statistics", analyze_file_statistics)

    def register_tool(self, name: str, tool: Callable | BaseTool) -> None:
        """Register a new tool"""
        self.tools[name] = tool

    def get_tool(self, name: str) -> Callable | BaseTool | None:
        """Get a tool by name"""
        return self.tools.get(name)

    def get_all_tools(self) -> list[Callable | BaseTool]:
        """Get all registered tools"""
        return list(self.tools.values())

    def get_tool_names(self) -> list[str]:
        """Get all tool names"""
        return list(self.tools.keys())


# Create a global tool manager instance
global_tool_manager = ToolManager()
