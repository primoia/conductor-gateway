# 🎼 Conductor Gateway

> The API gateway for the Conductor AI ecosystem, bridging web interfaces with the powerful Conductor engine.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/Build-Passing-brightgreen.svg)]()
[![Code Style](https://img.shields.io/badge/Code%20Style-Black-black.svg)]()

---

## 🚀 Overview

**Conductor Gateway** is a standalone FastAPI application that serves as the primary entry point for all UI clients (web, mobile, desktop) to interact with the `conductor` engine. It exposes the powerful, CLI-based features of Conductor through a modern, secure, and easy-to-use REST and SSE (Server-Sent Events) API.

This gateway enables real-time monitoring of AI agent execution, making it possible to build rich, interactive user interfaces on top of the headless Conductor core.

### Architecture Flow

```
+-----------------------+
|   UI Clients          |
| (Web, Mobile, etc.)   |
+-----------------------+
          |
          v (REST / SSE API Calls)
+-----------------------+
|   Conductor Gateway   |
| (FastAPI + MCP Server)|
+-----------------------+
          |
          v (CLI Commands)
+-----------------------+
|   Conductor Engine    |
| (Headless AI Worker)  |
+-----------------------+
```

## ✨ Key Features

-   **Single Point of Entry:** Provides a unified API for all Conductor interactions.
-   **Real-Time Streaming:** Uses Server-Sent Events (SSE) to stream agent execution logs and tokens in real-time.
-   **Standardized & Autonomous:** Built with modern Python standards, using Poetry for dependency management and a `src/` layout.
-   **Hybrid Configuration:** Easily configured via a `config.yaml` file, with support for environment variable overrides for production deployments.
-   **Containerized:** Includes a multi-stage `Dockerfile` and `docker-compose.yml` for easy and secure deployment.
-   **Extensible:** Exposes the full capabilities of the Conductor engine's advanced tools.

## 🏁 Getting Started

This guide will help you get the Conductor Gateway running locally.

### Prerequisites

-   Git
-   Docker and Docker Compose
-   A local clone of the [conductor](https://github.com/primoia/conductor) project.

### 1. Clone the Repository

```bash
git clone https://github.com/primoia/conductor-gateway.git
cd conductor-gateway
```

### 2. Configure the Gateway

You need to tell the gateway where to find your `conductor` engine instance.

```bash
# Copy the example configuration
cp config.yaml.example config.yaml
```

Now, open `config.yaml` and edit the `conductor.project_path` to point to the absolute path of your local `conductor` project directory.

```yaml
# config.yaml

server:
  host: "0.0.0.0"
  port: 5006
  mcp_port: 8006

conductor:
  # IMPORTANT: Change this to the correct path on your system
  project_path: "/path/to/your/conductor/project"
```

### 3. Run the Service

The easiest way to run the gateway is with Docker Compose. This command will build the Docker image and start the service.

```bash
docker compose up --build
```

### 4. Verify Installation

Once the container is running, you can check if the gateway is healthy by accessing the `/health` endpoint:

```bash
curl http://localhost:5006/health
```

You should see a JSON response with `"status": "healthy"`.

## ⚙️ API Usage

The primary way to interact with the gateway is via the SSE streaming endpoint. You first make a `POST` request to start a job, and then connect to a `GET` endpoint to receive the event stream.

**1. Start an execution:**

```bash
curl -X POST http://localhost:5006/api/v1/stream-execute \
  -H "Content-Type: application/json" \
  -d '{
    "command": "list all available agents"
  }'
```

This will return a `job_id`, for example: `{"job_id":"job_12345..."}`.

**2. Connect to the stream:**

```bash
curl http://localhost:5006/api/v1/stream/job_12345...
```

This will keep the connection open and stream back events from the agent's execution in real-time.

## 📚 Documentation

For detailed documentation on the architecture, API endpoints, and setup guides, please see the [docs/](./docs/) directory.

-   **[SAGA-GW-01: Structuring and Autonomy Plan](./docs/history/sagas/01_decouple_shared_lib.md)**
-   **[SAGA-GW-02: Tests and Documentation Plan](./docs/history/sagas/02_tests_and_documentation.md)**

## 🤝 Contributing

Contributions are welcome! Please read our (upcoming) `CONTRIBUTING.md` guide to learn how you can get involved.

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for details.
