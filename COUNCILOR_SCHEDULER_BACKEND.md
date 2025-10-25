# Backend Scheduler para Conselheiros

## Problema
Atualmente o scheduler está no frontend (Angular), o que causa:
- ❌ Perda de timers ao recarregar página
- ❌ Execuções duplicadas com múltiplas abas
- ❌ Não funciona quando usuário fecha o navegador

## Solução: Scheduler no Backend

### 1. Instalar APScheduler

```bash
cd /mnt/ramdisk/primoia-main/conductor-community/src/conductor-gateway
poetry add apscheduler
```

### 2. Criar Scheduler Service

Arquivo: `src/services/councilor_scheduler.py`

```python
"""
Backend Scheduler for Councilors - Persistent task execution
"""

import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.mongodb import MongoDBJobStore
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class CouncilorBackendScheduler:
    """
    Backend scheduler for councilor tasks
    - Persistent: Survives server restarts
    - No duplicates: Single source of truth
    - Always running: Independent of frontend
    """

    def __init__(self, db: AsyncIOMotorDatabase, conductor_client):
        self.db = db
        self.conductor_client = conductor_client

        # Configure APScheduler with MongoDB persistence
        jobstores = {
            'default': MongoDBJobStore(
                database='conductor_state',
                collection='apscheduler_jobs',
                client=db.client
            )
        }

        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone='UTC'
        )

        logger.info("🏛️ Councilor Backend Scheduler initialized")

    async def start(self):
        """Start the scheduler"""
        # Load active councilors from database
        await self.load_councilors()

        # Start APScheduler
        self.scheduler.start()
        logger.info("✅ Scheduler started")

    async def load_councilors(self):
        """Load all active councilors and schedule their tasks"""
        agents_collection = self.db.agents

        councilors = await agents_collection.find({
            "is_councilor": True,
            "councilor_config.schedule.enabled": True
        }).to_list(length=None)

        logger.info(f"📋 Loading {len(councilors)} active councilors")

        for councilor in councilors:
            await self.schedule_councilor(councilor)

    async def schedule_councilor(self, councilor: dict):
        """Schedule a councilor task"""
        agent_id = councilor["agent_id"]
        config = councilor["councilor_config"]
        schedule = config["schedule"]

        # Remove existing job if exists
        self.scheduler.remove_job(agent_id, jobstore='default')

        # Create trigger based on schedule type
        if schedule["type"] == "interval":
            # Parse interval: "30m" -> minutes=30
            trigger = self._parse_interval_trigger(schedule["value"])
        else:  # cron
            # Parse cron: "0 9 * * 1" -> Monday at 9am
            trigger = CronTrigger.from_crontab(schedule["value"])

        # Add job to scheduler
        self.scheduler.add_job(
            func=self._execute_councilor_task,
            trigger=trigger,
            id=agent_id,
            name=f"Councilor: {councilor.get('name', agent_id)}",
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

    def _parse_interval_trigger(self, value: str) -> IntervalTrigger:
        """Convert interval string to trigger"""
        # "30m" -> minutes=30
        # "1h"  -> hours=1
        # "2d"  -> days=2

        import re
        match = re.match(r'^(\d+)(m|h|d)$', value)
        if not match:
            raise ValueError(f"Invalid interval: {value}")

        num, unit = match.groups()
        num = int(num)

        if unit == 'm':
            return IntervalTrigger(minutes=num)
        elif unit == 'h':
            return IntervalTrigger(hours=num)
        elif unit == 'd':
            return IntervalTrigger(days=num)

    async def _execute_councilor_task(self, agent_id: str, config: dict):
        """Execute councilor task"""
        try:
            logger.info(f"🔎 Executing councilor task: {agent_id}")

            # Get task details
            task = config["task"]

            # Execute agent via Conductor API
            start_time = datetime.utcnow()

            result = await self.conductor_client.execute_agent(
                agent_name=agent_id,
                prompt=task["prompt"],
                instance_id=f"councilor_{agent_id}_{int(start_time.timestamp())}",
                context_mode="stateless",
                timeout=600
            )

            end_time = datetime.utcnow()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Analyze severity
            severity = self._analyze_severity(result.get("result", ""))

            # Save execution result
            executions_collection = self.db.councilor_executions
            await executions_collection.insert_one({
                "execution_id": f"exec_{agent_id}_{int(start_time.timestamp())}",
                "councilor_id": agent_id,
                "started_at": start_time,
                "completed_at": end_time,
                "duration_ms": duration_ms,
                "status": "completed",
                "severity": severity,
                "output": result.get("result", ""),
                "created_at": datetime.utcnow()
            })

            # Update agent stats
            await self._update_agent_stats(agent_id, severity == "success")

            # Send notification if configured
            if self._should_notify(config["notifications"], severity):
                await self._send_notification(agent_id, config, severity, result)

            logger.info(
                f"✅ Councilor task completed: {agent_id} "
                f"(severity={severity}, duration={duration_ms}ms)"
            )

        except Exception as e:
            logger.error(f"❌ Error executing councilor task {agent_id}: {e}")

            # Save error result
            executions_collection = self.db.councilor_executions
            await executions_collection.insert_one({
                "execution_id": f"exec_{agent_id}_{int(datetime.utcnow().timestamp())}",
                "councilor_id": agent_id,
                "started_at": datetime.utcnow(),
                "status": "error",
                "severity": "error",
                "error": str(e),
                "created_at": datetime.utcnow()
            })

    def _analyze_severity(self, output: str) -> str:
        """Analyze output to determine severity"""
        lower_output = output.lower()

        error_keywords = ['crítico', 'erro', 'falha', 'critical', 'error', 'fail']
        if any(keyword in lower_output for keyword in error_keywords):
            return 'error'

        warning_keywords = ['alerta', 'atenção', 'warning', 'aviso', 'vulnerab']
        if any(keyword in lower_output for keyword in warning_keywords):
            return 'warning'

        return 'success'

    async def _update_agent_stats(self, agent_id: str, success: bool):
        """Update agent statistics"""
        agents_collection = self.db.agents
        agent = await agents_collection.find_one({"agent_id": agent_id})

        stats = agent.get("stats", {
            "total_executions": 0,
            "success_rate": 0.0
        })

        total = stats.get("total_executions", 0) + 1
        old_rate = stats.get("success_rate", 0.0)
        old_successes = int((old_rate / 100.0) * (total - 1)) if total > 1 else 0
        new_successes = old_successes + (1 if success else 0)
        new_rate = (new_successes / total) * 100.0

        await agents_collection.update_one(
            {"agent_id": agent_id},
            {"$set": {
                "stats.total_executions": total,
                "stats.last_execution": datetime.utcnow(),
                "stats.success_rate": round(new_rate, 1)
            }}
        )

    def _should_notify(self, notifications: dict, severity: str) -> bool:
        """Check if should send notification"""
        if severity == 'error' and notifications.get('on_error'):
            return True
        if severity == 'warning' and notifications.get('on_warning'):
            return True
        if severity == 'success' and notifications.get('on_success'):
            return True
        return False

    async def _send_notification(self, agent_id: str, config: dict, severity: str, result: dict):
        """Send notification (implement based on channels)"""
        # TODO: Implement notification sending
        # - WebSocket to frontend
        # - Email via SMTP
        # - Slack/Discord webhook
        logger.info(f"📬 Notification sent for {agent_id}: {severity}")

    async def pause_councilor(self, agent_id: str):
        """Pause a councilor"""
        self.scheduler.pause_job(agent_id, jobstore='default')
        logger.info(f"⏸️ Paused: {agent_id}")

    async def resume_councilor(self, agent_id: str):
        """Resume a councilor"""
        self.scheduler.resume_job(agent_id, jobstore='default')
        logger.info(f"▶️ Resumed: {agent_id}")

    async def remove_councilor(self, agent_id: str):
        """Remove a councilor from scheduler"""
        self.scheduler.remove_job(agent_id, jobstore='default')
        logger.info(f"🗑️ Removed: {agent_id}")

    async def shutdown(self):
        """Shutdown scheduler gracefully"""
        self.scheduler.shutdown(wait=True)
        logger.info("🛑 Scheduler stopped")
```

