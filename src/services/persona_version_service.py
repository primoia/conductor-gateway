from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from bson import ObjectId
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, OperationFailure
import difflib
import json

from ..models.persona_version import (
    PersonaVersionCreate, PersonaVersionUpdate, PersonaVersionResponse,
    PersonaVersionListResponse, PersonaVersionCompareResponse,
    PersonaVersionRestoreResponse, PersonaVersionStatsResponse
)
from ..core.database import get_database


class PersonaVersionService:
    """Serviço para gerenciamento de versões de persona"""
    
    def __init__(self, db: Database):
        self.db = db
        self.collection: Collection = db.persona_versions
        self.agents_collection: Collection = db.agents
        self.personas_collection: Collection = db.personas
        
        # Criar índices para performance
        self._create_indexes()
    
    def _create_indexes(self):
        """Cria índices para otimizar consultas"""
        try:
            # Índice composto para consultas por agente e versão
            self.collection.create_index([
                ("agent_id", 1),
                ("version", -1)
            ], unique=True)
            
            # Índice para consultas por timestamp
            self.collection.create_index([("timestamp", -1)])
            
            # Índice para consultas por agente
            self.collection.create_index([("agent_id", 1)])
            
        except Exception as e:
            print(f"Erro ao criar índices: {e}")
    
    async def create_version(self, version_data: PersonaVersionCreate) -> PersonaVersionResponse:
        """Cria uma nova versão de persona"""
        try:
            # Verificar se o agente existe
            agent = await self.agents_collection.find_one({"_id": ObjectId(version_data.agent_id)})
            if not agent:
                raise ValueError(f"Agente {version_data.agent_id} não encontrado")
            
            # Buscar persona atual do agente
            persona = await self.personas_collection.find_one({"agent_id": version_data.agent_id})
            if not persona:
                raise ValueError(f"Persona não encontrada para o agente {version_data.agent_id}")
            
            # Verificar se a versão já existe
            existing_version = await self.collection.find_one({
                "agent_id": version_data.agent_id,
                "version": version_data.version
            })
            if existing_version:
                raise ValueError(f"Versão {version_data.version} já existe para o agente {version_data.agent_id}")
            
            # Criar documento da versão
            version_doc = {
                "agent_id": version_data.agent_id,
                "version": version_data.version,
                "timestamp": version_data.timestamp,
                "data": version_data.data,
                "metadata": version_data.metadata or {},
                "created_by": version_data.created_by,
                "change_description": version_data.change_description,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            # Inserir versão
            result = await self.collection.insert_one(version_doc)
            
            # Retornar versão criada
            created_version = await self.collection.find_one({"_id": result.inserted_id})
            return self._to_response(created_version)
            
        except Exception as e:
            raise Exception(f"Erro ao criar versão: {str(e)}")
    
    async def get_version(self, agent_id: str, version: int) -> Optional[PersonaVersionResponse]:
        """Busca uma versão específica de persona"""
        try:
            version_doc = await self.collection.find_one({
                "agent_id": agent_id,
                "version": version
            })
            
            if not version_doc:
                return None
            
            return self._to_response(version_doc)
            
        except Exception as e:
            raise Exception(f"Erro ao buscar versão: {str(e)}")
    
    async def list_versions(
        self, 
        agent_id: str, 
        page: int = 1, 
        per_page: int = 10,
        sort_by: str = "version",
        sort_order: str = "desc"
    ) -> PersonaVersionListResponse:
        """Lista versões de persona com paginação"""
        try:
            # Calcular skip
            skip = (page - 1) * per_page
            
            # Definir ordenação
            sort_direction = -1 if sort_order == "desc" else 1
            sort_field = sort_by if sort_by in ["version", "timestamp"] else "version"
            
            # Buscar versões
            cursor = self.collection.find(
                {"agent_id": agent_id}
            ).sort(sort_field, sort_direction).skip(skip).limit(per_page)
            
            versions = []
            async for doc in cursor:
                versions.append(self._to_response(doc))
            
            # Contar total
            total = await self.collection.count_documents({"agent_id": agent_id})
            total_pages = (total + per_page - 1) // per_page
            
            return PersonaVersionListResponse(
                versions=versions,
                total=total,
                page=page,
                per_page=per_page,
                total_pages=total_pages
            )
            
        except Exception as e:
            raise Exception(f"Erro ao listar versões: {str(e)}")
    
    async def update_version(
        self, 
        agent_id: str, 
        version: int, 
        update_data: PersonaVersionUpdate
    ) -> Optional[PersonaVersionResponse]:
        """Atualiza uma versão de persona"""
        try:
            # Verificar se a versão existe
            existing_version = await self.collection.find_one({
                "agent_id": agent_id,
                "version": version
            })
            if not existing_version:
                return None
            
            # Preparar dados de atualização
            update_doc = {
                "updated_at": datetime.utcnow()
            }
            
            if update_data.metadata is not None:
                update_doc["metadata"] = update_data.metadata
            
            if update_data.change_description is not None:
                update_doc["change_description"] = update_data.change_description
            
            # Atualizar versão
            await self.collection.update_one(
                {"agent_id": agent_id, "version": version},
                {"$set": update_doc}
            )
            
            # Retornar versão atualizada
            updated_version = await self.collection.find_one({
                "agent_id": agent_id,
                "version": version
            })
            
            return self._to_response(updated_version)
            
        except Exception as e:
            raise Exception(f"Erro ao atualizar versão: {str(e)}")
    
    async def delete_version(self, agent_id: str, version: int) -> bool:
        """Remove uma versão de persona"""
        try:
            result = await self.collection.delete_one({
                "agent_id": agent_id,
                "version": version
            })
            
            return result.deleted_count > 0
            
        except Exception as e:
            raise Exception(f"Erro ao remover versão: {str(e)}")
    
    async def compare_versions(
        self, 
        agent_id: str, 
        version1: int, 
        version2: int
    ) -> PersonaVersionCompareResponse:
        """Compara duas versões de persona"""
        try:
            # Buscar versões
            v1_doc = await self.collection.find_one({
                "agent_id": agent_id,
                "version": version1
            })
            v2_doc = await self.collection.find_one({
                "agent_id": agent_id,
                "version": version2
            })
            
            if not v1_doc:
                raise ValueError(f"Versão {version1} não encontrada")
            if not v2_doc:
                raise ValueError(f"Versão {version2} não encontrada")
            
            v1_response = self._to_response(v1_doc)
            v2_response = self._to_response(v2_doc)
            
            # Comparar conteúdo
            content1 = v1_doc["data"].get("content", "")
            content2 = v2_doc["data"].get("content", "")
            
            # Gerar diff
            differences = self._generate_diff(content1, content2)
            
            # Calcular estatísticas
            summary = self._calculate_comparison_summary(content1, content2, differences)
            
            return PersonaVersionCompareResponse(
                version1=v1_response,
                version2=v2_response,
                differences=differences,
                summary=summary
            )
            
        except Exception as e:
            raise Exception(f"Erro ao comparar versões: {str(e)}")
    
    async def restore_version(
        self, 
        agent_id: str, 
        version: int, 
        create_backup: bool = True
    ) -> PersonaVersionRestoreResponse:
        """Restaura uma versão de persona"""
        try:
            # Buscar versão para restaurar
            version_doc = await self.collection.find_one({
                "agent_id": agent_id,
                "version": version
            })
            if not version_doc:
                raise ValueError(f"Versão {version} não encontrada")
            
            # Buscar persona atual
            current_persona = await self.personas_collection.find_one({
                "agent_id": agent_id
            })
            
            backup_created = None
            
            # Criar backup da versão atual se solicitado
            if create_backup and current_persona:
                backup_data = PersonaVersionCreate(
                    agent_id=agent_id,
                    version=await self._get_next_version_number(agent_id),
                    timestamp=datetime.utcnow(),
                    data=current_persona.get("data", {}),
                    metadata={"restore_backup": True},
                    change_description="Backup criado antes da restauração"
                )
                backup_created = await self.create_version(backup_data)
            
            # Restaurar versão
            restored_data = version_doc["data"]
            await self.personas_collection.update_one(
                {"agent_id": agent_id},
                {
                    "$set": {
                        "data": restored_data,
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            return PersonaVersionRestoreResponse(
                success=True,
                message=f"Versão {version} restaurada com sucesso",
                restored_version=self._to_response(version_doc),
                backup_created=backup_created
            )
            
        except Exception as e:
            raise Exception(f"Erro ao restaurar versão: {str(e)}")
    
    async def get_stats(self, agent_id: str) -> PersonaVersionStatsResponse:
        """Obtém estatísticas de versionamento para um agente"""
        try:
            # Buscar todas as versões do agente
            cursor = self.collection.find({"agent_id": agent_id}).sort("timestamp", 1)
            versions = []
            async for doc in cursor:
                versions.append(doc)
            
            if not versions:
                return PersonaVersionStatsResponse(
                    agent_id=agent_id,
                    total_versions=0,
                    latest_version=0,
                    first_version_date=datetime.utcnow(),
                    last_version_date=datetime.utcnow(),
                    average_versions_per_day=0.0,
                    storage_size_bytes=0
                )
            
            # Calcular estatísticas
            total_versions = len(versions)
            latest_version = max(v["version"] for v in versions)
            first_version_date = min(v["timestamp"] for v in versions)
            last_version_date = max(v["timestamp"] for v in versions)
            
            # Calcular média de versões por dia
            days_diff = (last_version_date - first_version_date).days
            average_versions_per_day = total_versions / max(days_diff, 1)
            
            # Calcular tamanho total
            storage_size_bytes = sum(
                len(json.dumps(v["data"]).encode('utf-8')) 
                for v in versions
            )
            
            return PersonaVersionStatsResponse(
                agent_id=agent_id,
                total_versions=total_versions,
                latest_version=latest_version,
                first_version_date=first_version_date,
                last_version_date=last_version_date,
                average_versions_per_day=average_versions_per_day,
                storage_size_bytes=storage_size_bytes
            )
            
        except Exception as e:
            raise Exception(f"Erro ao obter estatísticas: {str(e)}")
    
    async def cleanup_old_versions(self, agent_id: str, keep_versions: int = 50) -> int:
        """Remove versões antigas, mantendo apenas as mais recentes"""
        try:
            # Buscar versões ordenadas por timestamp (mais recentes primeiro)
            cursor = self.collection.find(
                {"agent_id": agent_id}
            ).sort("timestamp", -1).skip(keep_versions)
            
            versions_to_delete = []
            async for doc in cursor:
                versions_to_delete.append(doc["_id"])
            
            if versions_to_delete:
                result = await self.collection.delete_many({
                    "_id": {"$in": versions_to_delete}
                })
                return result.deleted_count
            
            return 0
            
        except Exception as e:
            raise Exception(f"Erro ao limpar versões antigas: {str(e)}")
    
    async def _get_next_version_number(self, agent_id: str) -> int:
        """Obtém o próximo número de versão para um agente"""
        try:
            # Buscar a versão mais recente
            latest_version = await self.collection.find_one(
                {"agent_id": agent_id},
                sort=[("version", -1)]
            )
            
            if latest_version:
                return latest_version["version"] + 1
            else:
                return 1
                
        except Exception as e:
            raise Exception(f"Erro ao obter próximo número de versão: {str(e)}")
    
    def _generate_diff(self, content1: str, content2: str) -> List[Dict[str, Any]]:
        """Gera diff entre dois conteúdos"""
        try:
            lines1 = content1.splitlines()
            lines2 = content2.splitlines()
            
            diff = list(difflib.unified_diff(
                lines1, lines2,
                fromfile=f"versão_1",
                tofile=f"versão_2",
                lineterm=""
            ))
            
            differences = []
            for line in diff:
                if line.startswith('@@'):
                    # Cabeçalho do diff
                    differences.append({
                        "type": "header",
                        "content": line
                    })
                elif line.startswith('+'):
                    # Linha adicionada
                    differences.append({
                        "type": "added",
                        "content": line[1:]
                    })
                elif line.startswith('-'):
                    # Linha removida
                    differences.append({
                        "type": "removed",
                        "content": line[1:]
                    })
                elif line.startswith(' '):
                    # Linha inalterada
                    differences.append({
                        "type": "unchanged",
                        "content": line[1:]
                    })
            
            return differences
            
        except Exception as e:
            return [{"type": "error", "content": f"Erro ao gerar diff: {str(e)}"}]
    
    def _calculate_comparison_summary(
        self, 
        content1: str, 
        content2: str, 
        differences: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calcula resumo da comparação"""
        try:
            lines1 = content1.splitlines()
            lines2 = content2.splitlines()
            
            added_lines = len([d for d in differences if d["type"] == "added"])
            removed_lines = len([d for d in differences if d["type"] == "removed"])
            unchanged_lines = len([d for d in differences if d["type"] == "unchanged"])
            
            return {
                "total_lines_v1": len(lines1),
                "total_lines_v2": len(lines2),
                "added_lines": added_lines,
                "removed_lines": removed_lines,
                "unchanged_lines": unchanged_lines,
                "change_percentage": round(
                    (added_lines + removed_lines) / max(len(lines1), len(lines2)) * 100, 2
                ) if max(len(lines1), len(lines2)) > 0 else 0
            }
            
        except Exception as e:
            return {"error": f"Erro ao calcular resumo: {str(e)}"}
    
    def _to_response(self, doc: Dict[str, Any]) -> PersonaVersionResponse:
        """Converte documento do MongoDB para modelo de resposta"""
        return PersonaVersionResponse(
            id=str(doc["_id"]),
            agent_id=doc["agent_id"],
            version=doc["version"],
            timestamp=doc["timestamp"],
            data=doc["data"],
            metadata=doc.get("metadata", {}),
            created_by=doc.get("created_by"),
            change_description=doc.get("change_description")
        )


# Instância global do serviço
async def get_persona_version_service() -> PersonaVersionService:
    """Obtém instância do serviço de versionamento"""
    db = await get_database()
    return PersonaVersionService(db)