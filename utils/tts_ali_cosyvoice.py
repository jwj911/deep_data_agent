# coding=utf-8

import dashscope
from dashscope.audio.tts_v2 import *
import threading
from utils.tools import get_config, remove_emoji
from utils.log import init_log, timing_recorder
from pydub import AudioSegment
from io import BytesIO
import time

app_config = get_config()
api_key = app_config['model']['qwen_key']

from datetime import datetime
import pyaudio

logger = init_log(log_name="asr")

player = pyaudio.PyAudio().open(
    format=pyaudio.paInt16, channels=1, rate=16000, output=True
)


def get_timestamp():
    now = datetime.now()
    formatted_timestamp = now.strftime("[%Y-%m-%d %H:%M:%S.%f]")
    return formatted_timestamp


# 若没有将API Key配置到环境变量中，需将your-api-key替换为自己的API Key
dashscope.api_key = api_key

# 模型
model = "cosyvoice-v2"
# 音色
voice = "longjielidou_v2"
voice = "loongbella_v2"


# 定义回调接口
class Callback(ResultCallback):

    def __init__(self):
        super().__init__()
        self.done_event = threading.Event()

    def on_complete(self):
        print("语音合成完成，所有合成结果已被接收：" + get_timestamp())
        self.done_event.set()

    def on_error(self, message: str):
        print(f"语音合成出现异常：{message}")

    def on_event(self, message):
        pass

    def on_data(self, data: bytes) -> None:
        logger.info(f"讲话：{time.time() - timing_recorder.start:.3f}s")
        if not timing_recorder.stop:
            player.write(data)


# 定义保存音频的回调接口
class SaveCallback(ResultCallback):

    def __init__(self, output_path: str):
        super().__init__()
        self.done_event = threading.Event()
        self.audio_data = BytesIO()
        self.output_path = output_path

    def on_complete(self):
        self.audio_data.seek(0)
        audio_segment = AudioSegment(
            data=self.audio_data.read(),
            sample_width=2,  # 16bit = 2 bytes
            frame_rate=22050,
            channels=1
        )
        # 保存为mp3文件
        audio_segment.export(self.output_path, format="mp3")
        self.done_event.set()

    def on_error(self, message: str):
        print(f"语音合成出现异常：{message}")
        self.done_event.set()

    def on_event(self, message):
        pass

    def on_data(self, data: bytes) -> None:
        self.audio_data.write(data)


callback = Callback()

# 实例化SpeechSynthesizer，并在构造方法中传入模型（model）、音色（voice）等请求参数


def tts(text: str = ""):
    text = remove_emoji(text)
    if not text:
        return
    callback.done_event.clear()
    synthesizer = SpeechSynthesizer(
        model=model,
        voice=timing_recorder.voice,
        format=AudioFormat.PCM_16000HZ_MONO_16BIT,
        callback=callback,
        speech_rate=1.0,
    )
    synthesizer.call(text)
    callback.done_event.wait()
    print('tts end')

def tts_save_mp3(text: str = "", output_path: str = None):
    """合成语音并保存为mp3文件"""
    save_callback = SaveCallback(output_path)
    synthesizer = SpeechSynthesizer(
        model=model,
        voice=timing_recorder.voice,
        format=AudioFormat.PCM_22050HZ_MONO_16BIT,
        callback=save_callback,
        speech_rate=0.8,
    )
    synthesizer.call(text)
    save_callback.done_event.wait()
    print('tts save mp3 end')
    return output_path

def tts_async(text: str = ""):
    text = remove_emoji(text)
    if not text:
        return
    callback.done_event.clear()
    synthesizer = SpeechSynthesizer(
        model=model,
        voice=voice,
        format=AudioFormat.PCM_16000HZ_MONO_16BIT,
        callback=callback,
        speech_rate=1.0,
    )
    synthesizer.call(text)
    print('tts end')


if __name__ == "__main__":
    # 测试保存mp3功能
    text = "Today　is a good day, 今天的天气真棒"
    text = "This name is primarily used in American English, and it's quite fun—it gets its name because some varieties are white and oval, looking just like a large egg! While the deep purple, pear-shaped version is the most common, eggplants actually come in many different sizes, colors, and shapes. This name is primarily used in American English, and it's quite fun—it gets its name because some varieties are white and oval, looking just like a large egg! While the deep purple, pear-shaped version is the most common, eggplants actually come in many different sizes, colors, and shapes. This name is primarily used in American English, and it's quite fun—it gets its name because some varieties are white and oval, looking just like a large egg! While the deep purple, pear-shaped version is the most common, eggplants actually come in many different sizes, colors, and shapes."
    # tts_async(text)
    # tts(text)
    # timing_recorder.voice = "longjielidou_v2"
    output_file = tts_save_mp3(text, "test_aec.mp3")
    # # print(f"音频文件已保存：{output_file}")
