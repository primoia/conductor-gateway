# Conductor Gateway

Project: conductor-gateway

## Contexto
Gateway autônomo de alta performance que atua como ponte entre aplicações web e o sistema de execução de agentes do Conductor. Fornece API REST com streaming SSE (Server-Sent Events), integração Model Context Protocol (MCP) com 13+ ferramentas CLI, gerenciamento completo de screenplays/personas/conversas, sistema de monitoramento automatizado (Councilor) e WebSocket para atualizações em tempo real.

## Stack
- **Language**: Python 3.11+
- **Framework**: FastAPI 0.116+ (async API) + Uvicorn 0.36
- **Database**: MongoDB 4.15+ com Motor 3.7 (async driver)
- **MCP**: Model Context Protocol 1.14+ (mcp-use 1.3+)
- **AI Providers**: OpenAI (default), Anthropic, Groq, Fireworks AI, Ollama, Gemini (langchain integrations)
- **LangChain**: langchain-core 0.3+, langchain-openai, langchain-anthropic, langchain-community
- **Task Scheduler**: APScheduler 3.10 (Councilor automated runs)
- **WebSocket**: FastAPI WebSocket support para real-time updates
- **HTTP Clients**: httpx 0.28 (async), requests, aiohttp, Playwright, Selenium
- **Package Manager**: Poetry (dependency management + lock files)
- **Configuration**: PyYAML 6.0 (config files) + environment overrides
- **Logging**: python-json-logger (structured logging)
- **Rate Limiting**: slowapi 0.1+ (endpoint throttling)
- **Testing**: Pytest 7.4+, pytest-asyncio, pytest-cov (52+ test cases)
- **Quality**: Ruff (formatter + linter), MyPy (type checking), Bandit (security)
- **CI/CD**: GitHub Actions (test, lint, security, docker build, releases)
- **Container**: Docker multi-stage builds com health checks

## Capacidades Principais
- **Real-time Agent Execution**: SSE streaming com job queues, suporta execução non-blocking e atualizações incrementais
- **Task Queue Architecture**: Sistema avançado de filas para execução concorrente de agentes com status tracking
- **Multiple Payload Formats**: Aceita `textEntries` (estrutura complexa), `input` (simples), `command` (direto)
- **MCP Server Integration**: 13+ ferramentas CLI do Conductor (list agents, execute, validate, backup/restore, templates, migration)
- **Screenplay Management**: CRUD completo com working directory support, validação markdown, detecção de duplicatas, metadata, force save
- **Persona System**: Gerenciamento de personas com versionamento completo, CRUD, version history tracking
- **Conversation Management**: Sistema avançado de conversas com title/context editing, soft delete com propagação, message threading
- **Councilor Automation**: Sistema de monitoramento automatizado com scheduler backend, execução periódica de agentes, WebSocket updates, statistics tracking
- **Portfolio Chat**: Roteamento de chat de portfolio com rate limiting
- **Gamification Events**: Endpoint para dados históricos de gamificação
- **WebSocket Support**: Comunicação bidirecional em tempo real para updates de execução e Councilor status
- **Multi-Provider AI**: Suporte flexível para OpenAI, Anthropic, Groq, Fireworks, Ollama, Gemini
- **Conductor CLI Tools**: Integração completa com CLI (stateless, contextual, interactive modes)
- **Background Processing**: Execução não-bloqueante de agentes com event streaming
- **Health Checks**: Endpoints de health para monitoring e liveness probes
- **OpenAPI Docs**: Documentação automática em /docs (Swagger) e /redoc
