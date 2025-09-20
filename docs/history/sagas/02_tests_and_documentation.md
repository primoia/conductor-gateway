# SAGA-GW-02: Implementation of Tests and Technical Documentation

## Objective

To ensure the robustness, reliability, and maintainability of the `conductor-gateway` project by creating an initial test suite (unit and integration tests) and developing essential technical documentation, following the standards of the Conductor ecosystem.

## Context

*   **Project:** `conductor-gateway`
*   **Current State:** Post-refactoring from SAGA-GW-01. The project is autonomous, uses Poetry for dependency management, and follows the `src/` layout.
*   **Technologies:** FastAPI, Poetry, Pytest (to be implemented).

## Detailed Steps

### Part A: Test Implementation

1.  **Configure the Test Environment:**
    *   Add `pytest`, `pytest-asyncio`, and `httpx` to the development dependencies in `pyproject.toml` with the command `poetry add "pytest pytest-asyncio httpx" --group dev`.
    *   Create a `pytest.ini` file in the project root to configure test paths (e.g., `testpaths = tests`).

2.  **Create Unit Tests for the Tools:**
    *   Create the file `tests/tools/test_conductor_advanced_tools.py`.
    *   Write unit tests for the functions in `src/tools/conductor_advanced_tools.py`.
    *   **Important:** Use `unittest.mock.patch` to mock the `subprocess.run` call. The goal is to verify that the `conductor` commands are being constructed with the correct arguments, not to actually execute the `conductor` process.

3.  **Create Integration Tests for the API:**
    *   Create the file `tests/api/test_api_endpoints.py`.
    *   Use FastAPI's `TestClient` (or `httpx.AsyncClient`) to make real requests to the application's endpoints in a test environment.
    *   Test the main endpoints: `/health`, `/execute`, and the streaming flow with `/api/v1/stream-execute` and `/api/v1/stream/{job_id}`.
    *   Verify HTTP status codes, JSON response formats, and behavior in both success and error cases.

### Part B: Elaboration of Technical Documentation

4.  **Create Documentation Structure:**
    *   If it doesn't already exist, create the standard folder structure: `docs/architecture`, `docs/guides`, and `project-management/adr`.
    *   Copy the `DOCUMENTATION_GUIDE.md` from the `conductor` project into the `docs/` folder to maintain consistency.

5.  **Develop Architecture Documents:**
    *   Create the file `docs/architecture/01_gateway_overview.md`.
    *   This document should detail the gateway's role, the request flow (e.g., Web UI -> Gateway -> Conductor), and the internal architecture with FastAPI + MCP Server in a separate thread.

6.  **Develop User Guides:**
    *   Create `docs/guides/01_local_setup.md`: A step-by-step guide on how to clone the repository, configure `config.yaml`, install dependencies with `poetry install`, and run the server locally.
    *   Create `docs/guides/02_api_usage.md`: Document each API endpoint, including `curl` examples for requests and the expected response formats.

7.  **Update the Main `README.md`:**
    *   Refactor the `README.md` in the project root to serve as a "quick start guide".
    *   It should contain: a brief project description, prerequisites, a link to the setup guide in `docs/guides/01_local_setup.md`, and a link to the full API documentation.

## Verification

*   The test suite can be run successfully via the `poetry run pytest` command.
*   The tests cover the main functionalities of the tools and API endpoints.
*   The architecture and guide documents are created in the correct locations and contain the planned information.
*   The main `README.md` is clear, concise, and directs users to more detailed documentation.