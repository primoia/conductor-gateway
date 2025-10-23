"""
Modelos Pydantic para API do Gateway
"""

from typing import Any, Optional
from pydantic import BaseModel


class AgentExecuteRequest(BaseModel):
    """Payload para execução de agente."""

    input_text: str
    instance_id: Optional[str] = None
    context_mode: str = "stateless"
    cwd: Optional[str] = None
    screenplay_id: Optional[str] = None
    document_id: Optional[str] = None  # Deprecated, mantido para compatibilidade
    position: Optional[dict[str, Any]] = None
    ai_provider: Optional[str] = None
