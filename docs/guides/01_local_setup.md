# Local Setup and Development Guide

This guide provides step-by-step instructions to set up and run the `conductor-gateway` project on your local machine for development.

## Prerequisites

Before you begin, ensure you have the following installed:

-   **Git:** For cloning the repository.
-   **Python 3.11+**
-   **Poetry:** For managing Python dependencies. ([Installation Guide](https://python-poetry.org/docs/#installation))
-   **Docker & Docker Compose:** For the recommended container-based setup.
-   **A local clone of the `conductor` project:** The gateway needs to know where the core engine is located.

## 1. Clone the Repository

Clone the `conductor-gateway` project from GitHub:

```bash
git clone https://github.com/primoia/conductor-gateway.git
cd conductor-gateway
```

## 2. Install Dependencies

This project uses Poetry to manage its dependencies. Install them by running:

```bash
poetry install
```

This will create a virtual environment inside the project directory (`.venv/`) and install all necessary packages from `pyproject.toml`.

## 3. Configure the Gateway

The gateway needs to know where your local `conductor` engine project is located.

1.  **Copy the example configuration file:**

    ```bash
    cp config.yaml.example config.yaml
    ```

2.  **Edit `config.yaml`:**

    Open the newly created `config.yaml` file and change the `conductor.project_path` to the **absolute path** of your `conductor` project directory.

    ```yaml
    # config.yaml

    server:
      host: "0.0.0.0"
      port: 5006
      mcp_port: 8006

    conductor:
      # IMPORTANT: Change this to the correct path on your system
      project_path: "/home/user/projects/conductor"
    ```

## 4. Run the Service

You have two primary methods for running the service locally.

### Method A: Docker Compose (Recommended)

This is the easiest and most reliable way to run the service, as it mirrors a production-like environment.

```bash
docker compose up --build
```

This command will build the Docker image based on the `Dockerfile` and start the service. The gateway will be available at `http://localhost:5006`.

### Method B: Local Virtual Environment (For Active Development)

If you are actively developing and want features like hot-reloading, you can run the application directly using Poetry and Uvicorn.

```bash
poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 5006
```

-   `--reload`: Automatically reloads the server whenever you make a change to the code.

## 5. Verify the Setup

Once the service is running (using either method), you can verify that it's working correctly by sending a request to the `/health` endpoint:

```bash
curl http://localhost:5006/health
```

If the setup is successful, you will receive a JSON response with `"status": "healthy"`.

```json
{
  "status": "healthy",
  "service": "conductor_gateway",
  "version": "3.1.0",
  ...
}
```

You are now ready to develop and test the Conductor Gateway!
