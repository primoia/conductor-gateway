"""
Router de Persona
SAGA-008 - Fase 1: Core APIs
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Path
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...models.persona import PersonaCreate, PersonaUpdate, PersonaResponse, PersonaListResponse
from ...services.persona_service import PersonaService
from ...core.database import get_database

router = APIRouter(prefix="/api/agents", tags=["persona"])


def get_persona_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> PersonaService:
    """Dependency para obter o serviço de persona"""
    return PersonaService(db)


@router.post("/{agent_id}/persona", response_model=PersonaResponse, status_code=201)
async def create_persona(
    agent_id: str = Path(..., description="ID do agente"),
    persona_data: PersonaCreate = ...,
    service: PersonaService = Depends(get_persona_service)
):
    """
    Cria uma nova persona para um agente
    
    - **agent_id**: ID do agente proprietário
    - **persona_data**: Dados da persona (conteúdo em Markdown)
    
    Retorna a persona criada com ID e metadados.
    """
    try:
        persona = await service.create_persona(agent_id, persona_data)
        return persona
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/{agent_id}/persona", response_model=PersonaResponse)
async def get_persona(
    agent_id: str = Path(..., description="ID do agente"),
    service: PersonaService = Depends(get_persona_service)
):
    """
    Busca a persona de um agente
    
    - **agent_id**: ID do agente
    
    Retorna a persona se encontrada, 404 se não existir.
    """
    try:
        persona = await service.get_persona(agent_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona não encontrada")
        return persona
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.put("/{agent_id}/persona", response_model=PersonaResponse)
async def update_persona(
    agent_id: str = Path(..., description="ID do agente"),
    persona_data: PersonaUpdate = ...,
    service: PersonaService = Depends(get_persona_service)
):
    """
    Atualiza a persona de um agente
    
    - **agent_id**: ID do agente proprietário
    - **persona_data**: Dados atualizados da persona
    
    Retorna a persona atualizada. Apenas campos fornecidos serão atualizados.
    """
    try:
        persona = await service.update_persona(agent_id, persona_data)
        return persona
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.put("/{agent_id}/persona/permanent")
async def update_persona_permanent(
    agent_id: str = Path(..., description="ID do agente"),
    persona_data: PersonaUpdate = ...,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Atualiza a persona permanentemente na collection agents.

    - **agent_id**: ID do agente (agent_id, não instance_id)
    - **persona_data**: Dados atualizados da persona (content)

    Salva diretamente em agents.persona.content, afetando todas as instâncias.
    """
    try:
        from datetime import datetime

        if not persona_data.content:
            raise HTTPException(status_code=400, detail="Conteúdo da persona é obrigatório")

        agents_collection = db.agents

        # Verificar se o agente existe
        agent = await agents_collection.find_one({"agent_id": agent_id})
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' não encontrado")

        # Atualizar persona diretamente na collection agents
        result = await agents_collection.update_one(
            {"agent_id": agent_id},
            {
                "$set": {
                    "persona": {
                        "content": persona_data.content.strip(),
                        "updated_at": datetime.utcnow().isoformat(),
                        "reason": persona_data.metadata.get("reason", "Edição via interface") if persona_data.metadata else "Edição via interface"
                    }
                }
            }
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Falha ao atualizar persona")

        return {
            "success": True,
            "message": f"Persona do agente '{agent_id}' atualizada permanentemente",
            "agent_id": agent_id
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.delete("/{agent_id}/persona", status_code=204)
async def delete_persona(
    agent_id: str = Path(..., description="ID do agente"),
    service: PersonaService = Depends(get_persona_service)
):
    """
    Remove a persona de um agente
    
    - **agent_id**: ID do agente
    
    Retorna 204 se removida com sucesso, 404 se não encontrada.
    """
    try:
        deleted = await service.delete_persona(agent_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Persona não encontrada")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/personas", response_model=PersonaListResponse)
async def list_personas(
    page: int = Query(1, ge=1, description="Página atual"),
    per_page: int = Query(10, ge=1, le=100, description="Itens por página"),
    agent_id: Optional[str] = Query(None, description="Filtrar por agente"),
    service: PersonaService = Depends(get_persona_service)
):
    """
    Lista personas com paginação
    
    - **page**: Página atual (padrão: 1)
    - **per_page**: Itens por página (padrão: 10, máximo: 100)
    - **agent_id**: Filtrar por agente específico (opcional)
    
    Retorna lista paginada de personas com metadados de paginação.
    """
    try:
        personas = await service.list_personas(page, per_page, agent_id)
        return personas
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


# Endpoints adicionais para funcionalidades específicas

@router.get("/{agent_id}/persona/validate", response_model=dict)
async def validate_persona_content(
    agent_id: str = Path(..., description="ID do agente"),
    content: str = Query(..., description="Conteúdo da persona para validar"),
    service: PersonaService = Depends(get_persona_service)
):
    """
    Valida o conteúdo de uma persona sem salvá-la
    
    - **agent_id**: ID do agente
    - **content**: Conteúdo da persona para validar
    
    Retorna informações de validação e estatísticas do conteúdo.
    """
    try:
        # Validar agente
        if not await service.validator.validate_agent_exists(agent_id):
            raise HTTPException(status_code=404, detail="Agente não encontrado")
        
        # Validar conteúdo
        validation_result = await service.validator.validate_persona_content(content)
        
        return {
            "is_valid": True,
            "message": "Conteúdo válido",
            "validation": validation_result
        }
    except ValueError as e:
        return {
            "is_valid": False,
            "message": str(e),
            "validation": None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/{agent_id}/persona/stats", response_model=dict)
async def get_persona_stats(
    agent_id: str = Path(..., description="ID do agente"),
    service: PersonaService = Depends(get_persona_service)
):
    """
    Obtém estatísticas da persona de um agente
    
    - **agent_id**: ID do agente
    
    Retorna estatísticas detalhadas da persona.
    """
    try:
        persona = await service.get_persona(agent_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona não encontrada")
        
        # Calcular estatísticas
        stats = service.validator._calculate_content_stats(persona.content)
        
        return {
            "persona_id": persona.id,
            "agent_id": persona.agent_id,
            "version": persona.version,
            "created_at": persona.created_at,
            "updated_at": persona.updated_at,
            "content_stats": stats,
            "metadata": persona.metadata
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")