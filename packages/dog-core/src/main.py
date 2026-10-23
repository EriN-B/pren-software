from machine import PrenMachine
import sys

def main():
    machine = PrenMachine()
    machine.activate_initial_state()

if __name__ == "__main__":
    if input("Generate image? [y/N]: ").strip().lower() == "y":
        PrenMachine()._graph().write_png("state_machine.png")
    else:
        main()
