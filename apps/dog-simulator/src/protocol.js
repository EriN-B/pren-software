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
 * @property {Record<string, number[]>} detections Label to pixel box [x1, y1, x2, y2] in 640 x 480.
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
 *   | {type: "voice", word: string}
 *   | {type: "gesture", gesture: "auf"|"sitz"|"platz"|null}
 *   | {type: "emergency_stop", active: boolean}
 *   | {type: "place", object: "bone"|"person", x: number, y: number}
 *   | {type: "reset"}} ClientMessage
 */

export {};
