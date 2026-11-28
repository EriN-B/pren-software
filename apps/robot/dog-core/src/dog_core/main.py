import subprocess
import time

from statemachine.contrib.diagram import DotGraphMachine

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
    if input("Generate image? [y/n]: ").strip().lower() == "y":
        DotGraphMachine(PrenMachine)().write_png(
            "packages/dog-core/src/dog_core/state_machine.png"
        )
    else:
        # TODO: Remove the virtual UART setup when running on a Raspberry Pi.
        subprocess.Popen(
            "socat -d -d "
            "PTY,link=/tmp/pren-uart-pi,raw,echo=0 "
            "PTY,link=/tmp/pren-uart-pico,raw,echo=0",
            shell=True,
        )
        main()
