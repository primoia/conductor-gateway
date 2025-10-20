from fastapi import APIRouter, Depends, HTTPException, Query, Path
from typing import Optional
from datetime import datetime

from ...models.persona_version import (
    PersonaVersionCreate, PersonaVersionUpdate, PersonaVersionResponse,
    PersonaVersionListResponse, PersonaVersionCompareRequest,
    PersonaVersionCompareResponse, PersonaVersionRestoreRequest,
    PersonaVersionRestoreResponse, PersonaVersionStatsResponse
)
from ...services.persona_version_service import get_persona_version_service, PersonaVersionService

router = APIRouter(prefix="/api/agents", tags=["Persona Versioning"])


@router.post("/{agent_id}/persona/versions", response_model=PersonaVersionResponse)
async def create_persona_version(
    agent_id: str = Path(..., description="ID do agente"),
    version_data: PersonaVersionCreate = ...,
    service: PersonaVersionService = Depends(get_persona_version_service)
):
    """
    Cria uma nova versão de persona para um agente.
    
    - **agent_id**: ID do agente
    - **version_data**: Dados da versão a ser criada
    """
    try:
        # Definir agent_id do path
        version_data.agent_id = agent_id
        
        # Definir timestamp se não fornecido
        if not version_data.timestamp:
            version_data.timestamp = datetime.utcnow()
        
        version = await service.create_version(version_data)
        return version
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/{agent_id}/persona/versions/{version}", response_model=PersonaVersionResponse)
async def get_persona_version(
    agent_id: str = Path(..., description="ID do agente"),
    version: int = Path(..., description="Número da versão"),
    service: PersonaVersionService = Depends(get_persona_version_service)
):
    """
    Busca uma versão específica de persona.
    
    - **agent_id**: ID do agente
    - **version**: Número da versão
    """
    try:
        version_data = await service.get_version(agent_id, version)
        if not version_data:
            raise HTTPException(
                status_code=404, 
                detail=f"Versão {version} não encontrada para o agente {agent_id}"
            )
        return version_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/{agent_id}/persona/versions", response_model=PersonaVersionListResponse)
