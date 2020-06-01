#!/usr/bin/env python3

import pyaudio
import wave
import vosk
import time


def getGrammar(sentences):
    all_words = set()
    for sentence in sentences:
        for word in sentence.split(" "):
            all_words.add(word)
    return " ".join(all_words)


class AudioQueue:
    def __init__(self):
        self.chunks = []
        self.current_chunk = 0

    def addFramesToVector(self,
                          in_data,
                          frame_count,
                          time_info,
                          status_flags):
        self.chunks.append(in_data)
        return (in_data, pyaudio.paContinue)

    def getNextChunk(self):
        if len(self.chunks) > self.current_chunk:
            chunk_return_ix = self.current_chunk
            self.current_chunk += 1
            return self.chunks[chunk_return_ix]
        else:
            return None

    def clear(self):
        self.chunks.clear()
        self.current_chunk = 0


if __name__ == "__main__":
    # Chunk size needs to be large enough, otherwise parts of the audio will be dropped.
    chunk = 2048
    sample_format = pyaudio.paInt16
    channels = 1
    # Sample rate needs to be 48000 or something like that for the drivers to accept it.
    fs = 48000

    p = pyaudio.PyAudio()

    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        print(dev)
        print((i, dev['name'], dev['maxInputChannels'], dev['defaultSampleRate']))


    audio_queue = AudioQueue()
    stream = p.open(format=sample_format,
                    channels=channels,
                    rate=fs,
                    frames_per_buffer=chunk,
                    stream_callback=audio_queue.addFramesToVector,
                    # input_device_index=6, # 2 = antlion zero, 5 = laptop, 6 = antlion laptop, empty = system default.
                    input=True,
                    start=False)

    valid_commands = ["turn on turtle",
                      "turn off turtle",
                      "turn on green",
                      "turn off green",
                      "turn on blue",
                      "turn off blue",
                      "turn on corner",
                      "turn off corner",
                      "engage party mode",
                      "let there be light",
                      "you all suck",
                      "good night"
    ]
    grammar = getGrammar(valid_commands)
    print(grammar)
    voice_model  = vosk.Model("vosk-model-small-en-us-0.3")
    recognizer = vosk.KaldiRecognizer(voice_model, fs, grammar)

    current_frame = 0
    while True:
        input("Press ENTER to start recording. Ctrl-C to stop recording.")

        audio_queue.clear()
        stream.start_stream()
        print("Recording...")
        try:
            while True:
                time.sleep(0.5)
                #audio_data = stream.read(chunk)
                #audio_data = audio_queue.getNextChunk()
                audio_data = None
                if audio_data is not None:
                    #recognizer.AcceptWaveform(audio_data)
                    time.sleep(0.010)  # Sleep for some time to allow for collection of audio stream.
                else:
                    time.sleep(0.010)  # Sleep for some time to avoid busy wait.
        except KeyboardInterrupt:
            print("Stopped recording")

        stream.stop_stream()

        audio_data = audio_queue.getNextChunk()
        while audio_data is not None:
            recognizer.AcceptWaveform(audio_data)
            audio_data = audio_queue.getNextChunk()

        result = recognizer.FinalResult()
        print(result)
        recognizer = vosk.KaldiRecognizer(voice_model, fs, grammar)

        print("Saving last recording.")
        wf = wave.open("last_recording.wav", 'wb')
        wf.setnchannels(channels)
        wf.setsampwidth(p.get_sample_size(sample_format))
        wf.setframerate(fs)
        wf.writeframes(b''.join(audio_queue.chunks))
        wf.close()

    stream.close()
    p.terminate()
