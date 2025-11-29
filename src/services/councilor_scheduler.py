"""
Backend Scheduler for Councilors - Persistent task execution

This scheduler runs in the backend server and ensures councilor tasks
execute reliably, independent of frontend state.

Features:
- Persistent: Survives server restarts (jobs stored in MongoDB)
- No duplicates: Single source of truth
- Always running: Independent of frontend/browser
- Scalable: Can run in separate process/container
- Real-time events: Broadcasts execution events via WebSocket
"""

import logging
import re
from datetime import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class CouncilorBackendScheduler:
    """
    Backend scheduler for councilor periodic tasks

    Uses APScheduler with MongoDB persistence to ensure tasks
    run reliably even across server restarts.
    """

    def __init__(self, db: AsyncIOMotorDatabase, conductor_client):
        """
        Initialize the scheduler

        Args:
            db: Motor AsyncIOMotorDatabase instance
            conductor_client: ConductorClient instance for executing agents
        """
        self.db = db
        self.conductor_client = conductor_client
        self.agents_collection = db.agents
        self.tasks_collection = db.tasks  # Use tasks collection instead of councilor_executions

        # Configure APScheduler with in-memory job store
        # Note: MongoDB jobstore doesn't work with async objects like ConductorClient
        # Jobs are recreated from MongoDB agents collection on startup, so we don't lose them
        self.scheduler = AsyncIOScheduler(timezone='UTC')
        logger.info("🏛️ Councilor Backend Scheduler initialized (uses tasks collection)")

    async def start(self):
        """Start the scheduler and load active councilors"""
        try:
            # Load active councilors from database
            await self.load_councilors()

            # Start APScheduler
            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("✅ Councilor Scheduler started")
            else:
                logger.info("ℹ️ Scheduler already running")

        except Exception as e:
            logger.error(f"❌ Failed to start scheduler: {e}")
            raise

    async def load_councilors(self):
        """Load all active councilors from database and schedule their tasks"""
        try:
            # ============================================================
            # NEW: Load from agent_instances (is_councilor_instance=True)
            # ============================================================
            agent_instances = self.db.agent_instances
            instances_cursor = agent_instances.find({
                "is_councilor_instance": True,
                "councilor_config.schedule.enabled": True,
                "$or": [
                    {"isDeleted": {"$ne": True}},
                    {"isDeleted": {"$exists": False}}
                ]
            })

            councilor_instances = await instances_cursor.to_list(length=None)
            logger.info(f"📋 Loading {len(councilor_instances)} councilor instances from agent_instances")

            for instance in councilor_instances:
                try:
                    await self.schedule_councilor_instance(instance)
                except Exception as e:
                    instance_id = instance.get("instance_id", "unknown")
                    logger.error(f"❌ Failed to schedule councilor instance {instance_id}: {e}")

            # ============================================================
            # LEGACY: Also load from agents (is_councilor=True) for backwards compatibility
            # This will be deprecated once all councilors are migrated to instances
            # ============================================================
            cursor = self.agents_collection.find({
                "is_councilor": True,
                "councilor_config.schedule.enabled": True
            })

            legacy_councilors = await cursor.to_list(length=None)

            if legacy_councilors:
                logger.info(f"📋 Loading {len(legacy_councilors)} legacy councilors from agents collection")

                for councilor in legacy_councilors:
                    try:
                        await self.schedule_councilor(councilor)
                    except Exception as e:
                        agent_id = councilor.get("agent_id", "unknown")
                        logger.error(f"❌ Failed to schedule legacy councilor {agent_id}: {e}")

            total = len(councilor_instances) + len(legacy_councilors)
            logger.info(f"✅ Loaded {total} total councilors ({len(councilor_instances)} instances, {len(legacy_councilors)} legacy)")

        except Exception as e:
            logger.error(f"❌ Failed to load councilors: {e}")

    async def schedule_councilor(self, councilor: dict):
        """
        Schedule a councilor task

        Args:
            councilor: Agent document from MongoDB with councilor_config
        """
        agent_id = councilor["agent_id"]
        config = councilor.get("councilor_config")

        if not config:
            logger.warning(f"⚠️ Councilor {agent_id} has no config, skipping")
            return

        schedule = config.get("schedule", {})

        if not schedule.get("enabled"):
            logger.info(f"⏸️ Councilor {agent_id} schedule is disabled, skipping")
            return

        # Remove existing job if exists (to update it)
        try:
            self.scheduler.remove_job(agent_id, jobstore='default')
            logger.debug(f"Removed existing job for {agent_id}")
        except Exception:
            pass  # Job doesn't exist, that's fine

        # Create trigger based on schedule type
        try:
            if schedule["type"] == "interval":
                trigger = self._parse_interval_trigger(schedule["value"])
            elif schedule["type"] == "cron":
                trigger = CronTrigger.from_crontab(schedule["value"])
            else:
                logger.error(f"❌ Unknown schedule type: {schedule['type']}")
                return

            # Add job to scheduler
            self.scheduler.add_job(
                func=self._execute_councilor_task,
                trigger=trigger,
                id=agent_id,
                name=f"Councilor: {councilor.get('definition', {}).get('name', agent_id)}",
                kwargs={
                    'agent_id': agent_id,
                    'config': config
                },
                replace_existing=True,
                jobstore='default'
            )

            logger.info(
                f"⏰ Scheduled: {agent_id} - "
                f"{schedule['type']}={schedule['value']}"
            )

            # Execute immediately on first schedule (optional but recommended)
            # This ensures the councilor runs right away instead of waiting the full interval
            # Uncomment the line below to enable immediate first execution:
            # await self._execute_councilor_task(agent_id, config)

        except Exception as e:
            logger.error(f"❌ Failed to create trigger for {agent_id}: {e}")

    async def schedule_councilor_instance(self, instance: dict):
        """
        Schedule a councilor instance task (NEW instance-based approach).

        Args:
            instance: Agent instance document from MongoDB with councilor_config
        """
        instance_id = instance.get("instance_id")
        agent_id = instance.get("agent_id")
        screenplay_id = instance.get("screenplay_id")
        conversation_id = instance.get("conversation_id")
        config = instance.get("councilor_config")
        customization = instance.get("customization", {})

        if not config:
            logger.warning(f"⚠️ Councilor instance {instance_id} has no config, skipping")
            return

        schedule = config.get("schedule", {})

        if not schedule.get("enabled"):
            logger.info(f"⏸️ Councilor instance {instance_id} schedule is disabled, skipping")
            return

        # Use instance_id as job ID for uniqueness
        job_id = instance_id or agent_id

        # Remove existing job if exists (to update it)
        try:
            self.scheduler.remove_job(job_id, jobstore='default')
            logger.debug(f"Removed existing job for {job_id}")
        except Exception:
            pass  # Job doesn't exist, that's fine

        # Create trigger based on schedule type
        try:
            if schedule["type"] == "interval":
                trigger = self._parse_interval_trigger(schedule["value"])
            elif schedule["type"] == "cron":
                trigger = CronTrigger.from_crontab(schedule["value"])
            else:
                logger.error(f"❌ Unknown schedule type: {schedule['type']}")
                return

            # Get display name
            display_name = customization.get("display_name") if customization else None
            if not display_name:
                # Try to get from agent template
                agent = await self.agents_collection.find_one({"agent_id": agent_id})
                display_name = agent.get("definition", {}).get("name", agent_id) if agent else agent_id

            # Add job to scheduler with full instance data
            self.scheduler.add_job(
                func=self._execute_councilor_instance_task,
                trigger=trigger,
                id=job_id,
                name=f"Councilor Instance: {display_name}",
                kwargs={
                    'instance': instance  # Pass full instance with all IDs
                },
                replace_existing=True,
                jobstore='default'
            )

            logger.info(
                f"⏰ Scheduled instance: {instance_id} ({agent_id}) - "
                f"{schedule['type']}={schedule['value']}"
            )

        except Exception as e:
            logger.error(f"❌ Failed to create trigger for instance {instance_id}: {e}")

    async def _execute_councilor_instance_task(self, instance: dict):
        """
        Execute a councilor instance task (NEW instance-based approach).

        This method uses the SAME FLOW as user chat:
        1. Generate task_id
        2. Call Conductor API /agents/{agent_id}/execute (which inserts into tasks collection)
        3. Watcher picks up task and executes
        4. Conductor API polls and returns result

        This ensures councilor executions appear in the tasks table.

        Args:
            instance: Full instance document with all IDs
        """
        import httpx
        import os
        from bson import ObjectId

        instance_id = instance.get("instance_id")
        agent_id = instance.get("agent_id")
        screenplay_id = instance.get("screenplay_id")
        conversation_id = instance.get("conversation_id")
        config = instance.get("councilor_config", {})
        customization = instance.get("customization", {})
        cwd = instance.get("cwd")  # Working directory for execution

        task = config.get("task", {})
        display_name = customization.get("display_name") if customization else agent_id
        task_name = task.get("name", "Unknown Task")

        start_time = datetime.utcnow()
        execution_id = f"exec_{instance_id}_{int(start_time.timestamp() * 1000)}"
        task_id = str(ObjectId())  # Generate task_id like gateway does

        logger.info(f"🔎 Executing councilor instance task: {display_name} ({instance_id})")

        # 🔔 Emit "councilor_started" event via WebSocket with all IDs
        try:
            from src.api.websocket import gamification_manager
            await gamification_manager.broadcast("councilor_started", {
                "councilor_id": instance_id,
                "agent_id": agent_id,
                "task_name": task_name,
                "display_name": display_name,
                "execution_id": execution_id,
                "task_id": task_id,  # Include task_id for navigation
                "started_at": start_time.isoformat(),
                # Include IDs for navigation
                "screenplay_id": screenplay_id,
                "conversation_id": conversation_id,
                "instance_id": instance_id
            })
        except Exception as e:
            logger.warning(f"⚠️ Failed to broadcast councilor_started event: {e}")

        try:
            # Get prompt from task config
            prompt_text = task.get("prompt", "Analyze the project and provide insights")

            # Get Conductor API URL
            conductor_api_url = os.getenv("CONDUCTOR_API_URL", "http://primoia-conductor-api:8000")

            # Build payload (same as gateway user flow)
            payload = {
                "task_id": task_id,
                "user_input": prompt_text,
                "cwd": cwd,
                "timeout": 600,
                "provider": "claude",  # Default provider
                "instance_id": instance_id,
                "conversation_id": conversation_id,
                "screenplay_id": screenplay_id,
                "context_mode": "stateless",
                "is_councilor_execution": True,  # Mark as councilor execution
                "councilor_config": config
            }

            logger.info(f"🔍 [COUNCILOR INSTANCE] Calling Conductor API (same flow as user)")
            logger.info(f"   - POST {conductor_api_url}/agents/{agent_id}/execute")
            logger.info(f"   - task_id: {task_id}")
            logger.info(f"   - Input text: {prompt_text[:100]}...")
            logger.info(f"   - Instance ID: {instance_id}")
            logger.info(f"   - Screenplay ID: {screenplay_id}")
            logger.info(f"   - Conversation ID: {conversation_id}")
            logger.info(f"   - CWD: {cwd}")

            # Call Conductor API via HTTP (same as gateway does)
            async with httpx.AsyncClient(timeout=630) as client:
                response = await client.post(
                    f"{conductor_api_url}/agents/{agent_id}/execute",
                    json=payload
                )
                response.raise_for_status()
                result = response.json()

            end_time = datetime.utcnow()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Extract result data
            output = result.get("result", "") if isinstance(result, dict) else str(result)
            exit_code = result.get("exit_code", 0)
            severity = result.get("severity") or self._analyze_severity(output)

            logger.info(f"✅ [COUNCILOR INSTANCE] Execution completed for {instance_id}")
            logger.info(f"   - Task ID: {task_id}")
            logger.info(f"   - Severity: {severity}")
            logger.info(f"   - Duration: {duration_ms}ms")
            logger.info(f"   - Exit code: {exit_code}")

            # Update instance statistics
            await self._update_instance_stats(instance_id, exit_code == 0, duration_ms)

            # 🔔 Emit "councilor_completed" event via WebSocket with all IDs
            try:
                from src.api.websocket import gamification_manager
                await gamification_manager.broadcast("councilor_completed", {
                    "councilor_id": instance_id,
                    "agent_id": agent_id,
                    "task_name": task_name,
                    "display_name": display_name,
                    "execution_id": execution_id,
                    "task_id": task_id,  # Include task_id for navigation
                    "status": "completed",
                    "severity": severity,
                    "started_at": start_time.isoformat(),
                    "completed_at": end_time.isoformat(),
                    "duration_ms": duration_ms,
                    # Include IDs for navigation
                    "screenplay_id": screenplay_id,
                    "conversation_id": conversation_id,
                    "instance_id": instance_id
                })
            except Exception as e:
                logger.warning(f"⚠️ Failed to broadcast councilor_completed event: {e}")

        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Conductor API error for councilor {instance_id}: {e.response.status_code}")
            logger.error(f"   - Response: {e.response.text[:500] if e.response.text else 'empty'}")
            await self._handle_councilor_error(instance, instance_id, agent_id, task_name, display_name, execution_id, task_id, start_time, screenplay_id, conversation_id, str(e))

        except httpx.RequestError as e:
            logger.error(f"❌ Connection error to Conductor API for councilor {instance_id}: {e}")
            await self._handle_councilor_error(instance, instance_id, agent_id, task_name, display_name, execution_id, task_id, start_time, screenplay_id, conversation_id, str(e))

        except Exception as e:
            logger.error(f"❌ Error executing councilor instance task {instance_id}: {e}", exc_info=True)
            await self._handle_councilor_error(instance, instance_id, agent_id, task_name, display_name, execution_id, task_id, start_time, screenplay_id, conversation_id, str(e))

    async def _handle_councilor_error(self, instance: dict, instance_id: str, agent_id: str, task_name: str, display_name: str, execution_id: str, task_id: str, start_time: datetime, screenplay_id: str, conversation_id: str, error_message: str):
        """Handle councilor execution error - update stats and broadcast event"""
        end_time = datetime.utcnow()
        error_duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Update stats with failure
        await self._update_instance_stats(instance_id, success=False, duration_ms=error_duration_ms)

        # 🔔 Emit "councilor_error" event via WebSocket with all IDs
        try:
            from src.api.websocket import gamification_manager
            await gamification_manager.broadcast("councilor_error", {
                "councilor_id": instance_id,
                "agent_id": agent_id,
                "task_name": task_name,
                "display_name": display_name,
                "execution_id": execution_id,
                "task_id": task_id,
                "status": "error",
                "severity": "error",
                "error": error_message,
                "started_at": start_time.isoformat(),
                "completed_at": end_time.isoformat(),
                # Include IDs for navigation
                "screenplay_id": screenplay_id,
                "conversation_id": conversation_id,
                "instance_id": instance_id
            })
        except Exception as broadcast_err:
            logger.warning(f"⚠️ Failed to broadcast councilor_error event: {broadcast_err}")

    async def _update_instance_stats(self, instance_id: str, success: bool, duration_ms: int = 0):
        """
        Update councilor instance execution statistics (normalized structure).

        Args:
            instance_id: Instance ID
            success: Whether execution was successful
            duration_ms: Execution duration in milliseconds
        """
        try:
            agent_instances = self.db.agent_instances
            instance = await agent_instances.find_one({"instance_id": instance_id})

            if not instance:
                logger.warning(f"Instance {instance_id} not found for stats update")
                return

            # Get current statistics (support both old 'stats' and new 'statistics')
            statistics = instance.get("statistics", instance.get("stats", {
                "task_count": 0,
                "total_execution_time": 0.0,
                "average_execution_time": 0.0,
                "success_count": 0,
                "error_count": 0,
                "total_executions": 0,
                "success_rate": 0.0,
                "last_execution": None
            }))

            # Calculate new statistics
            now = datetime.utcnow()
            task_count = statistics.get("task_count", statistics.get("total_executions", 0)) + 1
            total_time = statistics.get("total_execution_time", 0.0) + duration_ms
            avg_time = total_time / task_count if task_count > 0 else 0.0
            success_count = statistics.get("success_count", 0) + (1 if success else 0)
            error_count = statistics.get("error_count", 0) + (0 if success else 1)
            success_rate = (success_count / task_count) * 100.0 if task_count > 0 else 0.0

            # Update in database with normalized structure
            await agent_instances.update_one(
                {"instance_id": instance_id},
                {"$set": {
                    # Normalized statistics (same as regular agent_instances)
                    "statistics.task_count": task_count,
                    "statistics.total_execution_time": total_time,
                    "statistics.average_execution_time": round(avg_time, 2),
                    "statistics.last_task_duration": duration_ms,
                    "statistics.last_task_completed_at": now.isoformat(),
                    "statistics.success_count": success_count,
                    "statistics.error_count": error_count,
                    "statistics.last_exit_code": 0 if success else 1,
                    # Councilor-specific (for backwards compatibility)
                    "statistics.total_executions": task_count,
                    "statistics.success_rate": round(success_rate, 1),
                    "statistics.last_execution": now.isoformat(),
                    # Top-level fields
                    "last_execution": now.isoformat(),
                    "updated_at": now.isoformat()
                }}
            )

            logger.debug(
                f"📊 Statistics updated for instance {instance_id}: "
                f"{task_count} executions, {success_rate:.1f}% success, avg {avg_time:.0f}ms"
            )

        except Exception as e:
            logger.warning(f"⚠️ Failed to update statistics for instance {instance_id}: {e}")

    def _parse_interval_trigger(self, value: str) -> IntervalTrigger:
        """
        Convert interval string to APScheduler trigger

        Args:
            value: Interval string like "30m", "1h", "2d"

        Returns:
            IntervalTrigger instance

        Examples:
            "30m" -> IntervalTrigger(minutes=30)
            "1h"  -> IntervalTrigger(hours=1)
            "2d"  -> IntervalTrigger(days=2)
        """
        match = re.match(r'^(\d+)(m|h|d)$', value)
        if not match:
            raise ValueError(f"Invalid interval format: {value}. Expected format: <number><unit> (e.g., 30m, 1h, 2d)")

        num, unit = match.groups()
        num = int(num)

        if unit == 'm':
            return IntervalTrigger(minutes=num)
        elif unit == 'h':
            return IntervalTrigger(hours=num)
        elif unit == 'd':
            return IntervalTrigger(days=num)
        else:
            raise ValueError(f"Unknown unit: {unit}")

    async def _execute_councilor_task(self, agent_id: str, config: dict):
        """
        Execute a councilor task

        This method is called by APScheduler at the scheduled intervals.

        Args:
            agent_id: Agent ID of the councilor
            config: Councilor configuration dict
        """
        task = config.get("task", {})
        customization = config.get("customization", {})
        display_name = customization.get("display_name", agent_id)
        task_name = task.get("name", "Unknown Task")

        start_time = datetime.utcnow()
        # Use milliseconds for unique execution_id to avoid collisions
        execution_id = f"exec_{agent_id}_{int(start_time.timestamp() * 1000)}"

        logger.info(f"🔎 Executing councilor task: {display_name} ({agent_id})")

        # 🔔 Emit "councilor_started" event via WebSocket
        try:
            from src.api.websocket import gamification_manager
            await gamification_manager.broadcast("councilor_started", {
                "councilor_id": agent_id,
                "task_name": task_name,
                "display_name": display_name,
                "execution_id": execution_id,
                "started_at": start_time.isoformat()
            })
        except Exception as e:
            logger.warning(f"⚠️ Failed to broadcast councilor_started event: {e}")

        try:
            # Execute agent via Conductor API
            # Conductor API will:
            # 1. Build the complete prompt using PromptEngine (persona, screenplay, playbook, history, user input)
            # 2. Insert task into MongoDB tasks collection with the complete prompt
            # 3. Wait for watcher to execute via LLM
            # 4. Return the result
            prompt_text = task.get("prompt", "Analyze the project and provide insights")

            logger.info(f"🔍 [COUNCILOR] Calling Conductor API for {agent_id}")
            logger.info(f"   - Input text: {prompt_text[:100]}...")
            logger.info(f"   - Conductor will build full prompt with PromptEngine")

            result = await self.conductor_client.execute_agent(
                agent_name=agent_id,
                prompt=prompt_text,  # ← This is just user input, Conductor will build full prompt
                instance_id=f"councilor_{agent_id}_{int(start_time.timestamp() * 1000)}",
                context_mode="stateless",
                timeout=600
            )

            end_time = datetime.utcnow()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Analyze severity of the result
            output = result.get("result", "") if isinstance(result, dict) else str(result)
            severity = self._analyze_severity(output)

            logger.info(f"✅ [COUNCILOR] Execution completed for {agent_id}")
            logger.info(f"   - Severity: {severity}")
            logger.info(f"   - Duration: {duration_ms}ms")
            logger.info(f"   - Note: Task already saved in MongoDB by Conductor API with full prompt")

            # NOTE: We don't insert to tasks collection here anymore!
            # The Conductor API already inserted the task with the COMPLETE prompt from PromptEngine.
            # Inserting again would create a duplicate with wrong prompt.

            # Update agent statistics
            await self._update_agent_stats(agent_id, severity == "success")

            logger.info(
                f"✅ Councilor task completed: {display_name} "
                f"(severity={severity}, duration={duration_ms}ms)"
            )

            # 🔔 Emit "councilor_completed" event via WebSocket
            try:
                from src.api.websocket import gamification_manager
                await gamification_manager.broadcast("councilor_completed", {
                    "councilor_id": agent_id,
                    "task_name": task_name,
                    "display_name": display_name,
                    "execution_id": execution_id,
                    "status": "completed",
                    "severity": severity,
                    "started_at": start_time.isoformat(),
                    "completed_at": end_time.isoformat(),
                    "duration_ms": duration_ms
                })
            except Exception as e:
                logger.warning(f"⚠️ Failed to broadcast councilor_completed event: {e}")

            # TODO: Send notifications based on config.notifications

        except Exception as e:
            logger.error(f"❌ Error executing councilor task {agent_id}: {e}", exc_info=True)

            end_time = datetime.utcnow()

            # Save error result to tasks collection
            await self.tasks_collection.insert_one({
                "task_id": execution_id,
                "agent_id": agent_id,
                "instance_id": f"councilor_{agent_id}_{int(start_time.timestamp() * 1000)}",
                "is_councilor_execution": True,  # Flag to identify councilor tasks
                "councilor_config": {
                    "task_name": task_name,
                    "display_name": display_name
                },
                "prompt": prompt_text,  # ← NOVO: Salva o prompt usado (mesmo em caso de erro)
                "status": "error",
                "severity": "error",
                "result": None,
                "error": str(e),
                "created_at": start_time,
                "completed_at": end_time,
                "duration": (end_time - start_time).total_seconds()
            })

            # Update stats with failure
            await self._update_agent_stats(agent_id, success=False)

            # 🔔 Emit "councilor_error" event via WebSocket
            try:
                from src.api.websocket import gamification_manager
                await gamification_manager.broadcast("councilor_error", {
                    "councilor_id": agent_id,
                    "task_name": task_name,
                    "display_name": display_name,
                    "execution_id": execution_id,
                    "status": "error",
                    "severity": "error",
                    "error": str(e),
                    "started_at": start_time.isoformat(),
                    "completed_at": datetime.utcnow().isoformat()
                })
            except Exception as broadcast_err:
                logger.warning(f"⚠️ Failed to broadcast councilor_error event: {broadcast_err}")

    def _analyze_severity(self, output: str) -> str:
        """
        Analyze output text to determine severity level

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

    async def _update_agent_stats(self, agent_id: str, success: bool):
        """
        Update agent execution statistics

        Args:
            agent_id: Agent ID
            success: Whether execution was successful
        """
        try:
            agent = await self.agents_collection.find_one({"agent_id": agent_id})

            if not agent:
                logger.warning(f"Agent {agent_id} not found for stats update")
                return

            stats = agent.get("stats", {
                "total_executions": 0,
                "success_rate": 0.0,
                "last_execution": None
            })

            # Calculate new statistics
            total = stats.get("total_executions", 0) + 1
            old_rate = stats.get("success_rate", 0.0)
            old_successes = int((old_rate / 100.0) * (total - 1)) if total > 1 else 0
            new_successes = old_successes + (1 if success else 0)
            new_rate = (new_successes / total) * 100.0

            # Update in database
            await self.agents_collection.update_one(
                {"agent_id": agent_id},
                {"$set": {
                    "stats.total_executions": total,
                    "stats.last_execution": datetime.utcnow(),
                    "stats.success_rate": round(new_rate, 1)
                }}
            )

            logger.debug(
                f"📊 Stats updated for {agent_id}: "
                f"{total} executions, {new_rate:.1f}% success"
            )

        except Exception as e:
            logger.warning(f"⚠️ Failed to update stats for {agent_id}: {e}")

    async def pause_councilor(self, agent_id: str):
        """
        Pause a councilor's scheduled tasks

        Args:
            agent_id: Agent ID to pause
        """
        try:
            self.scheduler.pause_job(agent_id, jobstore='default')
            logger.info(f"⏸️ Paused: {agent_id}")
        except Exception as e:
            logger.error(f"❌ Failed to pause {agent_id}: {e}")
            raise

    async def resume_councilor(self, agent_id: str):
        """
        Resume a paused councilor's scheduled tasks

        Args:
            agent_id: Agent ID to resume
        """
        try:
            self.scheduler.resume_job(agent_id, jobstore='default')
            logger.info(f"▶️ Resumed: {agent_id}")
        except Exception as e:
            logger.error(f"❌ Failed to resume {agent_id}: {e}")
            raise

    async def remove_councilor(self, agent_id: str):
        """
        Remove a councilor from the scheduler

        Args:
            agent_id: Agent ID to remove
        """
        try:
            self.scheduler.remove_job(agent_id, jobstore='default')
            logger.info(f"🗑️ Removed: {agent_id}")
        except Exception as e:
            # Job might not exist, that's okay
            logger.debug(f"Job {agent_id} not found in scheduler: {e}")

    async def reload_councilor(self, agent_id: str):
        """
        Reload a councilor's configuration and reschedule

        Args:
            agent_id: Agent ID to reload
        """
        try:
            # Fetch fresh config from database
            councilor = await self.agents_collection.find_one({"agent_id": agent_id})

            if not councilor:
                logger.warning(f"Councilor {agent_id} not found")
                return

            if not councilor.get("is_councilor"):
                logger.warning(f"Agent {agent_id} is not a councilor")
                return

            # Reschedule with new config
            await self.schedule_councilor(councilor)
            logger.info(f"🔄 Reloaded: {agent_id}")

        except Exception as e:
            logger.error(f"❌ Failed to reload {agent_id}: {e}")
            raise

    def get_scheduled_jobs(self) -> list:
        """
        Get list of currently scheduled jobs

        Returns:
            List of job info dictionaries
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        return jobs

    async def execute_councilor_now(self, agent_id: str) -> dict:
        """
        Execute a councilor task immediately (manual trigger)

        Args:
            agent_id: Agent ID of the councilor to execute

        Returns:
            Execution result dict with status, severity, output
        """
        logger.info(f"🚀 [EXECUTE NOW] Triggering immediate execution for {agent_id}")

        try:
            # Fetch councilor from database
            councilor = await self.agents_collection.find_one({"agent_id": agent_id})

            if not councilor:
                raise ValueError(f"Councilor {agent_id} not found")

            if not councilor.get("is_councilor"):
                raise ValueError(f"Agent {agent_id} is not a councilor")

            config = councilor.get("councilor_config")
            if not config:
                raise ValueError(f"Councilor {agent_id} has no configuration")

            # Execute the task directly (bypassing scheduler)
            await self._execute_councilor_task(agent_id, config)

            # Get updated stats
            updated_agent = await self.agents_collection.find_one({"agent_id": agent_id})
            stats = updated_agent.get("stats", {}) if updated_agent else {}

            return {
                "status": "completed",
                "agent_id": agent_id,
                "stats": stats
            }

        except Exception as e:
            logger.error(f"❌ [EXECUTE NOW] Failed for {agent_id}: {e}")
            raise

    async def shutdown(self):
        """Shutdown scheduler gracefully"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
                logger.info("🛑 Scheduler stopped")
        except Exception as e:
            logger.error(f"❌ Error during scheduler shutdown: {e}")
