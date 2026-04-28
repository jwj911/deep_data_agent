from moviepy import AudioFileClip, VideoFileClip, concatenate_audioclips, concatenate_videoclips
from utils.tools import get_root_path
import os


def merge_audio(audio_list: list = [], merged_filename: str = None):
    root_path = get_root_path()
    audio_clips = [
        AudioFileClip(os.path.join(root_path, file_path)) for file_path in audio_list
    ]
    final_audio = concatenate_audioclips(audio_clips)
    final_audio.write_audiofile(
        os.path.join(root_path, merged_filename), codec="libmp3lame", bitrate="64k"
    )
    for audio in audio_clips:
        audio.close()
    final_audio.close()
    for file_path in audio_list:
        os.remove(file_path)

def merge_video(video_list: list = [], merged_filename: str = None):
    root_path = get_root_path()
    video_clips = [
        VideoFileClip(os.path.join(root_path, file_path)) for file_path in video_list
    ]
    final_video = concatenate_videoclips(video_clips)
    final_video.write_videofile(
        os.path.join(root_path, merged_filename), codec="libx264", audio_codec="aac"
    )
    for video in video_clips:
        video.close()
    final_video.close()


def video2audio(video_path: str = "", audio_path: str = None, clip: list = []):
    try:
        video_clip = VideoFileClip(video_path)
        audio = video_clip.audio
        if len(clip) == 2:
            audio = audio.subclipped(clip[0], clip[1])
        if audio_path is None:
            pass
        else:
            audio.write_audiofile(audio_path)
        audio_clip.close()
    except Exception as e:
        print(f"提取音频时出错: {e}")


def handle_audio(
    audio_path: str = "",
    output_path: str = None,
    clip: list = [],
    volume_scale: float = 1,
):
    with AudioFileClip(audio_path) as audio:
        if len(clip) == 2:
            audio = audio.subclipped(clip[0], clip[1])
        audio = audio.with_volume_scaled(volume_scale)
        if output_path is None:
            output_path = audio_path
        audio.write_audiofile(output_path, bitrate="192k")


if __name__ == "__main__":
    pass
