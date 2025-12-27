"""
Councilor Router - API endpoints for councilor management

Provides endpoints for:
- Listing councilors
- Promoting/demoting agents
- Updating configurations
- Managing executions and reports
"""

import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...core.database import get_database
from ...services.councilor_service import CouncilorService
from ...services.councilor_scheduler import CouncilorBackendScheduler
from ...models.councilor import (
    PromoteToCouncilorRequest,
    UpdateCouncilorConfigRequest,
    UpdateScheduleRequest,
    CouncilorExecutionCreate,
    AgentWithCouncilorResponse,
    AgentListResponse,
    ExecutionListResponse,
    CouncilorExecutionResponse,
    CouncilorReportResponse,
    SuccessResponse,
    ScheduleResponse,
    # New instance-based models
    PromoteToCouncilorInstanceRequest,
    CouncilorInstanceResponse,
    CouncilorInstanceListResponse,
)

logger = logging.getLogger(__name__)


def _datetime_to_str(value) -> Optional[str]:
    """Convert datetime to ISO string, or return string as-is, or None"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


# Initialize router
router = APIRouter(
    prefix="/api/councilors",
    tags=["councilors"],
    responses={404: {"description": "Not found"}},
)


# ========== Dependency Injection ==========

def get_councilor_service(
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> CouncilorService:
    """Get councilor service instance"""
    return CouncilorService(db)


def get_councilor_scheduler() -> Optional[CouncilorBackendScheduler]:
    """Get councilor scheduler instance"""
    from ...api.app import councilor_scheduler
    return councilor_scheduler


# ========== Debug Endpoints ==========

@router.get("/scheduler/jobs")
async def get_scheduled_jobs(
    scheduler: Optional[CouncilorBackendScheduler] = Depends(get_councilor_scheduler)
):
    """Get list of scheduled jobs for debugging"""
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not available")

    jobs = scheduler.get_scheduled_jobs()
    return {"jobs": jobs, "count": len(jobs)}


# ========== Instance-Based Councilor Endpoints (NEW) ==========

@router.post(
    "/promote",
    response_model=CouncilorInstanceResponse,
    status_code=status.HTTP_201_CREATED
)
async def promote_to_councilor_instance(
    request: PromoteToCouncilorInstanceRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    scheduler: Optional[CouncilorBackendScheduler] = Depends(get_councilor_scheduler)
):
    """
    Promote an agent template to a councilor instance.

    This creates:
    1. A new screenplay for the councilor
    2. A new conversation in the screenplay
    3. A new agent_instance with councilor configuration

    **Request Body:**
    - `agent_id`: ID of the agent template to promote
    - `councilor_config`: Complete councilor configuration
    - `customization` (optional): Visual customization

    **Returns:**
    - instance_id, screenplay_id, conversation_id
    """
    import httpx
    from datetime import datetime
    from src.config.settings import CONDUCTOR_CONFIG

    agent_id = request.agent_id
    councilor_config = request.councilor_config
    customization = request.customization

    try:
        logger.info(f"⭐ [PROMOTE] Promoting agent '{agent_id}' to councilor instance")

        # 1. Validate agent template exists
        agents_collection = db.agents
        agent = await agents_collection.find_one({"agent_id": agent_id})

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent template '{agent_id}' not found"
            )

        # Get display name from customization or agent
        display_name = (
            customization.display_name if customization and customization.display_name
            else agent.get("definition", {}).get("name", agent_id)
        )

        # Generate unique IDs
        timestamp = int(datetime.utcnow().timestamp() * 1000)
        instance_id = f"councilor_{agent_id}_{timestamp}"

        # 2. Create screenplay for councilor
        logger.info(f"📜 [PROMOTE] Creating screenplay for councilor '{display_name}'")

        screenplays_collection = db.screenplays
        screenplay_name = f"Councilor: {display_name}"
        screenplay_content = f"""# {screenplay_name}

## Configuração
- **Agente:** {agent.get('definition', {}).get('name', agent_id)}
- **Tarefa:** {councilor_config.task.name}
- **Agendamento:** {councilor_config.schedule.type}={councilor_config.schedule.value}

## Descrição
{councilor_config.task.prompt[:500]}...

