from dog_core.machine import PrenMachine
from statemachine.contrib.diagram import DotGraphMachine

def main():
    machine = PrenMachine()
    machine.activate_initial_state()

if __name__ == "__main__":
    if input("Generate image? [y/n]: ").strip().lower() == "y":
                DotGraphMachine(PrenMachine)().write_png("packages/dog-core/src/dog_core/state_machine.png")
    else:
        main()
