# rotaryassistant


# Installing on target

```
sudo apt install python3-pip libgfortran3 portaudio19-dev wiringpi
pip3 install vosk pyaudio --user

wget https://alphacephei.com/kaldi/models/vosk-model-small-en-us-0.3.zip
unzip vosk-model-small-en-us-0.3.zip

git clone https://github.com/pikapalasokeri/piHomeEasy.git
cd piHomeEasy
make
sudo make install
cd ..
rm -rf piHomeEasy
```

# Programming NEXA switches

* Insert NEXA plug into wall.
* Quickly thereafter, execute `sudo piHomeEasy 15 1337 0 on` and listen for switch going "click click".
  - 15 is the pin number on the raspi.
  - 1337 is the transmitter number.
  - 0 is the receiver number, change this for each switch.
  

