# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TestFusion is an AI-driven test management platform built with Django 4.2 (backend) + Vue 3 (frontend). It provides test case management, API testing, UI automation (Selenium/Playwright + AI browser-use), app automation (uiautomator2/Android), AI-powered requirement analysis with RAG (ChromaDB), and test case generation.

## Backend Commands

```bash
# Start dev server (bind 0.0.0.0:8000 for LAN access)
python manage.py runserver
python manage.py runserver 0.0.0.0:8000

# After making model changes
python manage.py makemigrations <app_name>
python manage.py migrate

# Migration dependency order (apps with migrations):
# auth -> users -> projects -> requirement_analysis -> (other apps)
# Always run `python manage.py migrate` after pulling changes

# Superuser
python manage.py createsuperuser

# Django shell
python manage.py shell

# Reset password via shell
python -c "import os,django; os.environ['DJANGO_SETTINGS_MODULE']='backend.settings'; django.setup(); from apps.users.models import User; u=User.objects.get(username='admin'); u.set_password('newpass'); u.save()"

# Run tests
python manage.py test apps.assistant
python manage.py test apps.data_factory
python manage.py test apps.app_automation.tests

# Initialization commands
python manage.py init_locator_strategies   # UI test locator strategies
python manage.py load_component_pack       # App automation components
python manage.py run_all_scheduled_tasks   # Unified task scheduler
```

## Frontend Commands

```bash
cd frontend
npm install
npm run dev      # Dev server at localhost:3000
npm run build    # Production build
npm run lint     # Lint check

# Docker deployment
./deploy.sh start   # Production (port 80)
./deploy.sh dev     # Dev mode (port 3000)
```

## Environment

`.env` file at project root (backend root, not inside `backend/`):

```
SECRET_KEY=django-insecure-dev-key-xxx
DEBUG=True
ALLOWED_HOSTS=*
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
DB_HOST=localhost
DB_NAME=testhub
DB_USER=root
DB_PASSWORD=xxx
DB_PORT=3306
```

## Architecture

### Backend (`apps/`)

All Django apps live under `apps/`. The settings module is `backend.settings`.

**Key modules:**

- **users**: Custom User model (AbstractUser + UserProfile with theme/language/timezone/notifications). Custom login view (`LoginSerializer` accepts username+password, returns JWT `access`/`refresh` tokens)
- **projects**: Project + ProjectMember with role-based access (owner/admin/developer/tester/viewer)
- **testcases**: Manual test case management (steps, attachments, comments)
- **requirement_analysis**: AI analysis of PDF/Word/TXT docs, RAG-enhanced test case generation
  - `models.py` contains both ORM models AND `AIModelService` class (static async methods: generate/review/revise test cases, streaming via `call_openai_compatible_api_stream`)
  - `rag_engine.py` — ChromaDB-based RAG engine with local `sentence-transformers` model (fully offline)
  - `views.py` — DRF ViewSets including `TestCaseGenerationTaskViewSet` (SSE streaming, review workflow, batch adopt/discard)
- **api_testing**: HTTP/WebSocket request management, environments, test suites, scheduled tasks, Allure reports
- **ui_automation**: Selenium + Playwright + AI browser-use mode (`ai_agent.py`, `ai_models.py`)
- **app_automation**: uiautomator2-based Android automation with device management, UI Flow engine, Celery async execution
- **data_factory**: 51 utility tools (string/encoding/random/encryption/JSON/crontab), tag system, data reference
- **core**: Cross-module management commands (scheduler, locator strategies, webdriver download), unified notification config
- **assistant**: Dify AI chatbot integration
- **executions**: Test plan management and execution tracking
- **reviews**: Review workflow with templates and assignments

### Key Patterns

- **Views + Serializers**: DRF ModelViewSets with `@action` decorators for custom endpoints. Serializers use `SerializerMethodField` for display fields and auto-set `created_by`/`uploaded_by` in `create()`. The default approach for anonymous users: use first superuser
- **AI integration**: Provider-agnostic — `AIModelService.call_openai_compatible_api()` handles all models
  - URL auto-completion appends `/v1/chat/completions` if missing
  - 15-min timeout (read=900s), automatic continuation for truncated responses (finish_reason='length')
- **Streaming**: SSE endpoints (`stream_progress_sse`) poll DB every 0.5s, `PassThroughRenderer` bypasses DRF rendering
- **RAG (ChromaDB)**: `RAGEngine` in `rag_engine.py` — persistent ChromaDB with `company_knowledge` and `history_cases` collections
  - Uses local `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`) for embedding, fully offline
- **Pagination**: Custom pagination classes in each app's views.py (e.g., `TestCaseGenerationTaskPagination`)

### API Structure

All under `/api/`. Key prefixes:
- `/api/requirement-analysis/` — documents, analyses, requirements, test-cases, tasks, ai-models, prompts, testcase-generation, rag-documents
- `/api/auth/`, `/api/users/`, `/api/projects/`
- `/api/testcases/`, `/api/testsuites/`, `/api/executions/`, `/api/reports/`, `/api/reviews/`
- `/api/assistant/`, `/api/data-factory/`, `/api/core/`
- `/api/api-testing/`, `/api/ui-automation/`, `/api/app-automation/`
- API docs at `/api/docs/` (Swagger), `/api/redoc/` (ReDoc)

### Frontend Structure

Vue 3 + Element Plus + Pinia. Pages mirror backend apps:
- `src/views/requirement-analysis/`, `src/views/api-testing/`, `src/views/ui-automation/`, etc.
- `src/stores/` — Pinia stores per module
- `src/api/` — Axios API modules
- `src/utils/` — token refresh interceptor, etc.

## AI Model Configuration

Configured in `AIModelConfig` (`/api/requirement-analysis/ai-models/`):
- Multi-provider via unified OpenAI-compatible API
- `base_url` auto-completed to append `/v1/chat/completions` if missing
- **Roles**: `writer`, `reviewer`, `browser_use_text`, `embedding`
- Each role can have only one active config (enforced in app logic, not DB constraint)
- `api_key` is write-only in serializer, masked via `get_api_key_masked()`

### Known Issues & Pitfalls

1. **RAG embedding uses local model only** — The RAG engine uses `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`) directly, no external API needed. An `AIModelConfig` with `role='embedding'` is no longer required.
2. **RAGDocumentViewSet parsers** — Uses `[MultiPartParser, FormParser, JSONParser]`. For create (file upload) use form-data. For search use JSON.
3. **Embedding model first-load** — `sentence-transformers` downloads from HuggingFace on first use (~30s). Pre-cache for offline environments: `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"`
4. **Migration order** — Apps with migrations must be migrated in order: `auth → users → projects → requirement_analysis → ...`
5. **Default admin password** — The admin user's password is not standardized. Use the shell to reset if unknown.

## RAG API Flow

```
POST /api/requirement-analysis/rag-documents/         # Upload document (form-data: title, file, raw_text)
POST /api/requirement-analysis/rag-documents/{id}/process/  # Process: chunk + embed into ChromaDB
POST /api/requirement-analysis/rag-documents/search/   # Search (json: {query, top_k})
POST /api/requirement-analysis/testcase-generation/    # Create generation task (uses RAG context if enable_rag=true)
```

## Key Dependencies

Backend: Django 4.2, DRF 3.14, simpleui, drf-spectacular, django-filter, simplejwt, httpx, celery, chromadb, sentence-transformers, browser-use, langchain-openai, selenium, playwright, uiautomator2, pytest, allure-pytest

Frontend: Vue 3.3, Element Plus 2.3, Pinia, Vue Router 4, Axios, ECharts, Monaco Editor