---
*Este screenplay foi criado automaticamente para rastrear execuções do conselheiro.*
"""

        now = datetime.utcnow()
        screenplay_doc = {
            "name": screenplay_name,
            "description": f"Screenplay para conselheiro: {councilor_config.title}",
            "tags": ["councilor", "auto-generated"],
            "content": screenplay_content,
            "isDeleted": False,
            "version": 1,
            "createdAt": now,
            "updatedAt": now,
        }

        screenplay_result = await screenplays_collection.insert_one(screenplay_doc)
        screenplay_id = str(screenplay_result.inserted_id)
        logger.info(f"✅ [PROMOTE] Created screenplay: {screenplay_id}")

        # 3. Create conversation via Conductor API
        logger.info(f"💬 [PROMOTE] Creating conversation for councilor")

        conductor_url = CONDUCTOR_CONFIG.get('conductor_api_url', 'http://localhost:8000')
        conversation_payload = {
            "title": f"Histórico: {display_name}",
            "screenplay_id": screenplay_id,
            "agent_id": agent_id
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{conductor_url}/conversations/",
                    json=conversation_payload
                )

                if response.status_code not in (200, 201):
                    logger.error(f"❌ [PROMOTE] Failed to create conversation: {response.status_code} - {response.text}")
                    # Rollback: delete screenplay
                    await screenplays_collection.delete_one({"_id": screenplay_result.inserted_id})
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Failed to create conversation: {response.text}"
                    )

                conversation_data = response.json()
                conversation_id = conversation_data.get("conversation_id") or conversation_data.get("id")
                logger.info(f"✅ [PROMOTE] Created conversation: {conversation_id}")

        except httpx.RequestError as e:
            logger.error(f"❌ [PROMOTE] Connection error to Conductor API: {e}")
            # Rollback: delete screenplay
            await screenplays_collection.delete_one({"_id": screenplay_result.inserted_id})
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not connect to Conductor API: {str(e)}"
            )

        # 4. Create agent_instance via internal call (same structure as POST /api/agents/instances)
        # This ensures councilor instances have the SAME structure as chat instances
        logger.info(f"🏛️ [PROMOTE] Creating councilor instance: {instance_id}")

        agent_instances = db.agent_instances

        # Extract agent definition for normalized fields
        agent_definition = agent.get("definition", {})
        agent_emoji = agent_definition.get("emoji", "🏛️")

        # Build instance document with SAME structure as POST /api/agents/instances
        instance_doc = {
            # Required fields (same as chat)
            "instance_id": instance_id,
            "agent_id": agent_id,
            "screenplay_id": screenplay_id,
            "conversation_id": conversation_id,
            "position": {"x": 100, "y": 100},
            "status": "idle",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "last_execution": None,

            # Optional fields (same as chat)
            "cwd": request.cwd,
            "emoji": agent_emoji,
            "display_order": 0,
            "definition": {
                "title": agent_definition.get("name", agent_id),
                "description": agent_definition.get("description", ""),
                "unicode": agent_definition.get("unicode", "")
            },

            # Statistics (same as chat - initialized)
            "statistics": {
                "task_count": 0,
                "total_execution_time": 0.0,
                "average_execution_time": 0.0,
                "last_task_duration": 0.0,
                "last_task_completed_at": None,
                "success_count": 0,
                "error_count": 0,
                "last_exit_code": None,
                "total_executions": 0,
                "success_rate": 0.0,
                "last_execution": None
            },

            # Councilor-specific fields (extra)
            "is_councilor_instance": True,
            "councilor_config": councilor_config.model_dump(),
            "customization": customization.model_dump() if customization else None,
        }

        await agent_instances.insert_one(instance_doc)
        logger.info(f"✅ [PROMOTE] Created councilor instance: {instance_id}")

        # 5. Schedule in backend scheduler if available and enabled
        if scheduler and councilor_config.schedule.enabled:
            try:
                # Build councilor dict similar to legacy format for scheduler
                councilor_dict = {
                    "agent_id": agent_id,
                    "instance_id": instance_id,
                    "screenplay_id": screenplay_id,
                    "conversation_id": conversation_id,
                    "definition": agent.get("definition", {}),
                    "councilor_config": councilor_config.model_dump(),
                    "customization": customization.model_dump() if customization else None,
                    "cwd": request.cwd,  # Pass cwd to scheduler
                }
                await scheduler.schedule_councilor_instance(councilor_dict)
                logger.info(f"✅ [PROMOTE] Scheduled councilor '{instance_id}' in backend scheduler")
            except Exception as e:
                logger.warning(f"⚠️ [PROMOTE] Failed to schedule councilor: {e}")
                # Don't fail - instance was created, scheduler can pick it up on restart

        return CouncilorInstanceResponse(
            success=True,
            message=f"Agent '{agent_id}' promoted to councilor successfully",
            instance_id=instance_id,
            screenplay_id=screenplay_id,
            conversation_id=conversation_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [PROMOTE] Error promoting agent: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to promote agent: {str(e)}"
        )


@router.get(
    "/instances",
    response_model=CouncilorInstanceListResponse,
    status_code=status.HTTP_200_OK
)
async def list_councilor_instances(
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    List all councilor instances (from agent_instances collection).

    **Returns:**
    - List of councilor instances with agent template data
    """
    try:
        logger.info("📋 [INSTANCES] Listing councilor instances")

        agent_instances = db.agent_instances
        agents_collection = db.agents

        # Find all councilor instances
        cursor = agent_instances.find({
            "is_councilor_instance": True,
            "$or": [
                {"isDeleted": {"$ne": True}},
                {"isDeleted": {"$exists": False}}
            ]
        })

        instances = await cursor.to_list(length=None)

        # Enrich with agent template data
        result_instances = []
        for instance in instances:
            # Get agent template
            agent = await agents_collection.find_one({"agent_id": instance.get("agent_id")})

            # Get agent definition for fallback values
            agent_def = agent.get("definition", {}) if agent else {}

            result_instance = {
                "instance_id": instance.get("instance_id"),
                "agent_id": instance.get("agent_id"),
                "screenplay_id": instance.get("screenplay_id"),
                "conversation_id": instance.get("conversation_id"),
                "is_councilor_instance": True,
                "councilor_config": instance.get("councilor_config"),
                "customization": instance.get("customization"),
                "cwd": instance.get("cwd"),

                # Normalized fields (same as regular agent_instances)
                "emoji": instance.get("emoji") or agent_def.get("emoji", "🏛️"),
                "display_order": instance.get("display_order", 0),
                "definition": instance.get("definition") or {
                    "title": agent_def.get("name", instance.get("agent_id")),
                    "description": agent_def.get("description", ""),
                    "unicode": agent_def.get("unicode", "")
                },
                "position": instance.get("position", {"x": 100, "y": 100}),

                # Statistics (normalized) - prefer 'statistics', fallback to 'stats'
                "statistics": instance.get("statistics") or instance.get("stats", {
                    "task_count": 0,
                    "total_execution_time": 0.0,
                    "average_execution_time": 0.0,
                    "success_count": 0,
                    "error_count": 0,
                    "total_executions": 0,
                    "success_rate": 0.0,
                    "last_execution": None
                }),

                "status": instance.get("status", "idle"),
                "last_execution": _datetime_to_str(instance.get("last_execution")),
                "created_at": _datetime_to_str(instance.get("created_at")),
                "updated_at": _datetime_to_str(instance.get("updated_at")),

                # Agent template data (for backwards compatibility)
                "agent_name": agent_def.get("name"),
                "agent_emoji": agent_def.get("emoji"),
                "agent_description": agent_def.get("description"),
            }
            result_instances.append(result_instance)

        logger.info(f"📋 [INSTANCES] Found {len(result_instances)} councilor instances")

        return CouncilorInstanceListResponse(
            instances=result_instances,
            count=len(result_instances)
        )

    except Exception as e:
        logger.error(f"❌ [INSTANCES] Error listing councilor instances: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list councilor instances: {str(e)}"
        )


