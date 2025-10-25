"""
Pydantic models for Councilor system

Councilors are promoted agents that execute periodic automated tasks
to monitor project quality (similar to SimCity advisors).
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, validator


# ========== Schedule Models ==========

class CouncilorSchedule(BaseModel):
    """Schedule configuration for councilor tasks"""
    type: Literal["interval", "cron"] = Field(
        ...,
        description="Schedule type: interval (e.g., '30m') or cron expression"
    )
    value: str = Field(
        ...,
        description="Schedule value: '30m', '1h', '2h' for interval or cron expression"
    )
    enabled: bool = Field(
        default=True,
        description="Whether the schedule is active"
    )

    @validator('value')
    def validate_schedule_value(cls, v, values):
        """Validate schedule value format"""
        schedule_type = values.get('type')

        if schedule_type == 'interval':
            # Validate interval format: number + unit (m/h/d)
            import re
            if not re.match(r'^\d+[mhd]$', v):
                raise ValueError("Interval must be in format: number + unit (m/h/d), e.g., '30m', '1h', '2d'")
        elif schedule_type == 'cron':
            # Basic cron validation (5 fields)
            parts = v.split()
            if len(parts) != 5:
                raise ValueError("Cron expression must have 5 fields: minute hour day month weekday")

        return v


# ========== Task Models ==========

class CouncilorTask(BaseModel):
    """Task definition for councilor"""
    name: str = Field(..., description="Task name")
    prompt: str = Field(..., description="Prompt template to execute")
    context_files: Optional[List[str]] = Field(
        default=None,
        description="Optional files to include in execution context"
    )
    output_format: Literal["summary", "detailed", "checklist"] = Field(
        default="checklist",
        description="Expected output format"
    )

    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Task name cannot be empty")
        return v.strip()

    @validator('prompt')
    def validate_prompt(cls, v):
        if not v or not v.strip():
            raise ValueError("Task prompt cannot be empty")
        if len(v) > 10000:
            raise ValueError("Task prompt too long (max 10000 characters)")
        return v.strip()


# ========== Notifications Models ==========

class CouncilorNotifications(BaseModel):
    """Notification configuration"""
    on_success: bool = Field(default=False, description="Notify on successful execution")
    on_warning: bool = Field(default=True, description="Notify on warnings")
    on_error: bool = Field(default=True, description="Notify on errors")
    channels: List[Literal["panel", "toast", "email"]] = Field(
        default=["panel"],
        description="Notification channels"
    )

    @validator('channels')
    def validate_channels(cls, v):
        if not v or len(v) == 0:
            raise ValueError("At least one notification channel must be selected")
        return list(set(v))  # Remove duplicates


# ========== Councilor Config (Complete) ==========

class CouncilorConfig(BaseModel):
    """Complete councilor configuration"""
    title: str = Field(..., description="Councilor title/role")
    schedule: CouncilorSchedule
    task: CouncilorTask
    notifications: CouncilorNotifications

    @validator('title')
    def validate_title(cls, v):
        if not v or not v.strip():
            raise ValueError("Councilor title cannot be empty")
        return v.strip()


# ========== Agent Customization ==========

class AgentCustomization(BaseModel):
    """Agent visual customization"""
    enabled: bool = Field(default=True, description="Whether customization is enabled")
    display_name: Optional[str] = Field(None, description="Custom display name")
    avatar_url: Optional[str] = Field(None, description="Custom avatar URL")
    color: Optional[str] = Field(None, description="Custom color hex")

    @validator('color')
    def validate_color(cls, v):
        if v is not None and not v.startswith('#'):
            raise ValueError("Color must be a hex color starting with #")
        return v


# ========== Request Models ==========

class PromoteToCouncilorRequest(BaseModel):
    """Request to promote agent to councilor"""
    councilor_config: CouncilorConfig
    customization: Optional[AgentCustomization] = None

    class Config:
        json_schema_extra = {
            "example": {
                "councilor_config": {
                    "title": "Conselheiro de Qualidade",
                    "schedule": {
                        "type": "interval",
                        "value": "30m",
                        "enabled": True
                    },
                    "task": {
                        "name": "Verificar Cobertura de Testes",
                        "prompt": "Analise a cobertura de testes do projeto...",
                        "context_files": ["package.json"],
                        "output_format": "checklist"
                    },
                    "notifications": {
                        "on_success": False,
                        "on_warning": True,
                        "on_error": True,
                        "channels": ["panel", "toast"]
                    }
                },
                "customization": {
                    "display_name": "Dra. Testa",
                    "color": "#10b981"
                }
            }
        }


class UpdateCouncilorConfigRequest(BaseModel):
    """Request to update councilor configuration"""
    schedule: Optional[CouncilorSchedule] = None
    task: Optional[CouncilorTask] = None
    notifications: Optional[CouncilorNotifications] = None


class UpdateScheduleRequest(BaseModel):
    """Request to pause/resume schedule"""
    enabled: bool = Field(..., description="Enable or disable schedule")


# ========== Execution Models ==========

class CouncilorExecutionCreate(BaseModel):
    """Request to save execution result"""
    execution_id: str
    councilor_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: Literal["running", "completed", "error"]
    severity: Literal["success", "warning", "error"]
    output: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class CouncilorExecutionResponse(BaseModel):
    """Execution result response"""
    id: str = Field(..., alias="_id")
    execution_id: str
    councilor_id: str
    started_at: datetime
    completed_at: Optional[datetime]
    status: str
    severity: str
    output: Optional[str]
    error: Optional[str]
    duration_ms: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


# ========== Agent Response Models ==========

class AgentStats(BaseModel):
    """Agent execution statistics"""
    total_executions: int = 0
    last_execution: Optional[datetime] = None
    success_rate: float = 0.0


class AgentWithCouncilorResponse(BaseModel):
    """Agent with councilor information"""
    id: str = Field(..., alias="_id")
    agent_id: str
    name: Optional[str] = None
    title: Optional[str] = None
    emoji: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    model: Optional[str] = None
    is_councilor: bool = False
    councilor_config: Optional[CouncilorConfig] = None
    customization: Optional[AgentCustomization] = None
    stats: Optional[AgentStats] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        populate_by_name = True


# ========== Report Models ==========

class CouncilorReportResponse(BaseModel):
    """Councilor execution report"""
    councilor_id: str
    councilor_name: str
    recent_executions: List[CouncilorExecutionResponse]
    total_executions: int
    success_rate: float
    next_execution: Optional[datetime] = None


# ========== List Response Models ==========

class AgentListResponse(BaseModel):
    """List of agents response"""
    agents: List[AgentWithCouncilorResponse]
    count: int


class ExecutionListResponse(BaseModel):
    """List of executions response"""
    executions: List[CouncilorExecutionResponse]
    count: int


# ========== Success Response Models ==========

class SuccessResponse(BaseModel):
    """Generic success response"""
    success: bool = True
    message: str
    agent: Optional[AgentWithCouncilorResponse] = None
    execution: Optional[CouncilorExecutionResponse] = None


class ScheduleResponse(BaseModel):
    """Schedule update response"""
    success: bool = True
    message: str
    schedule: CouncilorSchedule
