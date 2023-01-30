#!/bin/bash -eu

/usr/sbin/pcscd -d &
./build_in_docker/pico_hsm > /dev/null &
pytest tests -W ignore::DeprecationWarning
