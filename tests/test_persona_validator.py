"""
Testes unitários para PersonaValidator
SAGA-008 - Fase 1: Core APIs
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
from pymongo.errors import PyMongoError

from src.services.persona_validator import PersonaValidator


@pytest.fixture
def mock_db():
    """Mock do banco de dados"""
    db = MagicMock()
    db.agents = MagicMock()
    db.personas = MagicMock()
    return db


@pytest.fixture
def validator(mock_db):
    """Instância do PersonaValidator"""
    return PersonaValidator(mock_db)


class TestValidateAgentExists:
    """Testes para validate_agent_exists"""
    
    @pytest.mark.asyncio
    async def test_validate_agent_exists_success(self, validator):
        """Testa validação de agente existente"""
        agent_id = "507f1f77bcf86cd799439011"
        validator.db.agents.find_one = AsyncMock(return_value={"_id": ObjectId(agent_id)})
        
        result = await validator.validate_agent_exists(agent_id)
        assert result is True
        
        validator.db.agents.find_one.assert_called_once_with(
            {"_id": ObjectId(agent_id)},
            {"_id": 1}
        )
    
    @pytest.mark.asyncio
    async def test_validate_agent_exists_not_found(self, validator):
        """Testa validação de agente não encontrado"""
        agent_id = "507f1f77bcf86cd799439011"
        validator.db.agents.find_one = AsyncMock(return_value=None)
        
        result = await validator.validate_agent_exists(agent_id)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_validate_agent_exists_invalid_id(self, validator):
        """Testa validação com ID inválido"""
        with pytest.raises(ValueError, match="ID do agente deve ser um ObjectId válido"):
            await validator.validate_agent_exists("invalid_id")
    
    @pytest.mark.asyncio
    async def test_validate_agent_exists_empty_id(self, validator):
        """Testa validação com ID vazio"""
        with pytest.raises(ValueError, match="ID do agente é obrigatório"):
            await validator.validate_agent_exists("")
    
    @pytest.mark.asyncio
    async def test_validate_agent_exists_none_id(self, validator):
        """Testa validação com ID None"""
        with pytest.raises(ValueError, match="ID do agente é obrigatório"):
            await validator.validate_agent_exists(None)
    
    @pytest.mark.asyncio
    async def test_validate_agent_exists_wrong_type(self, validator):
        """Testa validação com tipo incorreto"""
        with pytest.raises(ValueError, match="ID do agente deve ser uma string"):
            await validator.validate_agent_exists(123)
    
    @pytest.mark.asyncio
    async def test_validate_agent_exists_database_error(self, validator):
        """Testa validação com erro de banco de dados"""
        agent_id = "507f1f77bcf86cd799439011"
        validator.db.agents.find_one = AsyncMock(side_effect=PyMongoError("Database error"))
        
        with pytest.raises(ValueError, match="Erro ao verificar agente: Database error"):
            await validator.validate_agent_exists(agent_id)


class TestValidatePersonaContent:
    """Testes para validate_persona_content"""
    
    @pytest.mark.asyncio
    async def test_validate_persona_content_valid(self, validator):
        """Testa validação de conteúdo válido"""
        content = "# Teste\nEste é um teste de persona."
        
        result = await validator.validate_persona_content(content)
        
        assert result["is_valid"] is True
        assert result["content_length"] == len(content)
        assert "stats" in result
    
    @pytest.mark.asyncio
    async def test_validate_persona_content_empty(self, validator):
        """Testa validação de conteúdo vazio"""
        with pytest.raises(ValueError, match="Conteúdo da persona é obrigatório"):
            await validator.validate_persona_content("")
    
    @pytest.mark.asyncio
    async def test_validate_persona_content_none(self, validator):
        """Testa validação de conteúdo None"""
        with pytest.raises(ValueError, match="Conteúdo da persona é obrigatório"):
            await validator.validate_persona_content(None)
    
    @pytest.mark.asyncio
    async def test_validate_persona_content_wrong_type(self, validator):
        """Testa validação de conteúdo com tipo incorreto"""
        with pytest.raises(ValueError, match="Conteúdo da persona deve ser uma string"):
            await validator.validate_persona_content(123)
    
    @pytest.mark.asyncio
    async def test_validate_persona_content_too_large(self, validator):
        """Testa validação de conteúdo muito grande"""
        large_content = "x" * 50001  # 50KB + 1
        
        with pytest.raises(ValueError, match="Conteúdo da persona excede o limite de 50KB"):
            await validator.validate_persona_content(large_content)
    
    @pytest.mark.asyncio
    async def test_validate_persona_content_whitespace_only(self, validator):
        """Testa validação de conteúdo apenas com espaços"""
        with pytest.raises(ValueError, match="Conteúdo da persona não pode estar vazio"):
            await validator.validate_persona_content("   \n\t  ")
    
    @pytest.mark.asyncio
    async def test_validate_persona_content_invalid_characters(self, validator):
        """Testa validação de conteúdo com caracteres inválidos"""
        with pytest.raises(ValueError, match="Conteúdo contém caracteres inválidos"):
            await validator.validate_persona_content("Text with \x00 null char")
    
    @pytest.mark.asyncio
    async def test_validate_persona_content_invalid_markdown(self, validator):
        """Testa validação de conteúdo com markdown inválido"""
        with pytest.raises(ValueError, match="Conteúdo deve ser um Markdown válido"):
            await validator.validate_persona_content("Invalid markdown \x01\x02")


class TestValidatePersonaMetadata:
    """Testes para validate_persona_metadata"""
    
    @pytest.mark.asyncio
    async def test_validate_persona_metadata_valid(self, validator):
        """Testa validação de metadata válido"""
        metadata = {"author": "test", "version": "1.0"}
        
        result = await validator.validate_persona_metadata(metadata)
        
        assert result == metadata
    
    @pytest.mark.asyncio
    async def test_validate_persona_metadata_none(self, validator):
        """Testa validação de metadata None"""
        result = await validator.validate_persona_metadata(None)
        assert result == {}
    
    @pytest.mark.asyncio
    async def test_validate_persona_metadata_wrong_type(self, validator):
        """Testa validação de metadata com tipo incorreto"""
        with pytest.raises(ValueError, match="Metadata deve ser um dicionário"):
            await validator.validate_persona_metadata("invalid")
    
    @pytest.mark.asyncio
    async def test_validate_persona_metadata_too_large(self, validator):
        """Testa validação de metadata muito grande"""
        large_metadata = {"data": "x" * 5001}  # 5KB + 1
        
        with pytest.raises(ValueError, match="Metadata excede o limite de 5KB"):
            await validator.validate_persona_metadata(large_metadata)
    
    @pytest.mark.asyncio
    async def test_validate_persona_metadata_invalid_key(self, validator):
        """Testa validação de metadata com chave inválida"""
        with pytest.raises(ValueError, match="Chaves do metadata devem ser strings"):
            await validator.validate_persona_metadata({123: "value"})
    
    @pytest.mark.asyncio
    async def test_validate_persona_metadata_empty_key(self, validator):
        """Testa validação de metadata com chave vazia"""
        with pytest.raises(ValueError, match="Chaves do metadata não podem estar vazias"):
            await validator.validate_persona_metadata({"": "value"})
    
    @pytest.mark.asyncio
    async def test_validate_persona_metadata_non_serializable_value(self, validator):
        """Testa validação de metadata com valor não serializável"""
        class NonSerializable:
            pass
        
        with pytest.raises(ValueError, match="Valor do metadata 'key' não é serializável"):
            await validator.validate_persona_metadata({"key": NonSerializable()})


class TestValidatePersonaUpdate:
    """Testes para validate_persona_update"""
    
    @pytest.mark.asyncio
    async def test_validate_persona_update_success(self, validator):
        """Testa validação de atualização válida"""
        agent_id = "507f1f77bcf86cd799439011"
        persona_id = "507f1f77bcf86cd799439012"
        
        validator.db.agents.find_one = AsyncMock(return_value={"_id": ObjectId(agent_id)})
        validator.db.personas.find_one = AsyncMock(return_value={
            "_id": ObjectId(persona_id),
            "agent_id": ObjectId(agent_id)
        })
        
        result = await validator.validate_persona_update(agent_id, persona_id)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_persona_update_agent_not_found(self, validator):
        """Testa validação com agente não encontrado"""
        agent_id = "507f1f77bcf86cd799439011"
        persona_id = "507f1f77bcf86cd799439012"
        
        validator.db.agents.find_one = AsyncMock(return_value=None)
        
        with pytest.raises(ValueError, match="Agente não encontrado"):
            await validator.validate_persona_update(agent_id, persona_id)
    
    @pytest.mark.asyncio
    async def test_validate_persona_update_persona_not_found(self, validator):
        """Testa validação com persona não encontrada"""
        agent_id = "507f1f77bcf86cd799439011"
        persona_id = "507f1f77bcf86cd799439012"
        
        validator.db.agents.find_one = AsyncMock(return_value={"_id": ObjectId(agent_id)})
        validator.db.personas.find_one = AsyncMock(return_value=None)
        
        with pytest.raises(ValueError, match="Persona não encontrada ou não pertence ao agente"):
            await validator.validate_persona_update(agent_id, persona_id)
    
    @pytest.mark.asyncio
    async def test_validate_persona_update_invalid_agent_id(self, validator):
        """Testa validação com ID de agente inválido"""
        with pytest.raises(ValueError, match="ID do agente deve ser um ObjectId válido"):
            await validator.validate_persona_update("invalid_id", "507f1f77bcf86cd799439012")
    
    @pytest.mark.asyncio
    async def test_validate_persona_update_invalid_persona_id(self, validator):
        """Testa validação com ID de persona inválido"""
        agent_id = "507f1f77bcf86cd799439011"
        
        with pytest.raises(ValueError, match="ID da persona deve ser um ObjectId válido"):
            await validator.validate_persona_update(agent_id, "invalid_id")
    
    @pytest.mark.asyncio
    async def test_validate_persona_update_empty_persona_id(self, validator):
        """Testa validação com ID de persona vazio"""
        agent_id = "507f1f77bcf86cd799439011"
        
        with pytest.raises(ValueError, match="ID da persona é obrigatório"):
            await validator.validate_persona_update(agent_id, "")


class TestCalculateContentStats:
    """Testes para _calculate_content_stats"""
    
    def test_calculate_content_stats_basic(self, validator):
        """Testa cálculo de estatísticas básicas"""
        content = "# Header\n**Bold** and *italic* text with `code`."
        
        stats = validator._calculate_content_stats(content)
        
        assert stats["lines"] == 1
        assert stats["words"] == 7
        assert stats["characters"] == len(content)
        assert stats["markdown_elements"]["headers"] == 1
        assert stats["markdown_elements"]["bold"] == 1
        assert stats["markdown_elements"]["italic"] == 1
        assert stats["markdown_elements"]["code"] == 1
    
    def test_calculate_content_stats_multiline(self, validator):
        """Testa cálculo de estatísticas com múltiplas linhas"""
        content = """# Header 1
