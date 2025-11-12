# Architecture Overview: Conductor Gateway

## 1. Purpose

The Conductor Gateway serves as a dedicated **Backend-for-Frontend (BFF)** for the Conductor ecosystem. Its primary role is to expose the powerful, command-line-based `conductor` engine through a modern, secure, and scalable API. It acts as the single, unified entry point for any user interface (web, mobile, or desktop) that needs to interact with Conductor agents.

## 2. Core Components

The gateway is built on a robust and decoupled architecture:

### a. FastAPI Application (`src/api/app.py`)

This is the main web server that exposes all HTTP endpoints. It handles:
-   REST endpoints for synchronous actions (e.g., `/health`, `/execute`).
-   Server-Sent Events (SSE) endpoints for real-time streaming.
-   WebSocket connections for bidirectional real-time updates.
-   CORS (Cross-Origin Resource Sharing) middleware to allow access from web clients.
-   Application lifecycle management.
-   Task queue architecture for concurrent agent execution.

### b. API Routers (`src/api/routers/`)

Modular routers that organize functionality by domain:
-   **Agents Router**: Agent instance management and execution with working directory support.
-   **Screenplays Router**: CRUD operations for screenplays with markdown validation.
-   **Persona Router**: Persona management with versioning capabilities.
-   **Councilor Router**: Automated agent monitoring and scheduling.
-   **Portfolio Router**: Portfolio chat management with rate limiting.
-   **Conversations Router**: Conversation and message management with soft delete propagation.

### c. MongoDB Integration (`src/core/database.py`)

The gateway uses MongoDB for persistent storage:
-   **Motor Driver**: Async MongoDB driver for non-blocking operations.
-   **Document Storage**: Flexible schema for screenplays, personas, agents, and conversations.
-   **Connection Pooling**: Efficient connection management.

### d. MCP Server (`src/server/advanced_server.py`)

This is a background worker server, based on the `FastMCP` library, that runs in a separate thread. Its sole responsibility is to expose the `conductor` engine's functionalities as a set of tools that can be called by an AI agent.

### e. Conductor API Client (`src/clients/conductor_client.py`)

HTTP client for interacting with the Conductor API:
-   **Stateless Execution**: Fast agent execution without conversation history.
-   **Contextual Execution**: Execution with full conversation context.
-   **Multi-Provider Support**: OpenAI, Anthropic, Groq, Fireworks AI, Ollama, Gemini.
-   **Extended Timeout**: 10-minute timeout for long-running agent tasks.

### f. Background Services (`src/services/`)

-   **Screenplay Service**: Business logic for screenplay CRUD operations.
-   **Councilor Service**: Agent monitoring and execution management.
-   **Councilor Scheduler**: APScheduler-based backend scheduler for automated agent runs.

### g. Lifespan Management

The FastAPI application manages the lifecycle of all components. Using FastAPI's `lifespan` context manager:
-   **On Startup:**
    - MongoDB connection is established.
    - MCP Server is initialized and started in a background daemon thread.
    - Councilor backend scheduler is initialized for automated monitoring.
    - All routers and services are initialized with database connections.
-   **On Shutdown:**
    - MongoDB connections are closed gracefully.
    - Background schedulers are shut down.
    - The application shuts down gracefully.

This ensures that all components are properly initialized and cleaned up.

## 3. Request Flow (SSE Streaming)

The primary workflow for interacting with an agent is asynchronous and designed for real-time feedback.

```mermaid
sequenceDiagram
    participant Client as UI Client (Web/Mobile)
    participant Gateway as Conductor Gateway
    participant Agent as AI Agent (in Gateway)
    participant Conductor as Conductor Engine (CLI)

    Client->>+Gateway: POST /api/v1/stream-execute (command)
    Gateway-->>-Client: 200 OK ({"job_id": "xyz"})

    Client->>+Gateway: GET /api/v1/stream/{job_id}
    Gateway-->>-Client: Connection Established (SSE)

    Note over Gateway,Conductor: Gateway starts agent execution in a background task.

    Gateway->>+Agent: .run(command)
    Agent->>+Conductor: Executes CLI command (e.g., `conductor --list`)
    Conductor-->>-Agent: Returns result (stdout/stderr)
    Agent-->>-Gateway: Emits events (`on_tool_end`, `on_llm_new_token`, etc.)

    Gateway-->>Client: data: {"event": "on_tool_end", ...}
    Gateway-->>Client: data: {"event": "on_llm_new_token", ...}
    Gateway-->>Client: data: {"event": "end_of_stream"}
```

## 4. Configuration System (`src/config/settings.py`)

The gateway uses a hybrid configuration system for maximum flexibility:
1.  **Base Configuration:** A `config.yaml` file in the root directory defines all default settings.
2.  **Environment Overrides:** Any setting can be overridden by setting a corresponding environment variable (e.g., `PORT` overrides `server.port`).

This allows for easy configuration in local development (via the YAML file) and seamless integration with production environments and CI/CD pipelines (via environment variables).

## 5. Directory Structure

The project follows a standard Python `src/` layout:
-   `src/`: Contains all the application's source code.
    -   `api/`: Defines the FastAPI application and its endpoints.
        -   `routers/`: Domain-specific API routers (agents, screenplays, personas, councilor, portfolio, conversations).
        -   `app.py`: Main FastAPI application with lifecycle management.
        -   `models.py`: Pydantic models for request/response validation.
        -   `websocket.py`: WebSocket handlers for real-time updates.
    -   `clients/`: External service clients (Conductor API client).
    -   `config/`: Handles the configuration loading.
    -   `core/`: Core functionality (database connections, utilities).
    -   `models/`: Data models for domain entities (screenplay, persona, councilor).
    -   `services/`: Business logic layer (screenplay service, councilor service, scheduler).
    -   `server/`: Contains the MCP server implementation.
    -   `tools/`: Implements the tools that wrap the Conductor CLI.
    -   `utils/`: Contains internalized helper functions.
-   `tests/`: Contains unit and integration tests.
-   `docs/`: Project documentation.
-   `pyproject.toml`: Defines project metadata and dependencies using Poetry.