async def list_persona_versions(
    agent_id: str = Path(..., description="ID do agente"),
    page: int = Query(1, ge=1, description="Número da página"),
    per_page: int = Query(10, ge=1, le=100, description="Itens por página"),
    sort_by: str = Query("version", description="Campo para ordenação"),
    sort_order: str = Query("desc", description="Ordem da ordenação (asc/desc)"),
    service: PersonaVersionService = Depends(get_persona_version_service)
):
    """
    Lista versões de persona com paginação.
    
    - **agent_id**: ID do agente
    - **page**: Número da página (padrão: 1)
    - **per_page**: Itens por página (padrão: 10, máximo: 100)
    - **sort_by**: Campo para ordenação (version, timestamp)
    - **sort_order**: Ordem da ordenação (asc, desc)
    """
    try:
        if sort_by not in ["version", "timestamp"]:
            raise HTTPException(
                status_code=400, 
                detail="sort_by deve ser 'version' ou 'timestamp'"
            )
        
        if sort_order not in ["asc", "desc"]:
            raise HTTPException(
                status_code=400, 
                detail="sort_order deve ser 'asc' ou 'desc'"
            )
        
        versions = await service.list_versions(
            agent_id=agent_id,
            page=page,
            per_page=per_page,
            sort_by=sort_by,
            sort_order=sort_order
        )
        return versions
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.put("/{agent_id}/persona/versions/{version}", response_model=PersonaVersionResponse)
async def update_persona_version(
    agent_id: str = Path(..., description="ID do agente"),
    version: int = Path(..., description="Número da versão"),
    update_data: PersonaVersionUpdate = ...,
    service: PersonaVersionService = Depends(get_persona_version_service)
):
    """
    Atualiza uma versão de persona.
    
    - **agent_id**: ID do agente
    - **version**: Número da versão
    - **update_data**: Dados para atualização
    """
    try:
        updated_version = await service.update_version(agent_id, version, update_data)
        if not updated_version:
            raise HTTPException(
                status_code=404, 
                detail=f"Versão {version} não encontrada para o agente {agent_id}"
            )
        return updated_version
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.delete("/{agent_id}/persona/versions/{version}")
async def delete_persona_version(
    agent_id: str = Path(..., description="ID do agente"),
    version: int = Path(..., description="Número da versão"),
    service: PersonaVersionService = Depends(get_persona_version_service)
):
    """
    Remove uma versão de persona.
    
    - **agent_id**: ID do agente
    - **version**: Número da versão
    """
    try:
        success = await service.delete_version(agent_id, version)
        if not success:
            raise HTTPException(
                status_code=404, 
                detail=f"Versão {version} não encontrada para o agente {agent_id}"
            )
        return {"message": f"Versão {version} removida com sucesso"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.post("/{agent_id}/persona/versions/compare", response_model=PersonaVersionCompareResponse)
async def compare_persona_versions(
    agent_id: str = Path(..., description="ID do agente"),
    compare_request: PersonaVersionCompareRequest = ...,
    service: PersonaVersionService = Depends(get_persona_version_service)
):
    """
    Compara duas versões de persona.
    
    - **agent_id**: ID do agente
    - **compare_request**: Dados da comparação (version1, version2)
    """
    try:
        comparison = await service.compare_versions(
            agent_id=agent_id,
            version1=compare_request.version1,
            version2=compare_request.version2
        )
        return comparison
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.post("/{agent_id}/persona/versions/restore", response_model=PersonaVersionRestoreResponse)
async def restore_persona_version(
    agent_id: str = Path(..., description="ID do agente"),
    restore_request: PersonaVersionRestoreRequest = ...,
    service: PersonaVersionService = Depends(get_persona_version_service)
):
    """
    Restaura uma versão de persona.
    
    - **agent_id**: ID do agente
    - **restore_request**: Dados da restauração (version, create_backup)
    """
    try:
        result = await service.restore_version(
            agent_id=agent_id,
            version=restore_request.version,
            create_backup=restore_request.create_backup
        )
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/{agent_id}/persona/versions/stats", response_model=PersonaVersionStatsResponse)
async def get_persona_version_stats(
    agent_id: str = Path(..., description="ID do agente"),
    service: PersonaVersionService = Depends(get_persona_version_service)
):
    """
    Obtém estatísticas de versionamento para um agente.
    
    - **agent_id**: ID do agente
    """
    try:
        stats = await service.get_stats(agent_id)
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.post("/{agent_id}/persona/versions/cleanup")
async def cleanup_old_versions(
    agent_id: str = Path(..., description="ID do agente"),
    keep_versions: int = Query(50, ge=1, le=1000, description="Número de versões para manter"),
    service: PersonaVersionService = Depends(get_persona_version_service)
):
    """
    Remove versões antigas, mantendo apenas as mais recentes.
    
    - **agent_id**: ID do agente
    - **keep_versions**: Número de versões para manter (padrão: 50)
    """
    try:
        deleted_count = await service.cleanup_old_versions(agent_id, keep_versions)
        return {
            "message": f"Limpeza concluída. {deleted_count} versões removidas.",
            "deleted_count": deleted_count,
            "keep_versions": keep_versions
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/{agent_id}/persona/versions/latest", response_model=PersonaVersionResponse)
async def get_latest_persona_version(
    agent_id: str = Path(..., description="ID do agente"),
    service: PersonaVersionService = Depends(get_persona_version_service)
):
    """
    Busca a versão mais recente de persona.
    
    - **agent_id**: ID do agente
    """
    try:
        # Buscar versões ordenadas por versão (descendente)
        versions = await service.list_versions(
            agent_id=agent_id,
            page=1,
            per_page=1,
            sort_by="version",
            sort_order="desc"
        )
        
        if not versions.versions:
            raise HTTPException(
                status_code=404, 
                detail=f"Nenhuma versão encontrada para o agente {agent_id}"
            )
        
        return versions.versions[0]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/{agent_id}/persona/versions/first", response_model=PersonaVersionResponse)
async def get_first_persona_version(
    agent_id: str = Path(..., description="ID do agente"),
    service: PersonaVersionService = Depends(get_persona_version_service)
):
    """
    Busca a primeira versão de persona.
    
    - **agent_id**: ID do agente
    """
    try:
        # Buscar versões ordenadas por versão (ascendente)
        versions = await service.list_versions(
            agent_id=agent_id,
            page=1,
            per_page=1,
            sort_by="version",
            sort_order="asc"
        )
        
        if not versions.versions:
            raise HTTPException(
                status_code=404, 
                detail=f"Nenhuma versão encontrada para o agente {agent_id}"
            )
        
        return versions.versions[0]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/{agent_id}/persona/versions/range")
async def get_persona_versions_range(
    agent_id: str = Path(..., description="ID do agente"),
    from_version: int = Query(..., ge=1, description="Versão inicial"),
    to_version: int = Query(..., ge=1, description="Versão final"),
    service: PersonaVersionService = Depends(get_persona_version_service)
):
    """
    Busca versões em um intervalo específico.
    
    - **agent_id**: ID do agente
    - **from_version**: Versão inicial do intervalo
    - **to_version**: Versão final do intervalo
    """
    try:
        if from_version > to_version:
            raise HTTPException(
                status_code=400, 
                detail="from_version deve ser menor ou igual a to_version"
            )
        
        # Buscar versões no intervalo
        versions = []
        for version in range(from_version, to_version + 1):
            version_data = await service.get_version(agent_id, version)
            if version_data:
                versions.append(version_data)
        
        return {
            "agent_id": agent_id,
            "from_version": from_version,
            "to_version": to_version,
            "versions": versions,
            "count": len(versions)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")