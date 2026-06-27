const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function loadAppEnvironment({
  form,
  autoRefreshElement = null,
  activeElement = null,
  visibilityState = "visible",
  messageStreams = [],
  serverCard = null,
  commandForm = null,
  fetchImpl = async () => ({ ok: true, json: async () => ({ servers: [] }) }),
  flashDataset = {},
  initialUrl = "http://localhost/aiot-servers?success=test",
} = {}) {
  let domReadyHandler = null;
  const timers = [];
  let reloadCount = 0;
  const historyCalls = [];
  let layuiRenderCount = 0;

  const flashState = {
    dataset: flashDataset,
  };

  const document = {
    visibilityState,
    activeElement,
    addEventListener(eventName, handler) {
      if (eventName === "DOMContentLoaded") {
        domReadyHandler = handler;
      }
    },
    querySelector(selector) {
      if (selector === "[data-auto-refresh-seconds]") {
        return autoRefreshElement;
      }
      if (selector === ".admin-layout") {
        return flashState;
      }
      if (selector === `[data-server-card][data-server-id="1"]`) {
        return serverCard;
      }
      if (selector === "[data-command-form]") {
        return commandForm;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "form[data-confirm]") {
        return form ? [form] : [];
      }
      if (selector === "[data-message-stream]") {
        return messageStreams;
      }
      return [];
    },
  };

  const window = {
    layui: {
      use(_modules, callback) {
        callback();
      },
      form: {
        render(type) {
          if (type === "select") {
            layuiRenderCount += 1;
          }
        },
      },
      layer: {
        confirm(_message, _options, callback) {
          callback();
        },
        msg() {},
      },
    },
    confirm() {
      return true;
    },
    setInterval(callback, delay) {
      timers.push({ callback, delay });
      return timers.length;
    },
    fetch: fetchImpl,
    location: {
      href: initialUrl,
      reload() {
        reloadCount += 1;
      },
    },
    history: {
      replaceState(_state, _title, url) {
        historyCalls.push(url);
      },
    },
    URL,
  };

  const context = {
    window,
    document,
    layui: window.layui,
    console,
    URL,
  };

  const source = fs.readFileSync(
    path.join(__dirname, "..", "app", "static", "js", "app.js"),
    "utf8",
  );
  vm.runInNewContext(source, context, { filename: "app.js" });
  assert.ok(domReadyHandler, "DOMContentLoaded handler should be registered");
  domReadyHandler();

  return {
    timers,
    historyCalls,
    getReloadCount() {
      return reloadCount;
    },
    getLayuiRenderCount() {
      return layuiRenderCount;
    },
  };
}

function createConfirmForm() {
  const listeners = new Map();

  return {
    nativeSubmitCount: 0,
    requestSubmitCount: 0,
    confirmed: false,
    addEventListener(eventName, handler) {
      listeners.set(eventName, handler);
    },
    getAttribute(name) {
      if (name === "data-confirm") {
        return "确认执行当前操作吗？";
      }
      if (name === "data-confirmed") {
        return this.confirmed ? "1" : null;
      }
      return null;
    },
    setAttribute(name, value) {
      if (name === "data-confirmed") {
        this.confirmed = value === "1";
      }
    },
    removeAttribute(name) {
      if (name === "data-confirmed") {
        this.confirmed = false;
      }
    },
    requestSubmit() {
      this.requestSubmitCount += 1;
      if (this.requestSubmitCount > 5) {
        throw new Error("requestSubmit called repeatedly");
      }
      this.dispatchSubmit();
    },
    dispatchSubmit() {
      const event = {
        defaultPrevented: false,
        preventDefault() {
          this.defaultPrevented = true;
        },
      };
      listeners.get("submit")(event);
      if (!event.defaultPrevented) {
        this.nativeSubmitCount += 1;
      }
    },
  };
}

function createAutoRefreshElement(seconds) {
  return {
    getAttribute(name) {
      if (name === "data-auto-refresh-seconds") {
        return String(seconds);
      }
      return null;
    },
  };
}

function createMessageStream({ scrollHeight = 280 } = {}) {
  return {
    scrollHeight,
    scrollTop: 0,
    classList: {
      remove() {},
      add() {},
    },
    innerHTML: "",
  };
}

function createTextNode() {
  return { textContent: "" };
}

function createBadgeNode() {
  return {
    textContent: "",
    className: "",
    setAttribute() {},
  };
}

