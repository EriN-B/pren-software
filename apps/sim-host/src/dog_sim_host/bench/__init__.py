"""Test bench for the core's bone detector: many seeded single pictures, scored.

Each trial places the bone and the dog's camera at random (distance, angle, bone turn,
light, floor, a person, camera faults), renders what the camera sees and runs the core's
own detector on it. Runs are compared on the same seeds. A small web dashboard shows the
results; ``python -m dog_sim_host.bench --help`` lists the commands.
"""
