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
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pymongo import MongoClient

from src.clients.conductor_client import ConductorClient
from src.config.settings import CONDUCTOR_CONFIG, MONGODB_CONFIG, SERVER_CONFIG
from src.utils.mcp_utils import init_agent

logger = logging.getLogger(__name__)

# SSE Stream Manager - Global dictionary to manage active streams
ACTIVE_STREAMS: dict[str, asyncio.Queue] = {}

# MongoDB client - will be initialized in lifespan
mongo_client: MongoClient | None = None
mongo_db = None

# Conductor API client - will be initialized in lifespan
conductor_client: ConductorClient | None = None


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
    global mongo_client, mongo_db, conductor_client

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
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        mongo_client = None
        mongo_db = None

    # Initialize Conductor API client
    conductor_api_url = CONDUCTOR_CONFIG.get("conductor_api_url", "http://conductor-api:8000")
    conductor_client = ConductorClient(base_url=conductor_api_url)
    logger.info(f"Initialized ConductorClient with URL: {conductor_api_url}")

    # Start MCP server in daemon thread
    mcp_thread = threading.Thread(target=start_mcp_server, daemon=True, name="MCP-Server-Thread")
    mcp_thread.start()

    # Give MCP server time to start
    await asyncio.sleep(2)

    yield

    # Shutdown
    logger.info("Conductor Gateway API shutting down...")

    # Close Conductor client
    if conductor_client:
        await conductor_client.close()
        logger.info("ConductorClient closed")

    # Close MongoDB connection
    if mongo_client:
        mongo_client.close()
        logger.info("MongoDB connection closed")


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
            timeout_value = payload.get("timeout", 300)
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
            timeout = payload.get("timeout", 300)
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
            },
        }

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
                        "id": str(agent.get("_id", "")),
                        "agent_id": agent.get("agent_id", ""),
                        "name": definition.get("name", ""),
                        "emoji": definition.get("emoji", "🤖"),
                        "description": definition.get("description", ""),
                        "model": definition.get("model", "claude"),
                        "tags": definition.get("tags", [])
                    })
                else:
                    # Schema simples (fallback)
                    agents.append({
                        "id": str(agent.get("_id", "")),
                        "agent_id": agent.get("name", ""),
                        "name": agent.get("name", ""),
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

    @app.post("/api/agents/{agent_id}/execute")
    async def execute_agent_by_id(agent_id: str, payload: dict[str, Any]):
        """
        Execute a specific agent with input text and optional instance_id for context isolation.

        Payload format:
        {
            "input_text": "Text to process",
            "instance_id": "uuid-optional",
            "context_mode": "stateful|stateless",
            "document_id": "optional-document-id",
            "position": {"x": 100, "y": 200}
        }
        """
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        if not conductor_client:
            raise HTTPException(status_code=503, detail="Conductor client not available")

        try:
            # Validate payload
            input_text = payload.get("input_text")
            instance_id = payload.get("instance_id")
            context_mode = payload.get("context_mode", "stateless")
            document_id = payload.get("document_id")
            position = payload.get("position")

            if not input_text:
                raise HTTPException(status_code=400, detail="input_text is required")

            logger.info(
                f"[/api/agents/{agent_id}/execute] Executing agent with instance_id: {instance_id}, "
                f"context_mode: {context_mode}, input: {input_text[:100]}..."
            )

            # Get agent from MongoDB to verify it exists
            agents_collection = mongo_db["agents"]
            # Try to find by agent_id first, then fallback to name for compatibility
            agent = agents_collection.find_one({"agent_id": agent_id})
            if not agent:
                agent = agents_collection.find_one({"name": agent_id})

            if not agent:
                raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

            # Get the actual agent_id for consistent referencing
            actual_agent_id = agent.get("agent_id") or agent.get("name")

            # Execute the agent via Conductor API
            response = await conductor_client.execute_agent(
                agent_name=agent.get("name") or agent_id,
                prompt=input_text,
                instance_id=instance_id,
                context_mode=context_mode,
                cwd=CONDUCTOR_CONFIG.get("project_path"),
                timeout=CONDUCTOR_CONFIG.get("timeout", 300),
            )

            # Extract result from response
            result_text = response.get("result") or response.get("stdout") or str(response)

            # Save/update metadata for instance (if instance_id provided)
            if instance_id:
                agent_instances = mongo_db["agent_instances"]
                update_data = {
                    "agent_id": actual_agent_id,
                    "last_execution": datetime.now().isoformat(),
                }

                # Add optional fields if provided
                if document_id:
                    update_data["document_id"] = document_id
                if position:
                    update_data["position"] = position

                # Check if this is first execution
                existing = agent_instances.find_one({"instance_id": instance_id})
                if not existing:
                    update_data["created_at"] = datetime.now().isoformat()

                agent_instances.update_one(
                    {"instance_id": instance_id}, {"$set": update_data}, upsert=True
                )

                logger.info(f"Updated metadata for instance {instance_id}")

                # Note: Conversation history is now saved by conductor-api in agent_conversations collection
                # This avoids duplication and keeps history management centralized

            return {
                "status": "success",
                "result": response,
                "instance_id": instance_id,
                "context_mode": context_mode,
            }

        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"Conductor API error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Conductor API error: {e.response.text}",
            )
        except Exception as e:
            logger.error(f"Error executing agent {agent_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/agents/context/{instance_id}")
    async def get_agent_context(instance_id: str):
        """Get full context (persona, procedure, history) for a specific agent instance."""
        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        try:
            # 1. Get agent_id from agent_instances collection
            agent_instances_collection = mongo_db["agent_instances"]
            instance_doc = agent_instances_collection.find_one({"instance_id": instance_id})

            if not instance_doc:
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

            logger.info(
                f"Retrieved context for instance {instance_id}: "
                f"agent_id={agent_id}, history_count={len(history)}"
            )

            # 4. Build and return complete JSON
            return {
                "persona": persona,
                "operating_procedure": operating_procedure,
                "history": history
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error retrieving context for instance {instance_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    return app
