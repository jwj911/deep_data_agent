import os
import time
import dashscope
import pyaudio
from pydub import AudioSegment
from pathlib import Path
import numpy as np
from utils.tools import get_config, get_root_path

app_config = get_config()
API_KEY = app_config.get("model", {}).get("qwen_key")


def recognize_from_samples(samples, sample_rate=16000, temp_file="temp_asr_qwen.opus"):
    """从音频样本识别文字（兼容 asr_kimi_audio 的接口）"""
    start_time = time.time()

    # 确保samples是float32格式 (AudioSegment需要的原始格式)
    if samples.dtype == np.int16:
        samples = samples.astype(np.float32) / 32768.0

    # 转换为int16用于AudioSegment
    samples_int16 = (samples * 32767).astype(np.int16)

    # 直接从内存创建AudioSegment
    audio = AudioSegment(
        samples_int16.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,  # int16 = 2 bytes
        channels=1
    )

    # 导出为opus格式，使用极致压缩
    audio.export(
        temp_file,
        format="opus",
        # codec="libopus",
        # bitrate="16k",  # 极低比特率，适合语音
        # parameters=["-vbr", "on", "-compression_level", "10"]  # 最高压缩级别
    )

    # 调用 asr_from_file 进行识别
    result = asr_from_file(temp_file)

    return result


def asr_from_file(audio_file_path: str, language: str = None) -> str:
    context = "Transcribe the following audio, which is in Chinese and English, but more likely in Chinese."
    if not audio_file_path.startswith("file://"):
        audio_file_path = f"file://{os.path.abspath(audio_file_path)}"
    messages = [
        {
            "role": "system",
            "content": [
                {"text": context},
            ]
        },
        {
            "role": "user",
            "content": [
                {"audio": audio_file_path},
            ]
        }
    ]

    asr_options = {
        "enable_lid": False,
        "enable_itn": False
    }

    if language:
        asr_options["language"] = language

    response = dashscope.MultiModalConversation.call(
        api_key=API_KEY,
        model="qwen3-asr-flash",
        messages=messages,
        result_format="message",
        asr_options=asr_options
    )

    if response.status_code == 200:
        # 检查响应结构
        if hasattr(response.output, 'choices') and len(response.output.choices) > 0:
            message = response.output.choices[0].message
            if hasattr(message, 'content') and len(message.content) > 0:
                return message.content[0].get("text", "")

        # 如果结构不匹配，尝试直接获取文本
        if hasattr(response.output, 'text'):
            return response.output.text

    return None


def asr_from_microphone(duration: int = 5, sample_rate: int = 8000, language: str = None, context: str = "") -> str:
    chunk = 1024
    channels = 1
    format = pyaudio.paInt16

    audio = pyaudio.PyAudio()
    print(f"开始录音，时长 {duration} 秒...")

    stream = audio.open(format=format, channels=channels, rate=sample_rate, input=True, frames_per_buffer=chunk)
    frames = [stream.read(chunk) for _ in range(0, int(sample_rate / chunk * duration))]

    stream.stop_stream()
    stream.close()
    audio.terminate()

    start_time = time.time()

    # 使用 speex 编解码器，专为语音优化，比 opus 更快
    temp_audio = os.path.join(os.getcwd(), "temp_record.opus")
    audio_segment = AudioSegment(
        data=b''.join(frames),
        sample_width=audio.get_sample_size(format),
        frame_rate=sample_rate,
        channels=channels
    )

    # 使用 speex 编码，压缩更快且文件更小
    audio_segment.export(
        temp_audio,
        format="opus",
        # codec="libspeex",
        # parameters=["-q:a", "3"]  # 质量 3（0-10，3 适合语音识别）
    )

    result = asr_from_file(temp_audio, language=language, context=context)

    return result


if __name__ == "__main__":
    # print(asr_from_microphone())
    file_path = f"{get_root_path()}/utils/temp_asr_qwen.opus"
    print(asr_from_file(file_path))
