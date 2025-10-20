"""
Testes unitários para router de Persona
SAGA-008 - Fase 1: Core APIs
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
from datetime import datetime
from bson import ObjectId

from src.api.routers.persona import router
from src.models.persona import PersonaCreate, PersonaUpdate, PersonaResponse


@pytest.fixture
def app():
    """Aplicação FastAPI para testes"""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Cliente de teste"""
    return TestClient(app)


@pytest.fixture
def sample_persona_data():
    """Dados de exemplo para persona"""
    return {
        "content": "# Teste\nEste é um teste de persona.",
        "metadata": {"author": "test", "version": "1.0"}
    }


@pytest.fixture
def sample_persona_response():
    """Resposta de exemplo de persona"""
    return PersonaResponse(
        id="507f1f77bcf86cd799439011",
        agent_id="507f1f77bcf86cd799439012",
        content="# Teste\nEste é um teste de persona.",
        metadata={"author": "test", "version": "1.0"},
        version=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )


class TestCreatePersona:
    """Testes para POST /api/agents/{agent_id}/persona"""
    
    def test_create_persona_success(self, client, sample_persona_data, sample_persona_response):
        """Testa criação bem-sucedida de persona"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.create_persona = AsyncMock(return_value=sample_persona_response)
            mock_get_service.return_value = mock_service
            
            response = client.post(f"/api/agents/{agent_id}/persona", json=sample_persona_data)
            
            assert response.status_code == 201
            data = response.json()
            assert data["id"] == sample_persona_response.id
            assert data["agent_id"] == sample_persona_response.agent_id
            assert data["content"] == sample_persona_response.content
            assert data["metadata"] == sample_persona_response.metadata
            assert data["version"] == sample_persona_response.version
    
    def test_create_persona_validation_error(self, client, sample_persona_data):
        """Testa criação de persona com erro de validação"""
        agent_id = "507f1f77bcf86cd799439012"
        invalid_data = {"content": ""}  # Conteúdo vazio
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.create_persona = AsyncMock(side_effect=ValueError("Conteúdo da persona não pode estar vazio"))
            mock_get_service.return_value = mock_service
            
            response = client.post(f"/api/agents/{agent_id}/persona", json=invalid_data)
            
            assert response.status_code == 400
            assert "Conteúdo da persona não pode estar vazio" in response.json()["detail"]
    
    def test_create_persona_internal_error(self, client, sample_persona_data):
        """Testa criação de persona com erro interno"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.create_persona = AsyncMock(side_effect=Exception("Internal error"))
            mock_get_service.return_value = mock_service
            
            response = client.post(f"/api/agents/{agent_id}/persona", json=sample_persona_data)
            
            assert response.status_code == 500
            assert "Erro interno: Internal error" in response.json()["detail"]


