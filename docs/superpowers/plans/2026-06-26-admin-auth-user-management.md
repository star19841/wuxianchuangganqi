# 后台认证与用户管理实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成登录、注册、用户管理功能，并将登录页与后台界面调整为中文的 Layui 商业后台风格。

**Architecture:** 保持现有 Tornado MVC 结构，在 `app/models/` 中扩展用户数据能力，在 `app/controllers/` 中补充认证与用户管理流程，在 `app/templates/` 和 `app/static/` 中完成基于本地 `dist/layui-v2.13.7/` 的中文界面重构。

**Tech Stack:** Python, Tornado, SQLite, Tornado Template, Layui 2.13.7, unittest

---

### Task 1: 用户数据模型与默认管理员

**Files:**
- Modify: `app/models/db.py`
- Modify: `app/models/user.py`
- Test: `tests/test_user_repository.py`

- [ ] 为用户字段、唯一约束、默认管理员补充失败测试
- [ ] 运行测试并确认失败原因正确
- [ ] 实现数据库兼容初始化与默认账号 `star / 12345678`
- [ ] 再次运行测试确认通过

### Task 2: 认证流程与用户管理控制器

**Files:**
- Modify: `app/controllers/auth.py`
- Modify: `app/controllers/home.py`
- Modify: `app.py`
- Test: `tests/test_auth_flow.py`

- [ ] 为注册字段、禁用用户登录、用户列表与管理操作补充失败测试
- [ ] 运行测试并确认失败
- [ ] 实现控制器最小逻辑使测试通过
- [ ] 再次运行测试确认通过

### Task 3: 中文 Layui 界面重构

**Files:**
- Modify: `app/templates/base.html`
- Modify: `app/templates/login.html`
- Modify: `app/templates/register.html`
- Modify: `app/templates/index.html`
- Modify: `app/static/css/style.css`
- Modify: `app/static/js/app.js`

- [ ] 将本地 Layui 资源接入基础模板
- [ ] 按参考图重做中文登录页
- [ ] 将注册页改为同体系中文表单
- [ ] 将首页改为用户管理后台页并补齐表单与表格交互

### Task 4: 整体验证

**Files:**
- Test: `tests/test_user_repository.py`
- Test: `tests/test_auth_flow.py`

- [ ] 运行单元测试与集成测试
- [ ] 如有失败，修复后重跑直到通过
- [ ] 启动应用并进行最小运行验证
