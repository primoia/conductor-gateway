"""
Portfolio Chat Router - Public endpoint for portfolio assistant
"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.clients.conductor_client import ConductorClient
from src.config.settings import CONDUCTOR_CONFIG

logger = logging.getLogger(__name__)

# Initialize rate limiter (20 requests per minute per IP)
limiter = Limiter(key_func=get_remote_address)

# Create router with v1 prefix
router = APIRouter(prefix="/api/v1", tags=["portfolio"])

# Agent configuration
PORTFOLIO_AGENT_NAME = "PortfolioAssistant_Agent"


# Dependency to get conductor client
async def get_conductor_client():
    """Get conductor client instance"""
    from src.api.app import conductor_client
    if not conductor_client:
        raise HTTPException(status_code=503, detail="Conductor client not initialized")
    return conductor_client


class PortfolioChatRequest(BaseModel):
    """Request model for portfolio chat endpoint."""

    message: str = Field(..., description="User message to the portfolio assistant", min_length=1, max_length=2000)
    session_id: str | None = Field(None, description="Optional session ID for conversation context")


class PortfolioChatResponse(BaseModel):
    """Response model for portfolio chat endpoint."""

    response: str = Field(..., description="Assistant's response")
    session_id: str | None = Field(None, description="Session ID for conversation tracking")


@router.post("/portfolio-chat", response_model=PortfolioChatResponse)
@limiter.limit("20/minute")
async def portfolio_chat(
    request: Request,
    payload: PortfolioChatRequest,
    client: ConductorClient = Depends(get_conductor_client)
) -> PortfolioChatResponse:
    """
    Portfolio chat endpoint - allows users to interact with the portfolio assistant.

    Rate limited to 20 requests per minute per IP address.

    Args:
        request: FastAPI request object (used for rate limiting)
        payload: Chat request payload
        client: ConductorClient dependency

    Returns:
        PortfolioChatResponse with assistant's response

    Raises:
        HTTPException: 429 if rate limit exceeded
        HTTPException: 400 if message is invalid
        HTTPException: 500 if agent execution fails
    """
    try:
        logger.info(f"[Portfolio Chat] Received message: {payload.message[:100]}...")

        # Generate or use existing session_id for context continuity
        session_id = payload.session_id or f"portfolio-session-{uuid.uuid4()}"

        # Execute the PortfolioAssistant_Agent via conductor-api
        # Using stateful mode to maintain conversation context
        response = await client.execute_agent(
            agent_name=PORTFOLIO_AGENT_NAME,
            prompt=payload.message,
            instance_id=session_id,
            context_mode="stateful",  # Maintain conversation history
            cwd=CONDUCTOR_CONFIG.get("project_path"),
            timeout=60,  # Shorter timeout for public endpoint
            ai_provider=None  # Use default provider from agent config
        )

        # Extract the agent's response
        agent_response = response.get("result") or response.get("stdout") or str(response)

        logger.info(f"[Portfolio Chat] Agent responded successfully, session: {session_id}")

        return PortfolioChatResponse(
            response=agent_response,
            session_id=session_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Portfolio Chat] Error processing request: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Sorry, I'm having trouble responding right now. Please try again later."
        )
