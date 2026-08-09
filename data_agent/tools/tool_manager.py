from collections.abc import Callable

from data_agent.config.config import config
from data_agent.config.logger import tool_logger
from data_agent.tools.code_execution import execute_python_code
from data_agent.tools.document_analysis import analyze_document
from data_agent.tools.search import internet_search


class ToolManager:
    """Manager for AI agent tools"""

    def __init__(self) -> None:
        self.tools: dict[str, Callable] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register default tools"""
        self.register_tool("internet_search", internet_search)
        self.register_tool("analyze_document", analyze_document)
        if config.ENABLE_CODE_EXECUTION:
            tool_logger.warning(
                "Arbitrary Python code execution is explicitly enabled"
            )
            self.register_tool("execute_python_code", execute_python_code)

    def register_tool(self, name: str, tool: Callable) -> None:
        """Register a new tool"""
        self.tools[name] = tool

    def get_tool(self, name: str) -> Callable | None:
        """Get a tool by name"""
        return self.tools.get(name)

    def get_all_tools(self) -> list[Callable]:
        """Get all registered tools"""
        return list(self.tools.values())

    def get_tool_names(self) -> list[str]:
        """Get all tool names"""
        return list(self.tools.keys())


# Create a global tool manager instance
global_tool_manager = ToolManager()
