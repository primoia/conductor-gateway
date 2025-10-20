"""
Validador de Persona
SAGA-008 - Fase 1: Core APIs
"""

from typing import Optional, Dict, Any
from pymongo.errors import PyMongoError
import re
import json


class PersonaValidator:
    """Validador para operações de Persona"""
    
    def __init__(self, db):
        self.db = db
        self.agents_collection = db.agents
        self.personas_collection = db.personas
    
    async def validate_agent_exists(self, agent_id: str) -> bool:
        """
        Valida se o agente existe no banco de dados
        
        Args:
            agent_id: ID do agente
            
        Returns:
            bool: True se o agente existe, False caso contrário
            
        Raises:
            ValueError: Se o agent_id não é válido
        """
        if not agent_id:
            raise ValueError("ID do agente é obrigatório")
        
        if not isinstance(agent_id, str):
            raise ValueError("ID do agente deve ser uma string")
        
        # Validar formato do ID (string não vazia)
        if not agent_id.strip():
            raise ValueError("ID do agente não pode estar vazio")
        
        try:
            # Verificar se o agente existe
            agent = await self.agents_collection.find_one(
                {"agent_id": agent_id},
                {"_id": 1}
            )
            return agent is not None
        except PyMongoError as e:
            raise ValueError(f"Erro ao verificar agente: {str(e)}")
    
    async def validate_persona_content(self, content: str) -> Dict[str, Any]:
        """
        Valida o conteúdo da persona
        
        Args:
            content: Conteúdo da persona em Markdown
            
        Returns:
            Dict com informações de validação
            
        Raises:
            ValueError: Se o conteúdo não é válido
        """
        if not content:
            raise ValueError("Conteúdo da persona é obrigatório")
        
        if not isinstance(content, str):
            raise ValueError("Conteúdo da persona deve ser uma string")
        
        # Validar tamanho
        if len(content) > 50000:  # 50KB
            raise ValueError("Conteúdo da persona excede o limite de 50KB")
        
        # Validar se não está vazio após strip
        content_stripped = content.strip()
        if not content_stripped:
            raise ValueError("Conteúdo da persona não pode estar vazio")
        
        # Validar caracteres válidos
        if not self._is_valid_content(content_stripped):
            raise ValueError("Conteúdo contém caracteres inválidos")
        
        # Validar estrutura básica de markdown
        if not self._is_valid_markdown(content_stripped):
            raise ValueError("Conteúdo deve ser um Markdown válido")
        
        # Calcular estatísticas
        stats = self._calculate_content_stats(content_stripped)
        
        return {
            "is_valid": True,
            "content_length": len(content_stripped),
            "stats": stats
        }
    
    async def validate_persona_metadata(self, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Valida os metadados da persona
        
        Args:
            metadata: Metadados da persona
            
        Returns:
            Dict com metadados validados
            
        Raises:
            ValueError: Se os metadados não são válidos
        """
        if metadata is None:
            return {}
        
        if not isinstance(metadata, dict):
            raise ValueError("Metadata deve ser um dicionário")
        
        # Validar tamanho dos metadados
        try:
            metadata_str = json.dumps(metadata, ensure_ascii=False)
            if len(metadata_str) > 5000:  # 5KB
                raise ValueError("Metadata excede o limite de 5KB")
        except (TypeError, ValueError) as e:
            raise ValueError(f"Metadata contém dados não serializáveis: {str(e)}")
        
        # Validar chaves dos metadados
        for key, value in metadata.items():
            if not isinstance(key, str):
                raise ValueError("Chaves do metadata devem ser strings")
            
            if not key.strip():
                raise ValueError("Chaves do metadata não podem estar vazias")
            
            # Validar valor (deve ser serializável)
            try:
                json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                raise ValueError(f"Valor do metadata '{key}' não é serializável")
        
        return metadata
    
    async def validate_persona_update(self, agent_id: str, persona_id: str) -> bool:
        """
        Valida se a persona pode ser atualizada
        
        Args:
            agent_id: ID do agente
            persona_id: ID da persona
            
        Returns:
            bool: True se pode ser atualizada
            
        Raises:
            ValueError: Se não pode ser atualizada
        """
        # Validar agent_id
        if not await self.validate_agent_exists(agent_id):
            raise ValueError("Agente não encontrado")
        
        # Validar persona_id
        if not persona_id:
            raise ValueError("ID da persona é obrigatório")
        
        if not isinstance(persona_id, str) or not persona_id.strip():
            raise ValueError("ID da persona deve ser uma string válida")
        
        try:
            # Verificar se a persona existe e pertence ao agente
            persona = await self.personas_collection.find_one({
                "_id": persona_id,
                "agent_id": agent_id
            })
            
            if not persona:
                raise ValueError("Persona não encontrada ou não pertence ao agente")
            
            return True
        except PyMongoError as e:
            raise ValueError(f"Erro ao verificar persona: {str(e)}")
    
    def _is_valid_content(self, content: str) -> bool:
        """
        Verifica se o conteúdo contém apenas caracteres válidos
        
        Args:
            content: Conteúdo a ser validado
            
        Returns:
            bool: True se válido
        """
        # Verificar caracteres de controle inválidos
        invalid_chars = [
            '\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',
            '\x08', '\x0b', '\x0c', '\x0e', '\x0f', '\x10', '\x11', '\x12',
            '\x13', '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a',
            '\x1b', '\x1c', '\x1d', '\x1e', '\x1f'
        ]
        
        for char in invalid_chars:
            if char in content:
                return False
        
        return True
    
    def _is_valid_markdown(self, content: str) -> bool:
        """
        Validação básica de Markdown
        
        Args:
            content: Conteúdo em Markdown
            
        Returns:
            bool: True se é Markdown válido
        """
        if not content:
            return False
        
        # Padrões básicos de Markdown
        markdown_patterns = [
            r'^#+\s+',  # Headers
            r'\*\*.*?\*\*',  # Bold
            r'\*.*?\*',  # Italic
            r'`.*?`',  # Code
            r'```.*?```',  # Code blocks
            r'^\s*[-*+]\s+',  # Lists
            r'^\s*\d+\.\s+',  # Numbered lists
            r'\[.*?\]\(.*?\)',  # Links
            r'!\[.*?\]\(.*?\)',  # Images
            r'^\s*>\s+',  # Blockquotes
            r'^\s*---\s*$',  # Horizontal rules
        ]
        
        # Verificar se contém pelo menos um padrão de markdown
        for pattern in markdown_patterns:
            if re.search(pattern, content, re.MULTILINE | re.DOTALL):
                return True
        
        # Texto simples também é válido
        return True
    
    def _calculate_content_stats(self, content: str) -> Dict[str, Any]:
        """
        Calcula estatísticas do conteúdo
        
        Args:
            content: Conteúdo da persona
            
        Returns:
            Dict com estatísticas
        """
        lines = content.split('\n')
        words = content.split()
        
        # Contar elementos de markdown
        headers = len(re.findall(r'^#+\s+', content, re.MULTILINE))
        bold = len(re.findall(r'\*\*.*?\*\*', content))
        italic = len(re.findall(r'\*.*?\*', content))
        code_blocks = len(re.findall(r'```.*?```', content, re.DOTALL))
        links = len(re.findall(r'\[.*?\]\(.*?\)', content))
        images = len(re.findall(r'!\[.*?\]\(.*?\)', content))
        lists = len(re.findall(r'^\s*[-*+]\s+', content, re.MULTILINE))
        
        return {
            "lines": len(lines),
            "words": len(words),
            "characters": len(content),
            "markdown_elements": {
                "headers": headers,
                "bold": bold,
                "italic": italic,
                "code_blocks": code_blocks,
                "links": links,
                "images": images,
                "lists": lists
            }
        }