// @ts-check
/**
 * @file The 3D view: draws what MuJoCo simulates, plus the dog's own camera view.
 *
 * The browser simulates nothing. It builds one mesh per MuJoCo geom from the scene
 * message, then moves those meshes to the poses in each frame. Like MuJoCo, the
 * world is z-up: x forwards from home, y left, z up, in metres.
 */
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

/** @typedef {import("./protocol.js").Geom} Geom */
/** @typedef {import("./protocol.js").SceneMessage} SceneMessage */
/** @typedef {import("./protocol.js").Mesh} Mesh */
/** @typedef {import("./protocol.js").FrameMessage} FrameMessage */

THREE.Object3D.DEFAULT_UP.set(0, 0, 1);

const TRAIL_POINTS = 3000;

export class SimScene {
  /**
   * @param {HTMLCanvasElement} canvas Canvas filling the window.
   * @param {HTMLElement} eyeFrame Element marking where the dog's camera view is drawn.
   */
  constructor(canvas, eyeFrame) {
    this.canvas = canvas;
    this.eyeFrame = eyeFrame;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 0.9;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color("#12161b");
    this.scene.fog = new THREE.Fog("#12161b", 6, 14);
    const environment = new THREE.PMREMGenerator(this.renderer);
    this.scene.environment = environment.fromScene(new RoomEnvironment(), 0.04).texture;
    this.addLights();

    /** Orbiting camera for the user. */
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.02, 60);
    this.camera.position.set(-1.6, -1.9, 1.3);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.set(0, 0, 0.2);
    this.controls.enableDamping = true;
    this.controls.maxPolarAngle = Math.PI * 0.49;
    /** Keep the orbit centred on the dog. */
    this.follow = true;

    /** The dog's camera, posed from each frame. Looks along -z with y up, like MuJoCo's. */
    this.eye = new THREE.PerspectiveCamera(48.8, 4 / 3, 0.02, 30);

    /** @type {THREE.Mesh[]} One mesh per MuJoCo geom, in scene order. */
    this.meshes = [];
    this.group = new THREE.Group();
    this.scene.add(this.group);
    this.trail = this.createTrail();
    /** @type {THREE.Line[]} One line per tension spring, in tendon order. */
    this.springs = [];
    this.dogPosition = new THREE.Vector3();

    window.addEventListener("resize", () => this.resize());
    this.resize();
  }

  /** Soft sky light plus one shadow-casting sun. */
  addLights() {
    this.scene.add(new THREE.HemisphereLight("#dfe8ff", "#2a2f26", 0.9));
    const sun = new THREE.DirectionalLight("#fff4e0", 2.2);
    sun.position.set(-2.5, -1.5, 4);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = sun.shadow.camera.bottom = -3.5;
    sun.shadow.camera.right = sun.shadow.camera.top = 3.5;
    sun.shadow.bias = -0.0004;
    sun.shadow.radius = 4;
    this.scene.add(sun);
  }

  /**
   * A line along the floor showing where the dog has really been.
   * @returns {THREE.Line}
   */
  createTrail() {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array(TRAIL_POINTS * 3), 3),
    );
    geometry.setDrawRange(0, 0);
    const line = new THREE.Line(
      geometry,
      new THREE.LineBasicMaterial({ color: "#7cc4ff", transparent: true, opacity: 0.7 }),
    );
    line.frustumCulled = false;
    this.scene.add(line);
    return line;
  }

  /**
   * Replace everything drawn with the shapes from a scene message.
   * @param {SceneMessage} message
   */
  build(message) {
    this.group.clear();
    /** @type {Map<string, THREE.BufferGeometry>} */
    const parts = new Map();
    for (const [name, part] of Object.entries(message.meshes ?? {})) parts.set(name, partGeometry(part));
    this.meshes = message.geoms.map((geom) => {
      const mesh = createMesh(geom, parts);
      this.group.add(mesh);
      return mesh;
    });
    this.clearTrail();
    const grid = new THREE.GridHelper(6, 24, "#55605a", "#3a423d");
    grid.rotation.x = Math.PI / 2; // GridHelper lies in x-z; our floor is x-y
    grid.position.z = 0.001;
    this.group.add(grid);
  }

  /** Forget the trail, e.g. after a reset. */
  clearTrail() {
    this.trail.geometry.setDrawRange(0, 0);
  }

  /**
   * Move every mesh to where MuJoCo has it now.
   * @param {FrameMessage} frame
   * @param {number} dogGeomIndex Index of the dog's torso geom, for the trail and follow camera.
   */
  update(frame, dogGeomIndex) {
    frame.poses.forEach((pose, i) => {
      const mesh = this.meshes[i];
      if (mesh) applyPose(mesh, pose);
    });
    frame.springs.forEach((spring, i) => this.updateSpring(i, spring));
    applyPose(this.eye, frame.camera);
    const torso = frame.poses[dogGeomIndex];
    if (torso) {
      this.dogPosition.set(torso[0], torso[1], 0.2);
      this.extendTrail(torso[0], torso[1]);
    }
  }

  /**
   * Draw a spring between its two ends; it turns from yellow to red as it pulls harder.
   * @param {number} index
   * @param {import("./protocol.js").Spring} spring
   */
  updateSpring(index, { start, end, force }) {
    let line = this.springs[index];
    if (!line) {
      line = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial());
      line.frustumCulled = false;
      this.springs[index] = line;
      this.scene.add(line);
    }
    line.geometry.setFromPoints([new THREE.Vector3(...start), new THREE.Vector3(...end)]);
    const tension = Math.min(1, force / 15);
    /** @type {THREE.LineBasicMaterial} */ (line.material).color.setHSL(0.14 * (1 - tension), 0.9, 0.55);
  }

  /**
   * @param {number} x
   * @param {number} y
   */
  extendTrail(x, y) {
    const geometry = this.trail.geometry;
    const positions = /** @type {THREE.BufferAttribute} */ (geometry.getAttribute("position"));
    let count = geometry.drawRange.count;
    if (count > 0) {
      const last = count - 1;
      if (Math.hypot(positions.getX(last) - x, positions.getY(last) - y) < 0.01) return;
    }
    if (count >= TRAIL_POINTS) {
      positions.array.copyWithin(0, 3); // drop the oldest point
      count -= 1;
    }
    positions.setXYZ(count, x, y, 0.004);
    positions.needsUpdate = true;
    geometry.setDrawRange(0, count + 1);
  }

  /**
   * Where a click lands on the floor, or null if it misses.
   * @param {number} clientX
   * @param {number} clientY
   * @returns {THREE.Vector3 | null}
   */
  floorPoint(clientX, clientY) {
    const rect = this.canvas.getBoundingClientRect();
    const pointer = new THREE.Vector2(
      ((clientX - rect.left) / rect.width) * 2 - 1,
      -((clientY - rect.top) / rect.height) * 2 + 1,
    );
    const ray = new THREE.Raycaster();
    ray.setFromCamera(pointer, this.camera);
    const floor = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
    return ray.ray.intersectPlane(floor, new THREE.Vector3());
  }

  /** Draw the main view, then the dog's camera into the bottom-left corner. */
  render() {
    if (this.follow) {
      const shift = this.dogPosition.clone().sub(this.controls.target).multiplyScalar(0.08);
      this.controls.target.add(shift);
      this.camera.position.add(shift);
    }
    this.controls.update();
    const { width, height } = this.canvas.getBoundingClientRect();
    this.renderer.setScissorTest(false);
    this.renderer.setViewport(0, 0, width, height);
    this.renderer.render(this.scene, this.camera);

    // The eye view goes exactly where the inset element sits (WebGL counts y from the bottom).
    const canvasRect = this.canvas.getBoundingClientRect();
    const eyeRect = this.eyeFrame.getBoundingClientRect();
    const x = eyeRect.left - canvasRect.left;
    const y = canvasRect.bottom - eyeRect.bottom;
    this.renderer.setScissorTest(true);
    this.renderer.setScissor(x, y, eyeRect.width, eyeRect.height);
    this.renderer.setViewport(x, y, eyeRect.width, eyeRect.height);
    // The real camera sees neither the trail nor our spring lines.
    const overlays = [this.trail, ...this.springs];
    overlays.forEach((object) => (object.visible = false));
    this.renderer.render(this.scene, this.eye);
    overlays.forEach((object) => (object.visible = true));
  }

  resize() {
    const { width, height } = this.canvas.getBoundingClientRect();
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }
}