@router.delete(
    "/instances/{instance_id}",
    response_model=CouncilorInstanceResponse,
    status_code=status.HTTP_200_OK
)
async def demote_councilor_instance(
    instance_id: str = Path(..., description="Instance ID of the councilor to demote"),
    db: AsyncIOMotorDatabase = Depends(get_database),
    scheduler: Optional[CouncilorBackendScheduler] = Depends(get_councilor_scheduler)
):
    """
    Remove a councilor instance (soft delete).

    **Path Parameters:**
    - `instance_id`: Instance ID of the councilor

    **Returns:**
    - Success message
    """
    try:
        logger.info(f"🔻 [DEMOTE] Demoting councilor instance: {instance_id}")

        agent_instances = db.agent_instances

        # Find instance
        instance = await agent_instances.find_one({"instance_id": instance_id})

        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Councilor instance '{instance_id}' not found"
            )

        if not instance.get("is_councilor_instance"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Instance '{instance_id}' is not a councilor"
            )

        # Soft delete
        from datetime import datetime
        await agent_instances.update_one(
            {"instance_id": instance_id},
            {
                "$set": {
                    "isDeleted": True,
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
        )

        # Remove from scheduler if available
        if scheduler:
            try:
                # 🔥 Use instance_id como job_id (é assim que o job foi criado)
                # O scheduler usa instance_id como job_id: job_id = instance_id or agent_id
                await scheduler.remove_councilor(instance_id)
                logger.info(f"✅ [DEMOTE] Removed job '{instance_id}' from scheduler")
            except Exception as e:
                logger.warning(f"⚠️ [DEMOTE] Failed to remove from scheduler: {e}")

        logger.info(f"✅ [DEMOTE] Councilor instance '{instance_id}' demoted")

        return CouncilorInstanceResponse(
            success=True,
            message=f"Councilor instance '{instance_id}' demoted successfully",
            instance_id=instance_id,
            screenplay_id=instance.get("screenplay_id"),
            conversation_id=instance.get("conversation_id")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [DEMOTE] Error demoting councilor: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to demote councilor: {str(e)}"
        )


@router.post(
    "/instances/{instance_id}/execute-now",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK
)
async def execute_instance_now(
    instance_id: str = Path(..., description="Instance ID of the councilor to execute"),
    db: AsyncIOMotorDatabase = Depends(get_database),
    scheduler: Optional[CouncilorBackendScheduler] = Depends(get_councilor_scheduler)
):
    """
    Execute a councilor instance's task immediately.

    **Path Parameters:**
    - `instance_id`: Instance ID of the councilor

    **Returns:**
    - Execution result with status and stats
    """
    try:
        logger.info(f"🚀 [EXECUTE NOW] Triggering instance: {instance_id}")

        # Find instance
        agent_instances = db.agent_instances
        instance = await agent_instances.find_one({
            "instance_id": instance_id,
            "is_councilor_instance": True,
            "$or": [
                {"isDeleted": {"$ne": True}},
                {"isDeleted": {"$exists": False}}
            ]
        })

        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Councilor instance '{instance_id}' not found"
            )

        agent_id = instance.get("agent_id")

        # Execute via scheduler
        if scheduler:
            result = await scheduler.execute_councilor_now(agent_id, instance_id)
            logger.info(f"✅ [EXECUTE NOW] Instance '{instance_id}' executed successfully")

            return SuccessResponse(
                success=True,
                message=f"Councilor instance '{instance_id}' executed successfully",
                execution=result
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Scheduler not available"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [EXECUTE NOW] Error executing instance: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute instance: {str(e)}"
        )


@router.patch(
    "/instances/{instance_id}/schedule",
    response_model=ScheduleResponse,
    status_code=status.HTTP_200_OK
)
async def update_instance_schedule(
    instance_id: str = Path(..., description="Instance ID of the councilor"),
    request: UpdateScheduleRequest = ...,
    db: AsyncIOMotorDatabase = Depends(get_database),
    scheduler: Optional[CouncilorBackendScheduler] = Depends(get_councilor_scheduler)
):
    """
    Pause or resume a councilor instance schedule.

    **Path Parameters:**
    - `instance_id`: Instance ID of the councilor

    **Request Body:**
    - `enabled`: true to resume, false to pause

    **Returns:**
    - Updated schedule configuration
    """
    try:
        logger.info(f"⏯️ [SCHEDULE] Updating schedule for instance: {instance_id}, enabled={request.enabled}")

        agent_instances = db.agent_instances

        # Find instance
        instance = await agent_instances.find_one({"instance_id": instance_id})

        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Councilor instance '{instance_id}' not found"
            )

        if not instance.get("is_councilor_instance"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Instance '{instance_id}' is not a councilor"
            )

        # Update schedule enabled flag
        from datetime import datetime
        await agent_instances.update_one(
            {"instance_id": instance_id},
            {
                "$set": {
                    "councilor_config.schedule.enabled": request.enabled,
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
        )

        # Update scheduler if available
        if scheduler:
            try:
                if request.enabled:
                    # Reload councilor into scheduler
                    await scheduler.reload_councilors()
                    logger.info(f"▶️ [SCHEDULE] Resumed instance '{instance_id}' in scheduler")
                else:
                    # Remove from scheduler (pause)
                    # Job ID is just the instance_id (see councilor_scheduler.py line 213)
                    scheduler.scheduler.remove_job(instance_id, jobstore='default')
                    logger.info(f"⏸️ [SCHEDULE] Paused instance '{instance_id}' in scheduler")
            except Exception as e:
                logger.warning(f"⚠️ [SCHEDULE] Scheduler update failed: {e}")

        # Get updated schedule
        updated_instance = await agent_instances.find_one({"instance_id": instance_id})
        updated_schedule = updated_instance.get("councilor_config", {}).get("schedule", {})

        logger.info(f"✅ [SCHEDULE] Instance '{instance_id}' schedule updated: enabled={request.enabled}")

        return ScheduleResponse(
            success=True,
            message=f"Schedule {'resumed' if request.enabled else 'paused'} successfully",
            schedule=CouncilorSchedule(**updated_schedule)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [SCHEDULE] Error updating schedule: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update schedule: {str(e)}"
        )


@router.patch(
    "/instances/{instance_id}/config",
    response_model=CouncilorInstanceResponse,
    status_code=status.HTTP_200_OK
)
async def update_instance_config(
    instance_id: str = Path(..., description="Instance ID of the councilor"),
    request: dict = ...,
    db: AsyncIOMotorDatabase = Depends(get_database),
    scheduler: Optional[CouncilorBackendScheduler] = Depends(get_councilor_scheduler)
):
    """
    Update councilor instance configuration.

    **Path Parameters:**
    - `instance_id`: Instance ID of the councilor

    **Request Body:**
    - `title`: Councilor title/role
    - `task`: Task configuration (name, prompt, context_files)
    - `schedule`: Schedule configuration (type, value, enabled)
    - `notifications`: Notification preferences

    **Returns:**
    - Updated instance
    """
    try:
        logger.info(f"⚙️ [CONFIG] Updating config for instance: {instance_id}")

        agent_instances = db.agent_instances

        # Find instance
        instance = await agent_instances.find_one({"instance_id": instance_id})

        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Councilor instance '{instance_id}' not found"
            )

        # Build update document
        update_doc = {}
        councilor_config = instance.get("councilor_config", {})

        if "title" in request:
            councilor_config["title"] = request["title"]

        if "task" in request:
            councilor_config["task"] = {
                **councilor_config.get("task", {}),
                **request["task"]
            }

        if "schedule" in request:
            councilor_config["schedule"] = {
                **councilor_config.get("schedule", {}),
                **request["schedule"]
            }

        if "notifications" in request:
            councilor_config["notifications"] = {
                **councilor_config.get("notifications", {}),
                **request["notifications"]
            }

        update_doc["councilor_config"] = councilor_config
        update_doc["updated_at"] = datetime.utcnow()

        # Update cwd if provided
        if "cwd" in request and request["cwd"]:
            update_doc["cwd"] = request["cwd"]
            logger.info(f"📁 [CONFIG] Updating cwd to: {request['cwd']}")

        # Update in database
        result = await agent_instances.update_one(
            {"instance_id": instance_id},
            {"$set": update_doc}
        )

        if result.modified_count == 0:
            logger.warning(f"⚠️ [CONFIG] No changes made to instance '{instance_id}'")

        # Reload scheduler if schedule changed
        if scheduler and "schedule" in request:
            try:
                await scheduler.reload_councilors()
                logger.info(f"🔄 [CONFIG] Reloaded scheduler after config update")
            except Exception as e:
                logger.warning(f"⚠️ [CONFIG] Scheduler reload failed: {e}")

        # Get updated instance
        updated_instance = await agent_instances.find_one({"instance_id": instance_id})

        logger.info(f"✅ [CONFIG] Instance '{instance_id}' config updated")

        return CouncilorInstanceResponse(
            success=True,
            message="Configuration updated successfully",
            instance_id=instance_id,
            screenplay_id=updated_instance.get("screenplay_id", ""),
            conversation_id=updated_instance.get("conversation_id", ""),
            instance=updated_instance
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [CONFIG] Error updating config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update config: {str(e)}"
        )


# ========== Legacy List Endpoints ==========

@router.get("", response_model=AgentListResponse)
async def list_agents(
    is_councilor: Optional[bool] = Query(
        None,
        description="Filter by councilor status (true=councilors only, false=non-councilors, null=all)"
    ),
    service: CouncilorService = Depends(get_councilor_service)
):
    """
    List all agents, optionally filtered by councilor status

    **Query Parameters:**
    - `is_councilor`: Filter by councilor status
      - `true`: Only councilors
      - `false`: Only non-councilors
      - Not provided: All agents

    **Returns:**
    - List of agents with councilor information
    """
    try:
        logger.info(f"📋 Listing agents (is_councilor={is_councilor})")
        return await service.list_all_agents(is_councilor=is_councilor)
    except Exception as e:
        logger.error(f"❌ Error listing agents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agents: {str(e)}"
        )


# ========== Promote/Demote Endpoints ==========

@router.post(
    "/{agent_id}/promote-councilor",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK
)
async def promote_to_councilor(
    agent_id: str = Path(..., description="Agent ID to promote"),
    request: PromoteToCouncilorRequest = ...,
    service: CouncilorService = Depends(get_councilor_service),
    scheduler: Optional[CouncilorBackendScheduler] = Depends(get_councilor_scheduler)
):
    """
    Promote an agent to councilor status

    **Path Parameters:**
    - `agent_id`: Unique identifier of the agent to promote

    **Request Body:**
    - `councilor_config`: Complete councilor configuration
      - `title`: Councilor title/role
      - `schedule`: Task schedule (interval or cron)
      - `task`: Task definition (name, prompt, context files)
      - `notifications`: Notification preferences
    - `customization` (optional): Visual customization

    **Returns:**
    - Success message with updated agent

    **Errors:**
    - `404 Not Found`: Agent not found
    - `409 Conflict`: Agent is already a councilor
    - `400 Bad Request`: Invalid configuration
    """
    try:
        logger.info(f"⭐ Promoting agent '{agent_id}' to councilor")

        agent = await service.promote_to_councilor(agent_id, request)

        # Schedule in backend scheduler if available
        if scheduler and request.councilor_config.schedule.enabled:
            try:
                agent_dict = agent.model_dump() if hasattr(agent, 'model_dump') else agent.dict()
                await scheduler.schedule_councilor(agent_dict)
                logger.info(f"✅ Scheduled councilor '{agent_id}' in backend scheduler")
            except Exception as e:
                logger.error(f"⚠️ Failed to schedule councilor in backend: {e}")
                # Don't fail the promotion if scheduling fails

        return SuccessResponse(
            success=True,
            message=f"Agent '{agent_id}' promoted to councilor successfully",
            agent=agent
        )

    except ValueError as e:
        error_msg = str(e)
        logger.warning(f"⚠️ Validation error: {error_msg}")

        if "not found" in error_msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)
        elif "already a councilor" in error_msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_msg)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    except Exception as e:
        logger.error(f"❌ Error promoting agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to promote agent: {str(e)}"
        )


