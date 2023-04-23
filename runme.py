#!/usr/bin/env python3

import signal
import subprocess
import threading
import time
import sys
import logging
import json
import multiprocessing
import numpy as np
from collections import deque
import random

# Hack to enable --user packages to be used when runnig as root (which is needed for piHomeEasy, omg).
sys.path.append("/home/pi/.local/lib/python3.7/site-packages")
sys.path.append("/usr/local/lib/python3.7/dist-packages")
import pyaudio
from gpiozero import Button
import vosk

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
LOGGER = logging.getLogger("main")


def processVoskForever(pipe, fs, grammar):
    voice_model  = vosk.Model("/home/pi/vosk-model-small-en-us-0.3")
    max_num_iters_without_sound = 3
    buffer_size = max_num_iters_without_sound
    # TODO: Set process prio low.
    while True:
        recognizer = vosk.KaldiRecognizer(voice_model, fs, grammar)
        LOGGER.info("KaldiRecognizer created.")

        chunk_buffer = deque(maxlen=buffer_size)
        got_sound = False
        consecutive_without_sound = 0
        pipe_has_data = True
        bail_early = False
        while pipe_has_data and not bail_early:
            data = pipe.recv()
            if len(data) == 0:
                pipe_has_data = False
                LOGGER.info("Got end of line from audio pipe.")
            else:
                # Insert new chunk into buffer.
                chunk_buffer.append(data)
                float_data = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                rms = np.sqrt(float_data.dot(float_data) / float_data.size)
                LOGGER.info(f"rms: {rms}")
                if rms > 200.0:
                    got_sound = True
                    consecutive_without_sound = 0
                else:
                    consecutive_without_sound += 1

                if got_sound:
                    # If we have got some sound, start popping from the chunk buffer.
                    # This will mean that processing is delayed a few iterations.
                    # It also means that we won't cut any speech from the stream when
                    # we start talking in the middle of a chunk.
                    recognizer.AcceptWaveform(chunk_buffer.popleft())

                # If we have started actually processing due to there being sound some chunk,
                # and we then have a number of chunks without any sounds, consider done.
                if got_sound and consecutive_without_sound > max_num_iters_without_sound:
                    bail_early = True

        # Empty chunk buffer into recognizer.
        LOGGER.info("Emptying buffer.")
        while len(chunk_buffer) > 0:
            recognizer.AcceptWaveform(chunk_buffer.popleft())

        # Empty pipe.
        LOGGER.info("Emptying leftovers in pipe.")
        while pipe_has_data:
            pipe_has_data = len(pipe.recv()) != 0

        result = recognizer.FinalResult()
        LOGGER.info(f"Got final result from recognizer:\n{result}")
        pipe.send(result)
        LOGGER.info("Result was sent on pipe.")


class Recorder:
    def __init__(self, pipe):
        self.num_chunks = 0
        self.pyaudio = pyaudio.PyAudio()

        # Chunk size needs to be large enough, otherwise parts of the audio will be dropped.
        self.chunk = 4*1024
        self.sample_format = pyaudio.paInt16
        self.channels = 1
        # Sample rate needs to be 48000 or something like that for the drivers to accept it.
        self.fs = 44100

        self.pipe = pipe
        self.stream = None
        self.printDeviceInfo()

        self.num_chunks_to_skip = 6

    def start(self):
        self.num_chunks = 0
        self.stream.start_stream()

    def stop(self):
        if self.stream is not None:
            LOGGER.info("Stopping stream...")
            self.stream.stop_stream()
            self.stream.close()
            LOGGER.info("Done.")
            self.pipe.send(bytearray())
        LOGGER.info("Creating new stream...")
        self.stream = self.pyaudio.open(format=self.sample_format,
                                        channels=self.channels,
                                        rate=self.fs,
                                        frames_per_buffer=self.chunk,
                                        stream_callback=self.addFramesToPipe,
                                        input_device_index=2, # 2 = antlion zero, 5 = laptop,
                                                              # 6 = antlion laptop, empty = system default.
                                        input=True,
                                        start=False)
        LOGGER.info("Done.")

    def printDeviceInfo(self):
        for i in range(self.pyaudio.get_device_count()):
            dev = self.pyaudio.get_device_info_by_index(i)
            LOGGER.info(dev)
            LOGGER.info((i, dev['name'], dev['maxInputChannels'], dev['defaultSampleRate']))

    def addFramesToPipe(self,
                        in_data,
                        frame_count,
                        time_info,
                        status_flags):
        self.num_chunks += 1
        if self.num_chunks > self.num_chunks_to_skip:
            self.pipe.send(in_data)
        return (in_data, pyaudio.paContinue)


