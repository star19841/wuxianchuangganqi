# Model Engine And API Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 Layui 后台系统中新增模型引擎管理和接口管理两个一级页面，并完成模型配置、默认模型、模型测试、接口配置与联通性测试能力。

**Architecture:** 使用独立的数据表和仓储模块分别管理模型配置与接口配置；通过新增控制器和模板页面接入现有顶部栏与左侧菜单；模型测试走 OpenAI 兼容接口调用，接口测试走通用 HTTP 探活逻辑，并把失败信息可视化反馈到后台。

**Tech Stack:** Python, Tornado, SQLite, Tornado Template, Layui 2.13.7, unittest

---

### Task 1: 模型配置与接口配置数据层

**Files:**
- Modify: `app/models/db.py`
- Create: `app/models/model_engine.py`
- Create: `app/models/api_service.py`
- Test: `tests/test_model_engine_repository.py`
- Test: `tests/test_api_service_repository.py`

- [ ] 写默认模型自动写入、默认模型唯一、模型分页搜索、接口分页搜索的失败测试
- [ ] 运行两组仓储测试并确认失败
- [ ] 实现模型表、接口表与仓储最小代码
- [ ] 重跑仓储测试直到通过

### Task 2: 模型引擎控制器与模型测试

**Files:**
- Create: `app/controllers/model_engine.py`
- Modify: `app.py`
- Test: `tests/test_model_engine_flow.py`

- [ ] 写模型引擎页面渲染、模型新增、默认切换、测试入口的失败测试
- [ ] 运行 `tests/test_model_engine_flow.py` 并确认失败
- [ ] 实现模型引擎控制器与路由
- [ ] 重跑模型引擎流程测试直到通过

### Task 3: 接口管理控制器与接口测试

**Files:**
- Create: `app/controllers/api_service.py`
- Modify: `app.py`
- Test: `tests/test_api_service_flow.py`

- [ ] 写接口管理页、接口新增、删除、联通性测试入口的失败测试
- [ ] 运行 `tests/test_api_service_flow.py` 并确认失败
- [ ] 实现接口管理控制器与路由
- [ ] 重跑接口管理流程测试直到通过

### Task 4: 后台导航与页面实现

**Files:**
- Modify: `app/templates/_sidebar.html`
- Modify: `app/templates/_topbar.html`
- Create: `app/templates/model_engines.html`
- Create: `app/templates/api_services.html`
- Modify: `app/static/css/style.css`
- Modify: `app/static/js/app.js`

- [ ] 将“模型引擎”和“接口管理”接入左侧导航
- [ ] 完成模型引擎卡片页与测试区
- [ ] 完成接口管理配置页与测试区
- [ ] 统一按钮、提示、工具条与 Layui 风格

### Task 5: 整体验证

**Files:**
- Test: `tests/test_model_engine_repository.py`
- Test: `tests/test_api_service_repository.py`
- Test: `tests/test_model_engine_flow.py`
- Test: `tests/test_api_service_flow.py`
- Test: `tests/test_device_flow.py`
- Test: `tests/test_auth_flow.py`

- [ ] 运行全量测试
- [ ] 修复回归并重跑
- [ ] 做一次模板渲染验证