/**
 * Turn a CAD part's triangles into a flat-shaded geometry (sharp edges stay sharp).
 * @param {Mesh} part
 * @returns {THREE.BufferGeometry}
 */
function partGeometry(part) {
  const indexed = new THREE.BufferGeometry();
  indexed.setAttribute("position", new THREE.Float32BufferAttribute(part.vertices, 3));
  indexed.setIndex(part.faces);
  const flat = indexed.toNonIndexed();
  flat.computeVertexNormals();
  return flat;
}

/**
 * Build a mesh for one MuJoCo geom, with its size baked into the geometry.
 * @param {Geom} geom
 * @param {Map<string, THREE.BufferGeometry>} parts CAD part geometries by mesh name.
 * @returns {THREE.Mesh}
 */
function createMesh(geom, parts) {
  const [a, b, c] = geom.size;
  /** @type {THREE.BufferGeometry} */
  let shape;
  switch (geom.type) {
    case "plane":
      shape = new THREE.PlaneGeometry(2 * a || 20, 2 * b || 20);
      break;
    case "sphere":
      shape = new THREE.SphereGeometry(a, 32, 16);
      break;
    case "ellipsoid":
      shape = new THREE.SphereGeometry(1, 32, 16).scale(a, b, c);
      break;
    case "capsule": // MuJoCo capsules run along local z, three.js ones along y
      shape = new THREE.CapsuleGeometry(a, 2 * b, 8, 20).rotateX(Math.PI / 2);
      break;
    case "cylinder":
      shape = new THREE.CylinderGeometry(a, a, 2 * b, 40).rotateX(Math.PI / 2);
      break;
    case "mesh":
      shape = parts.get(geom.mesh ?? "") ?? new THREE.BufferGeometry();
      break;
    default: {
      const radius = Math.min(a, b, c) * 0.35;
      shape = new RoundedBoxGeometry(2 * a, 2 * b, 2 * c, 3, radius);
    }
  }
  const [red, green, blue, alpha] = geom.rgba;
  const material = new THREE.MeshStandardMaterial({
    color: new THREE.Color().setRGB(red, green, blue, THREE.SRGBColorSpace), // MuJoCo colours are sRGB
    roughness: geom.type === "plane" ? 0.95 : 0.5,
    metalness: 0.05,
    transparent: alpha < 1,
    opacity: alpha,
  });
  const mesh = new THREE.Mesh(shape, material);
  mesh.name = geom.name;
  mesh.visible = alpha > 0; // contact-only shapes (wheel tyres, casters) stay hidden
  mesh.castShadow = geom.type !== "plane" && alpha === 1;
  mesh.receiveShadow = true;
  return mesh;
}

/**
 * Set position and rotation from MuJoCo's [x, y, z, qw, qx, qy, qz].
 * @param {THREE.Object3D} object
 * @param {number[]} pose
 */
function applyPose(object, [x, y, z, qw, qx, qy, qz]) {
  object.position.set(x, y, z);
  object.quaternion.set(qx, qy, qz, qw); // three.js orders w last
}
