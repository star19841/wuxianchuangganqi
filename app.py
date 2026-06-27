"""Tornado 应用入口。"""

import os

try:
    import tornado.ioloop
    import tornado.web
except ModuleNotFoundError as exc:
    raise SystemExit(
        "缺少依赖：tornado。\n"
        "请先激活虚拟环境并安装：\n"
        "  .\\venv\\Scripts\\Activate.ps1\n"
        "  python -m pip install tornado\n"
    ) from exc

from app.controllers.auth import LoginHandler, LogoutHandler, RegisterHandler
from app.controllers.aiot_server import (
    AiotServerDeleteHandler,
    AiotServerListHandler,
    AiotServerRuntimeHandler,
    AiotServerSaveHandler,
    AiotServerSendCommandHandler,
    AiotServerStartHandler,
    AiotServerStopHandler,
    AiotServerToggleHandler,
)
from app.controllers.api_service import (
    ApiServiceDeleteHandler,
    ApiServiceListHandler,
    ApiServiceSaveHandler,
    ApiServiceTestHandler,
    ApiServiceWeatherHandler,
)
from app.controllers.data_report import DataReportListHandler, DataReportRuntimeHandler
from app.controllers.device import DeviceDeleteHandler, DeviceListHandler, DeviceSaveHandler
from app.controllers.home import IndexHandler, UserDeleteHandler, UserSaveHandler, UserToggleHandler
from app.controllers.model_engine import (
    ModelEngineChatHandler,
    ModelEngineDeleteHandler,
    ModelEngineListHandler,
    MobileChatHandler,
    ModelEngineSaveHandler,
    ModelEngineSetDefaultHandler,
    ModelEngineTestHandler,
)
from app.models.db import init_db
from app.services.aiot_server_manager import AiotServerManager


def make_app(debug=True):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    settings = dict(
        template_path=os.path.join(base_dir, "app", "templates"),
        static_path=os.path.join(base_dir, "app", "static"),
        cookie_secret="demo-cookie-secret-change-me",
        login_url="/auth/login",
        xsrf_cookies=True,
        debug=debug,
        autoreload=debug,
    )

    return tornado.web.Application(
        [
            (r"/", IndexHandler),
            (r"/auth/login", LoginHandler),
            (r"/auth/register", RegisterHandler),
            (r"/auth/logout", LogoutHandler),
            (r"/users/save", UserSaveHandler),
            (r"/users/toggle", UserToggleHandler),
            (r"/users/delete", UserDeleteHandler),
            (r"/devices", DeviceListHandler),
            (r"/devices/save", DeviceSaveHandler),
            (r"/devices/delete", DeviceDeleteHandler),
            (r"/aiot-servers", AiotServerListHandler),
            (r"/aiot-servers/runtime", AiotServerRuntimeHandler),
            (r"/aiot-servers/save", AiotServerSaveHandler),
            (r"/aiot-servers/send-command", AiotServerSendCommandHandler),
            (r"/aiot-servers/delete", AiotServerDeleteHandler),
            (r"/aiot-servers/toggle", AiotServerToggleHandler),
            (r"/aiot-servers/start", AiotServerStartHandler),
            (r"/aiot-servers/stop", AiotServerStopHandler),
            (r"/model-engines", ModelEngineListHandler),
            (r"/model-engines/save", ModelEngineSaveHandler),
            (r"/model-engines/delete", ModelEngineDeleteHandler),
            (r"/model-engines/default", ModelEngineSetDefaultHandler),
            (r"/model-engines/test", ModelEngineTestHandler),
            (r"/model-engines/chat", ModelEngineChatHandler),
            (r"/api-services", ApiServiceListHandler),
            (r"/api-services/save", ApiServiceSaveHandler),
            (r"/api-services/delete", ApiServiceDeleteHandler),
            (r"/api-services/test", ApiServiceTestHandler),
            (r"/api-services/weather", ApiServiceWeatherHandler),
            (r"/mobile/weather", ApiServiceWeatherHandler),
            (r"/data-reports", DataReportListHandler),
            (r"/data-reports/runtime", DataReportRuntimeHandler),
            (r"/mobile/chat", MobileChatHandler),
            (r"/dist/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(base_dir, "dist")}),
        ],
        **settings,
    )


if __name__ == "__main__":
    init_db()
    AiotServerManager.instance().bootstrap_enabled_servers()
    app = make_app()
    base_port = int(os.environ.get("PORT", "8888"))
    for port in range(base_port, base_port + 20):
        try:
            app.listen(port)
            print(f"Server started: http://localhost:{port}/", flush=True)
            break
        except OSError as exc:
            if getattr(exc, "winerror", None) == 10048:
                continue
            raise
    else:
        raise SystemExit(f"启动失败：端口 {base_port}~{base_port + 19} 均被占用")
    tornado.ioloop.IOLoop.current().start()
