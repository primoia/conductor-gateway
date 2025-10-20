"""
Testes unitários para PersonaService
SAGA-008 - Fase 1: Core APIs
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from bson import ObjectId
from pymongo.errors import PyMongoError, DuplicateKeyError

from src.services.persona_service import PersonaService
from src.models.persona import PersonaCreate, PersonaUpdate, PersonaResponse, PersonaListResponse


@pytest.fixture
def mock_db():
    """Mock do banco de dados"""
    db = MagicMock()
    db.personas = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    """Instância do PersonaService"""
    return PersonaService(mock_db)


@pytest.fixture
def sample_persona_data():
    """Dados de exemplo para persona"""
    return PersonaCreate(
        content="# Teste\nEste é um teste de persona.",
        metadata={"author": "test", "version": "1.0"}
    )


@pytest.fixture
def sample_persona_doc():
    """Documento de exemplo do MongoDB"""
    return {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "agent_id": ObjectId("507f1f77bcf86cd799439012"),
        "content": "# Teste\nEste é um teste de persona.",
        "metadata": {"author": "test", "version": "1.0"},
        "version": 1,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }


class TestCreatePersona:
    """Testes para create_persona"""
    
    @pytest.mark.asyncio
    async def test_create_persona_success(self, service, sample_persona_data, sample_persona_doc):
        """Testa criação bem-sucedida de persona"""
        agent_id = "507f1f77bcf86cd799439012"
        
        # Mock do validator
        with patch.object(service.validator, 'validate_agent_exists', return_value=True):
            with patch.object(service.validator, 'validate_persona_content', return_value={"is_valid": True}):
                with patch.object(service.validator, 'validate_persona_metadata', return_value=sample_persona_data.metadata):
                    # Mock do banco de dados
                    service.db.personas.find_one = AsyncMock(return_value=None)  # Nenhuma persona existente
                    service.db.personas.insert_one = AsyncMock(return_value=MagicMock(inserted_id=sample_persona_doc["_id"]))
                    service.db.personas.find_one = AsyncMock(return_value=sample_persona_doc)
                    
                    result = await service.create_persona(agent_id, sample_persona_data)
                    
                    assert isinstance(result, PersonaResponse)
                    assert result.id == str(sample_persona_doc["_id"])
                    assert result.agent_id == str(sample_persona_doc["agent_id"])
                    assert result.content == sample_persona_doc["content"]
                    assert result.metadata == sample_persona_doc["metadata"]
                    assert result.version == sample_persona_doc["version"]
    
    @pytest.mark.asyncio
    async def test_create_persona_agent_not_found(self, service, sample_persona_data):
        """Testa criação de persona com agente não encontrado"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=False):
            with pytest.raises(ValueError, match="Agente não encontrado"):
                await service.create_persona(agent_id, sample_persona_data)
    
    @pytest.mark.asyncio
    async def test_create_persona_already_exists(self, service, sample_persona_data, sample_persona_doc):
        """Testa criação de persona quando já existe uma para o agente"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=True):
            with patch.object(service.validator, 'validate_persona_content', return_value={"is_valid": True}):
                with patch.object(service.validator, 'validate_persona_metadata', return_value=sample_persona_data.metadata):
                    # Mock do banco de dados - persona já existe
                    service.db.personas.find_one = AsyncMock(return_value=sample_persona_doc)
                    
                    with pytest.raises(ValueError, match="Agente já possui uma persona. Use PUT para atualizar."):
                        await service.create_persona(agent_id, sample_persona_data)
    
    @pytest.mark.asyncio
    async def test_create_persona_database_error(self, service, sample_persona_data):
        """Testa criação de persona com erro de banco de dados"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=True):
            with patch.object(service.validator, 'validate_persona_content', return_value={"is_valid": True}):
                with patch.object(service.validator, 'validate_persona_metadata', return_value=sample_persona_data.metadata):
                    service.db.personas.find_one = AsyncMock(return_value=None)
                    service.db.personas.insert_one = AsyncMock(side_effect=PyMongoError("Database error"))
                    
                    with pytest.raises(PyMongoError, match="Erro ao criar persona: Database error"):
                        await service.create_persona(agent_id, sample_persona_data)


class TestGetPersona:
    """Testes para get_persona"""
    
    @pytest.mark.asyncio
    async def test_get_persona_success(self, service, sample_persona_doc):
        """Testa busca bem-sucedida de persona"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=True):
            service.db.personas.find_one = AsyncMock(return_value=sample_persona_doc)
            
            result = await service.get_persona(agent_id)
            
            assert isinstance(result, PersonaResponse)
            assert result.id == str(sample_persona_doc["_id"])
            assert result.agent_id == str(sample_persona_doc["agent_id"])
    
    @pytest.mark.asyncio
    async def test_get_persona_not_found(self, service):
        """Testa busca de persona não encontrada"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=True):
            service.db.personas.find_one = AsyncMock(return_value=None)
            
            result = await service.get_persona(agent_id)
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_get_persona_agent_not_found(self, service):
        """Testa busca de persona com agente não encontrado"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=False):
            with pytest.raises(ValueError, match="Agente não encontrado"):
                await service.get_persona(agent_id)
    
    @pytest.mark.asyncio
    async def test_get_persona_database_error(self, service):
        """Testa busca de persona com erro de banco de dados"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=True):
            service.db.personas.find_one = AsyncMock(side_effect=PyMongoError("Database error"))
            
            with pytest.raises(PyMongoError, match="Erro ao buscar persona: Database error"):
                await service.get_persona(agent_id)