### 3. Integrar no FastAPI App

Arquivo: `src/api/app.py`

```python
# Adicionar no lifespan
from src.services.councilor_scheduler import CouncilorBackendScheduler

# Global scheduler instance
councilor_scheduler: CouncilorBackendScheduler | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global mongo_client, mongo_db, conductor_client, councilor_scheduler

    # ... (código existente de inicialização)

    # Inicializar e iniciar scheduler de conselheiros
    councilor_scheduler = CouncilorBackendScheduler(mongo_db, conductor_client)
    await councilor_scheduler.start()
    logger.info("✅ Councilor Backend Scheduler started")

    yield

    # Shutdown
    if councilor_scheduler:
        await councilor_scheduler.shutdown()
        logger.info("Councilor scheduler stopped")

    # ... (resto do shutdown)
```

### 4. Atualizar Endpoints

```python
# Quando promover conselheiro
@router.post("/{agent_id}/promote-councilor")
async def promote_to_councilor(...):
    # ... (código existente)

    # Agendar no backend scheduler
    await councilor_scheduler.schedule_councilor(updated_agent)

    return response

# Quando pausar
@router.patch("/{agent_id}/councilor-schedule")
async def update_schedule(...):
    # ... (código existente)

    if request.enabled:
        await councilor_scheduler.resume_councilor(agent_id)
    else:
        await councilor_scheduler.pause_councilor(agent_id)

    return response
```

### 5. Remover Frontend Scheduler

O `CouncilorSchedulerService` no Angular passa a ser apenas:
- Visualizador de conselheiros
- Interface para configuração
- **SEM setInterval()**

## Vantagens

✅ **Persistente**: Jobs sobrevivem a restart do servidor
✅ **Único**: Não duplica com múltiplas abas
✅ **Confiável**: Funciona mesmo sem ninguém no frontend
✅ **Escalável**: Pode rodar em servidor separado
✅ **Rastreável**: Jobs salvos no MongoDB

## MongoDB Collections

```
conductor_state
├── agents (já existe)
├── councilor_executions (já existe)
└── apscheduler_jobs (NOVO - persiste jobs)
    └── {
        _id: "TestQuickValidation_Agent",
        next_run_time: ISODate("2025-10-25T13:00:00Z"),
        job_state: <serialized job data>
      }
```