class TestGetPersona:
    """Testes para GET /api/agents/{agent_id}/persona"""
    
    def test_get_persona_success(self, client, sample_persona_response):
        """Testa busca bem-sucedida de persona"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_persona = AsyncMock(return_value=sample_persona_response)
            mock_get_service.return_value = mock_service
            
            response = client.get(f"/api/agents/{agent_id}/persona")
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == sample_persona_response.id
            assert data["agent_id"] == sample_persona_response.agent_id
            assert data["content"] == sample_persona_response.content
    
    def test_get_persona_not_found(self, client):
        """Testa busca de persona não encontrada"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_persona = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service
            
            response = client.get(f"/api/agents/{agent_id}/persona")
            
            assert response.status_code == 404
            assert "Persona não encontrada" in response.json()["detail"]
    
    def test_get_persona_validation_error(self, client):
        """Testa busca de persona com erro de validação"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_persona = AsyncMock(side_effect=ValueError("Agente não encontrado"))
            mock_get_service.return_value = mock_service
            
            response = client.get(f"/api/agents/{agent_id}/persona")
            
            assert response.status_code == 400
            assert "Agente não encontrado" in response.json()["detail"]


class TestUpdatePersona:
    """Testes para PUT /api/agents/{agent_id}/persona"""
    
    def test_update_persona_success(self, client, sample_persona_response):
        """Testa atualização bem-sucedida de persona"""
        agent_id = "507f1f77bcf86cd799439012"
        update_data = {
            "content": "# Teste Atualizado\nConteúdo atualizado.",
            "metadata": {"author": "test", "version": "2.0"}
        }
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.update_persona = AsyncMock(return_value=sample_persona_response)
            mock_get_service.return_value = mock_service
            
            response = client.put(f"/api/agents/{agent_id}/persona", json=update_data)
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == sample_persona_response.id
            assert data["agent_id"] == sample_persona_response.agent_id
    
    def test_update_persona_validation_error(self, client):
        """Testa atualização de persona com erro de validação"""
        agent_id = "507f1f77bcf86cd799439012"
        invalid_data = {"content": ""}  # Conteúdo vazio
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.update_persona = AsyncMock(side_effect=ValueError("Conteúdo da persona não pode estar vazio"))
            mock_get_service.return_value = mock_service
            
            response = client.put(f"/api/agents/{agent_id}/persona", json=invalid_data)
            
            assert response.status_code == 400
            assert "Conteúdo da persona não pode estar vazio" in response.json()["detail"]


class TestDeletePersona:
    """Testes para DELETE /api/agents/{agent_id}/persona"""
    
    def test_delete_persona_success(self, client):
        """Testa remoção bem-sucedida de persona"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.delete_persona = AsyncMock(return_value=True)
            mock_get_service.return_value = mock_service
            
            response = client.delete(f"/api/agents/{agent_id}/persona")
            
            assert response.status_code == 204
    
    def test_delete_persona_not_found(self, client):
        """Testa remoção de persona não encontrada"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.delete_persona = AsyncMock(return_value=False)
            mock_get_service.return_value = mock_service
            
            response = client.delete(f"/api/agents/{agent_id}/persona")
            
            assert response.status_code == 404
            assert "Persona não encontrada" in response.json()["detail"]
    
    def test_delete_persona_validation_error(self, client):
        """Testa remoção de persona com erro de validação"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.delete_persona = AsyncMock(side_effect=ValueError("Agente não encontrado"))
            mock_get_service.return_value = mock_service
            
            response = client.delete(f"/api/agents/{agent_id}/persona")
            
            assert response.status_code == 400
            assert "Agente não encontrado" in response.json()["detail"]


class TestListPersonas:
    """Testes para GET /api/agents/personas"""
    
    def test_list_personas_success(self, client, sample_persona_response):
        """Testa listagem bem-sucedida de personas"""
        personas_list = {
            "personas": [sample_persona_response],
            "total": 1,
            "page": 1,
            "per_page": 10,
            "has_next": False,
            "has_prev": False
        }
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.list_personas = AsyncMock(return_value=personas_list)
            mock_get_service.return_value = mock_service
            
            response = client.get("/api/agents/personas")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data["personas"]) == 1
            assert data["total"] == 1
            assert data["page"] == 1
            assert data["per_page"] == 10
            assert data["has_next"] is False
            assert data["has_prev"] is False
    
    def test_list_personas_with_filters(self, client, sample_persona_response):
        """Testa listagem de personas com filtros"""
        personas_list = {
            "personas": [sample_persona_response],
            "total": 1,
            "page": 1,
            "per_page": 10,
            "has_next": False,
            "has_prev": False
        }
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.list_personas = AsyncMock(return_value=personas_list)
            mock_get_service.return_value = mock_service
            
            response = client.get("/api/agents/personas?page=2&per_page=5&agent_id=507f1f77bcf86cd799439012")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data["personas"]) == 1
    
    def test_list_personas_validation_error(self, client):
        """Testa listagem de personas com erro de validação"""
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.list_personas = AsyncMock(side_effect=ValueError("Página deve ser maior que 0"))
            mock_get_service.return_value = mock_service
            
            response = client.get("/api/agents/personas?page=0")
            
            assert response.status_code == 400
            assert "Página deve ser maior que 0" in response.json()["detail"]


