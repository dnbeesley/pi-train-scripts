import io
import json
import logging
import uuid
import schedule
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
        logging.debug(f'Sending: {msg}')
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
        logging.debug('# Enter _on_message()')
        try:
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
        finally:
            logging.debug('# Exit _on_message()')

    def _on_open(self, ws: websocket.WebSocketApp):
        self.web_socket.send("CONNECT\naccept-version:1.0,1.1,2.0\n\n\x00\n")
        client_id = str(uuid.uuid4())
        sub = stomper.subscribe("/topic/response", client_id, ack='auto')
        logging.debug(f'Sending: {sub}')
        self.web_socket.send(sub)
        self._is_open = True

    def _on_stomp_message(self, headers: dict, body: str):
        logging.debug('# Enter _on_stomp_message()')
        try:
            self._log_headers('Message', headers)
            if len(body.strip()) < 0:
                return

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
                logging.debug(f'Sensor: {address} has states: {states}')
            else:
                logging.debug(f'Response received: {obj}')
        except Exception as e:
            logging.exception(e)
        finally:
            logging.debug('# Exit _on_stomp_message()')

    def _send_read(self, address, length):
        body = {
            'address': address,
            'length': length
        }

        msg = stomper.send(
            '/topic/sensor',
            json.dumps(body),
            content_type='application/json')
        logging.debug(f'Sending: {msg}')
        self.web_socket.send(msg)

    def _wait_for_state(
            self,
            address: int,
            index: int,
            length: int,
            condition: Callable[[int], bool],
            interval_seconds: float):
        try:
            del self.sensors[address]
        except KeyError:
            pass

        job: schedule.Job = None
        try:
            job = schedule.every(interval_seconds).seconds.do(
                self._send_read, address=address, length=length)

            self._send_read(address, length)
            value = None
            while value is None or not condition(value):
                schedule.run_pending()
                value = self.get_sensor_value(address, index)
                time.sleep(0.001)
        finally:
            if job is not None:
                schedule.cancel_job(job)

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
        logging.debug(f'Sending: {msg}')
        self.web_socket.send(msg)

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
