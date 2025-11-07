"""
FastAPI Application for Conductor Gateway with SSE Support
"""

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from pymongo import MongoClient
from bson import ObjectId

from src.api.routers.screenplays import init_screenplay_service, router as screenplays_router
from src.api.routers.persona import router as persona_router
from src.api.routers.persona_version import router as persona_version_router
from src.api.routers.councilor import router as councilor_router
from src.api.routers.agents import router as agents_router
from src.api.routers.portfolio import router as portfolio_router, limiter
from src.api.routers.conversations import router as conversations_router  # 🔥 NOVO: Rotas de conversas
from src.api.models import AgentExecuteRequest
from src.api.websocket import gamification_manager
from src.core.database import init_database, close_database
from src.clients.conductor_client import ConductorClient
from src.config.settings import CONDUCTOR_CONFIG, MONGODB_CONFIG, SERVER_CONFIG
from src.utils.mcp_utils import init_agent
from src.services.councilor_scheduler import CouncilorBackendScheduler

logger = logging.getLogger(__name__)

# SSE Stream Manager - Global dictionary to manage active streams
ACTIVE_STREAMS: dict[str, asyncio.Queue] = {}

# MongoDB client - will be initialized in lifespan
mongo_client: MongoClient | None = None
mongo_db = None

# Conductor API client - will be initialized in lifespan
conductor_client: ConductorClient | None = None

# Councilor Backend Scheduler - will be initialized in lifespan
councilor_scheduler: CouncilorBackendScheduler | None = None


def mongo_to_dict(item: dict) -> dict:
    """Convert MongoDB document to JSON-serializable dict."""
    # Convert _id if it's an ObjectId (for some collections)
    if "_id" in item and hasattr(item["_id"], "__str__"):
        item["_id"] = str(item["_id"])

    # Convert datetime objects to ISO format strings
    for key, value in item.items():
        if hasattr(value, "isoformat"):  # datetime, date, or time object
            item[key] = value.isoformat()

    return item


