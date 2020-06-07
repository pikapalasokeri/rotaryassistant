#!/usr/bin/env python3

import signal
import subprocess
import threading
import time
import sys

# Hack to enable --user packages to be used when runnig as root (which is needed for piHomeEasy, omg).
sys.path.append("/home/pi/.local/lib/python3.7/site-packages")
sys.path.append("/usr/local/lib/python3.7/dist-packages")
import pyaudio
from gpiozero import Button
import vosk

class Recorder:
    def __init__(self):
        self.chunks = []
        self.current_chunk = 0
        self.pyaudio = pyaudio.PyAudio()

        # Chunk size needs to be large enough, otherwise parts of the audio will be dropped.
        self.chunk = 4*1024
        self.sample_format = pyaudio.paInt16
        self.channels = 1
        # Sample rate needs to be 48000 or something like that for the drivers to accept it.
        self.fs = 44100


        self.stream = self.pyaudio.open(format=self.sample_format,
                                        channels=self.channels,
                                        rate=self.fs,
                                        frames_per_buffer=self.chunk,
                                        stream_callback=self.addFramesToVector,
                                        input_device_index=2, # 2 = antlion zero, 5 = laptop,
                                                              # 6 = antlion laptop, empty = system default.
                                        input=True,
                                        start=False)

        self.printDeviceInfo()

    def start(self):
        self.chunks.clear()
        self.current_chunk = 0
        self.stream.start_stream()

    def stop(self):
        self.stream.stop_stream()

    def printDeviceInfo(self):
        for i in range(self.pyaudio.get_device_count()):
            dev = self.pyaudio.get_device_info_by_index(i)
            print(dev)
            print((i, dev['name'], dev['maxInputChannels'], dev['defaultSampleRate']))

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


def _getGrammar(sentences):
    all_words = set()
    for sentence in sentences:
        for word in sentence.split(" "):
            all_words.add(word)
    return " ".join(all_words)


class VoiceController:
    def __init__(self, handset):
        self.handset = handset
        self.condition = self.handset.condition
        self.recorder = Recorder()
        self.voice_model  = vosk.Model("/home/pi/vosk-model-small-en-us-0.3")
        self.commands = ["turn on turtle",
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
                         "good night",]
        self.grammar = _getGrammar(self.commands)
        self.recognizer = vosk.KaldiRecognizer(self.voice_model, self.recorder.fs, self.grammar)


    def runForever(self):
        while True:
            with self.condition:
                while not self.handset.active:
                    self.condition.wait()

                # We have been woken up by the handset being lifted.
                # Keep recording until it is put down again.
                print("Start recording")
                self.recorder.start()
                while self.handset.active:
                    time.sleep(0.1)

                print("Stopping recorder...")
                self.recorder.stop()
                time.sleep(0.1)
                print(f"Recording done. Got {len(self.recorder.chunks)} chunks.")

                num_secs = len(self.recorder.chunks) * self.recorder.chunk / (self.recorder.fs)
                print(f"num_secs: {num_secs}")

                audio_data = self.recorder.getNextChunk()
                while audio_data is not None:
                    self.recognizer.AcceptWaveform(audio_data)
                    audio_data = self.recorder.getNextChunk()

                result = self.recognizer.FinalResult()
                print(result)
                self.recognizer = vosk.KaldiRecognizer(self.voice_model, self.recorder.fs, self.grammar)


    def runForever2(self):
        while True:
            with self.condition:
                while not self.handset.active:
                    self.condition.wait()

                # We have been woken up by the handset being lifted.
                # Keep recording until it is put down again.

                print("Start recording")
                self.recorder.start()
                frames = []
                while self.handset.active:
                    data = self.recorder.stream.read(self.recorder.chunk)
                    frames.append(data)

                print("Stopping recorder...")
                self.recorder.stop()

                print(f"Recording done. Got {len(frames)} chunks.")

                num_secs = len(frames) * self.recorder.chunk / (self.recorder.fs)
                print(f"num_secs: {num_secs}")

                for audio_data in frames:
                    self.recognizer.AcceptWaveform(audio_data)

                result = self.recognizer.FinalResult()
                print(result)
                self.recognizer = vosk.KaldiRecognizer(self.voice_model, self.recorder.fs, self.grammar)