class TestUpdatePersona:
    """Testes para update_persona"""
    
    @pytest.mark.asyncio
    async def test_update_persona_success(self, service, sample_persona_doc):
        """Testa atualização bem-sucedida de persona"""
        agent_id = "507f1f77bcf86cd799439012"
        update_data = PersonaUpdate(
            content="# Teste Atualizado\nConteúdo atualizado.",
            metadata={"author": "test", "version": "2.0"}
        )
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=True):
            with patch.object(service.validator, 'validate_persona_content', return_value={"is_valid": True}):
                with patch.object(service.validator, 'validate_persona_metadata', return_value=update_data.metadata):
                    # Mock do banco de dados
                    service.db.personas.find_one = AsyncMock(return_value=sample_persona_doc)
                    service.db.personas.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
                    
                    # Mock da busca após atualização
                    updated_doc = sample_persona_doc.copy()
                    updated_doc["content"] = update_data.content
                    updated_doc["metadata"] = update_data.metadata
                    updated_doc["version"] = 2
                    service.db.personas.find_one = AsyncMock(return_value=updated_doc)
                    
                    result = await service.update_persona(agent_id, update_data)
                    
                    assert isinstance(result, PersonaResponse)
                    assert result.content == update_data.content
                    assert result.metadata == update_data.metadata
                    assert result.version == 2
    
    @pytest.mark.asyncio
    async def test_update_persona_agent_not_found(self, service):
        """Testa atualização de persona com agente não encontrado"""
        agent_id = "507f1f77bcf86cd799439012"
        update_data = PersonaUpdate(content="# Teste Atualizado")
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=False):
            with pytest.raises(ValueError, match="Agente não encontrado"):
                await service.update_persona(agent_id, update_data)
    
    @pytest.mark.asyncio
    async def test_update_persona_not_found(self, service):
        """Testa atualização de persona não encontrada"""
        agent_id = "507f1f77bcf86cd799439012"
        update_data = PersonaUpdate(content="# Teste Atualizado")
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=True):
            service.db.personas.find_one = AsyncMock(return_value=None)
            
            with pytest.raises(ValueError, match="Persona não encontrada para este agente"):
                await service.update_persona(agent_id, update_data)
    
    @pytest.mark.asyncio
    async def test_update_persona_no_data(self, service, sample_persona_doc):
        """Testa atualização de persona sem dados"""
        agent_id = "507f1f77bcf86cd799439012"
        update_data = PersonaUpdate()  # Sem dados para atualizar
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=True):
            service.db.personas.find_one = AsyncMock(return_value=sample_persona_doc)
            
            with pytest.raises(ValueError, match="Nenhum dado para atualizar"):
                await service.update_persona(agent_id, update_data)
    
    @pytest.mark.asyncio
    async def test_update_persona_database_error(self, service, sample_persona_doc):
        """Testa atualização de persona com erro de banco de dados"""
        agent_id = "507f1f77bcf86cd799439012"
        update_data = PersonaUpdate(content="# Teste Atualizado")
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=True):
            with patch.object(service.validator, 'validate_persona_content', return_value={"is_valid": True}):
                service.db.personas.find_one = AsyncMock(return_value=sample_persona_doc)
                service.db.personas.update_one = AsyncMock(side_effect=PyMongoError("Database error"))
                
                with pytest.raises(PyMongoError, match="Erro ao atualizar persona: Database error"):
                    await service.update_persona(agent_id, update_data)


class TestDeletePersona:
    """Testes para delete_persona"""
    
    @pytest.mark.asyncio
    async def test_delete_persona_success(self, service):
        """Testa remoção bem-sucedida de persona"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=True):
            service.db.personas.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
            
            result = await service.delete_persona(agent_id)
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_delete_persona_not_found(self, service):
        """Testa remoção de persona não encontrada"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=True):
            service.db.personas.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))
            
            result = await service.delete_persona(agent_id)
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_persona_agent_not_found(self, service):
        """Testa remoção de persona com agente não encontrado"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=False):
            with pytest.raises(ValueError, match="Agente não encontrado"):
                await service.delete_persona(agent_id)
    
    @pytest.mark.asyncio
    async def test_delete_persona_database_error(self, service):
        """Testa remoção de persona com erro de banco de dados"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch.object(service.validator, 'validate_agent_exists', return_value=True):
            service.db.personas.delete_one = AsyncMock(side_effect=PyMongoError("Database error"))
            
            with pytest.raises(PyMongoError, match="Erro ao remover persona: Database error"):
                await service.delete_persona(agent_id)


