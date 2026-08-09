import requests
import time
from pathlib import Path
from utils.tools import get_root_path
import soundfile as sf
from pydub import AudioSegment
import numpy as np

# 服务地址
BASE_URL = "https://1228e94d.r31.cpolar.top/kimiaudio"

def recognize_from_samples(samples, sample_rate=16000, temp_file="temp_asr.opus"):
    start_time = time.time()

    # 确保samples是正确的格式
    if samples.dtype != np.int16:
        samples = (samples * 32767).astype(np.int16)

    # 直接从内存创建AudioSegment，避免磁盘读写
    audio = AudioSegment(
        samples.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,  # int16 = 2 bytes
        channels=1
    )

    # 导出为opus格式，使用极致压缩
    audio.export(
        temp_file,
        format="opus",
        codec="libopus",
        bitrate="16k",  # 极低比特率，适合语音
        parameters=["-vbr", "on", "-compression_level", "10"]  # 最高压缩级别
    )

    with open(temp_file, 'rb') as f:
        files = {'audio_file': (Path(temp_file).name, f, 'audio/opus')}
        response = requests.post(f"{BASE_URL}/asr", files=files, timeout=10)

    request_time = time.time() - start_time

    if response.status_code == 200:
        result = response.json()
        print(f"asr (kimi): {result['text']} {request_time:.2f}s")
        return result['text']
    else:
        print(f"ASR API error: {response.text}")
        return None

def test_asr_single_file(audio_file_path: str):
    start_time = time.time()
    """测试单文件ASR"""
    print(f"\n=== 测试单文件ASR: {audio_file_path} ===")

    if not Path(audio_file_path).exists():
        print(f"文件不存在: {audio_file_path}")
        return

    with open(audio_file_path, 'rb') as f:
        files = {'audio_file': (Path(audio_file_path).name, f, 'audio/wav')}
        print(f"请求数据: {files}")
        response = requests.post(f"{BASE_URL}/asr", files=files)

    request_time = time.time() - start_time

    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"识别文本: {result['text']}")
        print(f"服务器处理时间: {result['processing_time']:.2f}秒")
        print(f"总请求时间: {request_time:.2f}秒")
    else:
        print(f"错误: {response.text}")

if __name__ == "__main__":
    root_path = get_root_path()
    # res = test_asr_single_file(f"{root_path}/temp_record.ogg")
    res = test_asr_single_file(f"{root_path}/hellohuanjue.wav")
    print(res)
    