@router.delete(
    "/{agent_id}/demote-councilor",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK
)
async def demote_councilor(
    agent_id: str = Path(..., description="Agent ID to demote"),
    service: CouncilorService = Depends(get_councilor_service),
    scheduler: Optional[CouncilorBackendScheduler] = Depends(get_councilor_scheduler)
):
    """
    Remove councilor status from an agent

    **Path Parameters:**
    - `agent_id`: Unique identifier of the agent to demote

    **Returns:**
    - Success message with updated agent

    **Errors:**
    - `404 Not Found`: Agent not found
    - `400 Bad Request`: Agent is not a councilor
    """
    try:
        logger.info(f"🔻 Demoting councilor '{agent_id}'")

        agent = await service.demote_councilor(agent_id)

        # Remove from backend scheduler if available
        if scheduler:
            try:
                await scheduler.remove_councilor(agent_id)
                logger.info(f"✅ Removed '{agent_id}' from scheduler")
            except Exception as e:
                logger.error(f"⚠️ Failed to remove from scheduler: {e}")
                # Don't fail the demotion if scheduler removal fails

        return SuccessResponse(
            success=True,
            message=f"Agent '{agent_id}' demoted from councilor",
            agent=agent
        )

    except ValueError as e:
        error_msg = str(e)
        logger.warning(f"⚠️ Validation error: {error_msg}")

        if "not found" in error_msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    except Exception as e:
        logger.error(f"❌ Error demoting councilor: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to demote councilor: {str(e)}"
        )


