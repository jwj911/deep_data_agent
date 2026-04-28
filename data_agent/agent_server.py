import os
from typing import Literal
from deepagents import create_deep_agent
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_community.chat_models import MoonshotChat
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from urllib3 import response
from utils.tools import get_config
from tavily import TavilyClient

app_config = get_config()

# define base chat model
class KimiChat(BaseChatModel):
    """ Kimi Chat Model """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = OpenAI(
            api_key = os.environ.get("MOONSHOT_API_KEY"),
            base_url = "https://api.moonshot.cn/v1"
        )

    def _generate(
        self, messages, stop = None, run_manager = None, **kwargs
    ):
        response = self.client.chat.completions.create(
            model = "kimi-k2-turbo-preview",
            messages = [{"role": m.type, "content": m.content} for m in messages],
            temperature = 0.3,
            stop = stop,
        )
        return ChatResult(
            generations = [ChatGeneration(message=AIMessage(content=response.choices[0].message.content))]
        )
    
    @property
    def _llm_type(self):
        return "kimi"

# Validate environment variables
if not os.environ.get("TAVILY_API_KEY"):
    raise ValueError("Environment variable TAVILY_API_KEY is not set")
if not os.environ.get("MOONSHOT_API_KEY"):
    raise ValueError("Environment variable MOONSHOT_API_KEY is not set")

# Initialize Tavily client
tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
print("Tavily client initialized.")

def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "images", "videos", "files"] = "general",
    include_raw_content: bool = False
) -> dict:
    "Run a search query using the Tavily API."
    return tavily_client.search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )

# System prompt to steer the agent to be an expert researcher
research_instructions = """You are an expert researcher. Your job is to conduct thorough research and then write a polished report.

You have access to an internet search tool as your primary means of gathering information.Finally, translate the answer to the chinese.

## `internet_search`

Use this to run an internet search for a given query. You can specify the max number of results to return, the topic, and whether raw content should be included.
"""

# Create the agent with proper configuration
print("Creating agent...")
agent = create_deep_agent(
    tools=[internet_search],
    system_prompt=research_instructions,
    model=ChatOpenAI(
        model="kimi-k2-turbo-preview",
        api_key=os.environ["MOONSHOT_API_KEY"],
        base_url="https://api.moonshot.cn/v1",
        temperature=0.3
    )
)
print("Agent created successfully!")

# Agent is ready for invocation via LangGraph server