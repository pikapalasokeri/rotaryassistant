#!/usr/bin/env python3

from gpiozero import Button
import signal
import subprocess


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
#    lur = Button(23)
#    lur.when_pressed = callbackLur

    lamp_mapping = {"green": 0,
                    "turtle": 1}

    lamp_controller = LampController(len(lamp_mapping))
    rotary_dial = RotaryDial(lamp_controller)

    print("Started. Waiting for input.")
    signal.pause()



if __name__ == "__main__":
    main()