def start_mcp_server():
    """Starts MCP server in a separate thread."""
    try:
        logger.info("Starting MCP server thread...")
        from src.server.advanced_server import ConductorAdvancedMCPServer

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
    global mongo_client, mongo_db, conductor_client, councilor_scheduler

    # Startup
    logger.info("Conductor Gateway API starting up...")

    # Initialize MongoDB connection
    try:
        mongo_client = MongoClient(MONGODB_CONFIG["url"])
        mongo_db = mongo_client[MONGODB_CONFIG["database"]]
        # Test connection
        mongo_client.admin.command("ping")
        logger.info(f"Connected to MongoDB: {MONGODB_CONFIG['url']}/{MONGODB_CONFIG['database']}")

        # Create indexes for agent_instances collection
        agent_instances = mongo_db["agent_instances"]
        agent_instances.create_index("instance_id", unique=True)
        logger.info("Created index on agent_instances.instance_id")

        # Ensure compound index on history collection for performance
        history_collection = mongo_db["history"]
        history_collection.create_index([("instance_id", 1), ("timestamp", 1)])
        logger.info("Ensured compound index on history collection [instance_id, timestamp]")

        # Create indexes for councilor system
        agents_collection = mongo_db["agents"]

        # Drop old non-unique index if exists to recreate as unique
        try:
            agents_collection.drop_index("agent_id_1")
            logger.info("Dropped old non-unique agent_id index")
        except Exception:
            pass  # Index doesn't exist or already correct

        agents_collection.create_index("agent_id", unique=True)
        agents_collection.create_index("is_councilor")
        logger.info("Created indexes on agents collection")

        # Tasks collection indexes (used for both agent tasks and councilor executions)
        tasks_collection = mongo_db["tasks"]
        try:
            # Try to create unique index on task_id (may fail if duplicates exist)
            tasks_collection.create_index("task_id", unique=True, sparse=True)
        except Exception as e:
            logger.warning(f"⚠️ Could not create unique index on task_id (may have duplicates): {e}")
            # Create non-unique index as fallback
            try:
                tasks_collection.create_index("task_id")
            except Exception:
                pass

        tasks_collection.create_index([("agent_id", 1), ("created_at", -1)])
        tasks_collection.create_index("is_councilor_execution")
        tasks_collection.create_index([("is_councilor_execution", 1), ("created_at", -1)])
        logger.info("Created indexes on tasks collection")

        # Initialize screenplay service
        init_screenplay_service(mongo_db)
        logger.info("Initialized ScreenplayService with MongoDB connection")
        
        # Initialize database for persona service
        init_database()
        logger.info("Initialized database connection for persona service")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        mongo_client = None
        mongo_db = None

    # Initialize Conductor API client
    conductor_api_url = CONDUCTOR_CONFIG.get("conductor_api_url", "http://conductor-api:8000")
    conductor_client = ConductorClient(base_url=conductor_api_url)
    logger.info(f"Initialized ConductorClient with URL: {conductor_api_url}")

    # Initialize and start Councilor Backend Scheduler
    if mongo_db is not None and conductor_client is not None:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            # Create async Motor client for scheduler
            async_mongo_client = AsyncIOMotorClient(MONGODB_CONFIG["url"])
            async_mongo_db = async_mongo_client[MONGODB_CONFIG["database"]]

            councilor_scheduler = CouncilorBackendScheduler(async_mongo_db, conductor_client)
            await councilor_scheduler.start()
            logger.info("✅ Councilor Backend Scheduler started")
        except Exception as e:
            logger.error(f"❌ Failed to start Councilor Scheduler: {e}")
            councilor_scheduler = None

    # Start MCP server in daemon thread
    mcp_thread = threading.Thread(target=start_mcp_server, daemon=True, name="MCP-Server-Thread")
    mcp_thread.start()

    # Give MCP server time to start
    await asyncio.sleep(2)

    yield

    # Shutdown
    logger.info("Conductor Gateway API shutting down...")

    # Shutdown Councilor Scheduler
    if councilor_scheduler:
        await councilor_scheduler.shutdown()
        logger.info("Councilor scheduler stopped")

    # Close Conductor client
    if conductor_client:
        await conductor_client.close()
        logger.info("ConductorClient closed")

    # Close MongoDB connection
    if mongo_client:
        mongo_client.close()
        logger.info("MongoDB connection closed")

    # Close database connection
    close_database()
    logger.info("Database connection closed")


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

    # Add CORS middleware with specific origins for portfolio
    allowed_origins = [
        "http://localhost:4321",  # Astro dev server
        "https://cezarfuhr.primoia.dev",  # Production portfolio domain
        "http://localhost:3000",  # Additional dev server (if needed)
    ]

    # In development, also allow wildcard (can be restricted via env var in production)
    if SERVER_CONFIG.get("environment", "development") == "development":
        allowed_origins.append("*")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add rate limiter state and exception handler
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Include routers
    app.include_router(screenplays_router)
    app.include_router(persona_router)
    app.include_router(persona_version_router)
    app.include_router(councilor_router)
    app.include_router(portfolio_router)
    app.include_router(conversations_router)  # 🔥 NOVO: Proxy para conversas globais

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

    @app.post("/conductor/execute")
    async def conductor_proxy(payload: dict[str, Any]):
        """
        Proxy endpoint for Conductor API - accessible from outside Docker.
        This allows MCP tools to call http://localhost:5006/conductor/execute
        instead of internal http://conductor-api:8000/conductor/execute
        """
        try:
            # Get internal conductor-api URL
            conductor_api_url = CONDUCTOR_CONFIG.get("conductor_api_url", "http://conductor-api:8000")
            url = f"{conductor_api_url}/conductor/execute"

            logger.info(
                f"[Proxy /conductor/execute] Proxying to {url}, "
                f"agent_id={payload.get('agent_id')}, instance_id={payload.get('instance_id')}"
            )
            logger.debug(f"[Proxy /conductor/execute] Full payload: {payload}")

            # Forward request to internal conductor-api with custom timeout
            timeout_value = payload.get("timeout", 600)
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_value + 10)) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()

                logger.info(
                    f"[Proxy /conductor/execute] Success! Status code: {response.status_code}"
                )
                logger.debug(f"[Proxy /conductor/execute] Response: {result}")

                return result

        except httpx.HTTPStatusError as e:
            logger.error(
                f"[Proxy /conductor/execute] HTTP error from conductor-api: "
                f"{e.response.status_code} - {e.response.text}"
            )
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.RequestError as e:
            logger.error(f"[Proxy /conductor/execute] Request error to conductor-api: {e}")
            raise HTTPException(status_code=503, detail=f"Conductor API unavailable: {str(e)}")
        except Exception as e:
            logger.error(f"[Proxy /conductor/execute] Error proxying to conductor-api: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/execute-agent")
    async def execute_agent(payload: dict[str, Any]):
        """Direct endpoint to execute agent via Conductor API."""
        try:
            from src.tools.conductor_advanced_tools import ConductorAdvancedTools

            # Extract parameters
            agent_id = payload.get("agent_id")
            input_text = payload.get("input_text")
            cwd = payload.get("cwd")
            timeout = payload.get("timeout", 600)
            instance_id = payload.get("instance_id")

            if not agent_id or not input_text or not cwd:
                raise HTTPException(
                    status_code=400,
                    detail="agent_id, input_text e cwd são obrigatórios"
                )

            logger.info(
                f"[/execute-agent] Executing agent {agent_id} with instance_id={instance_id}, "
                f"input: {input_text[:100]}..."
            )

            # Initialize conductor tools and execute
            conductor_tools = ConductorAdvancedTools()
            result = conductor_tools.execute_agent_stateless(
                agent_id=agent_id,
                input_text=input_text,
                cwd=cwd,
                timeout=timeout,
                instance_id=instance_id
            )

            logger.info(f"[/execute-agent] Agent {agent_id} execution completed with status: {result.get('status')}")

            return result

        except Exception as e:
            logger.error(f"[/execute-agent] Error executing agent: {e}", exc_info=True)
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
                "websocket_gamification": f"ws://{SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}/ws/gamification",
            },
        }

    # WebSocket Endpoints

    @app.websocket("/ws/gamification")
    async def websocket_gamification_endpoint(websocket: WebSocket):
        """
        WebSocket endpoint for real-time gamification events

        Events emitted:
        - connected: Connection established
        - councilor_started: Councilor execution started
        - councilor_completed: Councilor execution completed
        - councilor_error: Councilor execution failed
        - agent_metrics_updated: Agent metrics updated
        - system_alert: System alerts

        Commands accepted:
        - subscribe: Update event subscriptions
        - ping: Heartbeat check
        - get_stats: Get connection statistics
        """
        # Generate unique client ID
        client_id = str(uuid.uuid4())

        try:
            # Connect client
            await gamification_manager.connect(websocket, client_id)

            # Send connection success event
            await gamification_manager.send_to(client_id, "connected", {
                "message": "Connected to gamification WebSocket",
                "client_id": client_id
            })

            # Main message loop
            while True:
                # Receive message from client
                data = await websocket.receive_json()

                # Process client commands
                command = data.get("command")

                if command == "subscribe":
                    # Update subscriptions
                    topics = data.get("topics", ["all"])
                    gamification_manager.update_subscriptions(client_id, topics)
                    await gamification_manager.send_to(client_id, "subscribed", {
                        "topics": topics
                    })
                    logger.info(f"Client {client_id} subscribed to: {topics}")

                elif command == "ping":
                    # Heartbeat response
                    await gamification_manager.send_to(client_id, "pong", {
                        "timestamp": time.time()
                    })

                elif command == "get_stats":
                    # Send connection statistics
                    stats = gamification_manager.get_stats()
                    await gamification_manager.send_to(client_id, "stats", stats)

                else:
                    # Unknown command
                    await gamification_manager.send_to(client_id, "error", {
                        "message": f"Unknown command: {command}"
                    })

        except WebSocketDisconnect:
            logger.info(f"Client {client_id} disconnected")
        except Exception as e:
            logger.error(f"Error in WebSocket for client {client_id}: {e}", exc_info=True)
        finally:
            gamification_manager.disconnect(client_id)

    # Agent Management Endpoints

    @app.get("/api/agents")
    async def list_agents():
        """List all available agents from MongoDB."""
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            agents_collection = mongo_db["agents"]
            agents_cursor = agents_collection.find({})

            agents = []
            for agent in agents_cursor:
                # Suportar schema completo (conductor_state) e simples (fallback)
                if 'agent_id' in agent and 'definition' in agent:
                    # Schema completo
                    definition = agent.get('definition', {})
                    agents.append({
                        "id": str(agent.get("_id", "")),  # MongoDB ObjectId (for reference)
                        "agent_id": agent.get("agent_id", ""),  # Agent name/identifier
                        "name": definition.get("name", ""),
                        "emoji": definition.get("emoji", "🤖"),
                        "description": definition.get("description", ""),
                        "model": definition.get("model", "claude"),
                        "tags": definition.get("tags", [])
                    })
                else:
                    # Schema simples (fallback) - use 'name' field as agent_id
                    agent_name = agent.get("name", "")
                    agents.append({
                        "id": str(agent.get("_id", "")),  # MongoDB ObjectId (for reference)
                        "agent_id": agent_name,  # Use name as agent_id for consistency
                        "name": agent_name,
                        "emoji": agent.get("emoji", "🤖"),
                        "description": agent.get("prompt", "")[:100] + "..." if len(agent.get("prompt", "")) > 100 else agent.get("prompt", ""),
                        "model": agent.get("model", "claude"),
                        "tags": []
                    })

            logger.info(f"Retrieved {len(agents)} agents from MongoDB")
            return agents

        except Exception as e:
            logger.error(f"Error listing agents: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    def analyze_severity(output: str) -> str:
        """
        Analyze output text to determine severity level.

        Args:
            output: Agent output text

        Returns:
            Severity string: "success", "warning", or "error"
        """
        if not output:
            return "success"

        lower_output = output.lower()

        # Check for error indicators
        error_keywords = [
            'crítico', 'erro', 'falha', 'failed', 'error',
            'critical', 'fatal', 'exception'
        ]
        if any(keyword in lower_output for keyword in error_keywords):
            return 'error'

        # Check for warning indicators
        warning_keywords = [
            'alerta', 'atenção', 'warning', 'aviso',
            'vulnerab', 'deprecated', 'caution'
        ]
        if any(keyword in lower_output for keyword in warning_keywords):
            return 'warning'

        return 'success'

    @app.post("/api/agents/{agent_id}/execute")
    async def execute_agent_by_id(agent_id: str, request: AgentExecuteRequest):
        """
        Execute an agent via MongoDB Task Queue (asynchronous, resilient architecture).

        This endpoint submits tasks to MongoDB collection and polls for completion.
        The watcher process picks up pending tasks and executes them via LLM.

        Payload example:
        {
            "input_text": "your input here",
            "instance_id": "unique-instance-id",
            "context_mode": "stateless|stateful",
            "cwd": "/path/to/working/directory",
            "screenplay_id": "optional-screenplay-id",
            "document_id": "optional-document-id (deprecated, use screenplay_id)",
            "position": {"x": 100, "y": 200},
            "ai_provider": "claude|gemini|openai|etc"
        }
        """
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            # ========================================================================
            # 1. EXTRACT AND VALIDATE REQUEST DATA
            # ========================================================================
            input_text = request.input_text
            instance_id = request.instance_id
            conversation_id = request.conversation_id
            context_mode = request.context_mode
            cwd = request.cwd
            position = request.position
            ai_provider = request.ai_provider or "claude"  # Default to claude

            # Extract screenplay_id (support both screenplay_id and document_id for backward compatibility)
            screenplay_id = request.screenplay_id or request.document_id

            logger.info("=" * 80)
            logger.info(f"📥 [GATEWAY] Requisição recebida em /api/agents/{agent_id}/execute")
            logger.info(f"   - agent_id: {agent_id}")
            logger.info(f"   - instance_id: {instance_id}")
            logger.info(f"   - conversation_id: {conversation_id}")
            logger.info(f"   - input_text: {input_text[:100] if input_text else None}...")
            logger.info(f"   - context_mode: {context_mode}")
            logger.info(f"   - cwd: {cwd or 'não fornecido (usará default)'}")
            logger.info(f"   - ai_provider: {ai_provider}")
            logger.info("=" * 80)

            # ========================================================================
            # 🔥 VALIDAÇÕES OBRIGATÓRIAS: agent_id, instance_id, conversation_id
            # ========================================================================
            if not input_text:
                raise HTTPException(status_code=400, detail="input_text is required")

            if not instance_id:
                raise HTTPException(
                    status_code=400,
                    detail="instance_id is required. Cannot execute agent without instance context."
                )

            if not conversation_id:
                raise HTTPException(
                    status_code=400,
                    detail="conversation_id is required. Cannot execute agent without conversation context."
                )

            # ========================================================================
            # 2. VERIFY AGENT EXISTS IN DATABASE
            # ========================================================================
            agents_collection = mongo_db["agents"]
            # Try to find by agent_id first, then fallback to name for compatibility
            agent = agents_collection.find_one({"agent_id": agent_id})
            if not agent:
                agent = agents_collection.find_one({"name": agent_id})

            if not agent:
                raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

            # Get the actual agent_id for consistent referencing
            actual_agent_id = agent.get("agent_id") or agent.get("name")

            # Use cwd from payload if provided, otherwise use default from config
            final_cwd = cwd or CONDUCTOR_CONFIG.get("project_path")

            # ========================================================================
            # 3. EMIT WEBSOCKET EVENT: agent_execution_started
            # ========================================================================
            start_time = datetime.utcnow()
            execution_id = f"exec_{actual_agent_id}_{int(start_time.timestamp() * 1000)}"

            agent_definition = agent.get("definition", {}) if isinstance(agent.get("definition"), dict) else {}
            agent_name = agent_definition.get("name", agent_id)
            agent_emoji = agent_definition.get("emoji", "🤖")

            try:
                await gamification_manager.broadcast("agent_execution_started", {
                    "agent_id": actual_agent_id,
                    "agent_name": agent_name,
                    "agent_emoji": agent_emoji,
                    "instance_id": instance_id,
                    "execution_id": execution_id,
                    "started_at": start_time.isoformat(),
                    "level": "debug"  # Debug level - execution log
                })
            except Exception as e:
                logger.warning(f"⚠️ Failed to broadcast agent_execution_started event: {e}")

            # ========================================================================
            # 4. SUBMIT TASK TO MONGODB QUEUE (status: "pending")
            # ========================================================================
            logger.info("🔄 [GATEWAY] Submitting task to MongoDB queue...")

            tasks_collection = mongo_db["tasks"]

            # Create task document with status "pending" for watcher to process
            task_document = {
                "_id": ObjectId(),  # Generate _id upfront
                "task_id": execution_id,
                "agent_id": actual_agent_id,
                "provider": ai_provider,
                "prompt": input_text,  # Full prompt for watcher
                "cwd": final_cwd,
                "timeout": CONDUCTOR_CONFIG.get("timeout", 600),
                "status": "pending",  # Watcher will pick this up
                "instance_id": instance_id,
                "conversation_id": conversation_id,  # Required field from request
                "context_mode": context_mode,
                "context": {
                    "screenplay_id": screenplay_id,
                    "position": position,
                },
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "result": "",
                "exit_code": None,
                "duration": None,
                "is_councilor_execution": False,
                "severity": None,
            }

            # Insert task into MongoDB
            tasks_collection.insert_one(task_document)
            task_id_str = str(task_document["_id"])

            logger.info(f"✅ [GATEWAY] Task submitted to queue: {task_id_str}")
            logger.info(f"   - execution_id: {execution_id}")
            logger.info(f"   - agent_id: {actual_agent_id}")
            logger.info(f"   - provider: {ai_provider}")
            logger.info(f"   - status: pending (awaiting watcher)")

            # ========================================================================
            # 5. POLLING: Wait for watcher to process and complete the task
            # ========================================================================
            logger.info(f"⏳ [GATEWAY] Polling task {task_id_str} for completion...")

            poll_interval = 2.0  # seconds
            timeout = CONDUCTOR_CONFIG.get("timeout", 600) + 30  # Add buffer
            start_poll_time = time.time()

            task_status = "pending"
            task_doc = None

            while time.time() - start_poll_time < timeout:
                # Fetch task from MongoDB
                task_doc = tasks_collection.find_one({"_id": task_document["_id"]})

                if not task_doc:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Task {task_id_str} disappeared from database"
                    )

                task_status = task_doc.get("status")

                # Check if task is completed or failed
                if task_status not in ["pending", "processing"]:
                    logger.info(f"✅ [GATEWAY] Task {task_id_str} completed with status: {task_status}")
                    break

                # Log progress
                if task_status == "processing":
                    logger.debug(f"⏳ Task {task_id_str} is being processed by watcher...")

                # Wait before next poll
                await asyncio.sleep(poll_interval)

            # Check if we timed out
            if task_status in ["pending", "processing"]:
                logger.error(f"⏰ [GATEWAY] Task {task_id_str} timed out after {timeout}s")
                raise HTTPException(
                    status_code=504,
                    detail=f"Task execution timed out after {timeout} seconds. Task status: {task_status}"
                )

            # ========================================================================
            # 6. EXTRACT RESULT FROM COMPLETED TASK
            # ========================================================================
            result_text = task_doc.get("result", "")
            exit_code = task_doc.get("exit_code", 0)
            duration = task_doc.get("duration", 0)
            severity = task_doc.get("severity")

            # Analyze severity if not set by watcher
            if not severity:
                if exit_code == 0:
                    severity = analyze_severity(result_text)
                else:
                    severity = "error"

                # Update severity in task document
                tasks_collection.update_one(
                    {"_id": task_document["_id"]},
                    {"$set": {"severity": severity}}
                )

            end_time = task_doc.get("completed_at") or datetime.utcnow()
            duration_ms = int(duration * 1000) if duration else 0

            logger.info(f"📊 [GATEWAY] Task execution completed:")
            logger.info(f"   - Status: {task_status}")
            logger.info(f"   - Severity: {severity}")
            logger.info(f"   - Exit code: {exit_code}")
            logger.info(f"   - Duration: {duration_ms}ms")
            logger.info(f"   - Result length: {len(result_text)} chars")

            # ========================================================================
            # 7. EMIT WEBSOCKET EVENT: agent_execution_completed
            # ========================================================================
            try:
                summary = result_text[:200] if result_text else "Sem resultado"

                await gamification_manager.broadcast("agent_execution_completed", {
                    "agent_id": actual_agent_id,
                    "agent_name": agent_name,
                    "agent_emoji": agent_emoji,
                    "instance_id": instance_id,
                    "execution_id": execution_id,
                    "status": task_status,
                    "severity": severity,
                    "started_at": start_time.isoformat(),
                    "completed_at": end_time.isoformat() if hasattr(end_time, 'isoformat') else str(end_time),
                    "duration_ms": duration_ms,
                    "level": "result",
                    "summary": summary
                })
            except Exception as e:
                logger.warning(f"⚠️ Failed to broadcast agent_execution_completed event: {e}")

            # ========================================================================
            # 8. UPDATE INSTANCE METADATA (if instance_id provided)
            # ========================================================================
            if instance_id:
                agent_instances = mongo_db["agent_instances"]
                update_data = {
                    "agent_id": actual_agent_id,
                    "last_execution": datetime.utcnow().isoformat(),
                }

                # Add optional fields if provided
                if screenplay_id:
                    update_data["screenplay_id"] = screenplay_id
                if position:
                    update_data["position"] = position

                # Check if this is first execution
                existing = agent_instances.find_one({"instance_id": instance_id})
                if not existing:
                    update_data["created_at"] = datetime.utcnow().isoformat()

                agent_instances.update_one(
                    {"instance_id": instance_id},
                    {"$set": update_data},
                    upsert=True
                )

                logger.info(f"Updated metadata for instance {instance_id}")

            # ========================================================================
            # 9. RETURN RESULT TO CLIENT
            # ========================================================================
            return {
                "status": "success" if exit_code == 0 else "error",
                "result": {
                    "result": result_text,
                    "exit_code": exit_code,
                    "status": task_status,
                },
                "instance_id": instance_id,
                "context_mode": context_mode,
                "execution_id": execution_id,
                "task_id": task_id_str,
                "duration_ms": duration_ms,
            }

        except HTTPException:
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Error executing agent {agent_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=error_msg)

            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/agents/instances")
    async def create_agent_instance(payload: dict[str, Any]):
        """
        Create a new agent instance record in MongoDB.

        Required fields:
        - instance_id: Unique identifier (format: instance-{timestamp}-{random})
        - agent_id: Agent identifier (foreign key to agents collection)
        - position: {"x": float, "y": float}
        - screenplay_id: Screenplay identifier for context association (required)
        - conversation_id: Conversation identifier for context association (required)

        Optional fields:
        - cwd: Current working directory
        - status: Initial status (default: "pending")
        - config: Configuration object
        - emoji: Agent emoji
        - definition: Agent definition object
        """
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            # Validate required fields
            required_fields = ["instance_id", "agent_id", "position", "screenplay_id", "conversation_id"]
            missing_fields = [field for field in required_fields if field not in payload or not payload[field]]

            if missing_fields:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "success": False,
                        "error": f"Missing required fields: {', '.join(missing_fields)}. Um agente só pode ser instanciado se tiver screenplay_id e conversation_id setados.",
                        "required_fields": required_fields
                    }
                )

            instance_id = payload.get("instance_id")
            agent_id = payload.get("agent_id")
            position = payload.get("position")

            # Validate position format
            if not isinstance(position, dict) or "x" not in position or "y" not in position:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "success": False,
                        "error": "Invalid position format. Expected: {x: number, y: number}"
                    }
                )

            logger.info(f"Creating agent instance: {instance_id} for agent: {agent_id}")
            logger.info(f"🔍 [DEBUG] Payload recebido no gateway:")
            logger.info(f"   - payload completo: {payload}")
            logger.info(f"   - screenplay_id no payload: {payload.get('screenplay_id')}")
            logger.info(f"   - screenplay_id tipo: {type(payload.get('screenplay_id'))}")

            agent_instances = mongo_db["agent_instances"]

            # Check if instance already exists (prevent duplicates)
            existing = agent_instances.find_one({"instance_id": instance_id})
            if existing:
                logger.warning(f"Instance {instance_id} already exists")
                raise HTTPException(
                    status_code=409,
                    detail={
                        "success": False,
                        "error": "Instance already exists",
                        "instance_id": instance_id,
                        "hint": "Use PATCH /api/agents/instances/{id} to update existing instance"
                    }
                )

            # Build document with automatic timestamps
            now = datetime.now().isoformat()
            insert_doc = {
                "instance_id": instance_id,
                "agent_id": agent_id,
                "position": position,
                "status": payload.get("status", "pending"),  # Default to "pending"
                "created_at": now,
                "updated_at": now,
                "last_execution": None
            }

            # Add screenplay_id (now required)
            screenplay_id = payload.get("screenplay_id")
            logger.info(f"🔍 [DEBUG] Processando screenplay_id:")
            logger.info(f"   - screenplay_id extraído: {screenplay_id}")
            logger.info(f"   - screenplay_id é truthy: {bool(screenplay_id)}")
            insert_doc["screenplay_id"] = screenplay_id
            logger.info(f"   - ✅ screenplay_id adicionado ao insert_doc: {screenplay_id}")

            # Add conversation_id (now required)
            conversation_id = payload.get("conversation_id")
            logger.info(f"🔍 [DEBUG] Processando conversation_id:")
            logger.info(f"   - conversation_id extraído: {conversation_id}")
            logger.info(f"   - conversation_id é truthy: {bool(conversation_id)}")
            insert_doc["conversation_id"] = conversation_id
            logger.info(f"   - ✅ conversation_id adicionado ao insert_doc: {conversation_id}")

            # Add optional fields if provided
            # CWD: Try to inherit from screenplay if not provided
            cwd = payload.get("cwd")
            if not cwd and screenplay_id:
                # Try to get working_directory from screenplay
                try:
                    from bson import ObjectId
                    screenplays = mongo_db["screenplays"]
                    screenplay = screenplays.find_one(
                        {"_id": ObjectId(screenplay_id), "isDeleted": False}
                    )
                    if screenplay and screenplay.get("working_directory"):
                        cwd = screenplay["working_directory"]
                        logger.info(f"✅ [AGENT INSTANCE] Herdando CWD do screenplay {screenplay_id}: {cwd}")
                except Exception as e:
                    logger.warning(f"⚠️ [AGENT INSTANCE] Erro ao buscar working_directory do screenplay: {e}")

            if cwd:
                insert_doc["cwd"] = cwd
            if "config" in payload:
                insert_doc["config"] = payload["config"]
            if "emoji" in payload:
                insert_doc["emoji"] = payload["emoji"]
            if "definition" in payload:
                insert_doc["definition"] = payload["definition"]
            if "display_order" in payload:
                insert_doc["display_order"] = payload["display_order"]

            # Insert into MongoDB
            logger.info(f"🔍 [DEBUG] Documento final a ser inserido no MongoDB:")
            logger.info(f"   - insert_doc completo: {insert_doc}")
            logger.info(f"   - insert_doc contém screenplay_id: {'screenplay_id' in insert_doc}")
            if 'screenplay_id' in insert_doc:
                logger.info(f"   - insert_doc.screenplay_id: {insert_doc['screenplay_id']}")
            
            result = agent_instances.insert_one(insert_doc)
            logger.info(f"Successfully created instance {instance_id} with _id: {result.inserted_id}")

            # Fetch and return the created document
            created_doc = agent_instances.find_one({"_id": result.inserted_id})
            created_doc = mongo_to_dict(created_doc)

            return {
                "success": True,
                "message": "Instance created successfully",
                "instance": created_doc
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating agent instance: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.patch("/api/agents/instances/{instance_id}/cwd")
    async def update_instance_cwd(instance_id: str, payload: dict[str, Any]):
        """Update the current working directory (cwd) for a specific agent instance."""
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            cwd = payload.get("cwd")

            # Validation
            if not cwd or not isinstance(cwd, str):
                raise HTTPException(status_code=400, detail="Invalid cwd path")

            logger.info(f"Updating cwd for instance {instance_id} to: {cwd}")

            agent_instances = mongo_db["agent_instances"]

            # Update MongoDB
            result = agent_instances.update_one(
                {"instance_id": instance_id},
                {
                    "$set": {
                        "cwd": cwd,
                        "updated_at": datetime.now().isoformat()
                    }
                }
            )

            # Check if instance was found
            if result.matched_count == 0:
                logger.warning(f"Instance {instance_id} not found")
                raise HTTPException(
                    status_code=404,
                    detail=f"Instance not found"
                )

            logger.info(f"Successfully updated cwd for instance {instance_id}")

            return {
                "success": True,
                "message": "CWD updated successfully",
                "instance_id": instance_id,
                "cwd": cwd
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating instance cwd: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.patch("/api/agents/instances/{instance_id}/statistics")
    async def update_instance_statistics(instance_id: str, payload: dict[str, Any]):
        """
        Update execution statistics for a specific agent instance.

        This endpoint supports incremental updates to track task executions.

        Payload:
        - task_duration: Duration of the task in milliseconds (will be added to totals)
        - exit_code: Exit code of the task (0 = success, other = error)
        - increment_count: Whether to increment task count (default: True)

        The endpoint automatically:
        - Increments task_count
        - Adds task_duration to total_execution_time
        - Recalculates average_execution_time
        - Updates last_task_duration and last_task_completed_at
        """
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            task_duration = payload.get("task_duration")
            exit_code = payload.get("exit_code", 0)
            increment_count = payload.get("increment_count", True)

            # Validation
            if task_duration is None or not isinstance(task_duration, (int, float)):
                raise HTTPException(
                    status_code=400,
                    detail={"success": False, "error": "task_duration is required and must be a number"}
                )

            if task_duration < 0:
                raise HTTPException(
                    status_code=400,
                    detail={"success": False, "error": "task_duration must be positive"}
                )

            logger.info(f"Updating statistics for instance {instance_id}: duration={task_duration}ms, exit_code={exit_code}")

            agent_instances = mongo_db["agent_instances"]

            # Fetch current instance to calculate new statistics
            current_instance = agent_instances.find_one({"instance_id": instance_id})
            if not current_instance:
                logger.warning(f"Instance {instance_id} not found")
                raise HTTPException(status_code=404, detail={"success": False, "error": "Instance not found"})

            # Get current statistics or initialize
            current_stats = current_instance.get("statistics", {})
            current_task_count = current_stats.get("task_count", 0)
            current_total_time = current_stats.get("total_execution_time", 0.0)
            current_success_count = current_stats.get("success_count", 0)
            current_error_count = current_stats.get("error_count", 0)

            # Calculate new statistics
            new_task_count = current_task_count + 1 if increment_count else current_task_count
            new_total_time = current_total_time + task_duration
            new_average_time = new_total_time / new_task_count if new_task_count > 0 else 0.0

            # Update success/error counts
            new_success_count = current_success_count + (1 if exit_code == 0 else 0)
            new_error_count = current_error_count + (1 if exit_code != 0 else 0)

            # Build update document
            now = datetime.now().isoformat()
            update_doc = {
                "$set": {
                    "statistics": {
                        "task_count": new_task_count,
                        "total_execution_time": new_total_time,
                        "average_execution_time": new_average_time,
                        "last_task_duration": task_duration,
                        "last_task_completed_at": now,
                        "success_count": new_success_count,
                        "error_count": new_error_count,
                        "last_exit_code": exit_code
                    },
                    "updated_at": now,
                    "last_execution": now
                }
            }

            # Update MongoDB
            result = agent_instances.update_one(
                {"instance_id": instance_id},
                update_doc
            )

            if result.matched_count == 0:
                logger.warning(f"Instance {instance_id} not found during update")
                raise HTTPException(status_code=404, detail={"success": False, "error": "Instance not found"})

            logger.info(
                f"Successfully updated statistics for instance {instance_id}: "
                f"count={new_task_count}, total={new_total_time}ms, avg={new_average_time:.2f}ms"
            )

            return {
                "success": True,
                "message": "Statistics updated successfully",
                "instance_id": instance_id,
                "statistics": {
                    "task_count": new_task_count,
                    "total_execution_time": new_total_time,
                    "average_execution_time": new_average_time,
                    "last_task_duration": task_duration,
                    "success_count": new_success_count,
                    "error_count": new_error_count,
                    "success_rate": (new_success_count / new_task_count * 100) if new_task_count > 0 else 0.0
                }
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating instance statistics: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})

    @app.get("/api/agents/instances")
    async def list_agent_instances(
        agent_id: str = None,
        status: str = None,
        limit: int = 100,
        offset: int = 0,
        sort: str = "-created_at",
        include_deleted: bool = False
    ):
        """
        List all agent instances with optional filtering.

        Query parameters:
        - agent_id: Filter by agent_id
        - status: Filter by status (pending|queued|running|completed|error)
        - limit: Maximum number of results (default: 100, max: 500)
        - offset: Pagination offset (default: 0)
        - sort: Sort field, prefix with '-' for descending (default: -created_at)
        - include_deleted: Include soft-deleted instances (default: False)
        """
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            # Build query filter
            query_filter = {}
            if agent_id:
                query_filter["agent_id"] = agent_id
            if status:
                query_filter["status"] = status
            
            # Filter out deleted instances by default
            if not include_deleted:
                query_filter["isDeleted"] = {"$ne": True}

            # Validate and apply limits
            limit = max(1, min(limit, 500))  # Between 1 and 500
            offset = max(0, offset)

            # Parse sort field
            sort_field = sort.lstrip("-")
            sort_direction = -1 if sort.startswith("-") else 1

            logger.info(f"Listing agent instances with filter: {query_filter}, limit: {limit}, offset: {offset}")

            # Query MongoDB
            agent_instances = mongo_db["agent_instances"]
            cursor = agent_instances.find(query_filter)
            cursor = cursor.sort(sort_field, sort_direction).skip(offset).limit(limit)

            instances = []
            for doc in cursor:
                # Convert MongoDB document to JSON-serializable dict
                doc = mongo_to_dict(doc)
                instances.append(doc)

            logger.info(f"Retrieved {len(instances)} agent instances")

            return {
                "success": True,
                "count": len(instances),
                "instances": instances
            }

        except Exception as e:
            logger.error(f"Error listing agent instances: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/agents/instances/{instance_id}")
    async def get_agent_instance(instance_id: str):
        """Get a specific agent instance by ID."""
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            logger.info(f"Fetching agent instance: {instance_id}")

            agent_instances = mongo_db["agent_instances"]
            doc = agent_instances.find_one({"instance_id": instance_id, "isDeleted": {"$ne": True}})

            if not doc:
                logger.warning(f"Instance {instance_id} not found")
                raise HTTPException(
                    status_code=404,
                    detail={
                        "success": False,
                        "error": "Instance not found",
                        "instance_id": instance_id
                    }
                )

            # Convert to JSON-serializable dict
            doc = mongo_to_dict(doc)

            logger.info(f"Retrieved instance {instance_id}")

            return {
                "success": True,
                "instance": doc
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting instance {instance_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.patch("/api/agents/instances/reorder")
    async def reorder_agent_instances(payload: dict[str, Any]):
        """
        🔥 NOVO: Atualiza a ordem de exibição dos agentes no dock.

        Permite que o usuário reordene agentes via drag & drop,
        persistindo a ordem customizada no MongoDB.

        Request body:
        {
            "order_updates": [
                {"instance_id": "instance-xxx", "display_order": 0},
                {"instance_id": "instance-yyy", "display_order": 1},
                ...
            ]
        }

        Returns:
            Confirmação de sucesso com número de agentes atualizados
        """
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            order_updates = payload.get("order_updates", [])

            if not order_updates or not isinstance(order_updates, list):
                raise HTTPException(
                    status_code=400,
                    detail="Campo 'order_updates' é obrigatório e deve ser uma lista"
                )

            logger.info(f"🔄 [REORDER] Atualizando ordem de {len(order_updates)} agentes")

            agent_instances = mongo_db["agent_instances"]
            updated_count = 0

            for update in order_updates:
                instance_id = update.get("instance_id")
                display_order = update.get("display_order")

                if not instance_id or display_order is None:
                    logger.warning(f"⚠️ [REORDER] Update inválido ignorado: {update}")
                    continue

                result = agent_instances.update_one(
                    {"instance_id": instance_id},
                    {
                        "$set": {
                            "display_order": display_order,
                            "updated_at": datetime.now().isoformat()
                        }
                    }
                )

                if result.matched_count > 0:
                    updated_count += 1

            logger.info(f"✅ [REORDER] Ordem atualizada para {updated_count}/{len(order_updates)} agentes")

            return {
                "success": True,
                "message": f"Ordem atualizada para {updated_count} agentes",
                "updated_count": updated_count
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ [REORDER] Erro ao atualizar ordem dos agentes: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.patch("/api/agents/instances/{instance_id}")
    async def update_agent_instance(instance_id: str, payload: dict[str, Any]):
        """
        Update an agent instance (position, status, config, execution_state).

        Updatable fields:
        - position: {"x": float, "y": float}
        - status: "pending"|"queued"|"running"|"completed"|"error"
        - config: {"cwd": string, ...}
        - execution_state: {"start_time": ISO8601, "end_time": ISO8601, "error_message": string, "output": string}
        """
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            # Check if instance exists
            agent_instances = mongo_db["agent_instances"]
            existing = agent_instances.find_one({"instance_id": instance_id})

            if not existing:
                logger.warning(f"Instance {instance_id} not found for update")
                raise HTTPException(
                    status_code=404,
                    detail={
                        "success": False,
                        "error": "Instance not found",
                        "instance_id": instance_id
                    }
                )

            # Build update document
            update_doc = {"$set": {"updated_at": datetime.now().isoformat()}}
            updated_fields = []

            # Update position
            if "position" in payload:
                position = payload["position"]
                if not isinstance(position, dict) or "x" not in position or "y" not in position:
                    raise HTTPException(
                        status_code=400,
                        detail={"success": False, "error": "Invalid position format. Expected: {x: number, y: number}"}
                    )
                update_doc["$set"]["position"] = position
                updated_fields.append("position")

            # Update status
            if "status" in payload:
                status = payload["status"]
                valid_statuses = ["pending", "queued", "running", "completed", "error"]
                if status not in valid_statuses:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "success": False,
                            "error": f"Invalid status. Allowed values: {valid_statuses}"
                        }
                    )
                update_doc["$set"]["status"] = status
                updated_fields.append("status")

            # Update config (merge with existing)
            if "config" in payload:
                config_update = payload["config"]
                if not isinstance(config_update, dict):
                    raise HTTPException(
                        status_code=400,
                        detail={"success": False, "error": "Config must be an object"}
                    )
                for key, value in config_update.items():
                    update_doc["$set"][f"config.{key}"] = value
                updated_fields.append("config")

            # Update execution_state (merge with existing)
            if "execution_state" in payload:
                exec_update = payload["execution_state"]
                if not isinstance(exec_update, dict):
                    raise HTTPException(
                        status_code=400,
                        detail={"success": False, "error": "execution_state must be an object"}
                    )
                for key, value in exec_update.items():
                    update_doc["$set"][f"execution_state.{key}"] = value
                updated_fields.append("execution_state")

            # Perform update
            logger.info(f"Updating instance {instance_id} with fields: {updated_fields}")

            result = agent_instances.update_one(
                {"instance_id": instance_id},
                update_doc
            )

            return {
                "success": True,
                "message": "Instance updated successfully",
                "instance_id": instance_id,
                "updated_fields": updated_fields,
                "updated_at": update_doc["$set"]["updated_at"]
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating instance {instance_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/agents/instances/{instance_id}")
    async def delete_agent_instance(instance_id: str, hard: bool = False, cascade: bool = False):
        """
        Delete an agent instance (soft delete by default).

        Query parameters:
        - hard: If true, performs a hard delete (permanent removal). Default: false (soft delete)
        - cascade: If true with hard delete, also delete related history and logs (default: false)

        Soft delete (default):
        - Sets isDeleted=true on the instance
        - Instance remains in database but is filtered from normal queries

        Hard delete (hard=true):
        - Permanently removes the instance from database
        - If cascade=true, also removes related data
        """
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            # Check if instance exists
            agent_instances = mongo_db["agent_instances"]
            existing = agent_instances.find_one({"instance_id": instance_id})

            if not existing:
                logger.warning(f"Instance {instance_id} not found for deletion")
                raise HTTPException(
                    status_code=404,
                    detail={
                        "success": False,
                        "error": "Instance not found",
                        "instance_id": instance_id
                    }
                )

            # SOFT DELETE (default behavior)
            if not hard:
                logger.info(f"Soft deleting instance {instance_id} (setting isDeleted=true)")

                deletion_timestamp = datetime.now().isoformat()

                # 1. Marcar a instância como deletada
                result = agent_instances.update_one(
                    {"instance_id": instance_id},
                    {
                        "$set": {
                            "isDeleted": True,
                            "deleted_at": deletion_timestamp,
                            "updated_at": deletion_timestamp
                        }
                    }
                )

                # 2. Propagar soft-delete para mensagens de histórico
                history_collection = mongo_db["history"]
                history_result = history_collection.update_many(
                    {"instance_id": instance_id},
                    {
                        "$set": {
                            "isDeleted": True,
                            "deleted_at": deletion_timestamp
                        }
                    }
                )

                history_count = history_result.modified_count
                logger.info(
                    f"Successfully soft deleted instance {instance_id} "
                    f"and {history_count} history messages"
                )

                return {
                    "success": True,
                    "message": "Instance soft deleted successfully (marked as deleted)",
                    "instance_id": instance_id,
                    "deletion_type": "soft",
                    "isDeleted": True,
                    "history_messages_affected": history_count
                }

            # HARD DELETE (permanent removal)
            cascade_deleted = {}

            # Delete related data if cascade=true
            if cascade:
                logger.info(f"Cascade deleting related data for instance {instance_id}")

                # Delete from history collection
                history_collection = mongo_db["history"]
                history_result = history_collection.delete_many({"instance_id": instance_id})
                cascade_deleted["history_records"] = history_result.deleted_count

                # Delete from agent_chat_history collection (if exists)
                if "agent_chat_history" in mongo_db.list_collection_names():
                    chat_history_collection = mongo_db["agent_chat_history"]
                    chat_result = chat_history_collection.delete_many({"instance_id": instance_id})
                    cascade_deleted["chat_history_records"] = chat_result.deleted_count

                # Delete from agent_conversations collection (if exists)
                if "agent_conversations" in mongo_db.list_collection_names():
                    conversations_collection = mongo_db["agent_conversations"]
                    conv_result = conversations_collection.delete_many({"instance_id": instance_id})
                    cascade_deleted["conversation_records"] = conv_result.deleted_count

            # Delete the instance itself (permanent)
            logger.info(f"Hard deleting instance {instance_id} (permanent removal)")
            result = agent_instances.delete_one({"instance_id": instance_id})

            logger.info(f"Successfully hard deleted instance {instance_id}, cascade_deleted: {cascade_deleted}")

            return {
                "success": True,
                "message": "Instance permanently deleted",
                "instance_id": instance_id,
                "deletion_type": "hard",
                "cascade_deleted": cascade_deleted if cascade else None
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting instance {instance_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/tasks")
    async def list_tasks(
        status: str = Query(None, description="Filter by status (processing|completed|error)"),
        agent_id: str = Query(None, description="Filter by agent_id"),
        limit: int = Query(100, ge=1, le=500, description="Maximum number of results (default: 100, max: 500)"),
        offset: int = Query(0, ge=0, description="Pagination offset (default: 0)"),
        sort: str = Query("-created_at", description="Sort field, prefix with '-' for descending (default: -created_at)")
    ):
        """
        List all tasks with optional filtering by status and agent_id.

        Query parameters:
        - status: Filter by status (processing|completed|error) - optional
        - agent_id: Filter by agent_id - optional
        - limit: Maximum number of results (default: 100, max: 500)
        - offset: Pagination offset (default: 0)
        - sort: Sort field, prefix with '-' for descending (default: -created_at)

        Returns:
        - success: Boolean indicating success
        - count: Number of tasks returned
        - total: Total number of tasks matching filter
        - tasks: Array of task documents
        """
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            tasks_collection = mongo_db["tasks"]

            # Build query filter
            query_filter = {}
            if status:
                query_filter["status"] = status
            if agent_id:
                query_filter["agent_id"] = agent_id

            # Get total count
            total = tasks_collection.count_documents(query_filter)

            # Parse sort field
            sort_field = sort.lstrip("-")
            sort_direction = -1 if sort.startswith("-") else 1

            logger.info(f"Listing tasks with filter: {query_filter}, limit={limit}, offset={offset}, sort={sort}, total={total}")

            # Query MongoDB with pagination
            cursor = tasks_collection.find(query_filter)
            cursor = cursor.sort(sort_field, sort_direction).skip(offset).limit(limit)

            tasks = []
            for doc in cursor:
                # Convert MongoDB document to JSON-serializable dict
                doc = mongo_to_dict(doc)
                tasks.append(doc)

            logger.info(f"Retrieved {len(tasks)} tasks out of {total} total")

            return {
                "success": True,
                "count": len(tasks),
                "total": total,
                "tasks": tasks
            }

        except Exception as e:
            logger.error(f"Error listing tasks: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/tasks/processing")
    async def list_processing_tasks(
        limit: int = Query(100, ge=1, le=500, description="Maximum number of results (default: 100, max: 500)"),
        offset: int = Query(0, ge=0, description="Pagination offset (default: 0)"),
        sort: str = Query("-created_at", description="Sort field, prefix with '-' for descending (default: -created_at)")
    ):
        """
        List all tasks with status 'processing' with pagination.
        This is a convenience endpoint, equivalent to GET /api/tasks?status=processing

        Query parameters:
        - limit: Maximum number of results (default: 100, max: 500)
        - offset: Pagination offset (default: 0)
        - sort: Sort field, prefix with '-' for descending (default: -created_at)

        Returns:
        - success: Boolean indicating success
        - count: Number of tasks returned
        - total: Total number of processing tasks
        - tasks: Array of task documents
        """
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            tasks_collection = mongo_db["tasks"]

            # Build query filter for processing status
            query_filter = {"status": "processing"}

            # Get total count
            total = tasks_collection.count_documents(query_filter)

            # Parse sort field
            sort_field = sort.lstrip("-")
            sort_direction = -1 if sort.startswith("-") else 1

            logger.info(f"Listing processing tasks: limit={limit}, offset={offset}, sort={sort}, total={total}")

            # Query MongoDB with pagination
            cursor = tasks_collection.find(query_filter)
            cursor = cursor.sort(sort_field, sort_direction).skip(offset).limit(limit)

            tasks = []
            for doc in cursor:
                # Convert MongoDB document to JSON-serializable dict
                doc = mongo_to_dict(doc)
                tasks.append(doc)

            logger.info(f"Retrieved {len(tasks)} processing tasks out of {total} total")

            return {
                "success": True,
                "count": len(tasks),
                "total": total,
                "tasks": tasks
            }

        except Exception as e:
            logger.error(f"Error listing processing tasks: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/tasks/events")
    async def list_tasks_as_events(
        limit: int = Query(50, ge=1, le=200, description="Maximum number of events to return (default: 50, max: 200)"),
        include_councilors: bool = Query(True, description="Include councilor executions (default: true)"),
        include_regular: bool = Query(True, description="Include regular agent executions (default: true)")
    ):
        """
        List recent tasks formatted as gamification events for the frontend.

        This endpoint transforms MongoDB task documents into the same event format
        used by WebSocket real-time events, enabling historical event loading after page reloads.

        Query parameters:
        - limit: Maximum number of events (default: 50, max: 200)
        - include_councilors: Include councilor executions (default: true)
        - include_regular: Include regular agent executions (default: true)

        Returns:
        - success: Boolean indicating success
        - count: Number of events returned
        - events: Array of gamification events with format:
          {
            "type": "agent_execution_completed" | "agent_execution_error",
            "data": {
              "execution_id": str,
              "agent_id": str,
              "agent_name": str,
              "agent_emoji": str,
              "status": str,
              "severity": str,
              "summary": str,
              "duration_ms": int,
              "completed_at": str,
              "is_councilor": bool,
              "level": "result" | "debug"
            },
            "timestamp": int (milliseconds)
          }
        """
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            tasks_collection = mongo_db["tasks"]
            agents_collection = mongo_db["agents"]

            # Build query filter
            query_filter = {"status": {"$in": ["completed", "error"]}}

            # Filter by execution type
            councilor_filters = []
            if include_councilors:
                councilor_filters.append({"is_councilor_execution": True})
            if include_regular:
                councilor_filters.append({"is_councilor_execution": {"$ne": True}})

            if councilor_filters:
                if len(councilor_filters) == 1:
                    query_filter.update(councilor_filters[0])
                else:
                    query_filter["$or"] = councilor_filters

            logger.info(f"Listing tasks as events with filter: {query_filter}, limit={limit}")

            # Query MongoDB sorted by completed_at descending (most recent first)
            cursor = tasks_collection.find(query_filter)
            cursor = cursor.sort("completed_at", -1).limit(limit)

            # Build agent cache to avoid repeated lookups
            agent_cache = {}

            events = []
            for task_doc in cursor:
                agent_id = task_doc.get("agent_id", "unknown")

                # Get agent metadata (cached)
                if agent_id not in agent_cache:
                    agent = agents_collection.find_one({"agent_id": agent_id})
                    if agent:
                        definition = agent.get("definition", {})
                        agent_cache[agent_id] = {
                            "name": definition.get("name", agent_id),
                            "emoji": definition.get("emoji", "🤖")
                        }
                    else:
                        agent_cache[agent_id] = {
                            "name": agent_id,
                            "emoji": "🤖"
                        }

                agent_meta = agent_cache[agent_id]

                # Determine event type
                status = task_doc.get("status", "completed")
                event_type = "agent_execution_error" if status == "error" else "agent_execution_completed"

                # Extract task data
                task_id = task_doc.get("task_id", "")
                severity = task_doc.get("severity", "success")
                result = task_doc.get("result", "")
                duration = task_doc.get("duration", 0)
                completed_at = task_doc.get("completed_at")
                is_councilor = task_doc.get("is_councilor_execution", False)

                # Generate summary
                summary = result[:200] if result else "Execução concluída"
                if len(result) > 200:
                    summary += "..."

                # Determine level (result for councilors/errors, debug for regular executions)
                level = "result" if is_councilor or status == "error" else "debug"

                # Convert timestamp to milliseconds
                timestamp_ms = int(completed_at.timestamp() * 1000) if completed_at else 0

                # Build event in same format as WebSocket
                event = {
                    "type": event_type,
                    "data": {
                        "execution_id": task_id,
                        "agent_id": agent_id,
                        "agent_name": agent_meta["name"],
                        "agent_emoji": agent_meta["emoji"],
                        "status": status,
                        "severity": severity,
                        "summary": summary,
                        "duration_ms": int(duration * 1000),
                        "completed_at": completed_at.isoformat() if completed_at else None,
                        "is_councilor": is_councilor,
                        "level": level
                    },
                    "timestamp": timestamp_ms
                }

                events.append(event)

            logger.info(f"Retrieved {len(events)} tasks as events")

            return {
                "success": True,
                "count": len(events),
                "events": events
            }

        except Exception as e:
            logger.error(f"Error listing tasks as events: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/tasks/{task_id}/details")
    async def get_task_details(task_id: str):
        """
        Get complete task details including full prompt and result (not truncated).

        This endpoint is used by the report modal to load complete task data
        when the user wants to see the full prompt and result.

        Path parameters:
        - task_id: The unique task execution ID

        Returns:
        - success: Boolean indicating success
        - task: Complete task object with full prompt and result:
          {
            "task_id": str,
            "agent_id": str,
            "agent_name": str,
            "agent_emoji": str,
            "prompt": str | null,  # Full input text (if available)
            "result": str | null,  # Full result (not truncated)
            "status": str,
            "severity": str,
            "created_at": str,
            "completed_at": str,
            "duration": float,
            "error": str | null,
            "is_councilor": bool
          }
        """
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            tasks_collection = mongo_db["tasks"]
            agents_collection = mongo_db["agents"]

            logger.info(f"Fetching task details for task_id: {task_id}")

            # Find task by task_id (try multiple fields as fallback)
            task_doc = tasks_collection.find_one({"task_id": task_id})

            # Fallback: try searching by _id if it looks like an ObjectId
            if not task_doc:
                try:
                    from bson import ObjectId
                    if len(task_id) == 24:  # ObjectId length
                        task_doc = tasks_collection.find_one({"_id": ObjectId(task_id)})
                except Exception:
                    pass

            if not task_doc:
                logger.warning(f"Task not found: {task_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Task não encontrada. Este evento pode não ter dados completos salvos no banco de dados."
                )

            # Get agent metadata
            agent_id = task_doc.get("agent_id", "unknown")
            agent = agents_collection.find_one({"agent_id": agent_id})

            if agent:
                definition = agent.get("definition", {})
                agent_name = definition.get("name", agent_id)
                agent_emoji = definition.get("emoji", "🤖")
            else:
                agent_name = agent_id
                agent_emoji = "🤖"

            # Build complete task details
            task_details = {
                "task_id": task_doc.get("task_id", ""),
                "agent_id": agent_id,
                "agent_name": agent_name,
                "agent_emoji": agent_emoji,
                "prompt": task_doc.get("prompt") or task_doc.get("input_text"),  # Try both fields
                "result": task_doc.get("result"),  # Full result, not truncated
                "status": task_doc.get("status", "unknown"),
                "severity": task_doc.get("severity", "info"),
                "created_at": task_doc.get("created_at").isoformat() if task_doc.get("created_at") else None,
                "completed_at": task_doc.get("completed_at").isoformat() if task_doc.get("completed_at") else None,
                "duration": task_doc.get("duration", 0),
                "error": task_doc.get("error"),
                "is_councilor": task_doc.get("is_councilor_execution", False)
            }

            logger.info(f"Successfully retrieved task details for {task_id}")

            return {
                "success": True,
                "task": task_details
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching task details for {task_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/agents/context/{instance_id}")
    async def get_agent_context(instance_id: str):
        """Get full context (persona, procedure, history) for a specific agent instance."""
        logger.info(f"📖 [GATEWAY] get_agent_context chamado para instance_id: {instance_id}")
        
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            # 1. Get agent_id from agent_instances collection
            agent_instances_collection = mongo_db["agent_instances"]
            logger.info(f"   - Buscando em agent_instances collection...")
            instance_doc = agent_instances_collection.find_one({"instance_id": instance_id})
            logger.info(f"   - Documento encontrado: {instance_doc is not None}")

            if not instance_doc:
                logger.error(f"❌ [GATEWAY] Instance '{instance_id}' não encontrado em agent_instances")
                raise HTTPException(
                    status_code=404,
                    detail=f"Instance '{instance_id}' not found"
                )

            agent_id = instance_doc.get("agent_id")
            if not agent_id:
                raise HTTPException(
                    status_code=500,
                    detail=f"Instance '{instance_id}' has no associated agent_id"
                )

            # 2. Get persona and definition from agents collection
            agents_collection = mongo_db["agents"]
            agent_doc = agents_collection.find_one({"agent_id": agent_id})

            persona = ""
            operating_procedure = ""

            if agent_doc:
                # Extract persona.content (it's an object with 'content' field)
                persona_obj = agent_doc.get("persona", {})
                if isinstance(persona_obj, dict):
                    persona = persona_obj.get("content", "")
                else:
                    persona = str(persona_obj)

                # Extract definition (use as operating_procedure)
                definition = agent_doc.get("definition")
                if definition:
                    # Convert definition object to string if needed
                    if isinstance(definition, dict):
                        import json
                        operating_procedure = json.dumps(definition, indent=2)
                    else:
                        operating_procedure = str(definition)
            else:
                logger.warning(f"Agent '{agent_id}' not found in agents collection")

            # 3. Fetch history for the instance
            history_collection = mongo_db["history"]
            history_cursor = history_collection.find({"instance_id": instance_id}).sort("timestamp", 1)
            history = [mongo_to_dict(dict(item)) for item in history_cursor]

            # 4. Get cwd from instance document
            cwd = instance_doc.get("cwd")

            logger.info(
                f"Retrieved context for instance {instance_id}: "
                f"agent_id={agent_id}, history_count={len(history)}, cwd={cwd}"
            )

            # 5. Build and return complete JSON
            return {
                "persona": persona,
                "operating_procedure": operating_procedure,
                "history": history,
                "cwd": cwd
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error retrieving context for instance {instance_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    return app
