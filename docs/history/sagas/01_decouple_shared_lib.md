# SAGA-GW-01: Conductor Gateway Structuring and Autonomy Plan

**Objective:** To completely refactor the `conductor-gateway` project to be autonomous, robust, and align with the structure and tooling standards of the `conductor` project. This plan details the necessary steps to transform the initial version of the gateway into its standardized version.

---

### **Execution Plan**

**Phase 1: Adoption of Modern Tools and Standards**

1.  **Migrate to Poetry:**
    *   **Action:** Replace the `requirements.txt`-based dependency management with Poetry.
    *   **Steps:**
        1.  Initialize a new Poetry project with `poetry init`.
        2.  Add all runtime and development dependencies to `pyproject.toml` using `poetry add`.
        3.  Remove the `requirements.txt` and `requirements.docker.txt` files.

2.  **Adopt `src/` Layout:**
    *   **Action:** Restructure the source code into a standard package layout.
    *   **Steps:**
        1.  Create the `src/` directory in the project root.
        2.  Move all application modules (e.g., `main.py`, `api/`, `config/`, `tools/`, etc.) into `src/`.

**Phase 2: Decoupling and Code Cleanup**

1.  **Internalize Dependencies:**
    *   **Action:** Eliminate the dependency on the external `shared_lib`.
    *   **Steps:**
        1.  Identify the essential functions used from `shared_lib` (e.g., `init_agent`, `validate_gateway_api_key`).
        2.  Copy or recreate this functionality within a new utility package in the project, such as `src/utils/`.

2.  **Refactor and Unify the Application:**
    *   **Action:** Simplify the application's entry point and remove redundant logic.
    *   **Steps:**
        1.  Centralize the FastAPI application creation in a new file `src/api/app.py`, using a `create_app()` factory function and the `lifespan` manager to start the MCP server.
        2.  Simplify `src/main.py` to only import and run the `app` created in `src/api/app.py`.
        3.  Remove the "basic mode," focusing exclusively on `ConductorAdvancedMCPServer`.
        4.  Delete files that became obsolete with the unification, such as `api/routes.py` and `tools/conductor_tools.py`.

3.  **Update Imports:**
    *   **Action:** Go through all project files and fix the `import` statements to reflect the new folder structure and the removal of `shared_lib`.

**Phase 3: Standardization of Configuration and Build**

1.  **Implement Hybrid Configuration:**
    *   **Action:** Replace the use of `.env` with a more robust configuration system.
    *   **Steps:**
        1.  Refactor `src/config/settings.py` to read a `config.yaml` file as a base.
        2.  Implement the logic to allow environment variables to override the values from `config.yaml`.
        3.  Create a `config.yaml.example` file in the project root as a template.

2.  **Standardize Project Artifacts:**
    *   **Action:** Align the project's configuration files with those of `conductor`.
    *   **Steps:**
        1.  Copy the `.gitignore` file from the `conductor` project.
        2.  Create a `docker-compose.yml` file to facilitate the local development environment.
        3.  Replace the `Dockerfile` with a `multi-stage` version optimized for Poetry and the `src/` layout, including the `PYTHONPATH` definition.

**Phase 4: Verification**

1.  **Verify Dependencies:** Run `poetry install` to ensure `pyproject.toml` and `poetry.lock` are correct.
2.  **Verify Build:** Run `docker build .` to ensure the Docker image is built successfully.
3.  **Verify Execution:** Start the container (`docker compose up`) and confirm that the application starts without errors and responds to the `/health` endpoint.