# API Usage Guide

This guide details how to interact with the `conductor-gateway` API. The primary interface is designed for real-time interaction using Server-Sent Events (SSE).

**Base URL:** `http://localhost:5006`

---

## Main Workflow: SSE Streaming

The main workflow is a two-step process designed for asynchronous agent execution and real-time feedback.

### Step 1: Start an Execution

You initiate a task by sending a `POST` request to the `/api/v1/stream-execute` endpoint. The payload should be a JSON object containing the command you want the agent to run.

-   **Endpoint:** `POST /api/v1/stream-execute`
-   **Method:** `POST`
-   **Content-Type:** `application/json`

**Example Request (`curl`):**

```bash
curl -X POST http://localhost:5006/api/v1/stream-execute \
  -H "Content-Type: application/json" \
  -d '{
    "command": "list all available agents and their capabilities"
  }'
```

**Payload Structure:**

The gateway accepts flexible JSON payloads. It will look for the command under the keys `command`, `input`, or within a more complex `textEntries` structure for backward compatibility.

**Example Success Response:**

The server will immediately respond with a `200 OK` and a JSON object containing a unique `job_id` for this execution.

```json
{
  "job_id": "job_a8b4c1d8-e7f6-4a5b-8c7d-6e5f4a3b2c1d",
  "status": "started",
  "stream_url": "/api/v1/stream/job_a8b4c1d8-e7f6-4a5b-8c7d-6e5f4a3b2c1d"
}
```

### Step 2: Consume the Event Stream

Once you have the `job_id`, you connect to the corresponding `GET` endpoint to start receiving the stream of events.

-   **Endpoint:** `GET /api/v1/stream/{job_id}`
-   **Method:** `GET`

**Example Request (`curl`):**

```bash
# Use the job_id from the previous step
curl -N http://localhost:5006/api/v1/stream/job_a8b4c1d8-e7f6-4a5b-8c7d-6e5f4a3b2c1d
```

-   The `-N` flag in `curl` disables buffering, allowing you to see the events as they arrive.

**Event Stream Format:**

The server will hold the connection open and send `data:` events in the `text/event-stream` format. Each event is a JSON object containing details about the agent's execution.

**Example Events:**

```
data: {"event": "job_started", "data": {"message": "Initializing conductor execution..."}, ...}

data: {"event": "on_tool_start", "data": {"tool": "list_available_agents"}, ...}

data: {"event": "on_llm_new_token", "data": {"chunk": "The available agents are:"}, ...}

data: {"event": "on_llm_new_token", "data": {"chunk": "\n- SystemGuide_Meta_Agent"}, ...}

data: {"event": "result", "data": {"result": "...final agent output..."}, ...}

data: {"event": "end_of_stream", "data": {"message": "Stream finished"}, ...}
```

Your client application should parse these JSON objects to provide real-time feedback to the user.

---

## Other Endpoints

### Health Check

-   **Endpoint:** `GET /health`
-   **Description:** A simple endpoint to verify that the gateway service is running and properly configured.
-   **Example:** `curl http://localhost:5006/health`

### Synchronous Execution (for simple tasks)

-   **Endpoint:** `POST /execute`
-   **Description:** A simpler, synchronous endpoint that waits for the command to complete and returns the final result in a single response. Not recommended for long-running agent tasks.
-   **Example:**
    ```bash
    curl -X POST http://localhost:5006/execute \
      -H "Content-Type: application/json" \
      -d '{"command": "list agents"}'
    ```
