import pyaudio
import wave
import os
import subprocess

def record_minimal_audio(duration=5, output_file="output.opus"):
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 8000

    p = pyaudio.PyAudio()

    print(f"Recording {duration} seconds...")

    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)

    frames = []

    for _ in range(0, int(RATE / CHUNK * duration)):
        data = stream.read(CHUNK)
        frames.append(data)

    print("Recording completed!")

    stream.stop_stream()
    stream.close()
    p.terminate()

    temp_wav = "temp_record.wav"
    wf = wave.open(temp_wav, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

    try:
        subprocess.run([
            'ffmpeg', '-y', '-i', temp_wav,
            '-c:a', 'libopus',
            '-b:a', '6k',
            '-vbr', 'off',
            '-application', 'voip',
            output_file
        ], check=True, capture_output=True)

        os.remove(temp_wav)

        size = os.path.getsize(output_file)
        print(f"Audio saved: {output_file}")
        print(f"File size: {size} bytes ({size/1024:.2f} KB)")

    except subprocess.CalledProcessError as e:
        print(f"Conversion failed: {e}")
        print("Keeping wav file")
        os.rename(temp_wav, output_file.replace('.opus', '.wav'))

if __name__ == "__main__":
    record_minimal_audio(duration=5, output_file="output.opus")
