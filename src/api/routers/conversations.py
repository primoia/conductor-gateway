"""
🔥 NOVO: Router proxy para conversas globais.

Encaminha requisições de /api/conversations para o serviço conductor backend.

Ref: PLANO_REFATORACAO_CONVERSATION_ID.md - Fase 1
Data: 2025-11-01
"""

import logging
import httpx
from fastapi import APIRouter, HTTPException, Request, Response, Path, Query
from typing import Optional

from src.config.settings import CONDUCTOR_CONFIG

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/conversations", tags=["Conversations"])

# URL do serviço conductor backend
CONDUCTOR_URL = CONDUCTOR_CONFIG['conductor_api_url']


async def proxy_request(
    method: str,
    path: str,
    request: Request,
    timeout: float = 30.0
):
    """
    Faz proxy de uma requisição para o serviço conductor.

    Args:
        method: Método HTTP (GET, POST, PUT, DELETE)
        path: Caminho da rota
        request: Request original do FastAPI
        timeout: Timeout em segundos

    Returns:
        Response do conductor
    """
    url = f"{CONDUCTOR_URL}{path}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Preparar headers
            headers = dict(request.headers)
            headers.pop("host", None)  # Remover host header

            # Preparar body (se houver)
            body = await request.body()

            # Fazer requisição
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body if body else None,
                params=request.query_params
            )

            # Retornar response
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )

    except httpx.TimeoutException:
        logger.error(f"Timeout ao fazer proxy para {url}")
        raise HTTPException(status_code=504, detail="Gateway timeout")
    except httpx.RequestError as e:
        logger.error(f"Erro ao fazer proxy para {url}: {e}")
        raise HTTPException(status_code=502, detail=f"Bad gateway: {str(e)}")
    except Exception as e:
        logger.error(f"Erro inesperado no proxy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ==========================================
# Endpoints de Proxy
# ==========================================

@router.post("/")
async def create_conversation(request: Request):
    """Proxy: Criar nova conversa."""
    return await proxy_request("POST", "/conversations/", request)


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str = Path(...),
    request: Request = None
):
    """Proxy: Obter conversa por ID."""
    return await proxy_request("GET", f"/conversations/{conversation_id}", request)


@router.post("/{conversation_id}/messages")
async def add_message(
    conversation_id: str = Path(...),
    request: Request = None
):
    """Proxy: Adicionar mensagem à conversa."""
    return await proxy_request("POST", f"/conversations/{conversation_id}/messages", request)


@router.put("/{conversation_id}/active-agent")
async def set_active_agent(
    conversation_id: str = Path(...),
    request: Request = None
):
    """Proxy: Alterar agente ativo."""
    return await proxy_request("PUT", f"/conversations/{conversation_id}/active-agent", request)


@router.get("/")
async def list_conversations(request: Request):
    """Proxy: Listar conversas."""
    return await proxy_request("GET", "/conversations/", request)


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str = Path(...),
    request: Request = None
):
    """Proxy: Deletar conversa."""
    return await proxy_request("DELETE", f"/conversations/{conversation_id}", request)


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str = Path(...),
    request: Request = None
):
    """Proxy: Obter mensagens da conversa."""
    return await proxy_request("GET", f"/conversations/{conversation_id}/messages", request)
