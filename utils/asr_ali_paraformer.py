# For prerequisites running the following sample, visit https://help.aliyun.com/zh/model-studio/getting-started/first-api-call-to-qwen
import os
import signal  # for keyboard events handling (press "Ctrl+C" to terminate recording)
import sys

import dashscope
import pyaudio
from dashscope.audio.asr import *
from utils.tools import get_config

# Set recording parameters
sample_rate = 16000  # sampling rate (Hz)
channels = 1  # mono channel
dtype = 'int16'  # data type
format_pcm = 'pcm'  # the format of the audio data
block_size = 3200  # number of frames per buffer

app_config = get_config()
api_key = app_config["model"]["qwen_key"]
dashscope.api_key = api_key


class Callback(RecognitionCallback):
    def on_event(self, result: RecognitionResult) -> None:
        sentence = result.get_sentence()
        if 'text' in sentence:
            if RecognitionResult.is_sentence_end(sentence):
                # print(
                #     'RecognitionCallback sentence end, request_id:%s, usage:%s'
                #     % (result.get_request_id(), result.get_usage(sentence)))
                print('RecognitionCallback text: ', sentence['text'])


callback = Callback()
recognition = Recognition(
    model="paraformer-realtime-v2",
    format="pcm",
    sample_rate=16000,
    semantic_punctuation_enabled=False,
    callback=callback,
)
recognition.start()

recognition.send_audio_frame(audio_data)