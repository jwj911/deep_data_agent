from funasr import AutoModel
from modelscope.pipelines import pipeline
import json

def asr(audio_path:str="", output_path:str=None):
    model = AutoModel(
        # model="iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        model="iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        # model="manyeyes/aliparaformerasr-large-zh-en-timestamp-onnx-offline",
        model_revision="v2.0.4",
        vad_model="fsmn-vad",
        vad_model_revision="v2.0.4",
        punc_model="ct-punc-c",
        punc_model_revision="v2.0.4",
        spk_model="iic/speech_campplus_sv_zh-cn_16k-common",
        # spk_model_revision="v1.0.0",
        disable_update=True,
        ncpus=16,
        device = "mps",
        # speech_noise_thres=-1
    )
    res = model.generate(input=audio_path, batch_size_s=300, hotword="diffusion")
    if output_path:
        with open(output_path, "w") as f:
            f.write(json.dumps(res, ensure_ascii=False, indent=2))
    return res


def spk_divide():
    
    sv_pipeline = pipeline(
        task='speaker-verification',
        model='iic/speech_eres2net_large_200k_sv_zh-cn_16k-common',
        model_revision='v1.0.0'
    )
    speaker1_a_wav = 'https://modelscope.cn/api/v1/models/damo/speech_campplus_sv_zh-cn_16k-common/repo?Revision=master&FilePath=examples/speaker1_a_cn_16k.wav'
    speaker1_b_wav = 'https://modelscope.cn/api/v1/models/damo/speech_campplus_sv_zh-cn_16k-common/repo?Revision=master&FilePath=examples/speaker1_b_cn_16k.wav'
    speaker2_a_wav = 'https://modelscope.cn/api/v1/models/damo/speech_campplus_sv_zh-cn_16k-common/repo?Revision=master&FilePath=examples/speaker2_a_cn_16k.wav'
    # 相同说话人语音
    result = sv_pipeline([speaker1_a_wav, speaker1_b_wav])
    print(result)
    # 不同说话人语音
    result = sv_pipeline([speaker1_a_wav, speaker2_a_wav])
    print(result)
    # 可以自定义得分阈值来进行识别
    result = sv_pipeline([speaker1_a_wav, speaker2_a_wav], thr=0.372)
    print(result)

if __name__ == '__main__':
    spk_divide()
