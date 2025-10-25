"""
Councilor Router - API endpoints for councilor management

Provides endpoints for:
- Listing councilors
- Promoting/demoting agents
- Updating configurations
- Managing executions and reports
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...core.database import get_database
from ...services.councilor_service import CouncilorService
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
    ScheduleResponse
)

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(
    prefix="/api/agents",
    tags=["councilors"],
    responses={404: {"description": "Not found"}},
)


# ========== Dependency Injection ==========

def get_councilor_service(
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> CouncilorService:
    """Get councilor service instance"""
    return CouncilorService(db)


# ========== List Endpoints ==========

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
    service: CouncilorService = Depends(get_councilor_service)
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
    service: CouncilorService = Depends(get_councilor_service)
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
    service: CouncilorService = Depends(get_councilor_service)
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
