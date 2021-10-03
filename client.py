import io
import json
from json.decoder import JSONDecodeError
import logging
import uuid
import stomper
import time
import threading
import websocket
from typing import Callable, Dict, List

READ_DEVICE_COMMAND = 4


class TrainController():
    def __init__(self, url: str):
        self._is_open: bool = False
        self.sensors: Dict[int, List[int]] = {}
        self.web_socket = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )

    def __enter__(self):
        self._is_open = False
        threading.Thread(target=self.web_socket.run_forever).start()
        while self._is_open is False:
            pass
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        msg = stomper.disconnect()
        self.web_socket.send(msg)
        self.web_socket.close()

    def _log_headers(self, msg_name: str, headers: dict):
        for name, value in headers.items():
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

    def _on_message(self, ws: websocket.WebSocketApp, message: str):
        buf = io.StringIO(message)
        headers = {}
        while True:
            line = buf.readline()
            if len(line.strip()) == 0:
                break

            parts = line.split(':')
            key = parts[0].strip().lower()
            if len(parts) > 1:
                headers[key] = parts[1].strip()

        body = message[buf.tell():].strip('\0')
        self._on_stomp_message(headers, body)

    def _on_open(self, ws: websocket.WebSocketApp):
        self.web_socket.send("CONNECT\naccept-version:1.0,1.1,2.0\n\n\x00\n")
        client_id = str(uuid.uuid4())
        sub = stomper.subscribe("/topic/response", client_id, ack='auto')
        self.web_socket.send(sub)
        self._is_open = True

    def _on_stomp_message(self, headers: dict, body: str):
        try:
            if ('destination' not in headers or
                    headers['destination'] != '/topic/response'):
                pass
            self._log_headers('Message', headers)
            if len(body.strip()) < 0:
                logging.debug('Empty body received')
                return

            obj = json.loads(body)
            if (type(obj) == dict and
                    'cmd' in obj and
                    obj['cmd'] == READ_DEVICE_COMMAND):
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
                logging.debug(f'Sensor: {address} has states: {states}')
            else:
                logging.debug(f'Response received: {obj}')
        except JSONDecodeError:
            logging.error(f"Could not parse: '{body}'")
        except Exception as e:
            logging.exception(e)

    def _send_read(self, address, length):
        body = {
            'address': address,
            'length': length
        }

        msg = stomper.send(
            '/topic/sensor',
            json.dumps(body),
            content_type='application/json')
        self.web_socket.send(msg)

    def _wait_for_state(
            self,
            address: int,
            index: int,
            length: int,
            condition: Callable[[int], bool]):
        try:
            del self.sensors[address]
        except KeyError:
            pass

        self._send_read(address, length)
        while True:
            value = self.get_sensor_value(address, index)
            if value is None:
                time.sleep(0.001)
                continue
            if condition(value):
                break
            else:
                self._send_read(address, length)
                del self.sensors[address]

    def set_speed(self, channel: int, speed: int, reversed: bool):
        body = {
            'channel': channel,
            'speed': speed,
            'reversed': reversed,
        }

        msg = stomper.send(
            '/topic/motor-control',
            json.dumps(body),
            content_type='application/json')
        self.web_socket.send(msg)

    def wait_for_state_gt(
            self,
            address: int,
            index: int,
            length: int,
            threashold: int):
        self._wait_for_state(
            address,
            index,
            length,
            lambda state: state > threashold
        )

    def wait_for_state_lt(
            self,
            address: int,
            index: int,
            length: int,
            threashold: int):
        self._wait_for_state(
            address,
            index,
            length,
            lambda state: state < threashold
        )
