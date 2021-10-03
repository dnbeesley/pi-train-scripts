#!/usr/bin/python3
import logging
from client import TrainController

logging.basicConfig(
    format='%(asctime)s: %(message)s',
    level=logging.DEBUG
)

with TrainController(
        'ws://localhost:8080/pi-train-broker/agent-websocket') as controller:
    controller.set_speed(0, 160, True)
    controller.wait_for_state_gt(80, 1, 2, 200)
    logging.info('Stopping')
    controller.set_speed(0, 0, False)
