#!/bin/bash

systemctl stop rotaryassistant

echo "Copying systemd service file..."
cp rotaryassistant.service /etc/systemd/system/
echo "Done."


echo "Enabling and starting service..."
systemctl enable rotaryassistant
systemctl start rotaryassistant
echo "Done."


echo "Here comes the log..."
sleep 2
echo "Wait for it..."
sleep 3
journalctl --unit=rotaryassistant
