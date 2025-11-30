"""
🔥 NOVO: Router proxy para conversas globais.

Encaminha requisições de /api/conversations para o serviço conductor backend.

Ref: PLANO_REFATORACAO_CONVERSATION_ID.md - Fase 1
Data: 2025-11-01
"""

import logging
import httpx
from fastapi import APIRouter, HTTPException, Request, Response, Path, Query, UploadFile, File
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
async def list_conversations(
    request: Request,
    screenplay_id: str = Query(None, description="Filter by screenplay_id"),
    include_deleted: bool = Query(False, description="Include deleted conversations")
):
    """
    Lista conversas do MongoDB local, filtrando deletadas por padrão.
    """
    from src.config.settings import get_mongodb_client

    try:
        client = get_mongodb_client()
        db = client['conductor_state']
        conversations = db['conversations']

        # Build query filter
        query_filter = {}
        if screenplay_id:
            query_filter["screenplay_id"] = screenplay_id

        # Filter out deleted conversations by default
        if not include_deleted:
            query_filter["isDeleted"] = {"$ne": True}

        # Query MongoDB sorted by updated_at descending
        cursor = conversations.find(query_filter)
        cursor = cursor.sort("updated_at", -1)

        result = []
        for doc in cursor:
            # Convert ObjectId to string
            doc["_id"] = str(doc["_id"])
            result.append(doc)

        logger.info(f"Listed {len(result)} conversations (include_deleted={include_deleted})")

        return {
            "success": True,
            "count": len(result),
            "conversations": result
        }

    except Exception as e:
        logger.error(f"❌ Erro ao listar conversas: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao listar conversas: {str(e)}")


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str = Path(...),
    request: Request = None
):
    """
    Soft delete conversa e cascade para agent_instances.

    Marca a conversa como isDeleted=true e também marca todos os
    agent_instances dessa conversa como isDeleted=true.
    """
    from datetime import datetime
    from src.config.settings import get_mongodb_client

    try:
        # Conectar ao MongoDB
        client = get_mongodb_client()
        db = client['conductor_state']
        conversations = db['conversations']
        agent_instances = db['agent_instances']

        # Soft delete da conversa
        conv_result = conversations.update_one(
            {"conversation_id": conversation_id, "isDeleted": {"$ne": True}},
            {
                "$set": {
                    "isDeleted": True,
                    "deletedAt": datetime.utcnow(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
        )

        if conv_result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Conversa não encontrada ou já deletada")

        # Cascade: marcar agent_instances dessa conversa como deletados
        instances_result = agent_instances.update_many(
            {"conversation_id": conversation_id, "isDeleted": {"$ne": True}},
            {
                "$set": {
                    "isDeleted": True,
                    "deletedAt": datetime.utcnow(),
                    "deletedReason": "conversation_deleted"
                }
            }
        )

        logger.info(f"✅ Conversa {conversation_id} deletada (soft delete)")
        logger.info(f"   → {instances_result.modified_count} agent_instances marcados como deletados")

        return {
            "success": True,
            "message": "Conversa deletada com sucesso",
            "conversation_id": conversation_id,
            "instances_deleted": instances_result.modified_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao deletar conversa: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao deletar conversa: {str(e)}")


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str = Path(...),
    request: Request = None
):
    """Proxy: Obter mensagens da conversa."""
    return await proxy_request("GET", f"/conversations/{conversation_id}/messages", request)


@router.patch("/{conversation_id}/title")
async def update_conversation_title(
    conversation_id: str = Path(...),
    request: Request = None
):
    """Proxy: Atualizar título da conversa."""
    return await proxy_request("PATCH", f"/conversations/{conversation_id}/title", request)


@router.patch("/{conversation_id}/context")
async def update_conversation_context(
    conversation_id: str = Path(...),
    request: Request = None
):
    """Proxy: Atualizar contexto da conversa."""
    return await proxy_request("PATCH", f"/conversations/{conversation_id}/context", request)


@router.put("/{conversation_id}/messages/{message_id}/delete")
async def delete_message(
    conversation_id: str = Path(..., description="ID da conversa"),
    message_id: str = Path(..., description="ID da mensagem")
):
    """
    🔥 NOVO: Marca uma mensagem como deletada (soft delete).

    Args:
        conversation_id: ID da conversa
        message_id: ID da mensagem (UUID)

    Returns:
        Confirmação de sucesso
    """
    from datetime import datetime
    from src.config.settings import get_mongodb_client

    try:
        # Conectar ao MongoDB
        client = get_mongodb_client()
        db = client['conductor_state']
        conversations = db['conversations']

        # Atualizar a mensagem para marcar como deletada
        result = conversations.update_one(
            {
                "conversation_id": conversation_id,
                "messages.id": message_id
            },
            {
                "$set": {
                    "messages.$.isDeleted": True,
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Mensagem ou conversa não encontrada")

        logger.info(f"✅ Mensagem {message_id} marcada como deletada na conversa {conversation_id}")

        return {"success": True, "message": "Mensagem marcada como deletada"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao deletar mensagem: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao deletar mensagem: {str(e)}")


@router.patch("/reorder")
async def reorder_conversations(request: Request):
    """Proxy: Atualizar ordem de exibição das conversas."""
    return await proxy_request("PATCH", "/conversations/reorder", request)


@router.post("/{conversation_id}/context/upload")
async def upload_context_file(
    conversation_id: str = Path(..., description="ID da conversa"),
    file: UploadFile = File(..., description="Arquivo markdown (.md)")
):
    """
    Upload de arquivo markdown para definir o contexto da conversa.

    Args:
        conversation_id: ID da conversa
        file: Arquivo .md com o contexto

    Returns:
        Confirmação de sucesso e preview do contexto
    """
    try:
        # Validar extensão do arquivo
        if not file.filename.endswith('.md'):
            raise HTTPException(
                status_code=400,
                detail="Apenas arquivos .md são permitidos"
            )

        # Ler conteúdo do arquivo
        content = await file.read()
        markdown_content = content.decode('utf-8')

        # Validar tamanho (máximo 50KB para o contexto)
        MAX_CONTEXT_SIZE = 50 * 1024  # 50KB
        if len(markdown_content) > MAX_CONTEXT_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Arquivo muito grande. Máximo: {MAX_CONTEXT_SIZE / 1024}KB"
            )

        # Enviar para o conductor backend
        url = f"{CONDUCTOR_URL}/conversations/{conversation_id}/context"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(
                url,
                json={"context": markdown_content}
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Erro ao atualizar contexto: {response.text}"
                )

            return {
                "success": True,
                "message": "Contexto carregado com sucesso",
                "filename": file.filename,
                "size": len(markdown_content),
                "preview": markdown_content[:200] + ("..." if len(markdown_content) > 200 else "")
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao fazer upload de contexto: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao processar arquivo: {str(e)}")
