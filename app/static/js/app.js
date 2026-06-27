document.addEventListener("DOMContentLoaded", () => {
  if (window.layui) {
    layui.use(["layer", "element", "form"], () => {});
  }

  const passwordToggle = document.querySelector("[data-password-toggle]");
  const passwordInput = document.querySelector("[data-password-input]");
  const flashState = document.querySelector(".admin-layout");
  const sensorList = document.querySelector("[data-sensor-list]");
  const addSensorButton = document.querySelector("[data-add-sensor]");
  const autoRefreshTarget = document.querySelector("[data-auto-refresh-seconds]");
  const commandForm = document.querySelector("[data-command-form]");
  const commandPickerModal = document.querySelector("[data-command-picker-modal]");
  const modelChatModal = document.querySelector("[data-model-chat-modal]");
  const modelChatMessages = document.querySelector("[data-model-chat-messages]");
  const modelChatInput = document.querySelector("[data-model-chat-input]");
  const modelChatDeviceSummary = document.querySelector("[data-model-chat-device-summary]");
  const runtimeUrl = flashState?.dataset.aiotRuntimeUrl?.trim();
  const onlineControlDevicesScript = document.querySelector("[data-online-control-devices]");
  const reportRuntimeUrl = flashState?.dataset.reportRuntimeUrl?.trim();
  const reportTrendChartElement = document.querySelector("[data-report-trend-chart]");
  const reportSourceChartElement = document.querySelector("[data-report-source-chart]");
  const reportHistoryBody = document.querySelector("[data-report-history-body]");

  let latestOnlineDevices = [];
  let modelChatState = {
    modelId: "",
    modelName: "",
    modelModelName: "",
    apiUrl: "",
    temperature: "",
    maxTokens: "",
  };

  const readJsonScript = (scriptElement) => {
    if (!scriptElement) {
      return [];
    }
    try {
      return JSON.parse(scriptElement.textContent || "[]");
    } catch (_error) {
      return [];
    }
  };

  const modelChatOnlineDevices = readJsonScript(onlineControlDevicesScript);

  const getCookieValue = (name) => {
    const pattern = `${name}=`;
    return document.cookie
      .split(";")
      .map((item) => item.trim())
      .find((item) => item.startsWith(pattern))
      ?.slice(pattern.length) || "";
  };

  const scrollMessageStreamsToBottom = () => {
    document.querySelectorAll("[data-message-stream]").forEach((stream) => {
      stream.scrollTop = stream.scrollHeight;
    });
    document.querySelectorAll("[data-recent-events]").forEach((stream) => {
      stream.scrollTop = stream.scrollHeight;
    });
  };

  const escapeHtml = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const clearFlashQueryFromUrl = () => {
    if (!window.history?.replaceState || !window.location) {
      return;
    }
    const url = new URL(window.location.href);
    if (!url.searchParams.has("success") && !url.searchParams.has("error")) {
      return;
    }
    url.searchParams.delete("success");
    url.searchParams.delete("error");
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  };

  const renderMessages = (messages) =>
    messages
      .map(
        (message) => `
          <article class="aiot-message-item">
            <div class="aiot-message-head">
              <span class="aiot-message-source">${escapeHtml(message.box_id || "SYSTEM")}</span>
              <time>${escapeHtml(message.created_at || "")}</time>
            </div>
            <p>${escapeHtml(message.message_text || "")}</p>
          </article>
        `,
      )
      .join("");

  const renderRecentEvents = (events) =>
    (events || [])
      .map(
        (event) => `
          <article class="aiot-message-item aiot-event-item">
            <div class="aiot-message-head">
              <span class="aiot-message-source">${escapeHtml(event.box_id || "SYSTEM")}</span>
              <time>${escapeHtml(event.created_at || "")}</time>
            </div>
            <p>${escapeHtml(event.event_type || "")}${event.event_summary ? ` / ${escapeHtml(event.event_summary)}` : ""}</p>
          </article>
        `,
      )
      .join("");

  const renderRecentReportedDevices = (devices) =>
    (devices || [])
      .map(
        (device) => `
          <article class="aiot-message-item">
            <div class="aiot-message-head">
              <span class="aiot-message-source">${escapeHtml(device.box_id || "")}</span>
            </div>
            <p>${escapeHtml(device.last_event_type || "")}${device.event_summary ? ` / ${escapeHtml(device.event_summary)}` : ""}</p>
          </article>
        `,
      )
      .join("");

  const renderReportHistoryRows = (events) =>
    events
      .map((event) => {
        const sourceLabel =
          event.event_type === "device_report"
            ? "设备"
            : event.event_type === "user_action"
              ? "人工"
              : "同步";
        const source = event.actor_name ? `${sourceLabel} / ${event.actor_name}` : sourceLabel;
        const deviceLabel = event.box_id
          ? `${event.box_id}${event.device_name ? ` / ${event.device_name}` : ""}`
          : "-";
        return `
          <tr>
            <td>${escapeHtml(event.created_at || "")}</td>
            <td>${escapeHtml(source)}</td>
            <td>${escapeHtml(deviceLabel)}</td>
            <td>${escapeHtml(event.action_name || "")}</td>
            <td>${escapeHtml(event.detail_text || "-")}</td>
          </tr>
        `;
      })
      .join("");

  const renderModelChatBubble = ({ role, text, meta = "" }) => `
    <article class="model-chat-bubble ${role === "user" ? "is-user" : "is-assistant"}">
      <div class="model-chat-bubble-role">${escapeHtml(role === "user" ? "用户" : "AI 助手")}</div>
      <div class="model-chat-bubble-text">${escapeHtml(text || "")}</div>
      ${meta ? `<div class="model-chat-bubble-meta">${escapeHtml(meta)}</div>` : ""}
    </article>
  `;

  const appendModelChatBubble = (message) => {
    if (!modelChatMessages) {
      return;
    }
    modelChatMessages.insertAdjacentHTML("beforeend", renderModelChatBubble(message));
    modelChatMessages.scrollTop = modelChatMessages.scrollHeight;
  };

  const summarizeOnlineDevices = (devices) => {
    if (!devices.length) {
      return "当前没有在线开发板，您仍可以先测试对话，但不会自动下发控制命令。";
    }
    const sensorCount = devices.reduce((count, device) => count + (device.sensors || []).length, 0);
    const firstDevice = devices[0];
    return `当前已连接 ${devices.length} 台在线设备，共识别 ${sensorCount} 个传感器，优先控制 ${firstDevice.box_id}${firstDevice.device_name ? ` / ${firstDevice.device_name}` : ""}。`;
  };

  const buildModelChatGreeting = (devices) => {
    if (!devices.length) {
      return "您好，我是 AIOT 控制助手。当前没有在线设备，您可以先问我如何控制传感器，设备上线后我会自动生成可发送命令。";
    }
    const firstDevice = devices[0];
    const firstSensors = (firstDevice.sensors || [])
      .slice(0, 3)
      .map((sensor) => `${sensor.sensor_name} ${sensor.pin_code}`)
      .join("、");
    return `您好，我是 AIOT 控制助手。当前已连接在线设备 ${firstDevice.box_id}${firstDevice.device_name ? `（${firstDevice.device_name}）` : ""}，可协助控制 ${firstSensors || "已登记的传感器"}。`;
  };

  const openModelChatModal = (trigger) => {
    if (!modelChatModal || !modelChatMessages || !modelChatInput) {
      return;
    }

    modelChatState = {
      modelId: trigger.dataset.modelId || "",
      modelName: trigger.dataset.modelName || "",
      modelModelName: trigger.dataset.modelModelName || "",
      apiUrl: trigger.dataset.modelApiUrl || "",
      temperature: trigger.dataset.modelTemperature || "",
      maxTokens: trigger.dataset.modelMaxTokens || "",
    };

    const fields = {
      "[data-model-chat-name]": modelChatState.modelName,
      "[data-model-chat-model-name]": modelChatState.modelModelName,
      "[data-model-chat-temperature]": modelChatState.temperature,
      "[data-model-chat-max-tokens]": modelChatState.maxTokens,
      "[data-model-chat-api-url]": modelChatState.apiUrl,
    };
    Object.entries(fields).forEach(([selector, value]) => {
      const element = modelChatModal.querySelector(selector);
      if (element) {
        element.textContent = value || "-";
      }
    });

    if (modelChatDeviceSummary) {
      modelChatDeviceSummary.textContent = summarizeOnlineDevices(modelChatOnlineDevices);
    }
    modelChatMessages.innerHTML = "";
    appendModelChatBubble({ role: "assistant", text: buildModelChatGreeting(modelChatOnlineDevices) });
    modelChatInput.value = "";
    modelChatModal.classList.remove("is-hidden");
    document.body.classList.add("has-model-chat-open");
    window.setTimeout(() => modelChatInput.focus(), 60);
  };

  const closeModelChatModal = () => {
    if (!modelChatModal) {
      return;
    }
    modelChatModal.classList.add("is-hidden");
    document.body.classList.remove("has-model-chat-open");
  };

  const sendModelChatMessage = async () => {
    if (!modelChatModal || !modelChatInput || !modelChatState.modelId || !window.fetch) {
      return;
    }

    const text = modelChatInput.value.trim();
    if (!text) {
      return;
    }

    appendModelChatBubble({ role: "user", text });
    modelChatInput.value = "";

    const sendButton = modelChatModal.querySelector("[data-model-chat-send]");
    if (sendButton) {
      sendButton.disabled = true;
      sendButton.textContent = "发送中...";
    }

    try {
      const body = new URLSearchParams({
        _xsrf: getCookieValue("_xsrf"),
        model_id: modelChatState.modelId,
        message: text,
      });
      const response = await window.fetch("/model-engines/chat", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          Accept: "application/json",
        },
        body: body.toString(),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "发送失败");
      }

      const meta =
        payload.command_sent && payload.command_text
          ? `已发送命令: ${payload.command_text}`
          : payload.command_text
            ? `建议命令: ${payload.command_text}`
            : "";
      appendModelChatBubble({
        role: "assistant",
        text: payload.reply || "已收到。",
        meta,
      });
    } catch (error) {
      appendModelChatBubble({
        role: "assistant",
        text: error?.message || "模型请求失败，请稍后再试。",
      });
    } finally {
      if (sendButton) {
        sendButton.disabled = false;
        sendButton.textContent = "发送";
      }
      modelChatInput.focus();
    }
  };

  const renderDeviceOptions = (devices) => {
    const options = [
      `<option value="">${devices.length > 0 ? "选择在线设备" : "暂无在线设备"}</option>`,
    ];
    devices.forEach((device) => {
      const label = device.device_name
        ? `${device.box_id} / ${device.device_name}`
        : device.box_id;
      options.push(
        `<option value="${escapeHtml(device.box_id)}" data-server-id="${escapeHtml(device.server_id)}">${escapeHtml(label)}</option>`,
      );
    });
    return options.join("");
  };

  const rerenderLayuiSelects = () => {
    if (window.layui?.form?.render) {
      window.layui.form.render("select");
    }
  };

  const openCommandPicker = () => {
    if (!commandPickerModal) {
      return;
    }
    commandPickerModal.classList.remove("is-hidden");
    document.body?.classList?.add("has-command-picker-open");
  };

  const closeCommandPicker = () => {
    if (!commandPickerModal) {
      return;
    }
    commandPickerModal.classList.add("is-hidden");
    document.body?.classList?.remove("has-command-picker-open");
  };

  const updateCommandPanel = (servers) => {
    if (!commandForm) {
      return;
    }

    const deviceSelect = commandForm.querySelector("[data-online-device-select]");
    const commandInput = commandForm.querySelector("[data-command-input]");
    const commandDisplay = commandForm.querySelector("[data-command-display]");
    const serverIdInput = commandForm.querySelector("[data-command-server-id]");
    const commandPickerOpen = commandForm.querySelector("[data-command-picker-open]");
    const commandPickerLabel = commandForm.querySelector("[data-command-picker-label]");
    if (!deviceSelect || !commandInput || !commandDisplay || !serverIdInput || !commandPickerOpen) {
      return;
    }

    latestOnlineDevices = [];
    (servers || []).forEach((server) => {
      (server.online_devices || []).forEach((device) => {
        latestOnlineDevices.push({
          ...device,
          server_id: device.server_id || server.id,
        });
      });
    });

    const currentBoxId = deviceSelect.value;
    deviceSelect.innerHTML = renderDeviceOptions(latestOnlineDevices);
    deviceSelect.disabled = false;

    const selectedDevice =
      latestOnlineDevices.find((device) => device.box_id === currentBoxId) || latestOnlineDevices[0] || null;
    if (selectedDevice) {
      deviceSelect.value = selectedDevice.box_id;
      serverIdInput.value = `${selectedDevice.server_id}`;
    } else {
      deviceSelect.value = "";
      serverIdInput.value = "0";
    }
    commandPickerOpen.disabled = false;
    if (!commandInput.value) {
      commandDisplay.value = "";
      commandDisplay.placeholder = "点击左侧选择命令，例如 led_on / get_status";
      if (commandPickerLabel) {
        commandPickerLabel.textContent = "选择命令";
      }
    }
    rerenderLayuiSelects();
  };

  const updateServerCard = (server) => {
    const card = document.querySelector(`[data-server-card][data-server-id="${server.id}"]`);
    if (!card) {
      return;
    }

    card.classList.toggle("is-online", Boolean(server.is_running));

    const onlineCount = card.querySelector("[data-online-count]");
    const configStatus = card.querySelector("[data-config-status]");
    const deviceIds = card.querySelector("[data-device-ids]");
    const runtimeSummary = card.querySelector("[data-runtime-summary]");
    const runningBadge = card.querySelector("[data-running-badge]");
    const enabledBadge = card.querySelector("[data-enabled-badge]");
    const runningDot = card.querySelector("[data-running-dot]");
    const messageStream = card.querySelector("[data-message-stream]");
    const messageEmpty = card.querySelector("[data-message-empty]");
    const recentEvents = card.querySelector("[data-recent-events]");
    const recentReportedDevices = card.querySelector("[data-recent-reported-devices]");

    if (onlineCount) {
      onlineCount.textContent = `${server.online_count ?? 0}`;
    }
    if (configStatus) {
      configStatus.textContent = server.is_enabled ? "启用" : "停用";
    }
    if (deviceIds) {
      deviceIds.textContent = server.online_box_ids || "暂无在线设备";
    }
    if (runtimeSummary) {
      runtimeSummary.textContent = server.runtime_summary || "";
    }
    if (runningBadge) {
      runningBadge.textContent = server.is_running ? "运行中" : "已停止";
      runningBadge.className = `layui-badge ${server.is_running ? "layui-bg-green" : "layui-bg-gray"}`;
      runningBadge.setAttribute("data-running-badge", "");
    }
    if (enabledBadge) {
      enabledBadge.textContent = server.is_enabled ? "已启用" : "已停用";
      enabledBadge.className = `layui-badge-rim aiot-badge-rim${server.is_enabled ? "" : " is-muted"}`;
      enabledBadge.setAttribute("data-enabled-badge", "");
    }
    if (runningDot) {
      runningDot.className = `aiot-spotlight-dot ${server.is_running ? "is-online" : "is-offline"}`;
      runningDot.setAttribute("data-running-dot", "");
    }
    if (messageStream && messageEmpty) {
      const messages = Array.isArray(server.recent_messages) ? server.recent_messages : [];
      if (messages.length > 0) {
        messageStream.innerHTML = renderMessages(messages);
        messageStream.classList.remove("is-hidden");
        messageEmpty.classList.add("is-hidden");
      } else {
        messageStream.innerHTML = "";
        messageStream.classList.add("is-hidden");
        messageEmpty.classList.remove("is-hidden");
      }
    }
    if (recentEvents) {
      recentEvents.innerHTML = renderRecentEvents(server.recent_events || []);
    }
    if (recentReportedDevices) {
      recentReportedDevices.innerHTML = renderRecentReportedDevices(server.recent_reported_devices || []);
    }
  };

  const startAiotRuntimePolling = () => {
    if (!runtimeUrl || !autoRefreshTarget || !window.fetch) {
      return;
    }
    const seconds = Number.parseInt(autoRefreshTarget.getAttribute("data-auto-refresh-seconds") || "0", 10);
    if (seconds <= 0) {
      return;
    }

    const poll = async () => {
      if (document.visibilityState === "hidden") {
        return;
      }
      const active = document.activeElement;
      if (active && ["INPUT", "TEXTAREA"].includes(active.tagName)) {
        return;
      }
      try {
        const response = await window.fetch(runtimeUrl, {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if (!response.ok) {
          return;
        }
        const payload = await response.json();
        (payload.servers || []).forEach(updateServerCard);
        updateCommandPanel(payload.servers || []);
        scrollMessageStreamsToBottom();
      } catch (_error) {
        // Keep polling silent to avoid interrupting dashboard usage.
      }
    };

    window.setInterval(poll, seconds * 1000);
  };

  const startReportPolling = () => {
    if (!reportRuntimeUrl || !reportHistoryBody || !window.fetch) {
      return;
    }
    const trendChart =
      reportTrendChartElement && window.echarts ? window.echarts.init(reportTrendChartElement) : null;
    const sourceChart =
      reportSourceChartElement && window.echarts ? window.echarts.init(reportSourceChartElement) : null;
    const seconds = Number.parseInt(flashState?.dataset.reportRefreshSeconds || "0", 10);
    if (seconds <= 0) {
      return;
    }

    const renderSummary = (summary) => {
      Object.entries(summary || {}).forEach(([key, value]) => {
        const target = document.querySelector(`[data-report-summary-item="${key}"] strong`);
        if (target) {
          target.textContent = `${value ?? 0}`;
        }
      });
    };

    const renderCharts = (dailyTrend, sourceBreakdown) => {
      if (trendChart) {
        trendChart.setOption({
          tooltip: { trigger: "axis" },
          legend: { data: ["设备上报", "人工操作"] },
          xAxis: { type: "category", data: (dailyTrend || []).map((item) => item.day_label) },
          yAxis: { type: "value" },
          series: [
            {
              name: "设备上报",
              type: "line",
              smooth: true,
              data: (dailyTrend || []).map((item) => item.device_report_count),
            },
            {
              name: "人工操作",
              type: "bar",
              data: (dailyTrend || []).map((item) => item.user_action_count),
            },
          ],
        });
      }
      if (sourceChart) {
        sourceChart.setOption({
          tooltip: { trigger: "item" },
          series: [
            {
              type: "pie",
              radius: ["42%", "72%"],
              data: (sourceBreakdown || []).map((item) => ({
                name: item.event_type,
                value: item.total,
              })),
            },
          ],
        });
      }
    };

    const poll = async () => {
      try {
        const response = await window.fetch(reportRuntimeUrl, {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if (!response.ok) {
          return;
        }
        const payload = await response.json();
        renderSummary(payload.summary || {});
        reportHistoryBody.innerHTML = renderReportHistoryRows(payload.recent_events || []);
        renderCharts(payload.daily_trend || [], payload.source_breakdown || []);
      } catch (_error) {
        // Keep report polling silent for dashboard continuity.
      }
    };

    poll();
    window.setInterval(poll, seconds * 1000);
    window.addEventListener("resize", () => {
      trendChart?.resize();
      sourceChart?.resize();
    });
  };

  if (passwordToggle && passwordInput) {
    passwordToggle.addEventListener("click", () => {
      passwordInput.type = passwordInput.type === "password" ? "text" : "password";
    });
  }

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (form.getAttribute("data-confirmed") === "1") {
        form.removeAttribute("data-confirmed");
        return;
      }

      if (!window.layui || !layui.layer) {
        const fallbackMessage = form.getAttribute("data-confirm") || "确认执行当前操作吗？";
        if (!window.confirm(fallbackMessage)) {
          event.preventDefault();
        }
        return;
      }

      event.preventDefault();
      const message = form.getAttribute("data-confirm") || "确认执行当前操作吗？";
      layui.layer.confirm(message, { title: "操作确认", icon: 3 }, () => {
        form.setAttribute("data-confirmed", "1");
        form.requestSubmit();
      });
    });
  });

  if (flashState && window.layui && layui.layer) {
    const success = flashState.dataset.success?.trim();
    const error = flashState.dataset.error?.trim();
    if (success) {
      layui.layer.msg(success, { icon: 1, time: 1800 });
      clearFlashQueryFromUrl();
    } else if (error) {
      layui.layer.msg(error, { icon: 2, time: 2200 });
      clearFlashQueryFromUrl();
    }
  }

  if (commandForm) {
    const deviceSelect = commandForm.querySelector("[data-online-device-select]");
    const commandInput = commandForm.querySelector("[data-command-input]");
    const commandDisplay = commandForm.querySelector("[data-command-display]");
    const serverIdInput = commandForm.querySelector("[data-command-server-id]");
    const commandPickerOpen = commandForm.querySelector("[data-command-picker-open]");
    const commandPickerLabel = commandForm.querySelector("[data-command-picker-label]");

    if (deviceSelect && commandInput && commandDisplay && serverIdInput && commandPickerOpen) {
      deviceSelect.addEventListener("change", () => {
        const selectedDevice = latestOnlineDevices.find((device) => device.box_id === deviceSelect.value) || null;
        if (!selectedDevice) {
          serverIdInput.value = "0";
          return;
        }
        serverIdInput.value = `${selectedDevice.server_id}`;
      });
      commandPickerOpen.addEventListener("click", openCommandPicker);
      commandPickerModal?.querySelectorAll("[data-command-picker-close]").forEach((button) => {
        button.addEventListener("click", closeCommandPicker);
      });
      commandPickerModal?.querySelectorAll("[data-command-preset]").forEach((button) => {
        button.addEventListener("click", () => {
          commandInput.value = (button.dataset.commandPreset || "").trim();
          const label = (button.dataset.commandLabel || button.textContent || "").trim();
          commandDisplay.value = label;
          if (commandPickerLabel) {
            commandPickerLabel.textContent = label || "选择命令";
          }
          closeCommandPicker();
        });
      });
    }
  }

  if (modelChatModal) {
    document.querySelectorAll("[data-model-chat-open]").forEach((button) => {
      button.addEventListener("click", () => openModelChatModal(button));
    });

    modelChatModal.querySelectorAll("[data-model-chat-close]").forEach((button) => {
      button.addEventListener("click", closeModelChatModal);
    });

    modelChatModal.querySelector("[data-model-chat-clear]")?.addEventListener("click", () => {
      if (modelChatMessages) {
        modelChatMessages.innerHTML = "";
        appendModelChatBubble({ role: "assistant", text: buildModelChatGreeting(modelChatOnlineDevices) });
      }
      if (modelChatInput) {
        modelChatInput.value = "";
        modelChatInput.focus();
      }
    });

    modelChatModal.querySelector("[data-model-chat-send]")?.addEventListener("click", () => {
      sendModelChatMessage();
    });

    modelChatInput?.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeModelChatModal();
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        sendModelChatMessage();
      }
    });
  }

  scrollMessageStreamsToBottom();
  startAiotRuntimePolling();
  startReportPolling();

  if (sensorList && addSensorButton) {
    const createSensorRow = () => {
      const row = document.createElement("div");
      row.className = "sensor-row";
      row.innerHTML = `
        <input class="layui-input" name="sensor_name" placeholder="传感器名称">
        <input class="layui-input" name="pin_code" placeholder="引脚编号">
        <input class="layui-input" name="pin_remark" placeholder="引脚说明">
        <button class="layui-btn layui-btn-xs layui-bg-red" type="button" data-remove-sensor>删除</button>
      `;
      return row;
    };

    addSensorButton.addEventListener("click", () => {
      sensorList.appendChild(createSensorRow());
    });

    sensorList.addEventListener("click", (event) => {
      const target = event.target.closest("[data-remove-sensor]");
      if (!target) {
        return;
      }
      const rows = sensorList.querySelectorAll(".sensor-row");
      if (rows.length === 1) {
        rows[0].querySelectorAll("input").forEach((input) => {
          input.value = "";
        });
        return;
      }
      target.closest(".sensor-row")?.remove();
    });
  }
});
