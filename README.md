# TestFusion 智能测试管理平台

<div align="center">

**基于 AI 驱动的全栈测试管理平台**

*从精准检索到智能生成，重塑测试用例管理体验*

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.2-green.svg)](https://www.djangoproject.com/)
[![Vue](https://img.shields.io/badge/Vue-3.3-brightgreen.svg)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-GPL_v3-blue.svg)](LICENSE)

</div>

## 📖 项目简介

TestFusion 是一个功能强大的智能测试管理平台，集成了 **AI 需求分析**、**RAG 知识库**、**测试用例管理**、**API 测试**、**UI 自动化测试**、**APP 自动化测试** 等多个模块，旨在提升测试效率和质量。平台采用 Django + Vue3 技术栈，提供现代化的用户界面和丰富的功能特性。

---

## 🎯 核心功能

### 🤖 AI 智能化能力

> **解决痛点**：通用大模型不懂业务规范，生成内容"假大空"，历史用例无法复用，且大模型生成响应格式不稳定。

- **AI 需求分析**: 自动解析需求文档（PDF/Word/TXT），智能提取业务需求
- **RAG 增强生成**: 基于 ChromaDB 的语义粗筛，融合**本地二阶段余弦重排 (Reranker)**机制，大幅提升离线检索精度与抗噪能力
- **大模型用例自愈提取 (Self-Healing)**: 内置用例自愈解析与落库校验机制，自动校正乱序及Markdown格式瑕疵，确保 100% 优雅落库
- **多层次 Embedding**: 基于本地 sentence-transformers 多语言模型，首次使用自动下载，完全离线运行
- **智能对抗评审**: 独立评审 Agent 对生成用例进行覆盖率、逻辑自洽性、规范性质检
- **多模型支持**: 支持 DeepSeek、通义千问、硅基流动等多种 AI 模型

### 📋 测试用例管理
- 完整的用例生命周期管理：创建、编辑、版本控制、归档
- 支持步骤化用例设计，包含前置条件、操作步骤、预期结果
- 附件和团队协作评论

### 🔍 测试用例评审
- 评审流程管理：支持多人评审、评审模板、检查清单
- 状态跟踪：待评审、评审中、已通过、已拒绝
- 多层级反馈：整体意见、用例意见、步骤意见

### 🌐 API 测试
- 支持 HTTP/WebSocket 协议，树形结构组织 API
- 环境变量管理，支持变量替换
- 测试套件批量执行，支持断言和顺序配置
- 定时任务和 Allure 报告生成

### 🖥️ UI 自动化测试（Web）
- **高性能引擎封装**: 基于微软 Playwright 框架的高稳定性与高性能 Web UI 自动化测试驱动封装
- 元素库管理，支持多种定位策略
- 页面对象模式（POM），提高脚本可维护性
- 可视化脚本编辑器，支持步骤录制和回放
- 支持多浏览器：Chrome/Firefox/Edge

### 📱 APP 自动化测试（Android）
- **uiautomator2 + ADB**: 基于 ADB 与 uiautomator2 的 Android APP 自动化测试
- 设备管理：支持本地模拟器和远程设备，设备资源池管理
- UI Flow 编排：JSON 格式，支持多种动作类型与 OpenCV 模板匹配定位
- Celery 异步执行 + pytest + Allure 报告

### 🏭 数据工厂
- 51 个实用工具：字符/编码/随机/加密/测试数据/JSON/Crontab
- 标签系统，支持多标签管理和数据引用
- 在 API 测试和 UI 测试中直接引用数据工厂数据

---

## 🏗️ 技术架构

### 后端技术栈
- **框架**: Django 4.2 + Django REST Framework
- **数据库**: MySQL 8.0+ (PyMySQL)
- **API 文档**: drf-spectacular (Swagger/ReDoc)
- **安全认证**: JWT 双 Token 机制 (Access + Refresh)
- **AI 集成**:
  - DeepSeek Chat 模型：测试用例编写 + 评审 + 改进（15 分钟超时，自动续写）
  - 本地 sentence-transformers：离线 Embedding 模型（多语言），API 不可用时自动降级
  - ChromaDB：轻量级本地向量数据库，无需独立服务
- **自动化测试**: Selenium, Playwright, uiautomator2, Allure
- **异步任务**: Celery, httpx

### 前端技术栈
- **框架**: Vue 3.3 + Composition API
- **构建工具**: Vite 4.4
- **UI 组件**: Element Plus 2.3
- **状态管理**: Pinia 2.1
- **其他**: ECharts, Monaco Editor, Axios

---

## 📁 项目结构

```
testfusion/
├── apps/                           # Django 应用模块
│   ├── users/                      # 用户管理 (JWT 认证)
│   ├── projects/                   # 项目管理
│   ├── testcases/                  # 测试用例管理
│   ├── testsuites/                 # 测试套件
│   ├── executions/                 # 测试执行管理
│   ├── reports/                    # 测试报告
│   ├── reviews/                    # 用例评审
│   ├── versions/                   # 版本管理
│   ├── requirement_analysis/       # AI 需求分析 + RAG + 测试生成
│   │   ├── models.py               # ORM 模型 + AIModelService（生成/评审/改进）
│   │   ├── rag_engine.py           # ChromaDB 向量检索引擎
│   │   ├── views.py                # DRF ViewSets + SSE 流式输出
│   │   └── serializers.py          # DRF 序列化器
│   ├── api_testing/                # API 测试 (HTTP/WebSocket)
│   ├── ui_automation/              # UI 自动化 (Selenium/Playwright/AI)
│   ├── app_automation/             # APP 自动化 (uiautomator2/Celery)
│   ├── data_factory/               # 51 种数据工具
│   ├── assistant/                  # Dify 智能助手
│   ├── core/                       # 定时调度/通知/驱动管理
│   └── analytics/                  # 数据统计
├── backend/                        # Django 项目配置
│   ├── settings.py                 # 项目设置
│   └── urls.py                     # URL 路由
├── frontend/                       # Vue3 前端
│   ├── src/views/                  # 页面视图（按模块组织）
│   ├── src/api/                    # API 接口
│   ├── src/stores/                 # Pinia 状态管理
│   └── src/router/                 # 路由配置
├── apps/data/vector_db/            # ChromaDB 向量数据（持久化）
├── logs/                           # 日志
├── docs/                           # 文档
├── .env                            # 环境变量配置
├── manage.py                       # Django 管理脚本
└── requirements.txt                # Python 依赖
```

---

## 🚀 快速开始

### 环境要求
- **Python**: 3.12+（推荐 3.12，其他版本可能存在兼容性问题）
- **Node.js**: 18+
- **MySQL**: 8.0+
- **Redis**: 5.0+（关键依赖：用于图形验证码、Celery 异步队列及 WebSocket 实时推送）
- **Java**: 17+（可选，用于 Allure 报告）

### 后端部署

```bash
# 1. 克隆项目
git clone <repository-url>
cd testhub_platform

# 2. 创建虚拟环境
python -m venv venv
# Windows: venv\Scripts\activate
# Linux: source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
# 编辑 .env 文件，配置数据库连接信息

# 5. 创建数据库
mysql -u root -p -e "CREATE DATABASE testhub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 6. 执行迁移
python manage.py migrate

# 7. 创建超级用户
python manage.py createsuperuser

# 8. 初始化定位策略（UI 自动化需要）
python manage.py init_locator_strategies

# 9. 一键初始化黄金演示数据 (强烈推荐对外展示演示)
# 自动重置 admin 密码为 admin123456 并注入精美闭环的电商项目、执行记录与评审大盘数据
python manage.py shell -c "exec(open('tools/seed_demo_data.py', encoding='utf-8').read())"

# 10. 启动后端服务
python manage.py runserver
```

### 🖥️ 本地离线 Mock 演示与 E2E 验证 (适合演示与离线部署)

平台内置了 OpenAI 兼容的本地 Mock 大模型服务与完整的 E2E 自动化集成检验链：

```bash
# 1. 启动本地 Mock 大模型服务 (端口 9000)
# 支持大模型用例设计、修改、评审三大意图的智能分流与高拟真 Markdown 兜底返回
python tools/mock_openai_server.py --port 9000

# 2. 运行 E2E 全链路集成测试脚本
# 一键自动校验：RAG 向量粗筛 -> 大模型生成 -> 专家对抗评审 -> 格式自愈与测试用例落库物理闭环
python tools/run_mock_e2e.py
```

### 数据工厂模块

```bash
python manage.py makemigrations data_factory
python manage.py migrate data_factory
```

### 前端部署

```bash
cd frontend
npm install
npm run dev       # 开发模式 → http://localhost:3000
# npm run build   # 生产构建
```

### Docker 部署

```bash
cd frontend
./deploy.sh start   # 生产模式 (端口 80)
# ./deploy.sh dev   # 开发模式 (端口 3000)
```

### 访问地址
- **前端**: http://localhost:3000
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/api/docs/
- **Admin 后台**: http://localhost:8000/admin/

---

## 🔧 配置说明

### AI 模型配置

系统通过 `AIModelConfig` 统一管理 AI 模型，支持按角色配置：

| 角色 | 用途 | 推荐模型 |
|------|------|---------|
| `writer` | 测试用例编写 | deepseek-chat |
| `reviewer` | 测试用例评审 | deepseek-chat |
| `embedding` | RAG 向量化 | 本地 sentence-transformers（离线运行，无需 API Key）|
| `browser_use_text` | AI 浏览器自动化 | 视具体模型而定 |

> 💡 **RAG Embedding 说明**：系统直接使用本地 `paraphrase-multilingual-MiniLM-L12-v2` 模型进行向量化，完全离线运行，无需配置 API Key。如需预热模型可提前执行：
> ```bash
> python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
> ```

### JWT 安全配置

采用双 Token 机制：
- **Access Token**: 30 分钟有效
- **Refresh Token**: 7 天有效，支持自动轮换
- **Token 黑名单**: 登出时自动加入黑名单，防止重放攻击

### 环境变量 (.env)

```
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=*
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
DB_HOST=localhost
DB_NAME=testhub
DB_USER=root
DB_PASSWORD=your-password
DB_PORT=3306
```

### 运行时常见问题排查

#### 1. 验证码接口返回 500 (Redis 拒绝连接)
*   **现象**：访问 `/api/auth/captcha/` 时出现 `redis.exceptions.ConnectionError: Error 10061 connecting to 127.0.0.1:6379`。
*   **原因**：本地 Redis 服务未启动或配置的 Redis 地址不可达。本平台中的图形验证码、Celery 异步队列以及 WebSocket（基于 channels-redis）均强依赖 Redis。
*   **解决**：请确保已启动 Redis 服务（默认端口 6379）。

#### 2. 测试用例生成任务失败 (Unexpected UTF-8 BOM)
*   **现象**：在通过上传的需求文档进行用例生成时，如果上传的文档是以带有 BOM 签名的 UTF-8 编码保存的，解析时后端可能会抛出 UTF-8 BOM 解码异常。
*   **解决**：确保上传的 TXT/Markdown 需求文档在保存时使用“无 BOM 的 UTF-8”编码；或在解析文档时进行容错处理。

---

## 🧠 RAG 检索与增强生成

TestFusion 的 RAG 引擎（`rag_engine.py`）基于 ChromaDB 与本地重排器构建，提供高精度的语义级别测试数据和技术规范检索增强：

### 1) 检索流程（非阻塞漏斗式与本地二阶段重排）
为了避免同步调用大模型过滤导致的 HTTP 接口卡顿，RAG 模块已被彻底移入**异步后台线程**中执行，并引入了二阶段重排机制：

```
用户提交需求 (0.17s 瞬间响应)
    │
    ▼ (进入异步工作线程)
1. 向量粗筛：ChromaDB 语义检索 Top-K 文档切片 (历史用例 + 测试规范)
    │
    ▼
2. 余弦重排 (Rerank)：基于本地句向量模型计算余弦相似度，进行二阶段精细化重排序与低相关噪声滤除
    │
    ▼
3. LLM 细筛与拼装：后台调用大模型对重排后内容进行精准提炼去噪，将最核心上下文拼入用例生成 Prompt
```

### 2) 智能语义分块 (TextSplitter)
为了避免大文件切片时将连贯的 Markdown 表格、章节标题和核心条款生硬切断，系统采用**段落/表格自适应切片算法**：
*   **段落优先**：以双换行符（`\n\n`）对规范进行整块提取，尽可能保留列表和表格的物理完整性。
*   **句级降级**：只有单段字符超长时，才触发按句子标点（`。！？\n`）断开，且在切片间保留 `chunk_overlap`（重叠区）语义衔接。

### 3) Embedding 方案
直接使用本地 sentence-transformers 多语言模型（`paraphrase-multilingual-MiniLM-L12-v2`）进行向量化，无需外部 API 调用，完全离线运行，首次使用自动下载。若无 GPU 则自动使用 CPU 推理。

### 知识库管理

- **company_knowledge**: 存储技术规范、需求文档切片
- **history_cases**: 存储历史测试用例，支持"资产回流"

---

## 📊 数据库

项目使用 MySQL 8.0+。主要数据表包括：

- **用户**: `users_user`, `user_profiles`
- **项目**: `projects`, `project_members`
- **测试**: `testcases`, `testsuites`, `test_plans`, `test_runs`
- **AI**: `ai_model_config`, `prompt_config`, `generation_config`
- **RAG**: `rag_documents`, `testcase_generation_task`
- **自动化**: `ui_projects`, `api_projects`, `app_automation` 等

---

## 📝 许可证

本项目采用 GPL v3 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 💖 鸣谢与参考

本项目的设计与开发借鉴了以下优秀的开源项目，特此鸣谢：
- [testhub_platform](https://github.com/chenjigang4167/testhub_platform)
- [ByteDance-Auto_prd_test_agent](https://github.com/zxLeva/ByteDance--Auto_prd_test_agent)