function createClassList(initial = []) {
  const values = new Set(initial);
  return {
    add(name) {
      values.add(name);
    },
    remove(name) {
      values.delete(name);
    },
    toggle(name, force) {
      if (force) {
        values.add(name);
      } else {
        values.delete(name);
      }
    },
    contains(name) {
      return values.has(name);
    },
  };
}

function createServerCard() {
  const onlineCount = createTextNode();
  const configStatus = createTextNode();
  const deviceIds = createTextNode();
  const runtimeSummary = createTextNode();
  const runningBadge = createBadgeNode();
  const enabledBadge = createBadgeNode();
  const runningDot = createBadgeNode();
  const messageStream = createMessageStream();
  const messageEmpty = {
    classList: createClassList(["is-hidden"]),
  };

  return {
    classList: createClassList(),
    querySelector(selector) {
      const mapping = {
        "[data-online-count]": onlineCount,
        "[data-config-status]": configStatus,
        "[data-device-ids]": deviceIds,
        "[data-runtime-summary]": runtimeSummary,
        "[data-running-badge]": runningBadge,
        "[data-enabled-badge]": enabledBadge,
        "[data-running-dot]": runningDot,
        "[data-message-stream]": messageStream,
        "[data-message-empty]": messageEmpty,
      };
      return mapping[selector] || null;
    },
    onlineCount,
    configStatus,
    deviceIds,
    runtimeSummary,
    runningBadge,
    enabledBadge,
    runningDot,
    messageStream,
    messageEmpty,
  };
}

function createSelectNode() {
  const listeners = new Map();
  return {
    value: "",
    innerHTML: "",
    disabled: false,
    addEventListener(eventName, handler) {
      listeners.set(eventName, handler);
    },
    dispatchChange() {
      const handler = listeners.get("change");
      if (handler) {
        handler({ target: this });
      }
    },
  };
}

function createCommandForm() {
  const deviceSelect = createSelectNode();
  const sensorSelect = createSelectNode();
  const commandInput = { value: "" };
  const serverIdInput = { value: "0" };
  return {
    querySelector(selector) {
      const mapping = {
        "[data-online-device-select]": deviceSelect,
        "[data-sensor-select]": sensorSelect,
        "[data-command-input]": commandInput,
        "[data-command-server-id]": serverIdInput,
      };
      return mapping[selector] || null;
    },
    deviceSelect,
    sensorSelect,
    commandInput,
    serverIdInput,
  };
}

test("confirmed data-confirm form submits exactly once", () => {
  const form = createConfirmForm();
  loadAppEnvironment({ form, flashDataset: {} });

  form.dispatchSubmit();

  assert.equal(form.nativeSubmitCount, 1);
  assert.equal(form.requestSubmitCount, 1);
});

test("flash query is cleared after showing success toast", () => {
  const environment = loadAppEnvironment({
    flashDataset: { success: "服务配置已更新", error: "" },
  });

  assert.deepEqual(environment.historyCalls, ["/aiot-servers"]);
});

test("local runtime polling updates only server card content", async () => {
  const serverCard = createServerCard();
  const environment = loadAppEnvironment({
    autoRefreshElement: createAutoRefreshElement(5),
    flashDataset: { success: "", error: "", aiotRuntimeUrl: "/aiot-servers/runtime?page=1&keyword=" },
    messageStreams: [serverCard.messageStream],
    serverCard,
    fetchImpl: async () => ({
      ok: true,
      json: async () => ({
        servers: [
          {
            id: 1,
            online_count: 3,
            online_box_ids: "BOX-01, BOX-02",
            is_running: true,
            is_enabled: true,
            runtime_summary: "已接收到设备上报消息",
            recent_messages: [
              {
                box_id: "BOX-02",
                message_text: "temperature=26.5",
                created_at: "2026-06-27 00:20:00",
              },
            ],
          },
        ],
      }),
    }),
  });

  assert.equal(environment.timers.length, 1);
  await environment.timers[0].callback();

  assert.equal(serverCard.onlineCount.textContent, "3");
  assert.equal(serverCard.configStatus.textContent, "启用");
  assert.equal(serverCard.deviceIds.textContent, "BOX-01, BOX-02");
  assert.equal(serverCard.runtimeSummary.textContent, "已接收到设备上报消息");
  assert.match(serverCard.messageStream.innerHTML, /temperature=26\.5/);
  assert.equal(serverCard.messageStream.scrollTop, serverCard.messageStream.scrollHeight);
  assert.equal(environment.getReloadCount(), 0);
});

