from http import HTTPStatus
from dashscope.audio.asr import Transcription
import dashscope
from utils.tools import get_config
import requests

app_config = get_config()
dashscope.api_key = app_config.get("model", {}).get("qwen_key")


def create_transcript_task(file_url: str = ""):
    task_response = Transcription.async_call(
        model="paraformer-v2",
        file_urls=[file_url],
        language_hints=["zh", "en"],
        diarization_enabled=True,
    )
    return task_response.output.task_id


def get_result_by_taskid(task_id: str = ""):
    transcribe_response = Transcription.wait(task=task_id)
    asr_result = None
    if transcribe_response.status_code == HTTPStatus.OK:
        res = transcribe_response.output
        if res.get("task_status") == "SUCCEEDED":
            res_url = res.get("results", {})[0].get("transcription_url")
            _asr_result = requests.get(res_url).json()
            asr_result = [
                {
                    "key": _asr_result["file_url"],
                    "text": _asr_result["transcripts"][0]["text"],
                    "sentence_info": _asr_result["transcripts"][0]["sentences"],
                }
            ]
            for sentence in asr_result[0]["sentence_info"]:
                sentence["spk"] = sentence.pop("speaker_id")
                sentence["start"] = sentence.pop("begin_time")
                sentence["end"] = sentence.pop("end_time")
            return asr_result
    else:
        return None


if __name__ == "__main__":
    get_result_by_taskid(task_id="a7d3d59b-625f-421d-93a8-444c4d4077d0")