# ========== Configuration Endpoints ==========

@router.patch(
    "/{agent_id}/councilor-config",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK
)
async def update_councilor_config(
    agent_id: str = Path(..., description="Agent ID"),
    request: UpdateCouncilorConfigRequest = ...,
    service: CouncilorService = Depends(get_councilor_service)
):
    """
    Update councilor configuration

    **Path Parameters:**
    - `agent_id`: Unique identifier of the councilor

    **Request Body:**
    - `schedule` (optional): Update schedule configuration
    - `task` (optional): Update task configuration
    - `notifications` (optional): Update notification preferences

    **Returns:**
    - Success message with updated agent

    **Errors:**
    - `404 Not Found`: Agent not found or is not a councilor
    - `400 Bad Request`: Invalid configuration
    """
    try:
        logger.info(f"⚙️ Updating councilor config for '{agent_id}'")

        agent = await service.update_councilor_config(agent_id, request)

        return SuccessResponse(
            success=True,
            message="Councilor configuration updated successfully",
            agent=agent
        )

    except ValueError as e:
        error_msg = str(e)
        logger.warning(f"⚠️ Validation error: {error_msg}")

        if "not found" in error_msg.lower() or "not a councilor" in error_msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    except Exception as e:
        logger.error(f"❌ Error updating config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update configuration: {str(e)}"
        )


