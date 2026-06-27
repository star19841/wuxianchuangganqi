"""Model engine management handlers."""

import json
import math
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

import tornado.web

from app.controllers.base import BaseHandler
from app.models.aiot_server import AiotServerRepository
from app.models.model_engine import ModelEngineRepository
from app.services.aiot_server_manager import AiotServerManager


MODEL_PAGE_SIZE = 6
MODEL_REQUEST_TIMEOUT = 8
MODEL_CHAT_TIMEOUT = 90


def _build_model_payload(handler):
    return {
        "name": (handler.get_body_argument("name", "") or "").strip(),
        "api_key": (handler.get_body_argument("api_key", "") or "").strip(),
        "api_url": (handler.get_body_argument("api_url", "") or "").strip().rstrip("/"),
        "model_name": (handler.get_body_argument("model_name", "") or "").strip(),
        "temperature": (handler.get_body_argument("temperature", "0.7") or "0.7").strip(),
        "max_tokens": (handler.get_body_argument("max_tokens", "2048") or "2048").strip(),
        "is_default": handler.get_body_argument("is_default", "") == "1",
    }


def _request_json(url, payload, headers, timeout=MODEL_REQUEST_TIMEOUT):
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _list_online_control_devices():
    servers, _total = AiotServerRepository.list_servers(page=1, page_size=100, keyword="")
    if not servers:
        return []
    server_lookup = {row["id"]: dict(row) for row in servers}
    devices_by_server = AiotServerRepository.list_online_devices_by_server_ids(server_lookup.keys())

    devices = []
    for server_id, items in devices_by_server.items():
        server_name = server_lookup.get(server_id, {}).get("server_name", "")
        for device in items:
            devices.append(
                {
                    "server_id": server_id,
                    "server_name": server_name,
                    "box_id": device["box_id"],
                    "device_name": device["device_name"],
                    "category": device["category"],
                    "sensors": device["sensors"],
                }
            )
    return devices


def _build_aiot_chat_system_prompt(online_devices):
    if online_devices:
        device_lines = []
        for device in online_devices:
            sensor_lines = ", ".join(
                f"{sensor['sensor_name']}({sensor['pin_code']})"
                for sensor in device["sensors"]
            ) or "无传感器"
            device_lines.append(
                f"- box_id={device['box_id']}, device_name={device['device_name']}, "
                f"server={device['server_name']}, sensors={sensor_lines}"
            )
        device_text = "\n".join(device_lines)
    else:
        device_text = "- 当前没有在线设备"

    return (
        "你是 CdutAgentOS 的 AIOT 控制助手，负责帮助用户控制在线 ESP32 开发板。\n"
        "你必须只返回 JSON，不要输出任何额外说明。\n"
        'JSON 格式固定为 {"reply":"", "target_box_id":"", "command_text":""}。\n'
        "- reply: 给用户看的中文回复。\n"
        "- target_box_id: 当需要控制设备时，填写目标设备的 box_id；否则返回空字符串。\n"
        "- command_text: 当需要控制设备时，填写要直接发给开发板的原始命令；否则返回空字符串。\n"
        "- 如果用户是在查询状态、解释信息、或当前没有合适在线设备，就不要发命令。\n"
        "- 如果用户要求控制 LED/屏幕/传感器，请优先从在线设备及其传感器中选择最匹配的一项。\n"
        "- 当用户是开灯时，command_text 返回 on；关灯时返回 off；查看状态时返回 status。\n"
        "- reply 要自然简洁，若将发送命令，要明确告诉用户你准备控制哪个设备。\n"
        "当前在线设备如下：\n"
        f"{device_text}"
    )


def _parse_aiot_chat_response(content):
    text = (content or "").strip()
    if not text:
        return {"reply": "模型未返回内容。", "target_box_id": "", "command_text": ""}
    json_candidates = []
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced_match:
        json_candidates.append(fenced_match.group(1))
    json_candidates.extend(re.findall(r"\{.*?\}", text, flags=re.DOTALL))
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
        for candidate in json_candidates:
            try:
                payload = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
        if payload is None:
            return {"reply": text, "target_box_id": "", "command_text": ""}
    return {
        "reply": (payload.get("reply") or "").strip() or text,
        "target_box_id": (payload.get("target_box_id") or "").strip(),
        "command_text": (payload.get("command_text") or "").strip(),
    }


class ModelEngineListHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        keyword = (self.get_argument("keyword", "") or "").strip()
        page = max(int(self.get_argument("page", "1") or "1"), 1)
        edit_id = int(self.get_argument("edit_id", "0") or "0")

        models, total = ModelEngineRepository.list_models(
            page=page,
            page_size=MODEL_PAGE_SIZE,
            keyword=keyword,
        )
        editing = ModelEngineRepository.get_model_by_id(edit_id) if edit_id else None
        default_model = ModelEngineRepository.get_default_model()
        total_pages = max(math.ceil(total / MODEL_PAGE_SIZE), 1)

        self.render(
            "model_engines.html",
            title="模型引擎",
            username=self.current_user,
            models=models,
            keyword=keyword,
            page=page,
            total=total,
            total_pages=total_pages,
            editing=editing,
            default_model=default_model,
            online_control_devices=_list_online_control_devices(),
            error=self.get_argument("error", ""),
            success=self.get_argument("success", ""),
            active_nav="model_engines",
        )


class ModelEngineSaveHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        model_id = int(self.get_body_argument("model_id", "0") or "0")
        payload = _build_model_payload(self)
        if not all(
            [
                payload["name"],
                payload["api_key"],
                payload["api_url"],
                payload["model_name"],
                payload["temperature"],
                payload["max_tokens"],
            ]
        ):
            target = f"/model-engines?error={quote('请完整填写模型配置')}"
            if model_id:
                target += f"&edit_id={model_id}"
            self.redirect(target)
            return

        try:
            float(payload["temperature"])
            int(payload["max_tokens"])
        except ValueError:
            target = f"/model-engines?error={quote('温度或最大 Token 格式不正确')}"
            if model_id:
                target += f"&edit_id={model_id}"
            self.redirect(target)
            return

        if model_id:
            updated = ModelEngineRepository.update_model(model_id=model_id, **payload)
            if not updated:
                self.redirect(f"/model-engines?edit_id={model_id}&error={quote('模型名称已存在')}")
                return
            self.redirect(f"/model-engines?success={quote('模型配置已更新')}")
            return

        created = ModelEngineRepository.create_model(**payload)
        if not created:
            self.redirect(f"/model-engines?error={quote('模型名称已存在')}")
            return
        self.redirect(f"/model-engines?success={quote('模型配置已创建')}")


class ModelEngineDeleteHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        model_id = int(self.get_body_argument("model_id"))
        ModelEngineRepository.delete_model(model_id)
        self.redirect(f"/model-engines?success={quote('模型配置已删除')}")


class ModelEngineSetDefaultHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        model_id = int(self.get_body_argument("model_id"))
        ModelEngineRepository.set_default_model(model_id)
        self.redirect(f"/model-engines?success={quote('默认模型已切换')}")


class ModelEngineTestHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        model_id = int(self.get_body_argument("model_id"))
        prompt = (self.get_body_argument("prompt", "") or "").strip() or "请返回一句“模型联通成功”。"
        model = ModelEngineRepository.get_model_by_id(model_id)
        if not model:
            self.redirect(f"/model-engines?error={quote('未找到模型配置')}")
            return

        try:
            response = _request_json(
                f"{model['api_url']}/chat/completions",
                {
                    "model": model["model_name"],
                    "temperature": model["temperature"],
                    "max_tokens": model["max_tokens"],
                    "messages": [{"role": "user", "content": prompt}],
                },
                {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {model['api_key']}",
                },
                timeout=MODEL_CHAT_TIMEOUT,
            )
            message = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            flash = message[:60] or "模型连通成功"
            self.redirect(f"/model-engines?success={quote(f'测试成功：{flash}')}")
        except Exception as exc:  # noqa: BLE001
            self.redirect(f"/model-engines?error={quote(f'测试失败：{exc}')}")


class ModelEngineChatHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        model_id = int(self.get_body_argument("model_id", "0") or "0")
        message = (self.get_body_argument("message", "") or "").strip()
        model = ModelEngineRepository.get_model_by_id(model_id)
        if not model:
            self.set_status(404)
            self.write({"error": "未找到模型配置"})
            return
        if not message:
            self.set_status(400)
            self.write({"error": "请输入对话内容"})
            return

        online_devices = _list_online_control_devices()
        try:
            response = _request_json(
                f"{model['api_url']}/chat/completions",
                {
                    "model": model["model_name"],
                    "temperature": model["temperature"],
                    "max_tokens": model["max_tokens"],
                    "messages": [
                        {"role": "system", "content": _build_aiot_chat_system_prompt(online_devices)},
                        {"role": "user", "content": message},
                    ],
                },
                {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {model['api_key']}",
                },
                timeout=MODEL_CHAT_TIMEOUT,
            )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = _parse_aiot_chat_response(content)
        except Exception as exc:  # noqa: BLE001
            self.set_status(500)
            self.write({"error": f"模型请求失败：{exc}"})
            return

        command_sent = False
        target_box_id = parsed["target_box_id"]
        command_text = parsed["command_text"]
        if target_box_id and command_text:
            target_device = next((item for item in online_devices if item["box_id"] == target_box_id), None)
            if target_device:
                try:
                    AiotServerManager.instance().send_command(
                        target_device["server_id"],
                        target_box_id,
                        command_text,
                    )
                    command_sent = True
                except Exception:  # noqa: BLE001
                    command_sent = False

        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write(
            {
                "reply": parsed["reply"],
                "target_box_id": target_box_id,
                "command_text": command_text,
                "command_sent": command_sent,
                "online_device_count": len(online_devices),
            }
        )
