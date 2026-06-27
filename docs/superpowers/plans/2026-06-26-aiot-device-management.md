# AIOT Device Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为后台系统新增左侧导航与 AIOT 设备管理页面，完成设备与传感器的新增、编辑、删除、查询与分页。

**Architecture:** 保持现有 Tornado MVC 结构，新增设备主表与传感器子表，使用独立仓储模块封装设备数据操作，再通过独立控制器和模板页面承接左侧导航与设备卡片视图。用户列表继续作为一级页面，设备管理作为第二个一级页面。

**Tech Stack:** Python, Tornado, SQLite, Tornado Template, Layui 2.13.7, unittest

---

### Task 1: 设备数据模型与仓储

**Files:**
- Modify: `app/models/db.py`
- Create: `app/models/device.py`
- Test: `tests/test_device_repository.py`

- [ ] 写设备主表、传感器子表、`box_id` 唯一约束、分页搜索与级联删除的失败测试
- [ ] 运行 `tests/test_device_repository.py` 并确认失败
- [ ] 实现数据库结构与设备仓储最小代码
- [ ] 重跑 `tests/test_device_repository.py` 直到通过

### Task 2: 设备控制器与路由

**Files:**
- Create: `app/controllers/device.py`
- Modify: `app.py`
- Test: `tests/test_device_flow.py`

- [ ] 写设备管理页、创建设备、编辑设备、删除设备的失败测试
- [ ] 运行 `tests/test_device_flow.py` 并确认失败
- [ ] 实现设备控制器与路由
- [ ] 重跑 `tests/test_device_flow.py` 直到通过

### Task 3: 左侧导航与设备管理界面

**Files:**
- Modify: `app/templates/index.html`
- Create: `app/templates/devices.html`
- Modify: `app/static/css/style.css`
- Modify: `app/static/js/app.js`

- [ ] 调整左侧导航为“用户列表 / 设备管理”两级入口
- [ ] 完成设备管理页两列卡片布局与 6 条分页
- [ ] 完成动态传感器配置行交互
- [ ] 确保界面风格与现有 Layui 后台保持一致

### Task 4: 整体验证

**Files:**
- Test: `tests/test_user_repository.py`
- Test: `tests/test_auth_flow.py`
- Test: `tests/test_device_repository.py`
- Test: `tests/test_device_flow.py`

- [ ] 运行所有测试
- [ ] 修复回归问题并重跑
- [ ] 做一次最小模板渲染或页面访问验证
