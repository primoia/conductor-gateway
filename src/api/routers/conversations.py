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
    🔥 ATUALIZADO: Marca uma mensagem como deletada (soft delete) em AMBAS as collections:
    - conversations.messages (UI do chat)
    - tasks (histórico de execuções para PromptEngine)

    Args:
        conversation_id: ID da conversa
        message_id: ID da mensagem (UUID)

    Returns:
        Confirmação de sucesso com detalhes das atualizações
    """
    from datetime import datetime
    from src.config.settings import get_mongodb_client

    try:
        # Conectar ao MongoDB
        client = get_mongodb_client()
        db = client['conductor_state']
        conversations = db['conversations']
        tasks = db['tasks']

        # 1. Buscar a mensagem para obter seu conteúdo e timestamp
        conversation = conversations.find_one(
            {"conversation_id": conversation_id},
            {"messages": {"$elemMatch": {"id": message_id}}}
        )

        message_content = None
        message_timestamp = None
        if conversation and "messages" in conversation and len(conversation["messages"]) > 0:
            msg = conversation["messages"][0]
            message_content = msg.get("content", "")
            message_timestamp = msg.get("timestamp")

        # 2. Atualizar a mensagem na collection conversations
        result_conversations = conversations.update_one(
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

        if result_conversations.matched_count == 0:
            raise HTTPException(status_code=404, detail="Mensagem ou conversa não encontrada")

        logger.info(f"✅ Mensagem {message_id} marcada como deletada na conversa {conversation_id}")

        # 3. 🔥 NOVO: Também marcar tasks correspondentes como deletadas
        # Buscar tasks pelo conversation_id que contenham o conteúdo da mensagem no prompt
        tasks_updated = 0
        if message_content:
            # Buscar tasks que:
            # - Pertencem à mesma conversa
            # - Contêm o conteúdo da mensagem no prompt (user_input está embedado no prompt XML)
            # - Ainda não estão deletadas
            task_query = {
                "conversation_id": conversation_id,
                "isDeleted": {"$ne": True}
            }

            # Se temos o conteúdo da mensagem, buscar tasks que contenham esse conteúdo
            # O prompt XML contém o user_input dentro de <user_request>
            if len(message_content) > 20:
                # Usar substring para matching (primeiros 100 chars para evitar regex muito longo)
                search_content = message_content[:100].replace("\\", "\\\\").replace(".", "\\.").replace("*", "\\*")
                task_query["prompt"] = {"$regex": search_content, "$options": "i"}

            # Atualizar todas as tasks correspondentes
            result_tasks = tasks.update_many(
                task_query,
                {
                    "$set": {
                        "isDeleted": True,
                        "deleted_at": datetime.utcnow().isoformat(),
                        "deleted_message_id": message_id
                    }
                }
            )
            tasks_updated = result_tasks.modified_count

            if tasks_updated > 0:
                logger.info(f"✅ {tasks_updated} task(s) marcada(s) como deletada(s) para conversa {conversation_id}")
            else:
                logger.debug(f"ℹ️ Nenhuma task encontrada para marcar como deletada na conversa {conversation_id}")

        return {
            "success": True,
            "message": "Mensagem marcada como deletada",
            "details": {
                "conversations_updated": result_conversations.modified_count,
                "tasks_updated": tasks_updated
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao deletar mensagem: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao deletar mensagem: {str(e)}")


@router.put("/{conversation_id}/messages/{message_id}/toggle")
async def toggle_message(
    conversation_id: str = Path(..., description="ID da conversa"),
    message_id: str = Path(..., description="ID da mensagem")
):
    """
    Toggle message enabled/disabled state (soft delete).
    When disabled (isDeleted=true), message won't be included in PromptEngine.

    Args:
        conversation_id: ID da conversa
        message_id: ID da mensagem (UUID)

    Returns:
        Confirmação de sucesso com novo estado
    """
    from datetime import datetime
    from src.config.settings import get_mongodb_client

    try:
        # Conectar ao MongoDB
        client = get_mongodb_client()
        db = client['conductor_state']
        conversations = db['conversations']

        # 1. Buscar a mensagem atual para obter seu estado
        conversation = conversations.find_one(
            {"conversation_id": conversation_id},
            {"messages": {"$elemMatch": {"id": message_id}}}
        )

        if not conversation or "messages" not in conversation or len(conversation["messages"]) == 0:
            raise HTTPException(status_code=404, detail="Mensagem ou conversa não encontrada")

        msg = conversation["messages"][0]
        current_state = msg.get("isDeleted", False)
        new_state = not current_state

        # 2. Atualizar a mensagem na collection conversations
        result = conversations.update_one(
            {
                "conversation_id": conversation_id,
                "messages.id": message_id
            },
            {
                "$set": {
                    "messages.$.isDeleted": new_state,
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Mensagem ou conversa não encontrada")

        state_label = "disabled" if new_state else "enabled"
        logger.info(f"✅ Mensagem {message_id} toggled to {state_label} na conversa {conversation_id}")

        return {
            "success": True,
            "message": f"Mensagem {state_label}",
            "isDeleted": new_state
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao toggle mensagem: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao toggle mensagem: {str(e)}")


@router.put("/{conversation_id}/messages/{message_id}/hide")
async def hide_message(
    conversation_id: str = Path(..., description="ID da conversa"),
    message_id: str = Path(..., description="ID da mensagem")
):
    """
    Hide message permanently (isHidden=true).
    Message won't appear in chat or be included in PromptEngine.
    Only reversible via MongoDB directly.

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

        # Atualizar a mensagem para marcar como oculta permanentemente
        result = conversations.update_one(
            {
                "conversation_id": conversation_id,
                "messages.id": message_id
            },
            {
                "$set": {
                    "messages.$.isHidden": True,
                    "messages.$.hiddenAt": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Mensagem ou conversa não encontrada")

        logger.info(f"✅ Mensagem {message_id} ocultada permanentemente na conversa {conversation_id}")

        return {
            "success": True,
            "message": "Mensagem ocultada permanentemente",
            "isHidden": True
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao ocultar mensagem: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao ocultar mensagem: {str(e)}")


@router.post("/{conversation_id}/clone")
async def clone_conversation(
    conversation_id: str = Path(..., description="ID da conversa a ser clonada")
):
    """
    Clone a conversation with all messages and create new agent instances.

    Creates:
    - New conversation with copied messages (new IDs)
    - New agent_instances for each participant (new instance_ids)
    - Updates message references to new instance_ids

    Keeps:
    - Same screenplay_id
    - Same agent_ids (just new instances)

    Args:
        conversation_id: ID da conversa original

    Returns:
        Nova conversa clonada com novos IDs
    """
    from datetime import datetime
    from src.config.settings import get_mongodb_client
    import uuid

    try:
        client = get_mongodb_client()
        db = client['conductor_state']
        conversations = db['conversations']
        agent_instances = db['agent_instances']

        # 1. Buscar conversa original
        original = conversations.find_one({"conversation_id": conversation_id})
        if not original:
            raise HTTPException(status_code=404, detail="Conversa não encontrada")

        logger.info(f"🔄 Clonando conversa: {conversation_id}")

        # 2. Gerar novo conversation_id
        new_conversation_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        # 3. Buscar TODOS os agent_instances da conversa original (pela collection, não pelos participants)
        instance_id_map = {}  # old_instance_id -> new_instance_id
        new_participants = []

        # Buscar agentes pelo conversation_id na collection agent_instances
        original_instances = list(agent_instances.find({
            "conversation_id": conversation_id,
            "isDeleted": {"$ne": True}
        }))

        logger.info(f"   🔍 Encontradas {len(original_instances)} instâncias de agentes para clonar")

        # 4. Clonar cada agent_instance
        for original_instance in original_instances:
            old_instance_id = original_instance.get("instance_id")
            new_instance_id = str(uuid.uuid4())

            instance_id_map[old_instance_id] = new_instance_id

            # Criar novo documento de instância
            new_instance_doc = {
                "instance_id": new_instance_id,
                "agent_id": original_instance.get("agent_id"),
                "screenplay_id": original_instance.get("screenplay_id"),  # Mesmo screenplay
                "conversation_id": new_conversation_id,  # Nova conversa
                "position": original_instance.get("position", {}),
                "status": "pending",
                "cwd": original_instance.get("cwd"),
                "config": original_instance.get("config"),
                "emoji": original_instance.get("emoji"),
                "definition": original_instance.get("definition"),
                "display_order": original_instance.get("display_order", 0),
                "created_at": now,
                "updated_at": now,
                "last_execution": None,
                "statistics": {
                    "task_count": 0,
                    "total_execution_time": 0.0,
                    "average_execution_time": 0.0,
                    "last_task_duration": 0.0,
                    "last_task_completed_at": None,
                    "success_count": 0,
                    "error_count": 0,
                    "last_exit_code": None,
                    "total_executions": 0,
                    "success_rate": 0.0,
                    "last_execution": None
                }
            }
            agent_instances.insert_one(new_instance_doc)
            logger.info(f"   ✅ Nova instância criada: {new_instance_id} (clone de {old_instance_id})")

            # Buscar nome do participant original da conversa (mais confiável)
            original_participant = next(
                (p for p in original.get("participants", []) if p.get("instance_id") == old_instance_id),
                None
            )

            # Criar participant para a nova conversa
            participant_name = (
                (original_participant.get("name") if original_participant else None) or
                original_instance.get("definition", {}).get("name") or
                original_instance.get("agent_id") or
                "Agent"
            )
            new_participant = {
                "instance_id": new_instance_id,
                "agent_id": original_instance.get("agent_id"),
                "name": participant_name,
                "emoji": original_instance.get("emoji") or (original_participant.get("emoji") if original_participant else "🤖") or "🤖"
            }
            new_participants.append(new_participant)
            logger.info(f"   👤 Participant criado: {participant_name} ({new_participant['emoji']})")

        # Se não encontrou agentes na collection, copiar dos participants originais
        if not original_instances and original.get("participants"):
            logger.info(f"   ⚠️ Nenhuma instância na collection, copiando dos participants")
            for participant in original.get("participants", []):
                old_instance_id = participant.get("instance_id")
                new_instance_id = str(uuid.uuid4())

                if old_instance_id:
                    instance_id_map[old_instance_id] = new_instance_id

                new_participant = {
                    **participant,
                    "instance_id": new_instance_id
                }
                new_participants.append(new_participant)

        # 5. Copiar mensagens com novos IDs e atualizando referências
        # IMPORTANTE: Fazer deep copy para não afetar o original
        import copy
        new_messages = []
        original_messages = original.get("messages", [])
        logger.info(f"   📝 Copiando {len(original_messages)} mensagens")

        for msg in original_messages:
            # Deep copy para evitar side effects
            new_msg = copy.deepcopy(msg)
            new_msg["id"] = str(uuid.uuid4())

            # Atualizar instance_id do agente na mensagem (se houver)
            if "agent" in new_msg and new_msg["agent"]:
                old_inst = new_msg["agent"].get("instance_id")
                if old_inst and old_inst in instance_id_map:
                    new_msg["agent"]["instance_id"] = instance_id_map[old_inst]

            new_messages.append(new_msg)

        logger.info(f"   ✅ {len(new_messages)} mensagens copiadas")

        # 6. Atualizar active_agent com novo instance_id
        new_active_agent = None
        if original.get("active_agent"):
            old_active_inst = original["active_agent"].get("instance_id")
            new_active_agent = {
                **original["active_agent"],
                "instance_id": instance_id_map.get(old_active_inst, old_active_inst)
            }

        # 7. Criar nova conversa
        # Formatar hora para o título
        from datetime import datetime as dt
        hora_clone = dt.now().strftime("%H:%M")
        new_conversation = {
            "conversation_id": new_conversation_id,
            "title": f"{original.get('title', 'Conversa')} (copy {hora_clone})",
            "created_at": now,
            "updated_at": now,
            "screenplay_id": original.get("screenplay_id"),  # Mesmo screenplay
            "context": original.get("context"),
            "participants": new_participants,
            "active_agent": new_active_agent,
            "messages": new_messages,
            "display_order": (original.get("display_order", 0) or 0) + 1
        }

        conversations.insert_one(new_conversation)
        logger.info(f"✅ Conversa clonada: {new_conversation_id}")
        logger.info(f"   - {len(new_participants)} participantes clonados")
        logger.info(f"   - {len(new_messages)} mensagens copiadas")

        # Remover _id do MongoDB antes de retornar
        new_conversation.pop("_id", None)

        return {
            "success": True,
            "message": "Conversa clonada com sucesso",
            "original_conversation_id": conversation_id,
            "cloned_conversation": new_conversation,
            "instance_id_map": instance_id_map
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao clonar conversa: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao clonar conversa: {str(e)}")


@router.patch("/{conversation_id}/settings")
async def update_conversation_settings(
    conversation_id: str = Path(...),
    request: Request = None,
):
    """Proxy: Update conversation chain settings (max_chain_depth, auto_delegate)."""
    return await proxy_request("PATCH", f"/conversations/{conversation_id}/settings", request)


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
