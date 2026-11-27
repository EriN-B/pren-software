import subprocess
import time

from dog_core.machine import PrenMachine


def main():
    machine = PrenMachine()
    machine.activate_initial_state()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Shutting down...")


if __name__ == "__main__":
    # TODO: Remove the virtual UART setup when running on a Raspberry Pi.
    subprocess.Popen(
        "socat -d -d "
        "PTY,link=/tmp/pren-uart-pi,raw,echo=0 "
        "PTY,link=/tmp/pren-uart-pico,raw,echo=0",
        shell=True,
    )
    main()
