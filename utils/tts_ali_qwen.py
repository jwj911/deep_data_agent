import os
import dashscope
import pyaudio
import time
import base64
import numpy as np
from utils.tools import get_config

app_config = get_config()
api_key = app_config["model"]["qwen_key"]

# 全局资源，避免重复创建
player = None
tts_stream = None


def _init_audio_stream():
    """初始化音频流，使用较小的缓冲区以减少延迟"""
    global player, tts_stream
    if player is None:
        player = pyaudio.PyAudio()
    if tts_stream is None or not tts_stream.is_active():
        # frames_per_buffer 设置较小值以减少首包延迟
        # 256 frames @ 24kHz ≈ 10.6ms 延迟
        tts_stream = player.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=24000,
            output=True,
            frames_per_buffer=256,  # 减小缓冲区以降低延迟
        )
    return tts_stream


def tts(text: str = ""):
    """
    文本转语音，优化首包发声速度
    """
    stream = None
    first_chunk = True

    # 先调用 API，在收到第一个数据包时再初始化音频流
    responses = dashscope.audio.qwen_tts.SpeechSynthesizer.call(
        model="qwen3-tts-flash", api_key=api_key, text=text, voice="Cherry", stream=True
    )

    for chunk in responses:
        # 延迟初始化：在收到第一个音频数据时才创建音频流
        if first_chunk:
            stream = _init_audio_stream()
            first_chunk = False
            print(f"First chunk received: {time.time()}")

        audio_string = chunk["output"]["audio"]["data"]
        wav_bytes = base64.b64decode(audio_string)
        audio_np = np.frombuffer(wav_bytes, dtype=np.int16)

        # 直接播放音频数据
        stream.write(audio_np.tobytes())

    # 不关闭流，保持复用以提升下次调用速度


def cleanup():
    """清理音频资源，在程序退出时调用"""
    global player, tts_stream
    if tts_stream is not None:
        tts_stream.stop_stream()
        tts_stream.close()
        tts_stream = None
    if player is not None:
        player.terminate()
        player = None


if __name__ == "__main__":
    start_time = time.time()
    print(f"Start: {start_time}")
    tts(
        "This name is primarily used in American English, and it's quite fun—it gets its name because some varieties are white and oval, looking just like a large egg! While the deep purple, pear-shaped version is the most common, eggplants actually come in many different sizes, colors, and shapes."
    )
    print(f"Total time: {time.time() - start_time:.3f}s")
    # 清理资源
    cleanup()
