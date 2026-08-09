from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from openai import OpenAI

from data_agent.config.config import config


class KimiChat(BaseChatModel):
    """ Kimi Chat Model """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = OpenAI(
            api_key=config.MOONSHOT_API_KEY,
            base_url=config.MODEL_BASE_URL
        )

    def _generate(
        self, messages, stop=None, run_manager=None, **kwargs
    ):
        response = self.client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[{"role": m.type, "content": m.content} for m in messages],
            temperature=config.MODEL_TEMPERATURE,
            stop=stop,
        )
        return ChatResult(
            generations=[ChatGeneration(message=HumanMessage(content=response.choices[0].message.content))]
        )
    
    @property
    def _llm_type(self):
        return "kimi"