## Header 2

- Item 1
- Item 2

**Bold text** and *italic text*.

```python
def hello():
    print("Hello, World!")
```

[Link](https://example.com)
"""
        
        stats = validator._calculate_content_stats(content)
        
        assert stats["lines"] == 10
        assert stats["words"] == 20
        assert stats["characters"] == len(content)
        assert stats["markdown_elements"]["headers"] == 2
        assert stats["markdown_elements"]["lists"] == 2
        assert stats["markdown_elements"]["code_blocks"] == 1
        assert stats["markdown_elements"]["links"] == 1
    
    def test_calculate_content_stats_empty(self, validator):
        """Testa cálculo de estatísticas com conteúdo vazio"""
        content = ""
        
        stats = validator._calculate_content_stats(content)
        
        assert stats["lines"] == 1
        assert stats["words"] == 0
        assert stats["characters"] == 0
        assert all(count == 0 for count in stats["markdown_elements"].values())


class TestIsValidContent:
    """Testes para _is_valid_content"""
    
    def test_is_valid_content_valid(self, validator):
        """Testa validação de conteúdo válido"""
        assert validator._is_valid_content("Valid content with normal characters")
        assert validator._is_valid_content("Content with special chars: !@#$%^&*()")
        assert validator._is_valid_content("Content with unicode: café, naïve, résumé")
    
    def test_is_valid_content_invalid_control_chars(self, validator):
        """Testa validação de conteúdo com caracteres de controle inválidos"""
        assert not validator._is_valid_content("Text with \x00 null char")
        assert not validator._is_valid_content("Text with \x01 start of heading")
        assert not validator._is_valid_content("Text with \x02 start of text")
        assert not validator._is_valid_content("Text with \x03 end of text")
        assert not validator._is_valid_content("Text with \x04 end of transmission")
        assert not validator._is_valid_content("Text with \x05 enquiry")
        assert not validator._is_valid_content("Text with \x06 acknowledge")
        assert not validator._is_valid_content("Text with \x07 bell")
        assert not validator._is_valid_content("Text with \x08 backspace")
        assert not validator._is_valid_content("Text with \x0b vertical tab")
        assert not validator._is_valid_content("Text with \x0c form feed")
        assert not validator._is_valid_content("Text with \x0e shift out")
        assert not validator._is_valid_content("Text with \x0f shift in")
        assert not validator._is_valid_content("Text with \x10 data link escape")
        assert not validator._is_valid_content("Text with \x11 device control 1")
        assert not validator._is_valid_content("Text with \x12 device control 2")
        assert not validator._is_valid_content("Text with \x13 device control 3")
        assert not validator._is_valid_content("Text with \x14 device control 4")
        assert not validator._is_valid_content("Text with \x15 negative acknowledge")
        assert not validator._is_valid_content("Text with \x16 synchronous idle")
        assert not validator._is_valid_content("Text with \x17 end of transmission block")
        assert not validator._is_valid_content("Text with \x18 cancel")
        assert not validator._is_valid_content("Text with \x19 end of medium")
        assert not validator._is_valid_content("Text with \x1a substitute")
        assert not validator._is_valid_content("Text with \x1b escape")
        assert not validator._is_valid_content("Text with \x1c file separator")
        assert not validator._is_valid_content("Text with \x1d group separator")
        assert not validator._is_valid_content("Text with \x1e record separator")
        assert not validator._is_valid_content("Text with \x1f unit separator")


class TestIsValidMarkdown:
    """Testes para _is_valid_markdown"""
    
    def test_is_valid_markdown_headers(self, validator):
        """Testa validação de markdown com headers"""
        assert validator._is_valid_markdown("# Header 1")
        assert validator._is_valid_markdown("## Header 2")
        assert validator._is_valid_markdown("### Header 3")
        assert validator._is_valid_markdown("#### Header 4")
        assert validator._is_valid_markdown("##### Header 5")
        assert validator._is_valid_markdown("###### Header 6")
    
    def test_is_valid_markdown_bold_italic(self, validator):
        """Testa validação de markdown com bold e italic"""
        assert validator._is_valid_markdown("**Bold text**")
        assert validator._is_valid_markdown("*Italic text*")
        assert validator._is_valid_markdown("***Bold and italic***")
    
    def test_is_valid_markdown_code(self, validator):
        """Testa validação de markdown com código"""
        assert validator._is_valid_markdown("`inline code`")
        assert validator._is_valid_markdown("```code block```")
        assert validator._is_valid_markdown("```python\nprint('Hello')\n```")
    
    def test_is_valid_markdown_lists(self, validator):
        """Testa validação de markdown com listas"""
        assert validator._is_valid_markdown("- Item 1\n- Item 2")
        assert validator._is_valid_markdown("* Item 1\n* Item 2")
        assert validator._is_valid_markdown("+ Item 1\n+ Item 2")
        assert validator._is_valid_markdown("1. Item 1\n2. Item 2")
    
    def test_is_valid_markdown_links(self, validator):
        """Testa validação de markdown com links"""
        assert validator._is_valid_markdown("[Link text](https://example.com)")
        assert validator._is_valid_markdown("![Image alt](https://example.com/image.jpg)")
    
    def test_is_valid_markdown_blockquotes(self, validator):
        """Testa validação de markdown com blockquotes"""
        assert validator._is_valid_markdown("> This is a blockquote")
        assert validator._is_valid_markdown("> > Nested blockquote")
    
    def test_is_valid_markdown_horizontal_rules(self, validator):
        """Testa validação de markdown com regras horizontais"""
        assert validator._is_valid_markdown("---")
        assert validator._is_valid_markdown("***")
        assert validator._is_valid_markdown("___")
    
    def test_is_valid_markdown_plain_text(self, validator):
        """Testa validação de markdown com texto simples"""
        assert validator._is_valid_markdown("This is plain text")
        assert validator._is_valid_markdown("Simple text without markdown")
        assert validator._is_valid_markdown("Text with numbers 123 and symbols !@#")
    
    def test_is_valid_markdown_empty(self, validator):
        """Testa validação de markdown vazio"""
        assert not validator._is_valid_markdown("")
        assert not validator._is_valid_markdown("   ")
        assert not validator._is_valid_markdown("\n\t")
    
    def test_is_valid_markdown_mixed_content(self, validator):
        """Testa validação de markdown com conteúdo misto"""
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
        assert validator._is_valid_markdown(content)