@router.patch(
    "/{agent_id}/councilor-schedule",
    response_model=ScheduleResponse,
    status_code=status.HTTP_200_OK
)
async def update_schedule(
    agent_id: str = Path(..., description="Agent ID"),
    request: UpdateScheduleRequest = ...,
    service: CouncilorService = Depends(get_councilor_service),
    scheduler: Optional[CouncilorBackendScheduler] = Depends(get_councilor_scheduler)
):
    """
    Pause or resume councilor schedule

    **Path Parameters:**
    - `agent_id`: Unique identifier of the councilor

    **Request Body:**
    - `enabled`: True to resume, False to pause

    **Returns:**
    - Updated schedule configuration

    **Errors:**
    - `404 Not Found`: Agent not found or is not a councilor
    """
    try:
        logger.info(f"{'▶️' if request.enabled else '⏸️'} {'Resuming' if request.enabled else 'Pausing'} schedule for '{agent_id}'")

        schedule = await service.update_schedule(agent_id, request)

        # Update backend scheduler if available
        if scheduler:
            try:
                if request.enabled:
                    await scheduler.resume_councilor(agent_id)
                else:
                    await scheduler.pause_councilor(agent_id)
                logger.info(f"✅ Scheduler updated for '{agent_id}'")
            except Exception as e:
                logger.error(f"⚠️ Failed to update scheduler: {e}")
                # Don't fail the request if scheduler update fails

        return ScheduleResponse(
            success=True,
            message=f"Schedule {'resumed' if request.enabled else 'paused'}",
            schedule=schedule
        )

    except ValueError as e:
        error_msg = str(e)
        logger.warning(f"⚠️ Validation error: {error_msg}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)

    except Exception as e:
        logger.error(f"❌ Error updating schedule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update schedule: {str(e)}"
        )


# ========== Execution Endpoints ==========

@router.post(
    "/councilors/executions",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED
)
async def save_execution(
    execution: CouncilorExecutionCreate = ...,
    service: CouncilorService = Depends(get_councilor_service)
):
    """
    Save execution result

    **Request Body:**
    - `execution_id`: Unique execution identifier
    - `councilor_id`: Agent ID of the councilor
    - `started_at`: Execution start time
    - `completed_at` (optional): Execution completion time
    - `status`: Execution status (running, completed, error)
    - `severity`: Result severity (success, warning, error)
    - `output` (optional): Execution output
    - `error` (optional): Error message
    - `duration_ms` (optional): Execution duration in milliseconds

    **Returns:**
    - Saved execution result

    **Errors:**
    - `404 Not Found`: Councilor not found
    - `409 Conflict`: Execution ID already exists
    """
    try:
        logger.info(f"💾 Saving execution: {execution.execution_id}")

        saved_execution = await service.save_execution(execution)

        return SuccessResponse(
            success=True,
            message="Execution result saved successfully",
            execution=saved_execution
        )

    except ValueError as e:
        error_msg = str(e)
        logger.warning(f"⚠️ Validation error: {error_msg}")

        if "not found" in error_msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)
        elif "already exists" in error_msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_msg)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    except Exception as e:
        logger.error(f"❌ Error saving execution: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save execution: {str(e)}"
        )