class TestListPersonas:
    """Testes para list_personas"""
    
    @pytest.mark.asyncio
    async def test_list_personas_success(self, service, sample_persona_doc):
        """Testa listagem bem-sucedida de personas"""
        personas_docs = [sample_persona_doc]
        
        # Mock do cursor
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=personas_docs)
        service.db.personas.find = MagicMock(return_value=mock_cursor)
        service.db.personas.count_documents = AsyncMock(return_value=1)
        
        result = await service.list_personas(page=1, per_page=10)
        
        assert isinstance(result, PersonaListResponse)
        assert len(result.personas) == 1
        assert result.total == 1
        assert result.page == 1
        assert result.per_page == 10
        assert result.has_next is False
        assert result.has_prev is False
    
    @pytest.mark.asyncio
    async def test_list_personas_with_agent_filter(self, service, sample_persona_doc):
        """Testa listagem de personas com filtro por agente"""
        agent_id = "507f1f77bcf86cd799439012"
        personas_docs = [sample_persona_doc]
        
        # Mock do cursor
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=personas_docs)
        service.db.personas.find = MagicMock(return_value=mock_cursor)
        service.db.personas.count_documents = AsyncMock(return_value=1)
        
        result = await service.list_personas(page=1, per_page=10, agent_id=agent_id)
        
        assert isinstance(result, PersonaListResponse)
        assert len(result.personas) == 1
        assert result.total == 1
    
    @pytest.mark.asyncio
    async def test_list_personas_pagination(self, service, sample_persona_doc):
        """Testa listagem de personas com paginação"""
        personas_docs = [sample_persona_doc]
        
        # Mock do cursor
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=personas_docs)
        service.db.personas.find = MagicMock(return_value=mock_cursor)
        service.db.personas.count_documents = AsyncMock(return_value=25)  # Total de 25 personas
        
        result = await service.list_personas(page=2, per_page=10)
        
        assert isinstance(result, PersonaListResponse)
        assert result.page == 2
        assert result.per_page == 10
        assert result.total == 25
        assert result.has_next is True
        assert result.has_prev is True
    
    @pytest.mark.asyncio
    async def test_list_personas_invalid_page(self, service):
        """Testa listagem de personas com página inválida"""
        with pytest.raises(ValueError, match="Página deve ser maior que 0"):
            await service.list_personas(page=0, per_page=10)
    
    @pytest.mark.asyncio
    async def test_list_personas_invalid_per_page(self, service):
        """Testa listagem de personas com per_page inválido"""
        with pytest.raises(ValueError, match="Itens por página deve estar entre 1 e 100"):
            await service.list_personas(page=1, per_page=0)
        
        with pytest.raises(ValueError, match="Itens por página deve estar entre 1 e 100"):
            await service.list_personas(page=1, per_page=101)
    
    @pytest.mark.asyncio
    async def test_list_personas_invalid_agent_id(self, service):
        """Testa listagem de personas com agent_id inválido"""
        with pytest.raises(ValueError, match="ID do agente inválido"):
            await service.list_personas(page=1, per_page=10, agent_id="invalid_id")
    
    @pytest.mark.asyncio
    async def test_list_personas_database_error(self, service):
        """Testa listagem de personas com erro de banco de dados"""
        service.db.personas.find = MagicMock(side_effect=PyMongoError("Database error"))
        
        with pytest.raises(PyMongoError, match="Erro ao listar personas: Database error"):
            await service.list_personas(page=1, per_page=10)


class TestDocToResponse:
    """Testes para _doc_to_response"""
    
    def test_doc_to_response_success(self, service, sample_persona_doc):
        """Testa conversão de documento para PersonaResponse"""
        result = service._doc_to_response(sample_persona_doc)
        
        assert isinstance(result, PersonaResponse)
        assert result.id == str(sample_persona_doc["_id"])
        assert result.agent_id == str(sample_persona_doc["agent_id"])
        assert result.content == sample_persona_doc["content"]
        assert result.metadata == sample_persona_doc["metadata"]
        assert result.version == sample_persona_doc["version"]
        assert result.created_at == sample_persona_doc["created_at"]
        assert result.updated_at == sample_persona_doc["updated_at"]
    
    def test_doc_to_response_with_default_metadata(self, service):
        """Testa conversão de documento sem metadata"""
        doc = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "agent_id": ObjectId("507f1f77bcf86cd799439012"),
            "content": "# Teste",
            "version": 1,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = service._doc_to_response(doc)
        
        assert isinstance(result, PersonaResponse)
        assert result.metadata == {}