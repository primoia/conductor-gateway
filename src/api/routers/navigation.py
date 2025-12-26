# src/api/routers/navigation.py
"""
Navigation State Router - Proxy para o endpoint de navegação na conductor-api

MODELO DE DADOS:
- Cada roteiro (screenplay) tem seu próprio registro de estado
- Chave composta: user_id + screenplay_id
- Ao trocar de roteiro, recupera o estado salvo daquele roteiro
"""
from fastapi import APIRouter, HTTPException, Header, Request, Query
from typing import Optional
import httpx
import os
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/navigation", tags=["Navigation"])

CONDUCTOR_API_URL = os.getenv("CONDUCTOR_API_URL", "http://conductor-api:8000")


@router.get("")
async def get_navigation_state(
    screenplay_id: Optional[str] = Query(None, description="ID do roteiro"),
    conversation_id: Optional[str] = Query(None, description="ID da conversa"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id")
):
    """
    Proxy GET para conductor-api/navigation

    Casos:
    1. screenplay_id + conversation_id → retorna instance_id da conversa
    2. screenplay_id → retorna conversation_id + instance_id do roteiro
    3. Nenhum → retorna último roteiro acessado com seu estado
    """
    try:
        headers = {}
        if x_user_id:
            headers["X-User-Id"] = x_user_id
        if x_session_id:
            headers["X-Session-Id"] = x_session_id

        # Construir URL com query params
        url = f"{CONDUCTOR_API_URL}/navigation"
        params = {}
        if screenplay_id:
            params["screenplay_id"] = screenplay_id
        if conversation_id:
            params["conversation_id"] = conversation_id

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=headers,
                params=params,
                timeout=10.0
            )
            return response.json()

    except Exception as e:
        logger.error(f"[NAVIGATION] Erro ao obter estado: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/last")
async def get_last_screenplay(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id")
):
    """
    Proxy GET para conductor-api/navigation/last

    Retorna o último roteiro acessado pelo usuário.
    """
    try:
        headers = {}
        if x_user_id:
            headers["X-User-Id"] = x_user_id
        if x_session_id:
            headers["X-Session-Id"] = x_session_id

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{CONDUCTOR_API_URL}/navigation/last",
                headers=headers,
                timeout=10.0
            )
            return response.json()

    except Exception as e:
        logger.error(f"[NAVIGATION] Erro ao obter último roteiro: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("")
async def save_navigation_state(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id")
):
    """
    Proxy PUT para conductor-api/navigation

    Salva estado de navegação para um roteiro específico.
    Body deve conter: screenplay_id (obrigatório), conversation_id, instance_id
    """
    try:
        body = await request.json()

        headers = {"Content-Type": "application/json"}
        if x_user_id:
            headers["X-User-Id"] = x_user_id
        if x_session_id:
            headers["X-Session-Id"] = x_session_id

        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{CONDUCTOR_API_URL}/navigation",
                json=body,
                headers=headers,
                timeout=10.0
            )
            return response.json()

    except Exception as e:
        logger.error(f"[NAVIGATION] Erro ao salvar estado: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("")
async def clear_navigation_state(
    screenplay_id: Optional[str] = Query(None, description="ID do roteiro"),
    conversation_id: Optional[str] = Query(None, description="ID da conversa"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id")
):
    """
    Proxy DELETE para conductor-api/navigation

    - screenplay_id + conversation_id: limpa estado da conversa
    - screenplay_id: limpa estado do roteiro e todas suas conversas
    - Nenhum: limpa todos os estados do usuário
    """
    try:
        headers = {}
        if x_user_id:
            headers["X-User-Id"] = x_user_id
        if x_session_id:
            headers["X-Session-Id"] = x_session_id

        # Construir URL com query params
        url = f"{CONDUCTOR_API_URL}/navigation"
        params = {}
        if screenplay_id:
            params["screenplay_id"] = screenplay_id
        if conversation_id:
            params["conversation_id"] = conversation_id

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                url,
                headers=headers,
                params=params,
                timeout=10.0
            )
            return response.json()

    except Exception as e:
        logger.error(f"[NAVIGATION] Erro ao limpar estado: {e}")
        raise HTTPException(status_code=500, detail=str(e))
