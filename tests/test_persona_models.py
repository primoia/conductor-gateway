"""
Testes unitários para modelos de Persona
SAGA-008 - Fase 1: Core APIs
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from src.models.persona import (
    PersonaBase, PersonaCreate, PersonaUpdate, PersonaResponse, PersonaListResponse,
    _is_valid_markdown
)


class TestPersonaBase:
    """Testes para PersonaBase"""
    
    def test_persona_base_valid(self):
        """Testa criação válida de PersonaBase"""
        persona = PersonaBase(
            content="# Teste\nEste é um teste de persona.",
            metadata={"author": "test", "version": "1.0"}
        )
        
        assert persona.content == "# Teste\nEste é um teste de persona."
        assert persona.metadata == {"author": "test", "version": "1.0"}
    
    def test_persona_base_empty_metadata(self):
        """Testa PersonaBase com metadata vazio"""
        persona = PersonaBase(content="# Teste")
        assert persona.metadata == {}


class TestPersonaCreate:
    """Testes para PersonaCreate"""
    
    def test_persona_create_valid(self):
        """Testa criação válida de PersonaCreate"""
        persona = PersonaCreate(
            content="# Teste\nEste é um teste de persona.",
            metadata={"author": "test"}
        )
        
        assert persona.content == "# Teste\nEste é um teste de persona."
        assert persona.metadata == {"author": "test"}
    
    def test_persona_create_empty_content(self):
        """Testa PersonaCreate com conteúdo vazio"""
        with pytest.raises(ValidationError) as exc_info:
            PersonaCreate(content="")
        
        assert "Conteúdo da persona não pode estar vazio" in str(exc_info.value)
    
    def test_persona_create_whitespace_only(self):
        """Testa PersonaCreate com apenas espaços em branco"""
        with pytest.raises(ValidationError) as exc_info:
            PersonaCreate(content="   \n\t  ")
        
        assert "Conteúdo da persona não pode estar vazio" in str(exc_info.value)
    
    def test_persona_create_too_large(self):
        """Testa PersonaCreate com conteúdo muito grande"""
        large_content = "# Teste\n" + "x" * 50001  # 50KB + 1
        
        with pytest.raises(ValidationError) as exc_info:
            PersonaCreate(content=large_content)
        
        assert "Conteúdo da persona excede o limite de 50KB" in str(exc_info.value)
    
    def test_persona_create_invalid_markdown(self):
        """Testa PersonaCreate com markdown inválido"""
        with pytest.raises(ValidationError) as exc_info:
            PersonaCreate(content="\x00\x01\x02")  # Caracteres de controle inválidos
        
        assert "Conteúdo deve ser um Markdown válido" in str(exc_info.value)
    
    def test_persona_create_metadata_too_large(self):
        """Testa PersonaCreate com metadata muito grande"""
        large_metadata = {"data": "x" * 5001}  # 5KB + 1
        
        with pytest.raises(ValidationError) as exc_info:
            PersonaCreate(content="# Teste", metadata=large_metadata)
        
        assert "Metadata excede o limite de 5KB" in str(exc_info.value)
    
    def test_persona_create_invalid_metadata_type(self):
        """Testa PersonaCreate com metadata inválido"""
        with pytest.raises(ValidationError) as exc_info:
            PersonaCreate(content="# Teste", metadata="invalid")
        
        assert "Metadata deve ser um dicionário" in str(exc_info.value)


class TestPersonaUpdate:
    """Testes para PersonaUpdate"""
    
    def test_persona_update_valid(self):
        """Testa atualização válida de PersonaUpdate"""
        persona = PersonaUpdate(
            content="# Teste Atualizado\nConteúdo atualizado.",
            metadata={"author": "test", "updated": True}
        )
        
        assert persona.content == "# Teste Atualizado\nConteúdo atualizado."
        assert persona.metadata == {"author": "test", "updated": True}
    
    def test_persona_update_partial(self):
        """Testa PersonaUpdate com apenas alguns campos"""
        persona = PersonaUpdate(content="# Teste Atualizado")
        
        assert persona.content == "# Teste Atualizado"
        assert persona.metadata is None
    
    def test_persona_update_empty_content(self):
        """Testa PersonaUpdate com conteúdo vazio"""
        with pytest.raises(ValidationError) as exc_info:
            PersonaUpdate(content="")
        
        assert "Conteúdo da persona não pode estar vazio" in str(exc_info.value)
    
    def test_persona_update_none_content(self):
        """Testa PersonaUpdate com conteúdo None"""
        persona = PersonaUpdate(content=None)
        assert persona.content is None


class TestPersonaResponse:
    """Testes para PersonaResponse"""
    
    def test_persona_response_valid(self):
        """Testa criação válida de PersonaResponse"""
        now = datetime.utcnow()
        persona = PersonaResponse(
            id="507f1f77bcf86cd799439011",
            agent_id="507f1f77bcf86cd799439012",
            content="# Teste\nConteúdo da persona.",
            metadata={"author": "test"},
            version=1,
            created_at=now,
            updated_at=now
        )
        
        assert persona.id == "507f1f77bcf86cd799439011"
        assert persona.agent_id == "507f1f77bcf86cd799439012"
        assert persona.content == "# Teste\nConteúdo da persona."
        assert persona.metadata == {"author": "test"}
        assert persona.version == 1
        assert persona.created_at == now
        assert persona.updated_at == now


class TestPersonaListResponse:
    """Testes para PersonaListResponse"""
    
    def test_persona_list_response_valid(self):
        """Testa criação válida de PersonaListResponse"""
        now = datetime.utcnow()
        personas = [
            PersonaResponse(
                id="507f1f77bcf86cd799439011",
                agent_id="507f1f77bcf86cd799439012",
                content="# Teste 1",
                metadata={},
                version=1,
                created_at=now,
                updated_at=now
            ),
            PersonaResponse(
                id="507f1f77bcf86cd799439013",
                agent_id="507f1f77bcf86cd799439014",
                content="# Teste 2",
                metadata={},
                version=1,
                created_at=now,
                updated_at=now
            )
        ]
        
        response = PersonaListResponse(
            personas=personas,
            total=2,
            page=1,
            per_page=10,
            has_next=False,
            has_prev=False
        )
        
        assert len(response.personas) == 2
        assert response.total == 2
        assert response.page == 1
        assert response.per_page == 10
        assert response.has_next is False
        assert response.has_prev is False


class TestIsValidMarkdown:
    """Testes para função _is_valid_markdown"""
    
    def test_valid_markdown_headers(self):
        """Testa markdown válido com headers"""
        assert _is_valid_markdown("# Header 1\n## Header 2")
        assert _is_valid_markdown("### Header 3")
    
    def test_valid_markdown_bold_italic(self):
        """Testa markdown válido com bold e italic"""
        assert _is_valid_markdown("**Bold text** and *italic text*")
    
    def test_valid_markdown_code(self):
        """Testa markdown válido com código"""
        assert _is_valid_markdown("`inline code` and ```code block```")
    
    def test_valid_markdown_lists(self):
        """Testa markdown válido com listas"""
        assert _is_valid_markdown("- Item 1\n- Item 2")
        assert _is_valid_markdown("1. Item 1\n2. Item 2")
    
    def test_valid_markdown_links(self):
        """Testa markdown válido com links"""
        assert _is_valid_markdown("[Link text](https://example.com)")
        assert _is_valid_markdown("![Image alt](https://example.com/image.jpg)")
    
    def test_valid_markdown_blockquotes(self):
        """Testa markdown válido com blockquotes"""
        assert _is_valid_markdown("> This is a blockquote")
    
    def test_valid_markdown_horizontal_rules(self):
        """Testa markdown válido com regras horizontais"""
        assert _is_valid_markdown("---")
        assert _is_valid_markdown("***")
    
    def test_valid_plain_text(self):
        """Testa texto simples válido"""
        assert _is_valid_markdown("This is plain text")
        assert _is_valid_markdown("Simple text without markdown")
    
    def test_invalid_empty_content(self):
        """Testa conteúdo vazio"""
        assert not _is_valid_markdown("")
        assert not _is_valid_markdown("   ")
        assert not _is_valid_markdown("\n\t")
    
    def test_invalid_control_characters(self):
        """Testa caracteres de controle inválidos"""
        assert not _is_valid_markdown("\x00\x01\x02")
        assert not _is_valid_markdown("Text with \x00 null char")
    
    def test_valid_mixed_content(self):
        """Testa conteúdo misto válido"""
        content = """
# Título Principal

Este é um **texto em negrito** e *texto em itálico*.

## Lista de Itens

- Item 1
- Item 2
- Item 3

### Código

```python
def hello():
    print("Hello, World!")
```

> Esta é uma citação importante.

[Link para exemplo](https://example.com)
"""
        assert _is_valid_markdown(content)