test("local runtime polling skips fetch while an input is focused", async () => {
  let fetchCount = 0;
  const environment = loadAppEnvironment({
    autoRefreshElement: createAutoRefreshElement(5),
    activeElement: { tagName: "INPUT" },
    flashDataset: { success: "", error: "", aiotRuntimeUrl: "/aiot-servers/runtime?page=1&keyword=" },
    fetchImpl: async () => {
      fetchCount += 1;
      return { ok: true, json: async () => ({ servers: [] }) };
    },
  });

  await environment.timers[0].callback();

  assert.equal(fetchCount, 0);
});

test("local runtime polling still runs while a select is focused", async () => {
  let fetchCount = 0;
  const environment = loadAppEnvironment({
    autoRefreshElement: createAutoRefreshElement(5),
    activeElement: { tagName: "SELECT" },
    flashDataset: { success: "", error: "", aiotRuntimeUrl: "/aiot-servers/runtime?page=1&keyword=" },
    fetchImpl: async () => {
      fetchCount += 1;
      return { ok: true, json: async () => ({ servers: [] }) };
    },
  });

  await environment.timers[0].callback();

  assert.equal(fetchCount, 1);
});

test("selecting a sensor fills the command input with sensor and pin", async () => {
  const serverCard = createServerCard();
  const commandForm = createCommandForm();
  const environment = loadAppEnvironment({
    autoRefreshElement: createAutoRefreshElement(5),
    flashDataset: { success: "", error: "", aiotRuntimeUrl: "/aiot-servers/runtime?page=1&keyword=" },
    messageStreams: [serverCard.messageStream],
    serverCard,
    commandForm,
    fetchImpl: async () => ({
      ok: true,
      json: async () => ({
        servers: [
          {
            id: 1,
            online_count: 1,
            online_box_ids: "BOX-01",
            is_running: true,
            is_enabled: true,
            runtime_summary: "ready",
            recent_messages: [],
            online_devices: [
              {
                box_id: "BOX-01",
                device_name: "Living Screen",
                sensors: [
                  { sensor_name: "OLED", pin_code: "GPIO21", pin_remark: "SDA" },
                ],
              },
            ],
          },
        ],
      }),
    }),
  });

  await environment.timers[0].callback();
  commandForm.deviceSelect.value = "BOX-01";
  commandForm.deviceSelect.dispatchChange();
  commandForm.sensorSelect.value = "OLED|GPIO21";
  commandForm.sensorSelect.dispatchChange();

  assert.match(commandForm.sensorSelect.innerHTML, /OLED/);
  assert.equal(commandForm.commandInput.value, "sensor OLED GPIO21");
});

test("runtime polling rerenders layui selects after online device options change", async () => {
  const serverCard = createServerCard();
  const commandForm = createCommandForm();
  const environment = loadAppEnvironment({
    autoRefreshElement: createAutoRefreshElement(5),
    flashDataset: { success: "", error: "", aiotRuntimeUrl: "/aiot-servers/runtime?page=1&keyword=" },
    messageStreams: [serverCard.messageStream],
    serverCard,
    commandForm,
    fetchImpl: async () => ({
      ok: true,
      json: async () => ({
        servers: [
          {
            id: 1,
            online_count: 1,
            online_box_ids: "BOX-01",
            is_running: true,
            is_enabled: true,
            runtime_summary: "ready",
            recent_messages: [],
            online_devices: [
              {
                box_id: "BOX-01",
                device_name: "Living Screen",
                sensors: [
                  { sensor_name: "OLED", pin_code: "GPIO21", pin_remark: "SDA" },
                ],
              },
            ],
          },
        ],
      }),
    }),
  });

  await environment.timers[0].callback();

  assert.equal(environment.getLayuiRenderCount(), 1);
});

test("command panel stays clickable when there are no online devices", async () => {
  const commandForm = createCommandForm();
  const environment = loadAppEnvironment({
    autoRefreshElement: createAutoRefreshElement(5),
    flashDataset: { success: "", error: "", aiotRuntimeUrl: "/aiot-servers/runtime?page=1&keyword=" },
    commandForm,
    fetchImpl: async () => ({
      ok: true,
      json: async () => ({ servers: [] }),
    }),
  });

  await environment.timers[0].callback();

  assert.equal(commandForm.deviceSelect.disabled, false);
  assert.equal(commandForm.sensorSelect.disabled, false);
  assert.match(commandForm.deviceSelect.innerHTML, /暂无在线设备/);
  assert.match(commandForm.sensorSelect.innerHTML, /暂无可选传感器/);
  assert.equal(environment.getLayuiRenderCount(), 1);
});
