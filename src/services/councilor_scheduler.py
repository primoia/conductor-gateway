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
            # Find all councilors with enabled schedules
            cursor = self.agents_collection.find({
                "is_councilor": True,
                "councilor_config.schedule.enabled": True
            })

            councilors = await cursor.to_list(length=None)

            logger.info(f"📋 Loading {len(councilors)} active councilors")

            for councilor in councilors:
                try:
                    await self.schedule_councilor(councilor)
                except Exception as e:
                    agent_id = councilor.get("agent_id", "unknown")
                    logger.error(f"❌ Failed to schedule councilor {agent_id}: {e}")

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

    async def shutdown(self):
        """Shutdown scheduler gracefully"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
                logger.info("🛑 Scheduler stopped")
        except Exception as e:
            logger.error(f"❌ Error during scheduler shutdown: {e}")
