"""
Councilor Service - Business logic for councilor management

Handles:
- Promoting/demoting agents to/from councilors
- Updating councilor configurations
- Managing execution results
- Generating reports
"""

import logging
from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..models.councilor import (
    PromoteToCouncilorRequest,
    UpdateCouncilorConfigRequest,
    UpdateScheduleRequest,
    CouncilorExecutionCreate,
    AgentWithCouncilorResponse,
    CouncilorExecutionResponse,
    CouncilorReportResponse,
    AgentStats,
    AgentListResponse,
    ExecutionListResponse
)

logger = logging.getLogger(__name__)


class CouncilorService:
    """Service for managing councilors"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.agents_collection = db.agents
        self.executions_collection = db.councilor_executions

    async def ensure_indexes(self):
        """Create MongoDB indexes for performance"""
        try:
            # Agent indexes
            await self.agents_collection.create_index("agent_id", unique=True)
            await self.agents_collection.create_index("is_councilor")

            # Execution indexes
            await self.executions_collection.create_index("execution_id", unique=True)
            await self.executions_collection.create_index([
                ("councilor_id", 1),
                ("started_at", -1)
            ])
            await self.executions_collection.create_index("councilor_id")
            await self.executions_collection.create_index("started_at")

            logger.info("✅ Councilor indexes created successfully")
        except Exception as e:
            logger.warning(f"⚠️ Failed to create indexes: {e}")

    # ========== Agent Validation ==========

    async def _get_agent(self, agent_id: str) -> dict:
        """Get agent by agent_id, raise ValueError if not found"""
        agent = await self.agents_collection.find_one({"agent_id": agent_id})
        if not agent:
            raise ValueError(f"Agent with agent_id '{agent_id}' not found")
        return agent

    async def _agent_exists(self, agent_id: str) -> bool:
        """Check if agent exists"""
        count = await self.agents_collection.count_documents({"agent_id": agent_id})
        return count > 0

    # ========== List Operations ==========

    async def list_councilors(self) -> AgentListResponse:
        """List all agents that are councilors"""
        try:
            cursor = self.agents_collection.find({"is_councilor": True})
            agents = await cursor.to_list(length=None)

            councilors = []
            for agent in agents:
                councilors.append(self._agent_to_response(agent))

            return AgentListResponse(
                agents=councilors,
                count=len(councilors)
            )
        except Exception as e:
            logger.error(f"❌ Error listing councilors: {e}")
            raise

    async def list_all_agents(self, is_councilor: Optional[bool] = None) -> AgentListResponse:
        """List all agents, optionally filtered by councilor status"""
        try:
            query = {}
            if is_councilor is not None:
                query["is_councilor"] = is_councilor

            cursor = self.agents_collection.find(query)
            agents = await cursor.to_list(length=None)

            agent_responses = []
            for agent in agents:
                agent_responses.append(self._agent_to_response(agent))

            return AgentListResponse(
                agents=agent_responses,
                count=len(agent_responses)
            )
        except Exception as e:
            logger.error(f"❌ Error listing agents: {e}")
            raise

    # ========== Promote/Demote Operations ==========

    async def promote_to_councilor(
        self,
        agent_id: str,
        request: PromoteToCouncilorRequest
    ) -> AgentWithCouncilorResponse:
        """Promote an agent to councilor"""
        try:
            # Validate agent exists
            agent = await self._get_agent(agent_id)

            # Check if already a councilor
            if agent.get("is_councilor"):
                raise ValueError(f"Agent '{agent_id}' is already a councilor")

            # Prepare update data
            update_data = {
                "is_councilor": True,
                "councilor_config": request.councilor_config.model_dump(),
                "updated_at": datetime.utcnow()
            }

            # Add customization if provided
            if request.customization:
                update_data["customization"] = request.customization.model_dump()

            # Initialize stats if not exists
            if "stats" not in agent:
                update_data["stats"] = {
                    "total_executions": 0,
                    "last_execution": None,
                    "success_rate": 0.0
                }

            # Update agent in database
            result = await self.agents_collection.update_one(
                {"agent_id": agent_id},
                {"$set": update_data}
            )

            if result.modified_count == 0:
                raise ValueError("Failed to update agent")

            # Get updated agent
            updated_agent = await self._get_agent(agent_id)

            logger.info(f"✅ Agent '{agent_id}' promoted to councilor")

            return self._agent_to_response(updated_agent)

        except ValueError as e:
            logger.warning(f"⚠️ Validation error promoting agent: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error promoting agent to councilor: {e}")
            raise

    async def demote_councilor(self, agent_id: str) -> AgentWithCouncilorResponse:
        """Remove councilor status from an agent"""
        try:
            # Validate agent exists
            agent = await self._get_agent(agent_id)

            # Check if is councilor
            if not agent.get("is_councilor"):
                raise ValueError(f"Agent '{agent_id}' is not a councilor")

            # Update agent in database
            result = await self.agents_collection.update_one(
                {"agent_id": agent_id},
                {
                    "$set": {
                        "is_councilor": False,
                        "updated_at": datetime.utcnow()
                    },
                    "$unset": {
                        "councilor_config": ""
                    }
                }
            )

            if result.modified_count == 0:
                raise ValueError("Failed to update agent")

            # Get updated agent
            updated_agent = await self._get_agent(agent_id)

            logger.info(f"✅ Agent '{agent_id}' demoted from councilor")

            return self._agent_to_response(updated_agent)

        except ValueError as e:
            logger.warning(f"⚠️ Validation error demoting councilor: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error demoting councilor: {e}")
            raise

    # ========== Configuration Updates ==========

    async def update_councilor_config(
        self,
        agent_id: str,
        request: UpdateCouncilorConfigRequest
    ) -> AgentWithCouncilorResponse:
        """Update councilor configuration"""
        try:
            # Validate agent exists and is councilor
            agent = await self._get_agent(agent_id)
            if not agent.get("is_councilor"):
                raise ValueError(f"Agent '{agent_id}' is not a councilor")

            # Build update data (only update provided fields)
            update_data = {"updated_at": datetime.utcnow()}

            if request.schedule is not None:
                update_data["councilor_config.schedule"] = request.schedule.model_dump()

            if request.task is not None:
                update_data["councilor_config.task"] = request.task.model_dump()

            if request.notifications is not None:
                update_data["councilor_config.notifications"] = request.notifications.model_dump()

            # Update agent
            result = await self.agents_collection.update_one(
                {"agent_id": agent_id},
                {"$set": update_data}
            )

            if result.modified_count == 0:
                raise ValueError("No changes made to configuration")

            # Get updated agent
            updated_agent = await self._get_agent(agent_id)

            logger.info(f"✅ Councilor config updated for '{agent_id}'")

            return self._agent_to_response(updated_agent)

        except ValueError as e:
            logger.warning(f"⚠️ Validation error updating config: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error updating councilor config: {e}")
            raise

    async def update_schedule(
        self,
        agent_id: str,
        request: UpdateScheduleRequest
    ) -> dict:
        """Pause or resume councilor schedule"""
        try:
            # Validate agent exists and is councilor
            agent = await self._get_agent(agent_id)
            if not agent.get("is_councilor"):
                raise ValueError(f"Agent '{agent_id}' is not a councilor")

            # Update schedule enabled status
            result = await self.agents_collection.update_one(
                {"agent_id": agent_id},
                {
                    "$set": {
                        "councilor_config.schedule.enabled": request.enabled,
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            if result.modified_count == 0:
                raise ValueError("Failed to update schedule")

            # Get updated agent
            updated_agent = await self._get_agent(agent_id)
            schedule = updated_agent["councilor_config"]["schedule"]

            logger.info(f"✅ Schedule {'enabled' if request.enabled else 'paused'} for '{agent_id}'")

            return {
                "type": schedule["type"],
                "value": schedule["value"],
                "enabled": schedule["enabled"]
            }

        except ValueError as e:
            logger.warning(f"⚠️ Validation error updating schedule: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error updating schedule: {e}")
            raise

    # ========== Execution Management ==========

    async def save_execution(
        self,
        execution: CouncilorExecutionCreate
    ) -> CouncilorExecutionResponse:
        """Save execution result"""
        try:
            # Validate councilor exists
            if not await self._agent_exists(execution.councilor_id):
                raise ValueError(f"Councilor '{execution.councilor_id}' not found")

            # Prepare document
            execution_doc = {
                "execution_id": execution.execution_id,
                "councilor_id": execution.councilor_id,
                "started_at": execution.started_at,
                "completed_at": execution.completed_at,
                "status": execution.status,
                "severity": execution.severity,
                "output": execution.output,
                "error": execution.error,
                "duration_ms": execution.duration_ms,
                "created_at": datetime.utcnow()
            }

            # Insert into database
            result = await self.executions_collection.insert_one(execution_doc)

            # Update agent stats
            await self._update_agent_stats(
                execution.councilor_id,
                execution.severity == "success"
            )

            logger.info(f"✅ Execution saved: {execution.execution_id}")

            # Return response
            execution_doc["_id"] = str(result.inserted_id)
            return CouncilorExecutionResponse(**execution_doc)

        except DuplicateKeyError:
            raise ValueError(f"Execution with ID '{execution.execution_id}' already exists")
        except ValueError as e:
            logger.warning(f"⚠️ Validation error saving execution: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error saving execution: {e}")
            raise

    async def get_executions(
        self,
        councilor_id: str,
        limit: int = 10
    ) -> ExecutionListResponse:
        """Get recent executions for a councilor"""
        try:
            # Validate councilor exists
            if not await self._agent_exists(councilor_id):
                raise ValueError(f"Councilor '{councilor_id}' not found")

            # Query executions
            cursor = self.executions_collection.find(
                {"councilor_id": councilor_id}
            ).sort("started_at", -1).limit(limit)

            executions = await cursor.to_list(length=limit)

            execution_responses = []
            for exec_doc in executions:
                exec_doc["_id"] = str(exec_doc["_id"])
                execution_responses.append(CouncilorExecutionResponse(**exec_doc))

            return ExecutionListResponse(
                executions=execution_responses,
                count=len(execution_responses)
            )

        except ValueError as e:
            logger.warning(f"⚠️ Validation error getting executions: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error getting executions: {e}")
            raise

    async def get_latest_execution(
        self,
        councilor_id: str
    ) -> Optional[CouncilorExecutionResponse]:
        """Get latest execution for a councilor"""
        try:
            # Validate councilor exists
            if not await self._agent_exists(councilor_id):
                raise ValueError(f"Councilor '{councilor_id}' not found")

            # Query latest execution
            exec_doc = await self.executions_collection.find_one(
                {"councilor_id": councilor_id},
                sort=[("started_at", -1)]
            )

            if not exec_doc:
                return None

            exec_doc["_id"] = str(exec_doc["_id"])
            return CouncilorExecutionResponse(**exec_doc)

        except ValueError as e:
            logger.warning(f"⚠️ Validation error getting latest execution: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error getting latest execution: {e}")
            raise

    # ========== Reports ==========

    async def get_councilor_report(
        self,
        agent_id: str,
        limit: int = 10
    ) -> CouncilorReportResponse:
        """Get comprehensive report for a councilor"""
        try:
            # Get agent
            agent = await self._get_agent(agent_id)
            if not agent.get("is_councilor"):
                raise ValueError(f"Agent '{agent_id}' is not a councilor")

            # Get recent executions
            executions_response = await self.get_executions(agent_id, limit)

            # Get stats
            stats = agent.get("stats", {
                "total_executions": 0,
                "success_rate": 0.0
            })

            # Get councilor name
            customization = agent.get("customization", {})
            councilor_name = customization.get("display_name", agent.get("name", agent_id))

            # Calculate next execution (TODO: implement based on schedule)
            next_execution = None  # Would need scheduler logic

            return CouncilorReportResponse(
                councilor_id=agent_id,
                councilor_name=councilor_name,
                recent_executions=executions_response.executions,
                total_executions=stats.get("total_executions", 0),
                success_rate=stats.get("success_rate", 0.0),
                next_execution=next_execution
            )

        except ValueError as e:
            logger.warning(f"⚠️ Validation error getting report: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error getting councilor report: {e}")
            raise

    # ========== Helper Methods ==========

    async def _update_agent_stats(self, agent_id: str, success: bool):
        """Update agent execution statistics"""
        try:
            agent = await self._get_agent(agent_id)
            stats = agent.get("stats", {
                "total_executions": 0,
                "last_execution": None,
                "success_rate": 0.0
            })

            # Increment total executions
            total = stats.get("total_executions", 0) + 1

            # Calculate new success rate
            old_rate = stats.get("success_rate", 0.0)
            old_successes = int((old_rate / 100.0) * (total - 1)) if total > 1 else 0
            new_successes = old_successes + (1 if success else 0)
            new_rate = (new_successes / total) * 100.0

            # Update stats
            await self.agents_collection.update_one(
                {"agent_id": agent_id},
                {
                    "$set": {
                        "stats.total_executions": total,
                        "stats.last_execution": datetime.utcnow(),
                        "stats.success_rate": round(new_rate, 1)
                    }
                }
            )

            logger.debug(f"📊 Stats updated for '{agent_id}': {total} executions, {new_rate:.1f}% success")

        except Exception as e:
            logger.warning(f"⚠️ Failed to update stats for '{agent_id}': {e}")

    def _agent_to_response(self, agent: dict) -> AgentWithCouncilorResponse:
        """Convert MongoDB agent document to response model"""
        # Convert ObjectId to string
        agent_copy = dict(agent)
        agent_copy["_id"] = str(agent_copy["_id"])

        # Ensure required fields exist
        if "is_councilor" not in agent_copy:
            agent_copy["is_councilor"] = False

        return AgentWithCouncilorResponse(**agent_copy)
