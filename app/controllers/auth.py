"""认证相关控制器。"""

from app.controllers.base import BaseHandler
from app.models.user import UserRepository


class LoginHandler(BaseHandler):
    def get(self):
        self.render("login.html", title="登录", error=None)

    def post(self):
        username = (self.get_body_argument("username", "") or "").strip()
        password = self.get_body_argument("password", "")

        if not username or not password:
            self.set_status(400)
            return self.render("login.html", title="登录", error="请输入用户名和密码")

        if UserRepository.is_disabled(username):
            self.set_status(403)
            return self.render("login.html", title="登录", error="当前账号已被禁用，请联系管理员")

        if not UserRepository.verify_user(username, password):
            self.set_status(401)
            return self.render("login.html", title="登录", error="用户名或密码错误")

        self.set_secure_cookie("username", username)
        self.redirect("/")


class RegisterHandler(BaseHandler):
    def get(self):
        self.render("register.html", title="注册", error=None, form_data={})

    def post(self):
        form_data = {
            "username": (self.get_body_argument("username", "") or "").strip(),
            "display_name": (self.get_body_argument("display_name", "") or "").strip(),
            "phone": (self.get_body_argument("phone", "") or "").strip(),
        }
        password = self.get_body_argument("password", "")
        password2 = self.get_body_argument("password2", "")

        if not all([form_data["username"], form_data["display_name"], form_data["phone"], password]):
            self.set_status(400)
            return self.render(
                "register.html",
                title="注册",
                error="请完整填写注册信息",
                form_data=form_data,
            )

        if password != password2:
            self.set_status(400)
            return self.render(
                "register.html",
                title="注册",
                error="两次输入的密码不一致",
                form_data=form_data,
            )

        created = UserRepository.create_user(
            username=form_data["username"],
            password=password,
            display_name=form_data["display_name"],
            phone=form_data["phone"],
        )
        if not created:
            self.set_status(409)
            return self.render(
                "register.html",
                title="注册",
                error="用户名或手机号已存在",
                form_data=form_data,
            )

        self.redirect("/auth/login")


class LogoutHandler(BaseHandler):
    def post(self):
        self.clear_cookie("username")
        self.redirect("/auth/login")
