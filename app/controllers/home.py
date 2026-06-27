"""用户管理相关控制器。"""

import math

import tornado.web

from app.controllers.base import BaseHandler
from app.models.user import UserRepository


PAGE_SIZE = 20


class IndexHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        keyword = (self.get_argument("keyword", "") or "").strip()
        page = max(int(self.get_argument("page", "1") or "1"), 1)
        edit_id = int(self.get_argument("edit_id", "0") or "0")

        users, total = UserRepository.list_users(page=page, page_size=PAGE_SIZE, keyword=keyword)
        editing_user = UserRepository.get_user_by_id(edit_id) if edit_id else None
        total_pages = max(math.ceil(total / PAGE_SIZE), 1)

        self.render(
            "index.html",
            title="用户管理",
            username=self.current_user,
            users=users,
            keyword=keyword,
            page=page,
            page_size=PAGE_SIZE,
            total=total,
            total_pages=total_pages,
            editing_user=editing_user,
            error=self.get_argument("error", ""),
            success=self.get_argument("success", ""),
            active_nav="users",
        )


class UserSaveHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        user_id = int(self.get_body_argument("user_id", "0") or "0")
        display_name = (self.get_body_argument("display_name", "") or "").strip()
        phone = (self.get_body_argument("phone", "") or "").strip()
        password = self.get_body_argument("password", "")
        keyword = (self.get_body_argument("keyword", "") or "").strip()
        page = self.get_body_argument("page", "1")

        if user_id:
            if not display_name or not phone:
                return self.redirect(
                    f"/?edit_id={user_id}&page={page}&keyword={keyword}&error=请完整填写用户信息"
                )
            updated = UserRepository.update_user(
                user_id=user_id,
                display_name=display_name,
                phone=phone,
                password=password,
            )
            if not updated:
                return self.redirect(f"/?edit_id={user_id}&page={page}&keyword={keyword}&error=手机号已存在")
            self.redirect(f"/?page={page}&keyword={keyword}&success=用户信息已更新")
            return

        username = (self.get_body_argument("username", "") or "").strip()
        if not username or not display_name or not phone or not password:
            self.redirect(f"/?page={page}&keyword={keyword}&error=请完整填写新增用户信息")
            return

        created = UserRepository.create_user(
            username=username,
            password=password,
            display_name=display_name,
            phone=phone,
        )
        if not created:
            self.redirect(f"/?page={page}&keyword={keyword}&error=用户名或手机号已存在")
            return
        self.redirect(f"/?page={page}&keyword={keyword}&success=新用户创建成功")


class UserToggleHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        user_id = int(self.get_body_argument("user_id"))
        disabled = self.get_body_argument("disabled") == "1"
        keyword = (self.get_body_argument("keyword", "") or "").strip()
        page = self.get_body_argument("page", "1")
        UserRepository.set_user_disabled_by_id(user_id, disabled)
        tip = "用户已禁用" if disabled else "用户已启用"
        self.redirect(f"/?page={page}&keyword={keyword}&success={tip}")


class UserDeleteHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        user_id = int(self.get_body_argument("user_id"))
        keyword = (self.get_body_argument("keyword", "") or "").strip()
        page = self.get_body_argument("page", "1")
        user = UserRepository.get_user_by_id(user_id)
        if user and user["username"] == "star":
            self.redirect(f"/?page={page}&keyword={keyword}&error=默认管理员不允许删除")
            return
        UserRepository.delete_user(user_id)
        self.redirect(f"/?page={page}&keyword={keyword}&success=用户已删除")
