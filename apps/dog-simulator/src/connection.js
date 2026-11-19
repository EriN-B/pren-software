// @ts-check
/**
 * @file The WebSocket to the sim host, reconnecting by itself.
 */

/** @typedef {import("./protocol.js").SceneMessage} SceneMessage */
/** @typedef {import("./protocol.js").FrameMessage} FrameMessage */
/** @typedef {import("./protocol.js").ClientMessage} ClientMessage */

/**
 * Keeps one connection to the sim host open and hands incoming messages to callbacks.
 */
export class SimConnection {
  /**
   * @param {string} url For example `ws://localhost:8780`.
   * @param {object} handlers
   * @param {(scene: SceneMessage) => void} handlers.onScene Called after every (re)connect.
   * @param {(frame: FrameMessage) => void} handlers.onFrame Called for every frame.
   * @param {(connected: boolean) => void} handlers.onStatus Called when the connection opens or drops.
   */
  constructor(url, { onScene, onFrame, onStatus }) {
    this.url = url;
    this.onScene = onScene;
    this.onFrame = onFrame;
    this.onStatus = onStatus;
    /** @type {WebSocket | null} */
    this.socket = null;
    this.open();
  }

  /** Connect, and try again every second while the sim host is not running. */
  open() {
    const socket = new WebSocket(this.url);
    this.socket = socket;
    socket.onopen = () => this.onStatus(true);
    socket.onclose = () => {
      this.onStatus(false);
      setTimeout(() => this.open(), 1000);
    };
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "scene") this.onScene(message);
      else if (message.type === "frame") this.onFrame(message);
    };
  }

  /**
   * Send a message; silently dropped while disconnected.
   * @param {ClientMessage} message
   */
  send(message) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
    }
  }
}
