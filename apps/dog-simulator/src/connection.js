// @ts-check
/**
 * @file The WebSocket to the sim host, reconnecting by itself.
 */

/** @typedef {import("./protocol.js").SceneMessage} SceneMessage */
/** @typedef {import("./protocol.js").FrameMessage} FrameMessage */
/** @typedef {import("./protocol.js").ClientMessage} ClientMessage */
/** @typedef {import("./protocol.js").LogEntry} LogEntry */

/** First byte of a binary message: which image follows (see dog_protocol). */
export const IMAGE_DOG_CAMERA = 0;
export const IMAGE_WEBCAM = 1;

/**
 * Keeps one connection to the sim host open and hands incoming messages to callbacks.
 */
export class SimConnection {
  /**
   * @param {string} url For example `ws://localhost:8780`.
   * @param {object} handlers
   * @param {(scene: SceneMessage) => void} handlers.onScene Called after every (re)connect.
   * @param {(frame: FrameMessage) => void} handlers.onFrame Called for every frame.
   * @param {(channel: number, jpeg: Blob) => void} handlers.onImage Called for every image
   *   (binary message): `IMAGE_DOG_CAMERA` or `IMAGE_WEBCAM`, then the JPEG.
   * @param {(entries: LogEntry[]) => void} handlers.onLogs Called with new log lines.
   * @param {(connected: boolean) => void} handlers.onStatus Called when the connection opens or drops.
   */
  constructor(url, { onScene, onFrame, onImage, onLogs, onStatus }) {
    this.url = url;
    this.onScene = onScene;
    this.onFrame = onFrame;
    this.onImage = onImage;
    this.onLogs = onLogs;
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
    socket.binaryType = "arraybuffer";
    socket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        const channel = new Uint8Array(event.data, 0, 1)[0];
        this.onImage(channel, new Blob([event.data.slice(1)], { type: "image/jpeg" }));
        return;
      }
      const message = JSON.parse(event.data);
      if (message.type === "scene") this.onScene(message);
      else if (message.type === "frame") this.onFrame(message);
      else if (message.type === "logs") this.onLogs(message.entries);
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