@router.get(
    "/{agent_id}/councilor-reports",
    response_model=CouncilorReportResponse,
    status_code=status.HTTP_200_OK
)
async def get_councilor_report(
    agent_id: str = Path(..., description="Agent ID"),
    limit: int = Query(10, ge=1, le=100, description="Number of recent executions to include"),
    service: CouncilorService = Depends(get_councilor_service)
):
    """
    Get comprehensive report for a councilor

    **Path Parameters:**
    - `agent_id`: Unique identifier of the councilor

    **Query Parameters:**
    - `limit`: Number of recent executions to include (1-100, default: 10)

    **Returns:**
    - Councilor report with:
      - Councilor ID and name
      - Recent executions
      - Total execution count
      - Success rate
      - Next scheduled execution (if available)

    **Errors:**
    - `404 Not Found`: Councilor not found
    """
    try:
        logger.info(f"📋 Getting report for councilor '{agent_id}'")

        report = await service.get_councilor_report(agent_id, limit)
        return report

    except ValueError as e:
        error_msg = str(e)
        logger.warning(f"⚠️ Validation error: {error_msg}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)

    except Exception as e:
        logger.error(f"❌ Error getting report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get report: {str(e)}"
        )


@router.get(
    "/{agent_id}/councilor-reports/latest",
    response_model=Optional[CouncilorExecutionResponse],
    status_code=status.HTTP_200_OK
)
async def get_latest_execution(
    agent_id: str = Path(..., description="Agent ID"),
    service: CouncilorService = Depends(get_councilor_service)
):
    """
    Get latest execution for a councilor

    **Path Parameters:**
    - `agent_id`: Unique identifier of the councilor

    **Returns:**
    - Latest execution result or null if no executions

    **Errors:**
    - `404 Not Found`: Councilor not found
    """
    try:
        logger.info(f"📄 Getting latest execution for '{agent_id}'")

        execution = await service.get_latest_execution(agent_id)
        return execution

    except ValueError as e:
        error_msg = str(e)
        logger.warning(f"⚠️ Validation error: {error_msg}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)

    except Exception as e:
        logger.error(f"❌ Error getting latest execution: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get latest execution: {str(e)}"
        )


# ========== Execute Now Endpoint ==========

@router.post(
    "/{agent_id}/execute-now",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK
)
async def execute_councilor_now(
    agent_id: str = Path(..., description="Agent ID of the councilor to execute"),
    service: CouncilorService = Depends(get_councilor_service),
    scheduler: Optional[CouncilorBackendScheduler] = Depends(get_councilor_scheduler)
):
    """
    Execute a councilor's task immediately

    **Path Parameters:**
    - `agent_id`: Unique identifier of the councilor

    **Returns:**
    - Execution result with severity and output

    **Errors:**
    - `404 Not Found`: Councilor not found
    - `400 Bad Request`: Agent is not a councilor
    - `503 Service Unavailable`: Scheduler not available
    """
    try:
        logger.info(f"🚀 Executing councilor '{agent_id}' immediately")

        # Validate councilor exists
        from ...core.database import get_db_instance
        db = get_db_instance()
        if not db:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )

        # First check agent_instances (NEW instance-based councilors)
        instance = await db.agent_instances.find_one({
            "agent_id": agent_id,
            "is_councilor_instance": True,
            "$or": [
                {"isDeleted": {"$ne": True}},
                {"isDeleted": {"$exists": False}}
            ]
        })

        if instance:
            logger.info(f"🏛️ Found councilor instance for agent '{agent_id}'")
        else:
            # Fallback to legacy agents collection
            agent = await db.agents.find_one({"agent_id": agent_id})
            if not agent:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent '{agent_id}' not found"
                )

            if not agent.get("is_councilor"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Agent '{agent_id}' is not a councilor"
                )
            logger.info(f"🏛️ Found legacy councilor for agent '{agent_id}'")

        # Execute via scheduler if available
        if scheduler:
            try:
                result = await scheduler.execute_councilor_now(agent_id)
                logger.info(f"✅ Councilor '{agent_id}' executed successfully")

                return SuccessResponse(
                    success=True,
                    message=f"Councilor '{agent_id}' executed successfully",
                    execution=result
                )
            except Exception as e:
                logger.error(f"❌ Failed to execute councilor: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to execute councilor: {str(e)}"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Scheduler not available"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error executing councilor: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute councilor: {str(e)}"
        )