class TestValidatePersonaContent:
    """Testes para GET /api/agents/{agent_id}/persona/validate"""
    
    def test_validate_persona_content_success(self, client):
        """Testa validação bem-sucedida de conteúdo"""
        agent_id = "507f1f77bcf86cd799439012"
        content = "# Teste\nEste é um teste de persona."
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.validator.validate_agent_exists = AsyncMock(return_value=True)
            mock_service.validator.validate_persona_content = AsyncMock(return_value={
                "is_valid": True,
                "content_length": len(content),
                "stats": {"lines": 2, "words": 6, "characters": len(content)}
            })
            mock_get_service.return_value = mock_service
            
            response = client.get(f"/api/agents/{agent_id}/persona/validate?content={content}")
            
            assert response.status_code == 200
            data = response.json()
            assert data["is_valid"] is True
            assert data["message"] == "Conteúdo válido"
            assert data["validation"]["content_length"] == len(content)
    
    def test_validate_persona_content_invalid(self, client):
        """Testa validação de conteúdo inválido"""
        agent_id = "507f1f77bcf86cd799439012"
        content = ""  # Conteúdo vazio
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.validator.validate_agent_exists = AsyncMock(return_value=True)
            mock_service.validator.validate_persona_content = AsyncMock(side_effect=ValueError("Conteúdo da persona não pode estar vazio"))
            mock_get_service.return_value = mock_service
            
            response = client.get(f"/api/agents/{agent_id}/persona/validate?content={content}")
            
            assert response.status_code == 200
            data = response.json()
            assert data["is_valid"] is False
            assert "Conteúdo da persona não pode estar vazio" in data["message"]
            assert data["validation"] is None
    
    def test_validate_persona_content_agent_not_found(self, client):
        """Testa validação de conteúdo com agente não encontrado"""
        agent_id = "507f1f77bcf86cd799439012"
        content = "# Teste"
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.validator.validate_agent_exists = AsyncMock(return_value=False)
            mock_get_service.return_value = mock_service
            
            response = client.get(f"/api/agents/{agent_id}/persona/validate?content={content}")
            
            assert response.status_code == 404
            assert "Agente não encontrado" in response.json()["detail"]


class TestGetPersonaStats:
    """Testes para GET /api/agents/{agent_id}/persona/stats"""
    
    def test_get_persona_stats_success(self, client, sample_persona_response):
        """Testa busca bem-sucedida de estatísticas"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_persona = AsyncMock(return_value=sample_persona_response)
            mock_service.validator._calculate_content_stats = MagicMock(return_value={
                "lines": 2,
                "words": 6,
                "characters": 30,
                "markdown_elements": {"headers": 1, "bold": 0, "italic": 0}
            })
            mock_get_service.return_value = mock_service
            
            response = client.get(f"/api/agents/{agent_id}/persona/stats")
            
            assert response.status_code == 200
            data = response.json()
            assert data["persona_id"] == sample_persona_response.id
            assert data["agent_id"] == sample_persona_response.agent_id
            assert data["version"] == sample_persona_response.version
            assert "content_stats" in data
            assert data["content_stats"]["lines"] == 2
            assert data["content_stats"]["words"] == 6
    
    def test_get_persona_stats_not_found(self, client):
        """Testa busca de estatísticas de persona não encontrada"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_persona = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service
            
            response = client.get(f"/api/agents/{agent_id}/persona/stats")
            
            assert response.status_code == 404
            assert "Persona não encontrada" in response.json()["detail"]
    
    def test_get_persona_stats_validation_error(self, client):
        """Testa busca de estatísticas com erro de validação"""
        agent_id = "507f1f77bcf86cd799439012"
        
        with patch('src.api.routers.persona.get_persona_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_persona = AsyncMock(side_effect=ValueError("Agente não encontrado"))
            mock_get_service.return_value = mock_service
            
            response = client.get(f"/api/agents/{agent_id}/persona/stats")
            
            assert response.status_code == 400
            assert "Agente não encontrado" in response.json()["detail"]


class TestRouterIntegration:
    """Testes de integração do router"""
    
    def test_router_prefix(self, app):
        """Testa se o router está configurado com o prefixo correto"""
        routes = [route.path for route in app.routes if hasattr(route, 'path')]
        
        # Verifica se as rotas estão com o prefixo correto
        persona_routes = [route for route in routes if '/persona' in route]
        assert len(persona_routes) > 0
        
        # Verifica se todas as rotas começam com /api/agents
        for route in persona_routes:
            assert route.startswith('/api/agents')
    
    def test_router_tags(self, app):
        """Testa se o router está configurado com as tags corretas"""
        routes = [route for route in app.routes if hasattr(route, 'tags')]
        
        # Verifica se há rotas com tag 'persona'
        persona_routes = [route for route in routes if 'persona' in route.tags]
        assert len(persona_routes) > 0