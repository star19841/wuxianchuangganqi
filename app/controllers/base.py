"""
Controller 公共基类（BaseHandler）

在 Tornado 中：
- 每个 URL 对应一个 RequestHandler（可以理解为 Controller）
- RequestHandler 提供 get()/post() 等方法来处理 HTTP 请求

本 BaseHandler 主要提供统一的登录态获取逻辑，供其他 Handler 继承使用。
"""

import tornado.web


class BaseHandler(tornado.web.RequestHandler):
    """
    所有业务 Handler 的基类。

    Tornado 的认证机制：
    - 框架会通过 get_current_user() 的返回值判断是否“已登录”
    - 如果返回 None，则 @tornado.web.authenticated 会触发跳转到 login_url
    """

    def get_current_user(self):
        """
        返回当前登录用户（字符串），或 None。

        这里演示用 secure cookie 存储 username：
        - set_secure_cookie() 会对 cookie 内容签名，防止客户端篡改
        - get_secure_cookie() 会校验签名，校验失败则返回 None
        """
        username = self.get_secure_cookie("username")
        if not username:
            return None
        # cookie 取回的是 bytes，这里转成 str 方便在模板里显示
        return username.decode("utf-8")