class Handset:
    def __init__(self, condition):
        self.button = Button(23)
        self.button.when_released = self.callbackHandsetLifted
        self.button.when_pressed = self.callbackHandsetPutDown
        self.condition = condition
        self.active = False

    def callbackHandsetLifted(self):
        print("Handset lifted")
        with self.condition:
            self.active = True
            self.condition.notify_all()


    def callbackHandsetPutDown(self):
        print("Handset put down")
        self.active = False


class LampController:
    def __init__(self, num_lamps):
       self.lamp_state = [False] * num_lamps
       self.rf_pin = 15
       self.emitter_id = 1337

       self.allOff()

    def toggle(self, lamp_idx):
        print("Toggle:", lamp_idx)
        if lamp_idx >= len(self.lamp_state):
            print("No lamp at index:", lamp_idx)
            return

        if self.lamp_state[lamp_idx]:
            self.turnOff(lamp_idx)
        else:
            self.turnOn(lamp_idx)

    def turnOff(self, lamp_idx):
        print("Turn off:", lamp_idx)
        if lamp_idx >= len(self.lamp_state):
            print("No lamp at index:", lamp_idx)
            return

        if lamp_idx >= 0:
            self.lamp_state[lamp_idx] = False
        elif lamp_idx == -1:
            self.lamp_state = [False]*len(self.lamp_state)
        else:
            print(f"Bad lamp idx '{lamp_idx}'")
            return

        self._callPiHomeEasy(lamp_idx, "off")

    def turnOn(self, lamp_idx):
        print("Turn on:", lamp_idx)
        if lamp_idx >= len(self.lamp_state):
            print("No lamp at index:", lamp_idx)
            return

        if lamp_idx >= 0:
            self.lamp_state[lamp_idx] = True
        elif lamp_idx == -1:
            self.lamp_state = [True]*len(self.lamp_state)
        else:
            print(f"Bad lamp idx '{lamp_idx}'")
            return

        self._callPiHomeEasy(lamp_idx, "on")

    def allOff(self):
        print("All off")
        self.turnOff(-1)

    def _callPiHomeEasy(self, receiver_id, state):
        bin_path = "/home/pi/piHomeEasy/piHomeEasy"
        command = [bin_path, str(self.rf_pin), str(self.emitter_id), str(receiver_id), state]
        print(f"Call piHomeEasy: {command}")
        ret = subprocess.run(command)
        print("Exit code:", ret.returncode)


class RotaryDial:
    def __init__(self, lamp_controller):
        self.pulse_button = Button(25)
        self.pulse_button.when_released = self.callbackPulseDetected

        self.active_button = Button(12)
        self.active_button.when_pressed = self.callbackActiveTrue
        self.active_button.when_released = self.callbackActiveFalse

        self.is_active = False
        self.pulses = 0

        self.lamp_controller = lamp_controller

    def callbackActiveTrue(self):
        self.is_active = True

    def callbackActiveFalse(self):
        self.is_active = False
        print("Got some pulses:", self.pulses)

        if self.pulses == 1:
            self.lamp_controller.allOff()
        elif self.pulses > 1:
            self.lamp_controller.toggle(self.pulses - 2)

        self.pulses = 0


    def callbackPulseDetected(self):
        if self.is_active:
            self.pulses += 1


def main():
    lamp_mapping = {"green": 0,
                    "turtle": 1}

    lamp_controller = LampController(len(lamp_mapping))
    rotary_dial = RotaryDial(lamp_controller)

    condition = threading.Condition()
    handset = Handset(condition)
    voice_controller = VoiceController(handset)

    print("Started. Waiting for input.")
    voice_controller.runForever()


if __name__ == "__main__":
    main()
