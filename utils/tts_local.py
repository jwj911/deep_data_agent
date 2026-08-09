import argparse
import logging
import queue
import sys
import threading
import time

import numpy as np
import sherpa_onnx
import soundfile as sf

import sounddevice as sd
from utils.tools import get_root_path

def add_kitten_args(parser):
    parser.add_argument(
        "--kitten-model",
        type=str,
        default=f"{get_root_path()}/local_models/kitten-nano-en-v0_1-fp16/model.fp16.onnx",
        help="Path to model.onnx for kitten",
    )

    parser.add_argument(
        "--kitten-voices",
        type=str,
        default=f"{get_root_path()}/local_models/kitten-nano-en-v0_1-fp16/voices.bin",
        help="Path to voices.bin for kitten",
    )

    parser.add_argument(
        "--kitten-tokens",
        type=str,
        default=f"{get_root_path()}/local_models/kitten-nano-en-v0_1-fp16/tokens.txt",
        help="Path to tokens.txt for kitten",
    )

    parser.add_argument(
        "--kitten-data-dir",
        type=str,
        default=f"{get_root_path()}/local_models/kitten-nano-en-v0_1-fp16/espeak-ng-data",
        help="Path to the dict directory of espeak-ng.",
    )


def get_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    add_kitten_args(parser)

    parser.add_argument(
        "--tts-rule-fsts",
        type=str,
        default="",
        help="Path to rule.fst",
    )

    parser.add_argument(
        "--output-filename",
        type=str,
        default="./generated.wav",
        help="Path to save generated wave",
    )

    parser.add_argument(
        "--sid",
        type=int,
        default=0,
        help="""Speaker ID. Used only for multi-speaker models, e.g.
        models trained using the VCTK dataset. Not used for single-speaker
        models, e.g., models trained using the LJ speech dataset.
        """,
    )

    parser.add_argument(
        "--debug",
        type=bool,
        default=False,
        help="True to show debug messages",
    )

    parser.add_argument(
        "--provider",
        type=str,
        default="cpu",
        help="valid values: cpu, cuda, coreml",
    )

    parser.add_argument(
        "--num-threads",
        type=int,
        default=1,
        help="Number of threads for neural network computation",
    )

    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Speech speed. Larger->faster; smaller->slower",
    )

    parser.add_argument(
        "--text",
        type=str,
        default="",
        help="The input text to generate audio for",
    )
    args = parser.parse_args()
    return args


# buffer saves audio samples to be played
buffer = queue.Queue()

# started is set to True once generated_audio_callback is called.
started = False

# stopped is set to True once all the text has been processed
stopped = False

# killed is set to True once ctrl + C is pressed
killed = False

# Note: When started is True, and stopped is True, and buffer is empty,
# we will exit the program since all audio samples have been played.

sample_rate = None

event = threading.Event()

first_message_time = None


def generated_audio_callback(samples: np.ndarray, progress: float):
    """This function is called whenever max_num_sentences sentences
    have been processed.

    Note that it is passed to C++ and is invoked in C++.

    Args:
      samples:
        A 1-D np.float32 array containing audio samples
    """
    global first_message_time
    if first_message_time is None:
        first_message_time = time.time()

    buffer.put(samples)
    global started

    if started is False:
        logging.info("Start playing ...")
    started = True

    # 1 means to keep generating
    # 0 means to stop generating
    if killed:
        return 0

    return 1


# see https://python-sounddevice.readthedocs.io/en/0.4.6/api/streams.html#sounddevice.OutputStream
def play_audio_callback(
    outdata: np.ndarray, frames: int, time, status: sd.CallbackFlags
):
    if killed or (started and buffer.empty() and stopped):
        event.set()

    # outdata is of shape (frames, num_channels)
    if buffer.empty():
        outdata.fill(0)
        return

    n = 0
    while n < frames and not buffer.empty():
        remaining = frames - n
        k = buffer.queue[0].shape[0]

        if remaining <= k:
            outdata[n:, 0] = buffer.queue[0][:remaining]
            buffer.queue[0] = buffer.queue[0][remaining:]
            n = frames
            if buffer.queue[0].shape[0] == 0:
                buffer.get()

            break
        outdata[n : n + k, 0] = buffer.get()
        n += k

    if n < frames:
        outdata[n:, 0] = 0


# Please see
# https://python-sounddevice.readthedocs.io/en/0.4.6/usage.html#device-selection
# for how to select a device
def play_audio():
    with sd.OutputStream(
        channels=1,
        callback=play_audio_callback,
        dtype="float32",
        samplerate=sample_rate,
        blocksize=1024,
    ):
        event.wait()

    logging.info("Exiting ...")

args = get_args()
tts_config = sherpa_onnx.OfflineTtsConfig(
    model=sherpa_onnx.OfflineTtsModelConfig(
        kitten=sherpa_onnx.OfflineTtsKittenModelConfig(
            model=args.kitten_model,
            voices=args.kitten_voices,
            tokens=args.kitten_tokens,
            data_dir=args.kitten_data_dir,
        ),
        provider=args.provider,
        debug=args.debug,
        num_threads=args.num_threads,
    ),
    rule_fsts=args.tts_rule_fsts,
    max_num_sentences=1,
)

if not tts_config.validate():
    raise ValueError("Please check your config")

logging.info("Loading model ...")
tts = sherpa_onnx.OfflineTts(tts_config)
logging.info("Loading model done.")
sample_rate = tts.sample_rate

play_back_thread = threading.Thread(target=play_audio)


def text2speech(text: str = ""):
    play_back_thread.start()
    print("Start generating ...", time.time())
    start_time = time.time()
    audio = tts.generate(
        text,
        sid=args.sid,
        speed=args.speed,
        callback=generated_audio_callback,
    )
    end_time = time.time()
    logging.info("Finished generating! Elapsed time: %.3f", end_time - start_time)
    global stopped
    stopped = True
    play_back_thread.join()


if __name__ == "__main__":
    text2speech(text="This name is primarily used in American English, and it's quite fun—it gets its name because some varieties are white and oval, looking just like a large egg! While the deep purple, pear-shaped version is the most common, eggplants actually come in many different sizes, colors, and shapes.")
