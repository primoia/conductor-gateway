"""
FastAPI Application for Conductor Gateway with SSE Support
"""

import asyncio
import json
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.config.settings import SERVER_CONFIG
from src.utils.mcp_utils import init_agent

logger = logging.getLogger(__name__)

# SSE Stream Manager - Global dictionary to manage active streams
ACTIVE_STREAMS: dict[str, asyncio.Queue] = {}


def start_mcp_server():
    """Starts MCP server in a separate thread."""
    try:
        logger.info("Starting MCP server thread...")
        from server.advanced_server import ConductorAdvancedMCPServer

        server = ConductorAdvancedMCPServer(port=SERVER_CONFIG["mcp_port"])
        server.run(transport="sse")
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}", exc_info=True)


async def run_agent_with_queue(job_id: str, payload: dict[str, Any], queue: asyncio.Queue):
    """Execute agent and populate queue with events using native MCPAgent event subscription."""
    try:
        logger.info(f"Starting agent execution for job {job_id}")

        # Initialize agent with conductor_gateway configuration
        agent_config = {
            "mcpServers": {
                "http": {
                    "url": f"http://localhost:{SERVER_CONFIG['mcp_port']}/sse",
                    "reconnect": True,
                    "reconnectInterval": 1000,
                    "maxReconnectAttempts": 5,
                    "timeout": 30000,
                }
            }
        }
        agent = init_agent(agent_config=agent_config)

        # Create event handlers that put events into the queue
        def create_event_handler(event_name: str):
            def handler(data):
                event_data = {
                    "event": event_name,
                    "data": data,
                    "timestamp": time.time(),
                    "job_id": job_id,
                }
                try:
                    queue.put_nowait(event_data)
                    logger.debug(f"Event queued: {event_name} for job {job_id}")
                except asyncio.QueueFull:
                    logger.warning(f"Queue full for job {job_id}, dropping event {event_name}")
                except Exception as e:
                    logger.error(f"Error queuing event {event_name}: {e}")

            return handler

        # Subscribe to MCPAgent events using native API
        try:
            # Standard LangChain callback events that MCPAgent likely supports
            agent.on("on_llm_start", create_event_handler("on_llm_start"))
            agent.on("on_llm_new_token", create_event_handler("on_llm_new_token"))
            agent.on("on_llm_end", create_event_handler("on_llm_end"))
            agent.on("on_tool_start", create_event_handler("on_tool_start"))
            agent.on("on_tool_end", create_event_handler("on_tool_end"))
            agent.on("on_chain_start", create_event_handler("on_chain_start"))
            agent.on("on_chain_end", create_event_handler("on_chain_end"))
            logger.info(f"Event handlers registered for job {job_id}")
        except AttributeError as e:
            logger.warning(f"Some event handlers not available: {e}")
            # Continue execution even if some events aren't supported

        # Send initial status event
        await queue.put(
            {
                "event": "job_started",
                "data": {"message": "Inicializando execução do conductor..."},
                "timestamp": time.time(),
                "job_id": job_id,
            }
        )

        # Extract user command from payload
        user_command = payload.get("textEntries", [{}])[0].get("content", "")
        if not user_command:
            user_command = payload.get("input", "") or payload.get("command", "")

        logger.info(f"Executing command: {user_command[:100]}...")

        # Send progress event
        await queue.put(
            {
                "event": "status_update",
                "data": {"message": "Conectando ao conductor e descobrindo ferramentas..."},
                "timestamp": time.time(),
                "job_id": job_id,
            }
        )

        # Execute the agent command (this is blocking but handlers will fire during execution)
        result = await agent.run(user_command)

        # Send result event
        await queue.put(
            {
                "event": "result",
                "data": {"result": result, "message": "Comando executado com sucesso"},
                "timestamp": time.time(),
                "job_id": job_id,
            }
        )

        logger.info(f"Agent execution completed for job {job_id}")

    except Exception as e:
        logger.error(f"Error in agent execution for job {job_id}: {e}", exc_info=True)
        await queue.put(
            {
                "event": "error",
                "data": {"error": str(e), "message": "Erro durante execução"},
                "timestamp": time.time(),
                "job_id": job_id,
            }
        )
    finally:
        # Signal end of stream
        await queue.put(
            {
                "event": "end_of_stream",
                "data": {"message": "Stream finalizado"},
                "timestamp": time.time(),
                "job_id": job_id,
            }
        )
        # Clean up the stream from active dictionary
        ACTIVE_STREAMS.pop(job_id, None)
        logger.info(f"Cleaned up stream for job {job_id}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for FastAPI."""
    # Startup
    logger.info("Conductor Gateway API starting up...")

    # Start MCP server in daemon thread
    mcp_thread = threading.Thread(target=start_mcp_server, daemon=True, name="MCP-Server-Thread")
    mcp_thread.start()

    # Give MCP server time to start
    await asyncio.sleep(2)

    yield

    # Shutdown
    logger.info("Conductor Gateway API shutting down...")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""

    # Initialize FastAPI application with lifespan
    app = FastAPI(
        title="Conductor Gateway API",
        description="Bridge service for integrating primoia-browse-use with conductor project",
        version="3.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Em produção, especificar domínios específicos
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # SSE Streaming Endpoints - Following Plan2 Hybrid REST + EventSource pattern

    @app.post("/api/v1/stream-execute")
    async def start_execution(request: Request):
        """Start execution and return job_id for SSE streaming (Plan2 Hybrid Pattern)."""
        try:
            # Generate unique job ID
            job_id = f"job_{uuid.uuid4()}"

            # Parse request payload
            payload = await request.json()
            command_preview = payload.get("textEntries", [{}])[0].get("content", "")[:50]
            if not command_preview:
                command_preview = payload.get("input", "")[:50] or payload.get("command", "")[:50]

            logger.info(
                f"Starting streaming execution for job {job_id}, command: {command_preview}..."
            )

            # Create event queue for this job
            event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)  # Prevent memory issues
            ACTIVE_STREAMS[job_id] = event_queue

            # Start agent execution in background task
            asyncio.create_task(run_agent_with_queue(job_id, payload, event_queue))

            # Return job_id immediately
            return {"job_id": job_id, "status": "started", "stream_url": f"/api/v1/stream/{job_id}"}

        except Exception as e:
            logger.error(f"Error starting execution: {e}", exc_info=True)
            return {"error": str(e)}, 500

    @app.get("/api/v1/stream/{job_id}")
    async def stream_events(job_id: str):
        """SSE endpoint that streams events for a specific job_id (Plan2 Hybrid Pattern)."""
        queue = ACTIVE_STREAMS.get(job_id)
        if not queue:
            return Response(
                status_code=404, content=f"Job ID '{job_id}' not found or already completed."
            )

        logger.info(f"Starting SSE stream for job {job_id}")

        async def event_generator():
            """Generate SSE events from the job's queue."""
            try:
                while True:
                    # Wait for next event in queue
                    event = await queue.get()

                    # Check for end of stream
                    if event.get("event") == "end_of_stream":
                        logger.info(f"End of stream reached for job {job_id}")
                        break

                    # Format as SSE and yield
                    sse_data = json.dumps(event)
                    yield f"data: {sse_data}\n\n"

            except asyncio.CancelledError:
                logger.info(f"SSE stream cancelled for job {job_id}")
            except Exception as e:
                logger.error(f"Error in SSE stream for job {job_id}: {e}")
                # Send error event before closing
                error_event = {
                    "event": "error",
                    "data": {"error": str(e)},
                    "timestamp": time.time(),
                    "job_id": job_id,
                }
                yield f"data: {json.dumps(error_event)}\n\n"
            finally:
                # Clean up
                ACTIVE_STREAMS.pop(job_id, None)
                logger.info(f"SSE stream cleanup completed for job {job_id}")

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            },
        )

    @app.post("/execute")
    async def execute_command(payload: dict[str, Any]):
        """Simple synchronous execute endpoint for direct command execution."""
        try:
            # Extract command from different payload formats
            command = None
            if "input" in payload:
                command = payload["input"]
            elif "command" in payload:
                command = payload["command"]
            elif "textEntries" in payload and payload["textEntries"]:
                # Handle complex payload format
                command = payload["textEntries"][0].get("content", "")

            if not command:
                raise HTTPException(status_code=400, detail="No command found in payload")

            logger.info(f"Executing command: {command[:100]}...")

            # Initialize agent with conductor_gateway configuration
            agent_config = {
                "mcpServers": {
                    "http": {
                        "url": f"http://localhost:{SERVER_CONFIG['mcp_port']}/sse",
                        "reconnect": True,
                        "reconnectInterval": 1000,
                        "maxReconnectAttempts": 5,
                    }
                }
            }
            agent = init_agent(agent_config)
            result = await agent.run(command)

            return {"status": "success", "result": result}

        except Exception as e:
            logger.error(f"Error executing command: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/health")
    @app.options("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "conductor_gateway",
            "version": "3.1.0",
            "mode": SERVER_CONFIG.get("conductor_server_mode", "unknown"),
            "endpoints": {
                "api": f"http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}/api/v1",
                "mcp": f"http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['mcp_port']}",
                "health": f"http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}/health",
            },
        }

    return app
