/**
 * Claw 嵌入式网页 SDK（Vanilla JS，无构建依赖）。
 * 宿主通过 /sdk/claw-bridge.js 提供；iframe 内页面引入后即可使用 window.claw。
 *
 * 下行：父窗口 postMessage { source: 'claw-platform', type: 'CLAW_UPDATE_STATE', embedId?, payload }
 * 上行：claw.emit → { source: 'claw-iframe', type: 'CLAW_EVENT', embedId?, eventName, payload }
 */
(function clawBridgeIife() {
  "use strict";

  if (typeof window === "undefined") return;

  var listeners = new Set();
  /** @type {string | null} */
  var configuredEmbedId = null;

  function onMessage(ev) {
    var d = ev.data;
    if (!d || typeof d !== "object") return;
    if (d.type !== "CLAW_UPDATE_STATE") return;
    if (d.source !== "claw-platform") return;
    if (configuredEmbedId != null && d.embedId != null && d.embedId !== configuredEmbedId) return;

    var payload = d.payload;
    listeners.forEach(function (cb) {
      try {
        cb(payload);
      } catch (e) {
        console.error("[claw-bridge] onUpdate callback error", e);
      }
    });
  }

  window.addEventListener("message", onMessage);

  window.claw = {
    /**
     * @param {{ embedId?: string }} opts
     */
    configure: function (opts) {
      if (!opts || typeof opts !== "object") return;
      if (typeof opts.embedId === "string" && opts.embedId.trim()) {
        configuredEmbedId = opts.embedId.trim();
      }
    },

    /**
     * @param {(payload: unknown) => void} callback
     * @returns {() => void} unsubscribe
     */
    onUpdate: function (callback) {
      if (typeof callback !== "function") {
        return function () {};
      }
      listeners.add(callback);
      return function () {
        listeners.delete(callback);
      };
    },

    /**
     * @param {string} eventName
     * @param {unknown} [payload]
     */
    emit: function (eventName, payload) {
      if (!window.parent || window.parent === window) return;
      /** @type {Record<string, unknown>} */
      var msg = {
        source: "claw-iframe",
        type: "CLAW_EVENT",
        eventName: String(eventName || ""),
        payload: payload === undefined ? null : payload,
      };
      if (configuredEmbedId != null) {
        msg.embedId = configuredEmbedId;
      }
      window.parent.postMessage(msg, "*");
    },
  };
})();
