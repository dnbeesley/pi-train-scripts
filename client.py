import json
import logging
import uuid
import schedule
import stomper
import stomper.stompbuffer
import time
import threading
import websocket
from typing import Callable, Dict, List

READ_DEVICE_COMMAND = 4


class TrainController():
    def __init__(self, url: str):
        self.sensors: Dict[int, List[int]] = {}
        self.stomp_buffer = stomper.stompbuffer.StompBuffer()
        self.web_socket = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )

    def __enter__(self):
        threading.Thread(target=self.web_socket.run_forever).start()
        return self

    def __exit__(self):
        self.web_socket.send(stomper.disconnect())
        self.web_socket.close()

    def _log_headers(self, msg_name: str, headers: dict):
        for (name, value) in headers:
            logging.debug(f'{msg_name} has header {name}: {value}')

    def get_sensor_value(self, address: int, index: int):
        try:
            return self.sensors[address][index]
        except KeyError:
            return None
        except IndexError:
            return None

    def _on_close(
            self,
            ws: websocket.WebSocketApp,
            status_code: int,
            message: str):
        logging.debug(
            f'Socket closed with status: {status_code} and message: {message}')

    def _on_error(self, ws: websocket.WebSocketApp, message: str):
        logging.error(f'Received error: {message}')

    def _on_message(self, ws: websocket.WebSocketApp, message):
        self.stomp_buffer.appendData(message)
        while True:
            msg = self.stomp_buffer.getOneMessage()
            if msg is None:
                break

            self._on_stomp_message(msg['headers'], msg['body'])

    def _on_open(self, ws: websocket.WebSocketApp):
        self.web_socket.send("CONNECT\naccept-version:1.0,1.1,2.0\n\n\x00\n")
        client_id = str(uuid.uuid4())
        sub = stomper.subscribe("/topic/response", client_id, ack='auto')
        self.web_socket.send(sub)

    def _on_stomp_message(self, headers: dict, body: str):
        self._log_headers('Message', headers)
        try:
            obj = json.loads(body)
            if 'cmd' in obj and obj['cmd'] == READ_DEVICE_COMMAND:
                if 'address' not in obj:
                    raise Exception(
                        'The "address" field was missing from the response to'
                        + 'a read device command')
                else:
                    address = obj['address']
                if 'states' not in obj:
                    raise Exception(
                        'The "states" field was missing from the response to'
                        + 'a read device command')
                else:
                    states = obj['states']

                self.sensors[address] = states
        except Exception as e:
            logging.exception(e)

    def _send_read(self, address, length):
        body = {
            'address': address,
            'length': length,
        }

        self.web_socket.send(stomper.send('/topic/sensor', json.dumps(body)))

    def _wait_for_state(
            self,
            address: int,
            index: int,
            length: int,
            condition: Callable[[int], bool],
            interval_seconds: float):
        job = schedule.every(interval_seconds).seconds.do(
            self._send_read, address=address, length=length)
        del self.handler.sensors[address]
        self._send_read(address, length)
        value = None
        while value is None or not condition(value):
            schedule.run_pending()
            value = self.handler.get_sensor_value(address, index)
            time.sleep(0.1)

        schedule.cancel_job(job)

    def set_speed(self, channel: int, speed: int, reversed: bool):
        body = {
            'channel': channel,
            'speed': speed,
            'reversed': reversed,
        }

        self.web_socket.send(
            stomper.send('/topic/motor-control', json.dumps(body)))

    def wait_for_state_gt(
            self,
            address: int,
            index: int,
            length: int,
            threashold: int,
            interval_seconds: float):
        self._wait_for_state(
            address,
            index,
            length,
            lambda state: state > threashold,
            interval_seconds
        )

    def wait_for_state_lt(
            self,
            address: int,
            index: int,
            length: int,
            threashold: int,
            interval_seconds: float):
        self._wait_for_state(
            address,
            index,
            length,
            lambda state: state < threashold,
            interval_seconds
        )