def _getGrammar(commands):
    all_words = set()
    for sentence, _ in commands.items():
        for word in sentence.split(" "):
            all_words.add(word)
    return " ".join(all_words)


class VoiceController:
    def __init__(self, handset, lamp_controller, mapping):
        self.handset = handset
        self.condition = self.handset.condition
        self.lamp_controller = lamp_controller
        self.mapping = mapping
        self.commands = {"activate turtle": lambda idx=self.mapping["turtle"]: self.lamp_controller.turnOn(idx),
                         "shut down turtle": lambda idx=self.mapping["turtle"]: self.lamp_controller.turnOff(idx),
                         "activate christmas": lambda idx=self.mapping["turtle"]: self.lamp_controller.turnOn(idx),
                         "shut down christmas": lambda idx=self.mapping["turtle"]: self.lamp_controller.turnOff(idx),
                         "activate green": lambda idx=self.mapping["green"]: self.lamp_controller.turnOn(idx),
                         "shut down green": lambda idx=self.mapping["green"]: self.lamp_controller.turnOff(idx),
                         "activate blue": lambda idx=self.mapping["blue"]: self.lamp_controller.turnOn(idx),
                         "shut down blue": lambda idx=self.mapping["blue"]: self.lamp_controller.turnOff(idx),
                         "activate corner": lambda idx=self.mapping["corner"]: self.lamp_controller.turnOn(idx),
                         "shut down corner": lambda idx=self.mapping["corner"]: self.lamp_controller.turnOff(idx),
                         "activate yellow": lambda idx=self.mapping["yellow"]: self.lamp_controller.turnOn(idx),
                         "shut down yellow": lambda idx=self.mapping["yellow"]: self.lamp_controller.turnOff(idx),
                         "activate everything": self.lamp_controller.allOn,
                         "shut down everything": self.lamp_controller.allOff,
                         "activate random": self.lamp_controller.randomOn,
                         "shut down random": self.lamp_controller.randomOff,
                         "let there be light": self.lamp_controller.allOn,
                         "you all suck": self.lamp_controller.allOff,
                         "good night": self.lamp_controller.allOff}

        self.grammar = _getGrammar(self.commands)

        self.pipe_recorder_end, self.pipe_processor_end = multiprocessing.Pipe()
        self.recorder = Recorder(self.pipe_recorder_end)
        self.vosk_process = multiprocessing.Process(target=processVoskForever,
                                                    args=(self.pipe_processor_end,
                                                          self.recorder.fs,
                                                          self.grammar))
        self.vosk_process.start()


    def runForever(self):
        # This is done here since it didn't work to have it in the constructor.
        # Probably due to forking of this process _after_ the stream is constructed
        # messes things up. With the stop() call here we fork the process _before_
        # stream is constructed and so we don't get any conflicts.
        self.recorder.stop()

        while True:
            with self.condition:
                while not self.handset.active:
                    self.condition.wait()

                # We have been woken up by the handset being lifted.
                # Keep recording until it is put down again.
                LOGGER.info("Start recording")
                self.recorder.start()
                while self.handset.active:
                    time.sleep(0.1)

                LOGGER.info("Stopping recorder...")
                self.recorder.stop()
                time.sleep(0.1)
                LOGGER.info(f"Recording done. Got {self.recorder.num_chunks} chunks.")

                num_secs = self.recorder.num_chunks * self.recorder.chunk / (self.recorder.fs)
                LOGGER.info(f"num_secs: {num_secs}")

                result = self.pipe_recorder_end.recv()
                LOGGER.info(result)
                json_result = json.loads(result)
                if "text" in json_result:
                    text = json_result["text"]
                    matched_command = False
                    for command_text, command_func in self.commands.items():
                        if command_text in text:
                            LOGGER.info(f"Text is likely command. '{text}'. Running '{command_text}'.")
                            command_func()
                            matched_command = True
                            break
                    if not matched_command:
                        LOGGER.info("Text didn't match any command.")


