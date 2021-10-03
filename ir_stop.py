from .client import TrainController

with TrainController(
        'ws://localhost:8080/pi-train-broker/agent-websocketws') as controller:
    controller.set_speed(1, 160, True)
    controller.wait_for_state_gt(80, 1, 2, 200)
    controller.set_speed(1, 0, False)
