#!/usr/bin/python3
import datetime
import math
import serial
import time


def main():
    with serial.Serial('/dev/ttyACM0') as conn:
        print_serial_buffer(conn)
        write_motor_state(conn, 0, 0, True)
        time.sleep(0.1)
        print_serial_buffer(conn)
        end = datetime.datetime.now() + datetime.timedelta(seconds=5)
        while datetime.datetime.now() < end:
            read_cuurent(conn, 0)
            time.sleep(0.1)
            print_serial_buffer(conn)

        print_serial_buffer(conn)
        write_motor_state(conn, 0, 255, True)
        time.sleep(0.1)
        print_serial_buffer(conn)
        end = datetime.datetime.now() + datetime.timedelta(seconds=5)
        while datetime.datetime.now() < end:
            read_cuurent(conn, 0)
            time.sleep(0.1)
            print_serial_buffer(conn)

        write_motor_state(conn, 0, 0, True)
        time.sleep(0.1)
        print_serial_buffer(conn)


def print_serial_buffer(conn: serial.Serial):
    while conn.in_waiting:
        print(str(conn.readline()).strip())


def read_cuurent(conn: serial.Serial, channel: int):
    conn.write(bytes([0x03, channel, 0xFF]))


def write_motor_state(
        conn: serial.Serial, channel: int, speed: int, isReversed: bool):
    value0 = math.floor(speed / 0x40)
    if isReversed:
        value0 += 0x04

    value1 = speed % 0x40
    output = bytes([
         0x01,
         channel,
         value0,
         value1,
         0xFF
    ])

    return conn.write(output)


if __name__ == '__main__':
    main()
