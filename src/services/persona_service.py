"""
Serviço de Persona
SAGA-008 - Fase 1: Core APIs
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pymongo.errors import PyMongoError, DuplicateKeyError
from motor.motor_asyncio import AsyncIOMotorDatabase

from .persona_validator import PersonaValidator
from ..models.persona import PersonaCreate, PersonaUpdate, PersonaResponse, PersonaListResponse


class PersonaService:
    """Serviço para operações de Persona"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.personas_collection = db.personas
        self.validator = PersonaValidator(db)
    
    async def create_persona(self, agent_id: str, persona_data: PersonaCreate) -> PersonaResponse:
        """
        Cria uma nova persona para um agente
        
        Args:
            agent_id: ID do agente
            persona_data: Dados da persona
            
        Returns:
            PersonaResponse: Persona criada
            
        Raises:
            ValueError: Se os dados são inválidos
            PyMongoError: Se há erro no banco de dados
        """
        # Validar agente
        if not await self.validator.validate_agent_exists(agent_id):
            raise ValueError("Agente não encontrado")
        
        # Validar conteúdo
        content_validation = await self.validator.validate_persona_content(persona_data.content)
        
        # Validar metadata
        validated_metadata = await self.validator.validate_persona_metadata(persona_data.metadata)
        
        # Verificar se já existe persona para o agente
        existing_persona = await self.personas_collection.find_one({
            "agent_id": agent_id
        })
        
        if existing_persona:
            raise ValueError("Agente já possui uma persona. Use PUT para atualizar.")
        
        # Preparar dados para inserção
        persona_doc = {
            "agent_id": agent_id,
            "content": persona_data.content.strip(),
            "metadata": validated_metadata,
            "version": 1,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        try:
            # Inserir persona
            result = await self.personas_collection.insert_one(persona_doc)
            
            # Buscar persona criada
            created_persona = await self.personas_collection.find_one({
                "_id": result.inserted_id
            })
            
            return self._doc_to_response(created_persona)
            
        except DuplicateKeyError:
            raise ValueError("Persona já existe para este agente")
        except PyMongoError as e:
            raise PyMongoError(f"Erro ao criar persona: {str(e)}")
    
    async def get_persona(self, agent_id: str) -> Optional[PersonaResponse]:
        """
        Busca a persona de um agente
        
        Args:
            agent_id: ID do agente
            
        Returns:
            PersonaResponse ou None se não encontrada
            
        Raises:
            ValueError: Se agent_id é inválido
            PyMongoError: Se há erro no banco de dados
        """
        # Validar agente
        if not await self.validator.validate_agent_exists(agent_id):
            raise ValueError("Agente não encontrado")
        
        try:
            # Buscar persona
            persona_doc = await self.personas_collection.find_one({
                "agent_id": agent_id
            })
            
            if not persona_doc:
                return None
            
            return self._doc_to_response(persona_doc)
            
        except PyMongoError as e:
            raise PyMongoError(f"Erro ao buscar persona: {str(e)}")
    
    async def update_persona(self, agent_id: str, persona_data: PersonaUpdate) -> PersonaResponse:
        """
        Atualiza a persona de um agente
        
        Args:
            agent_id: ID do agente
            persona_data: Dados atualizados da persona
            
        Returns:
            PersonaResponse: Persona atualizada
            
        Raises:
            ValueError: Se os dados são inválidos
            PyMongoError: Se há erro no banco de dados
        """
        # Validar agente
        if not await self.validator.validate_agent_exists(agent_id):
            raise ValueError("Agente não encontrado")
        
        # Buscar persona existente
        existing_persona = await self.personas_collection.find_one({
            "agent_id": agent_id
        })
        
        if not existing_persona:
            raise ValueError("Persona não encontrada para este agente")
        
        # Preparar dados de atualização
        update_data = {}
        
        if persona_data.content is not None:
            # Validar conteúdo
            content_validation = await self.validator.validate_persona_content(persona_data.content)
            update_data["content"] = persona_data.content.strip()
        
        if persona_data.metadata is not None:
            # Validar metadata
            validated_metadata = await self.validator.validate_persona_metadata(persona_data.metadata)
            update_data["metadata"] = validated_metadata
        
        if not update_data:
            raise ValueError("Nenhum dado para atualizar")
        
        # Incrementar versão
        update_data["version"] = existing_persona["version"] + 1
        update_data["updated_at"] = datetime.utcnow()
        
        try:
            # Atualizar persona
            result = await self.personas_collection.update_one(
                {"_id": existing_persona["_id"]},
                {"$set": update_data}
            )
            
            if result.modified_count == 0:
                raise ValueError("Falha ao atualizar persona")
            
            # Buscar persona atualizada
            updated_persona = await self.personas_collection.find_one({
                "_id": existing_persona["_id"]
            })
            
            return self._doc_to_response(updated_persona)
            
        except PyMongoError as e:
            raise PyMongoError(f"Erro ao atualizar persona: {str(e)}")
    
    async def delete_persona(self, agent_id: str) -> bool:
        """
        Remove a persona de um agente
        
        Args:
            agent_id: ID do agente
            
        Returns:
            bool: True se removida com sucesso
            
        Raises:
            ValueError: Se agent_id é inválido
            PyMongoError: Se há erro no banco de dados
        """
        # Validar agente
        if not await self.validator.validate_agent_exists(agent_id):
            raise ValueError("Agente não encontrado")
        
        try:
            # Remover persona
            result = await self.personas_collection.delete_one({
                "agent_id": agent_id
            })
            
            return result.deleted_count > 0
            
        except PyMongoError as e:
            raise PyMongoError(f"Erro ao remover persona: {str(e)}")
    
    async def list_personas(self, page: int = 1, per_page: int = 10, 
                          agent_id: Optional[str] = None) -> PersonaListResponse:
        """
        Lista personas com paginação
        
        Args:
            page: Página atual
            per_page: Itens por página
            agent_id: Filtrar por agente (opcional)
            
        Returns:
            PersonaListResponse: Lista paginada de personas
            
        Raises:
            ValueError: Se parâmetros são inválidos
            PyMongoError: Se há erro no banco de dados
        """
        # Validar parâmetros
        if page < 1:
            raise ValueError("Página deve ser maior que 0")
        
        if per_page < 1 or per_page > 100:
            raise ValueError("Itens por página deve estar entre 1 e 100")
        
        # Preparar filtro
        filter_query = {}
        if agent_id:
            filter_query["agent_id"] = agent_id
        
        try:
            # Calcular skip
            skip = (page - 1) * per_page
            
            # Buscar personas
            cursor = self.personas_collection.find(filter_query).sort(
                "updated_at", -1
            ).skip(skip).limit(per_page)
            
            personas_docs = await cursor.to_list(length=per_page)
            
            # Converter para response
            personas = [self._doc_to_response(doc) for doc in personas_docs]
            
            # Contar total
            total = await self.personas_collection.count_documents(filter_query)
            
            # Calcular paginação
            has_next = (skip + per_page) < total
            has_prev = page > 1
            
            return PersonaListResponse(
                personas=personas,
                total=total,
                page=page,
                per_page=per_page,
                has_next=has_next,
                has_prev=has_prev
            )
            
        except PyMongoError as e:
            raise PyMongoError(f"Erro ao listar personas: {str(e)}")
    
    def _doc_to_response(self, doc: Dict[str, Any]) -> PersonaResponse:
        """
        Converte documento do MongoDB para PersonaResponse
        
        Args:
            doc: Documento do MongoDB
            
        Returns:
            PersonaResponse: Persona convertida
        """
        return PersonaResponse(
            id=str(doc["_id"]),
            agent_id=doc["agent_id"],
            content=doc["content"],
            metadata=doc.get("metadata", {}),
            version=doc["version"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"]
        )