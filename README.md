# Conductor Gateway

[![Tests](https://github.com/primoia/conductor-gateway/actions/workflows/test.yml/badge.svg)](https://github.com/primoia/conductor-gateway/actions/workflows/test.yml)
[![Code Quality](https://github.com/primoia/conductor-gateway/actions/workflows/lint.yml/badge.svg)](https://github.com/primoia/conductor-gateway/actions/workflows/lint.yml)
[![Docker Build](https://github.com/primoia/conductor-gateway/actions/workflows/docker.yml/badge.svg)](https://github.com/primoia/conductor-gateway/actions/workflows/docker.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**A high-performance, autonomous gateway service that bridges web applications with the Conductor agent execution system through Server-Sent Events (SSE) streaming and Model Context Protocol (MCP) integration.**

## 🚀 Features

### 🔄 **Real-time Agent Execution**
- **SSE Streaming**: Live event streaming from agent execution with job queues
- **Task Queue Architecture**: Advanced queue-based agent execution with concurrent processing
- **Multiple Payload Formats**: Support for `textEntries`, `input`, and `command` formats
- **Background Processing**: Non-blocking agent execution with real-time updates
- **WebSocket Support**: Real-time bidirectional communication for live updates

### 🛠 **MCP Server Integration**
- **13+ Advanced Tools**: Complete Conductor CLI integration including:
  - Agent listing, info, and validation
  - Stateless and contextual execution modes
  - Interactive sessions with conversation history
  - System management (backup, restore, migration)
  - Template installation and configuration

### 📝 **Content Management**
- **Screenplay Management**: Complete CRUD operations for screenplay handling
  - Working directory support for custom execution contexts
  - Markdown validation and duplicate detection
  - Metadata management and force save capabilities
- **Persona System**: Comprehensive persona management with versioning
  - CRUD operations for persona configurations
  - Version control and history tracking
- **Conversation Management**: Advanced conversation and message handling
  - Title and context editing
  - Soft delete with propagation to history messages
  - Message threading and organization

### 🤖 **Automation & Monitoring**
- **Councilor System**: Automated agent monitoring and execution
  - Backend scheduler for periodic agent runs
  - Real-time WebSocket updates for councilor status
  - Agent statistics tracking and reporting
- **Portfolio Management**: Portfolio chat routing with rate limiting
- **Gamification**: Task events endpoint for historical gamification data

### 🏗 **Production Architecture**
- **FastAPI Framework**: High-performance async API with automatic OpenAPI docs
- **MongoDB Integration**: Robust document storage with Motor async driver
- **Poetry Dependency Management**: Modern Python packaging with lock files
- **Docker Support**: Multi-stage builds with health checks
- **Configuration Management**: YAML-based config with environment overrides
- **Multi-Provider AI Support**: OpenAI, Anthropic, Groq, Fireworks AI, Ollama, and Gemini

### 🧪 **Quality Assurance**
- **Comprehensive Testing**: 52+ test cases covering unit, integration, and API testing
- **GitHub Actions CI/CD**: Automated testing, linting, security checks, and releases
- **Code Quality Tools**: Ruff formatting, MyPy typing, Bandit security scanning
- **Pre-commit Hooks**: Automated quality checks on every commit

## 📦 Installation

### Prerequisites
- **Python 3.11+**
- **Poetry** (for dependency management)
- **Docker** (optional, for containerized deployment)

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/primoia/conductor-gateway.git
cd conductor-gateway

# Install Poetry (if not already installed)
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Copy configuration template
cp config.yaml.example config.yaml

# Start the server
poetry run python src/main.py
```

### Docker Deployment

```bash
# Build the image
docker build -t conductor-gateway .

# Run with docker-compose
docker-compose up -d

# Or run standalone
docker run -p 5006:5006 -p 8006:8006 conductor-gateway
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `HOST` | Server host address | `0.0.0.0` |
| `PORT` | API server port | `5006` |
| `MCP_PORT` | MCP server port | `8006` |
| `CONDUCTOR_PROJECT_PATH` | Path to Conductor project | `/path/to/conductor` |
| `CONDUCTOR_TIMEOUT` | Command execution timeout | `600` (10 minutes) |
| `MONGODB_URI` | MongoDB connection string | `mongodb://localhost:27017` |
| `MONGODB_DB_NAME` | MongoDB database name | `conductor_gateway` |
| `OPENAI_API_KEY` | OpenAI API key for LLM | Required for agent execution |
| `AI_PROVIDER` | AI provider selection | `openai` (options: openai, anthropic, groq, fireworks, ollama, gemini) |

### Configuration File

Create `config.yaml` based on `config.yaml.example`:

```yaml
server:
  host: "0.0.0.0"
  port: 5006
  mcp_port: 8006

conductor:
  project_path: "/path/to/conductor"
  scripts_path: "scripts"
  timeout: 300
```

## 🔌 API Usage

### API Endpoints Overview

The gateway provides multiple routers for different functionalities:

- `/api/agents` - Agent instance management and execution
- `/api/screenplays` - Screenplay CRUD operations and validation
- `/api/personas` - Persona management
- `/api/persona-versions` - Persona version control
- `/api/councilor` - Automated monitoring and scheduling
- `/api/portfolio` - Portfolio chat management
- `/api/conversations` - Conversation and message management
- `/api/v1/tasks/events` - Gamification task events

### Health Check

```bash
curl http://localhost:5006/health
```

Response:
```json
{
  "status": "healthy",
  "service": "conductor_gateway",
  "version": "3.1.0",
  "endpoints": {
    "api": "http://localhost:5006/api/v1",
    "mcp": "http://localhost:8006",
    "health": "http://localhost:5006/health"
  }
}
```

### Synchronous Execution

```bash
curl -X POST http://localhost:5006/execute \
  -H "Content-Type: application/json" \
  -d '{
    "textEntries": [
      {"content": "List available agents", "type": "text"}
    ]
  }'
```

### Streaming Execution (SSE)

**Step 1**: Start execution
```bash
curl -X POST http://localhost:5006/api/v1/stream-execute \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Execute agent with real-time updates"
  }'
```

Response:
```json
{
  "job_id": "job_123e4567-e89b-12d3-a456-426614174000",
  "status": "started",
  "stream_url": "/api/v1/stream/job_123e4567-e89b-12d3-a456-426614174000"
}
```

**Step 2**: Connect to SSE stream
```bash
curl -N http://localhost:5006/api/v1/stream/job_123e4567-e89b-12d3-a456-426614174000
```

SSE Events:
```
data: {"event": "job_started", "data": {"message": "Inicializando execução..."}, "timestamp": 1234567890, "job_id": "job_123..."}

data: {"event": "status_update", "data": {"message": "Conectando ao conductor..."}, "timestamp": 1234567891, "job_id": "job_123..."}

data: {"event": "result", "data": {"result": "Agent response", "message": "Comando executado com sucesso"}, "timestamp": 1234567892, "job_id": "job_123..."}
```

### Multiple Payload Formats

The API supports various payload formats for flexibility:

```bash
# Format 1: textEntries (complex structure)
{
  "textEntries": [
    {"content": "Your command here", "type": "text"}
  ],
  "metadata": {"source": "web"}
}

# Format 2: input (simple)
{
  "input": "Your command here"
}

# Format 3: command (direct)
{
  "command": "Your command here"
}
```

## 🛠 Development

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run specific test categories
poetry run pytest -m unit          # Unit tests only
poetry run pytest -m integration   # Integration tests only
poetry run pytest -m api          # API tests only

# Run with coverage
poetry run pytest --cov=src --cov-report=html

# Quick validation script
python run_tests.py
```

### Code Quality

```bash
# Format code
poetry run ruff format src/ tests/

# Lint code
poetry run ruff check src/ tests/

# Type checking
poetry run mypy src/

# Security scanning
poetry run bandit -r src/

# Install pre-commit hooks
poetry run pre-commit install
```

### Project Structure

```
conductor-gateway/
├── src/                        # Source code
│   ├── api/                   # FastAPI application
│   │   ├── routers/          # API route handlers
│   │   │   ├── agents.py    # Agent instance management
│   │   │   ├── screenplays.py # Screenplay operations
│   │   │   ├── persona.py   # Persona management
│   │   │   ├── persona_version.py # Version control
│   │   │   ├── councilor.py # Automated monitoring
│   │   │   ├── portfolio.py # Portfolio chat
│   │   │   └── conversations.py # Conversation management
│   │   ├── app.py            # Main application
│   │   ├── models.py         # Pydantic models
│   │   └── websocket.py      # WebSocket handlers
│   ├── clients/              # External service clients
│   │   └── conductor_client.py # Conductor API client
│   ├── config/               # Configuration management
│   ├── core/                 # Core functionality
│   │   └── database.py       # MongoDB connection
│   ├── models/               # Data models
│   │   ├── screenplay.py    # Screenplay models
│   │   ├── persona.py       # Persona models
│   │   ├── persona_version.py # Version models
│   │   └── councilor.py     # Councilor models
│   ├── services/             # Business logic
│   │   ├── screenplay_service.py
│   │   ├── councilor_service.py
│   │   └── councilor_scheduler.py
│   ├── server/               # MCP server implementation
│   ├── tools/                # Conductor CLI tools
│   └── utils/                # Utility functions
├── tests/                    # Test suite
│   ├── unit/                 # Unit tests
│   ├── integration/          # Integration tests
│   └── conftest.py          # Test configuration
├── .github/                  # GitHub Actions workflows
├── docs/                     # Documentation
├── pyproject.toml           # Project configuration
├── Dockerfile               # Container definition
└── docker-compose.yml      # Development environment
```

## 🔧 MCP Tools Available

The gateway provides 13+ MCP tools for comprehensive Conductor integration:

### Basic Commands
- `list_available_agents` - List all available agents with capabilities
- `get_agent_info` - Get detailed agent information
- `validate_conductor_system` - Validate system configuration

### Agent Execution
- `execute_agent_stateless` - Fast execution without history
- `execute_agent_contextual` - Execution with conversation context
- `start_interactive_session` - Interactive agent sessions

### System Management
- `install_agent_templates` - Install agent templates
- `backup_agents` / `restore_agents` - Agent backup/restore
- `migrate_storage` - Storage migration (filesystem ↔ MongoDB)

### Configuration
- `set_environment` - Set environment context
- `get_system_config` - Get current configuration
- `clear_agent_history` - Clear conversation history

## 📚 Documentation

- [Architecture Overview](docs/architecture/01_gateway_overview.md)
- [Local Development Guide](docs/guides/01_local_setup.md)
- [API Documentation](docs/guides/02_api_usage.md)
- [Contributing Guidelines](CONTRIBUTING.md)

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details on:

- Development setup and workflow
- Code style and testing requirements
- Pull request process
- Issue reporting

### Quick Start for Contributors

```bash
# Fork and clone the repo
git clone https://github.com/YOUR_USERNAME/conductor-gateway.git
cd conductor-gateway

# Set up development environment
poetry install
poetry run pre-commit install

# Create feature branch
git checkout -b feature/your-feature-name

# Make changes and test
poetry run pytest
python run_tests.py

# Submit pull request
```

## 📊 Performance

- **Concurrent SSE Streams**: Supports multiple simultaneous streaming connections
- **Background Processing**: Non-blocking agent execution with event queues
- **Resource Efficient**: Memory-bounded queues prevent resource exhaustion
- **Health Monitoring**: Built-in health checks and logging

## 🔒 Security

- **Bandit Security Scanning**: Automated vulnerability detection
- **Input Validation**: Comprehensive payload validation
- **CORS Configuration**: Configurable cross-origin policies
- **Environment Isolation**: Secure configuration management

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Issues**: [GitHub Issues](https://github.com/primoia/conductor-gateway/issues)
- **Discussions**: [GitHub Discussions](https://github.com/primoia/conductor-gateway/discussions)
- **Documentation**: [Project Docs](docs/)

## 🎯 Key Technologies

- **[FastAPI](https://fastapi.tiangolo.com/)** - High-performance async web framework
- **[MongoDB](https://www.mongodb.com/)** - Document database with Motor async driver
- **[Poetry](https://python-poetry.org/)** - Modern Python dependency management
- **[MCP](https://modelcontextprotocol.io/)** - Model Context Protocol for tool integration
- **[APScheduler](https://apscheduler.readthedocs.io/)** - Advanced Python scheduler
- **[Ruff](https://docs.astral.sh/ruff/)** - Fast Python linter and formatter
- **[MyPy](https://mypy.readthedocs.io/)** - Static type checking
- **[Pytest](https://pytest.org/)** - Testing framework

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/) for high-performance async APIs
- Uses [Poetry](https://python-poetry.org/) for modern Python dependency management
- Powered by [MCP](https://modelcontextprotocol.io/) for extensible tool integration
- Quality assured with [Ruff](https://docs.astral.sh/ruff/), [MyPy](https://mypy.readthedocs.io/), and [Pytest](https://pytest.org/)
- Database powered by [MongoDB](https://www.mongodb.com/) for flexible document storage

---

**Built with ❤️ by the Primoia team**