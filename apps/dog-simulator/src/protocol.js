// @ts-check
/**
 * @file Messages exchanged with the sim host over the WebSocket.
 *
 * Mirrors `packages/dog-protocol/src/dog_protocol/__init__.py`; change both together.
 * Only type definitions live here, so this module exports nothing at runtime.
 */

/**
 * One shape to draw. Sizes follow MuJoCo: half extents for boxes, radius and half
 * length for capsules and cylinders.
 * @typedef {object} Geom
 * @property {string} name
 * @property {string} body Name of the body the geom belongs to, e.g. "dog" or "bone".
 * @property {"plane"|"sphere"|"capsule"|"ellipsoid"|"cylinder"|"box"|"mesh"} type
 * @property {number[]} size
 * @property {number[]} rgba Colour, each channel 0..1.
 * @property {string} [mesh] Key into `SceneMessage.meshes`, only for type "mesh".
 */

/**
 * Triangles of a CAD part in metres, in the frame of the geoms that use it.
 * @typedef {object} Mesh
 * @property {number[]} vertices x, y, z, x, y, z, ...
 * @property {number[]} faces Three vertex indices per triangle.
 */

/**
 * Sent once after connecting.
 * @typedef {object} SceneMessage
 * @property {"scene"} type
 * @property {Geom[]} geoms
 * @property {Record<string, Mesh>} meshes CAD parts, shared by every geom that uses them.
 */

/**
 * One actuated joint.
 * @typedef {object} Joint
 * @property {string} name
 * @property {number} angle Radians.
 * @property {number} velocity Radians per second.
 * @property {number} target Servo angle in rad, or wheel speed in rad/s.
 * @property {number} torque Newton metres the motor applies now.
 * @property {number} limit Newton metres the motor can apply at most.
 */

/**
 * One log line: from the sim host, the dog core, or a UART command to the Pico.
 * @typedef {object} LogEntry
 * @property {number} seq Increasing; the backlog arrives again after a reconnect.
 * @property {number} time Wall clock, seconds since 1970.
 * @property {"core"|"sim"|"uart"} source
 * @property {"DEBUG"|"INFO"|"WARNING"|"ERROR"|"CRITICAL"} level
 * @property {string} message
 */

/**
 * One box the core's own detector (YOLO) reported.
 * @typedef {object} CoreDetection
 * @property {"bone"|"person"|"shoe"} label
 * @property {number[]} box Pixel box [x1, y1, x2, y2] in 640 x 480.
 * @property {number} confidence 0..1.
 */

/**
 * Light of the dog's camera image; the viewer's 3D view keeps its own.
 * @typedef {object} Light
 * @property {number} brightness Sun, 0 to 1.
 * @property {number} elevation Sun height in degrees, 90 = straight above.
 * @property {number} azimuth Where the sun stands, degrees counter-clockwise from +x.
 * @property {number} ambient Light from all sides, 0 to 1.
 */

/**
 * Sent about 30 times a second.
 * @typedef {object} FrameMessage
 * @property {"frame"} type
 * @property {number} time Simulation time in seconds.
 * @property {number[][]} poses Per geom, in scene order: x, y, z, qw, qx, qy, qz.
 * @property {number[]} camera The dog's eye camera: x, y, z, qw, qx, qy, qz.
 * @property {Joint[]} joints
 * @property {Record<string, number>} sensors
 * @property {{posture: string, emergency_stop: boolean, speed: number,
 *   turn_rate_deg: number, turning_to: number|null, log: object[]}} pico
 * @property {{attached: boolean, state: string|null, error: string|null}} core
 * @property {Light} light Of the dog's camera image.
 * @property {Record<string, number[]>} detections True position: label to pixel box [x1, y1, x2, y2] in 640 x 480.
 * @property {CoreDetection[]} core_detections What the core's own detector found just now.
 * @property {Spring[]} springs The leg tension springs.
 */

/**
 * One tension spring ("Zugfeder").
 * @typedef {object} Spring
 * @property {string} name
 * @property {number[]} start World position of the body end.
 * @property {number[]} end World position of the leg end.
 * @property {number} force Newtons it pulls with; 0 when slack.
 */

/**
 * Anything the browser may send.
 * @typedef {{type: "pico", message: object}
 *   | {type: "emergency_stop", active: boolean}
 *   | {type: "place", object: "bone"|"person", x: number, y: number, yaw: number}
 *   | {type: "reset"}
 *   | {type: "random_bone"}
 *   | ({type: "light"} & Light)
 *   | {type: "random_light"}
 *   | {type: "voice", word: "hier"|"sitz"|"platz"|"auf"|"such"|"brav"}} ClientMessage
 */

export {};
