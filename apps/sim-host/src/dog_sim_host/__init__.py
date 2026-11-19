"""Simulator host: the dog robot in MuJoCo, an emulated Pico, and the viewer server.

Modules, from the bottom up:

- `world`: the MuJoCo scene (robot from ``assets/dog.xml``, world from ``assets/scene.xml``)
- `pico`: emulates the Pico firmware: UART commands in, motor targets and odometry out
- `uart_link`: the virtual serial port the core connects to
- `core_adapters`: stand-ins for camera, microphone and recognition models
- `core_runner`: runs the real core with those stand-ins
- `app`: the real-time loop and the WebSocket server for the browser viewer
"""
