"""API service handlers."""

import json
import math
from urllib.parse import quote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

import tornado.web

from app.controllers.base import BaseHandler
from app.models.api_service import ApiServiceRepository


API_PAGE_SIZE = 20
API_TEST_TIMEOUT = 20


def _service_form_payload(handler):
    return {
        "name": (handler.get_body_argument("name", "") or "").strip(),
        "category": (handler.get_body_argument("category", "") or "").strip(),
        "base_url": (handler.get_body_argument("base_url", "") or "").strip(),
        "method": (handler.get_body_argument("method", "GET") or "GET").strip().upper(),
        "headers_json": (handler.get_body_argument("headers_json", "{}") or "{}").strip(),
        "sample_params": (handler.get_body_argument("sample_params", "{}") or "{}").strip(),
        "description": (handler.get_body_argument("description", "") or "").strip(),
        "is_enabled": handler.get_body_argument("is_enabled", "0") == "1",
    }


def _append_query_to_url(raw_url, params):
    parsed = urlparse(raw_url)
    query = urlencode(params, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def _resolve_weather_request(service, city):
    params = json.loads(service["sample_params"] or "{}")
    weather_city = city or params.get("city") or params.get("location") or "chengdu"
    format_name = params.get("format") or "j1"

    base_url = service["base_url"].strip().rstrip("/")
    if "{city}" in base_url:
        url = base_url.replace("{city}", quote(str(weather_city)))
    else:
        url = f"{base_url}/{quote(str(weather_city))}"
    url = _append_query_to_url(url, {"format": format_name})
    headers = json.loads(service["headers_json"] or "{}")
    return url, headers, weather_city


def _fetch_weather_payload(city):
    service = ApiServiceRepository.get_enabled_service_by_category("天气")
    if not service:
        ApiServiceRepository.ensure_builtin_services()
        service = ApiServiceRepository.get_enabled_service_by_category("天气")
    url, headers, weather_city = _resolve_weather_request(service, city)
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=API_TEST_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
        status = getattr(response, "status", 200)
    return {"city": weather_city, "url": url, "status": status, "data": payload}


class ApiServiceListHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        ApiServiceRepository.ensure_builtin_services()
        keyword = (self.get_argument("keyword", "") or "").strip()
        page = max(int(self.get_argument("page", "1") or "1"), 1)
        edit_id = int(self.get_argument("edit_id", "0") or "0")

        services, total = ApiServiceRepository.list_services(page=page, page_size=API_PAGE_SIZE, keyword=keyword)
        editing = ApiServiceRepository.get_service_by_id(edit_id) if edit_id else None
        total_pages = max(math.ceil(total / API_PAGE_SIZE), 1)

        self.render(
            "api_services.html",
            title="接口管理",
            username=self.current_user,
            services=services,
            keyword=keyword,
            page=page,
            total=total,
            total_pages=total_pages,
            editing=editing,
            error=self.get_argument("error", ""),
            success=self.get_argument("success", ""),
            active_nav="api_services",
        )


class ApiServiceSaveHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        service_id = int(self.get_body_argument("service_id", "0") or "0")
        payload = _service_form_payload(self)
        if not all([payload["name"], payload["category"], payload["base_url"], payload["method"]]):
            target = f"/api-services?error={quote('请完整填写接口信息')}"
            if service_id:
                target += f"&edit_id={service_id}"
            self.redirect(target)
            return

        try:
            json.loads(payload["headers_json"] or "{}")
            json.loads(payload["sample_params"] or "{}")
        except json.JSONDecodeError:
            target = f"/api-services?error={quote('请求头或示例参数必须是 JSON')}"
            if service_id:
                target += f"&edit_id={service_id}"
            self.redirect(target)
            return

        if service_id:
            updated = ApiServiceRepository.update_service(service_id=service_id, **payload)
            if not updated:
                self.redirect(f"/api-services?edit_id={service_id}&error={quote('接口名称已存在')}")
                return
            self.redirect(f"/api-services?success={quote('接口配置已更新')}")
            return

        created = ApiServiceRepository.create_service(**payload)
        if not created:
            self.redirect(f"/api-services?error={quote('接口名称已存在')}")
            return
        self.redirect(f"/api-services?success={quote('接口配置已创建')}")


class ApiServiceDeleteHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        service_id = int(self.get_body_argument("service_id"))
        ApiServiceRepository.delete_service(service_id)
        self.redirect(f"/api-services?success={quote('接口配置已删除')}")


class ApiServiceTestHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        service_id = int(self.get_body_argument("service_id"))
        service = ApiServiceRepository.get_service_by_id(service_id)
        if not service:
            self.redirect(f"/api-services?error={quote('未找到接口配置')}")
            return

        try:
            headers = json.loads(service["headers_json"] or "{}")
            sample_params = json.loads(service["sample_params"] or "{}")
            body = None
            url = service["base_url"]
            if service["category"] == "天气":
                url, headers, _weather_city = _resolve_weather_request(service, sample_params.get("city"))
            elif service["method"] == "GET":
                url = _append_query_to_url(url, sample_params)
            else:
                body = json.dumps(sample_params).encode("utf-8")
                headers.setdefault("Content-Type", "application/json")

            request = Request(url, data=body, headers=headers, method=service["method"])
            with urlopen(request, timeout=API_TEST_TIMEOUT) as response:
                status = response.status
            self.redirect(f"/api-services?success={quote(f'联通成功，状态码 {status}')}")
        except Exception as exc:  # noqa: BLE001
            self.redirect(f"/api-services?error={quote(f'联通失败：{exc}')}")


class ApiServiceWeatherHandler(tornado.web.RequestHandler):
    def get(self):
        city = (self.get_argument("city", "chengdu") or "chengdu").strip()
        try:
            payload = _fetch_weather_payload(city)
        except Exception as exc:  # noqa: BLE001
            self.set_status(502)
            self.write({"error": f"天气接口请求失败: {exc}"})
            return
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write(payload)
