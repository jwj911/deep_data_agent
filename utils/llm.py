import os
from openai import OpenAI
from utils.tools import get_config

# apikey
app_config = get_config()
api_key = app_config["model"]["qwen_key"]

model_map = {
    "datasphere": {
        "model": "QwQ-32B",
        "url": os.environ.get("DATASPHERE_URL", ""),
        "api_key": "empty",
    },
    "local-8b": {
        "model": "qwen3:8b",
        "url": "http://localhost:11434/v1",
        "api_key": "empty",
    },
    "local-14b": {
        "model": "qwen3:14b",
        "url": "http://localhost:11434/v1",
        "api_key": "empty",
    },
    "local-4b-thinking": {
        "model": "qwen3:4b-thinking",
        "url": "http://localhost:11434/v1",
        "api_key": "empty",
    },
    "deepseek": {
        "model": "deepseek-r1",
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": api_key,
    },
    "qwen3-full-online": {
        "model": "qwen3-235b-a22b",
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": api_key,
    },
    "qwen3-32b-online": {
        "model": "qwen3-32b",
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": api_key,
    },
    "qwen3-max": {
        "model": "qwen3-max",
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": api_key,
    },
    "qwen-plus": {
        "model": "qwen-plus-latest",
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": api_key,
    },
    "qwen-turbo-online": {
        "model": "qwen-turbo-latest",
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": api_key,
    },
    "qwen3-0.6b": {
        "model": "qwen3-0.6b",
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": api_key,
    },
    "opensource-zwz": {
        "model": "Qwen3-30B-A3B-Thinking-2507-FP8",
        "url": os.environ.get("OPEN_SOURCE_URL", ""),
        "api_key": "empty",
    },
}


def _get_model_config(model_name: str):
    model = model_map[model_name]
    if not model["url"]:
        raise ValueError(f"Model '{model_name}' URL is not configured. Please set the corresponding environment variable.")
    return model

def chat(
    prompt: str = "",
    system_prompt: str = "",
    model_name: str = "qwen-turbo-online",
    stream: bool = True,
    history: list = None,
    temperature: float = 0.8,
):
    # 多轮对话
    model = _get_model_config(model_name)
    client = OpenAI(
        base_url=model["url"], api_key=model["api_key"]  # 未启用认证时可用任意字符串
    )
    if history is None:
        history = []
    history.insert(0, {"role": "system", "content": system_prompt})
    history.append({"role": "user", "content": prompt})
    chat_completion = client.chat.completions.create(
        model=model["model"],
        messages=history,
        temperature=temperature,
        top_p=0.95,
        max_tokens=7192,
        stream=stream
    )
    if stream is False:
        response = chat_completion.choices[0].message.content
        print(chat_completion.choices[0].message)
    else:
        response = ""
        for chunk in chat_completion:
            if chunk.choices and chunk.choices[0].delta.content:
                response += chunk.choices[0].delta.content  # 聚合所有内容块

    if "</think>" in response:

        response = response.split("</think>")[1].replace("```", "").replace("json", "")
    else:
        response = response.replace("```", "").replace("json", "")
    return response


def chat_think(
    prompt: str = "",
    system_prompt: str = "",
    model_name: str = "qwen-turbo-online",
    history: list = None,
    temperature: float = 1.2,
    thinking_budget: int = 5000,
    tools: list = [],
):
    # 多轮对话
    model = _get_model_config(model_name)
    client = OpenAI(
        base_url=model["url"], api_key=model["api_key"]  # 未启用认证时可用任意字符串
    )
    if history is None:
        history = []
    history.insert(0, {"role": "system", "content": system_prompt})
    history.append({"role": "user", "content": prompt})
    chat_completion = client.chat.completions.create(
        model=model["model"],
        messages=history,
        temperature=temperature,
        top_p=0.95,
        max_tokens=7192,
        stream=True,
        # tools=tools,
        extra_body={"enable_thinking": True, "thinking_budget": thinking_budget},
    )

    reasoning_content = ""
    answer_content = ""
    for chunk in chat_completion:
        if chunk.choices:
            delta = chunk.choices[0].delta
            if (
                hasattr(delta, "reasoning_content")
                and delta.reasoning_content is not None
            ):
                reasoning_content += delta.reasoning_content
            if hasattr(delta, "content") and delta.content is not None:
                answer_content += delta.content  # 聚合所有内容块
    answer_content = answer_content.replace("```", "").replace("json", "")
    return {
        "reason": reasoning_content,
        "answer": answer_content,
    }


def chat_think_local(
    prompt: str = "",
    system_prompt: str = "",
    model_name: str = "qwen-turbo-online",
    stream: bool = True,
    history: list = None,
    temperature: float = 0.6,
    tools: list = [],
):
    # 多轮对话
    model = _get_model_config(model_name)
    client = OpenAI(
        base_url=model["url"], api_key=model["api_key"]  # 未启用认证时可用任意字符串
    )
    if history is None:
        history = []
    history.insert(0, {"role": "system", "content": system_prompt})
    history.append({"role": "user", "content": prompt})
    chat_completion = client.chat.completions.create(
        model=model["model"],
        messages=history,
        temperature=temperature,
        top_p=0.95,
        max_tokens=7192,
        stream=stream,
        tools=tools,
        extra_body={"top_k": 20, "min_p": 0},  # 设置 min_p 参数
    )
    reason = ""
    if stream is False:
        response = chat_completion.choices[0].message.content
    else:
        response = ""
        for chunk in chat_completion:
            if chunk.choices and chunk.choices[0].delta.content:
                response += chunk.choices[0].delta.content  # 聚合所有内容块

    if "</think>" in response:
        reason = response.split("</think>")[0].replace("<think>", "")
        response = response.split("</think>")[1].replace("```", "").replace("json", "")
    else:
        response = response.replace("```", "").replace("json", "")
    return {
        "reason": reason,
        "answer": response,
    }


if __name__ == "__main__":
    # res = chat_think_local("你好", model_name="local-4b-thinking")
    # print(res)
    # res = chat(prompt="茄子用英文怎么说", model_name="opensource-zwz")
    res = chat(
        # system_prompt=system_prompt,
        prompt="hello",
        model_name="qwen3-32b-online",
        stream=True,
    )
    print(res)