class Handset:
    def __init__(self, condition):
        self.button = Button(23)
        self.button.when_released = self.callbackHandsetLifted
        self.button.when_pressed = self.callbackHandsetPutDown
        self.condition = condition
        self.active = False

    def callbackHandsetLifted(self):
        LOGGER.info("Handset lifted")
        with self.condition:
            self.active = True
            self.condition.notify_all()

    def callbackHandsetPutDown(self):
        LOGGER.info("Handset put down")
        self.active = False


class LampController:
    def __init__(self, num_lamps):
       self.lamp_state = [False] * num_lamps
       self.rf_pin = 15
       self.emitter_id = 1337

       self.allOff()

    def toggle(self, lamp_idx):
        LOGGER.info(f"Toggle: {lamp_idx}")
        if lamp_idx >= len(self.lamp_state):
            LOGGER.info(f"No lamp at index {lamp_idx}")
            return

        if self.lamp_state[lamp_idx]:
            self.turnOff(lamp_idx)
        else:
            self.turnOn(lamp_idx)

    def turnOff(self, lamp_idx):
        LOGGER.info(f"Turn off: {lamp_idx}")
        if lamp_idx >= len(self.lamp_state):
            LOGGER.info(f"No lamp at index: {lamp_idx}")
            return

        if lamp_idx >= 0:
            self.lamp_state[lamp_idx] = False
        elif lamp_idx == -1:
            self.lamp_state = [False]*len(self.lamp_state)
        else:
            LOGGER.info(f"Bad lamp idx '{lamp_idx}'")
            return

        self._callPiHomeEasy(lamp_idx, "off")

    def turnOn(self, lamp_idx):
        LOGGER.info(f"Turn on: {lamp_idx}")
        if lamp_idx >= len(self.lamp_state):
            LOGGER.info(f"No lamp at index: {lamp_idx}")
            return

        if lamp_idx >= 0:
            self.lamp_state[lamp_idx] = True
        elif lamp_idx == -1:
            self.lamp_state = [True]*len(self.lamp_state)
        else:
            LOGGER.info(f"Bad lamp idx: {lamp_idx}")
            return

        self._callPiHomeEasy(lamp_idx, "on")

    def allOff(self):
        LOGGER.info("All off")
        self.turnOff(-1)

    def allOn(self):
        LOGGER.info("All on")
        self.turnOn(-1)

    def randomOn(self):
        lamp_idx = self._getRandom(False)
        if lamp_idx is not None:
            self.turnOn(lamp_idx)

    def randomOff(self):
        lamp_idx = self._getRandom(True)
        if lamp_idx is not None:
            self.turnOff(lamp_idx)

    def _callPiHomeEasy(self, receiver_id, state):
        command = ["piHomeEasy", str(self.rf_pin), str(self.emitter_id), str(receiver_id), state]
        LOGGER.info(f"Call piHomeEasy: {command}")
        ret = subprocess.run(command)
        LOGGER.info(f"Exit code: {ret.returncode}")

    def _getRandom(self, current_state):
        lamps_with_current_state = []
        for lamp_idx, state in enumerate(self.lamp_state):
            if state == current_state:
                lamps_with_current_state.append(lamp_idx)
        if lamps_with_current_state:
            return random.choice(lamps_with_current_state)
        else:
            return None


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
        LOGGER.info(f"Got some pulses: {self.pulses}")

        if self.pulses == 1:
            self.lamp_controller.allOff()
        elif self.pulses > 1:
            self.lamp_controller.toggle(self.pulses - 2)

        self.pulses = 0

    def callbackPulseDetected(self):
        if self.is_active:
            self.pulses += 1


def main():
    mapping = {"green": 0,
               "turtle": 1,
               "corner": 2,
               "yellow": 3,
               "blue": 4}
    num_lamps = len(mapping)
    lamp_controller = LampController(num_lamps)
    rotary_dial = RotaryDial(lamp_controller)

    condition = threading.Condition()
    handset = Handset(condition)

    voice_controller = VoiceController(handset, lamp_controller, mapping)

    LOGGER.info("Started. Waiting for input.")
    voice_controller.runForever()


if __name__ == "__main__":
    main()
