"""
Modelos Pydantic para Persona
SAGA-008 - Fase 1: Core APIs
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, validator
import re


class PersonaBase(BaseModel):
    """Modelo base para Persona"""
    content: str = Field(..., description="Conteúdo da persona em Markdown")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadados adicionais")


class PersonaCreate(PersonaBase):
    """Modelo para criação de Persona"""
    
    @validator('content')
    def validate_content(cls, v):
        if not v or not v.strip():
            raise ValueError("Conteúdo da persona não pode estar vazio")
        
        if len(v) > 50000:  # 50KB limite
            raise ValueError("Conteúdo da persona excede o limite de 50KB")
        
        # Validação básica de markdown
        if not _is_valid_markdown(v):
            raise ValueError("Conteúdo deve ser um Markdown válido")
        
        return v.strip()
    
    @validator('metadata')
    def validate_metadata(cls, v):
        if v is None:
            return {}
        
        # Validar que metadata é um dicionário
        if not isinstance(v, dict):
            raise ValueError("Metadata deve ser um dicionário")
        
        # Validar tamanho do metadata
        import json
        metadata_str = json.dumps(v)
        if len(metadata_str) > 5000:  # 5KB limite para metadata
            raise ValueError("Metadata excede o limite de 5KB")
        
        return v


class PersonaUpdate(PersonaBase):
    """Modelo para atualização de Persona"""
    
    @validator('content')
    def validate_content(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError("Conteúdo da persona não pode estar vazio")
            
            if len(v) > 50000:  # 50KB limite
                raise ValueError("Conteúdo da persona excede o limite de 50KB")
            
            # Validação básica de markdown
            if not _is_valid_markdown(v):
                raise ValueError("Conteúdo deve ser um Markdown válido")
        
        return v.strip() if v else v
    
    @validator('metadata')
    def validate_metadata(cls, v):
        if v is not None:
            # Validar que metadata é um dicionário
            if not isinstance(v, dict):
                raise ValueError("Metadata deve ser um dicionário")
            
            # Validar tamanho do metadata
            import json
            metadata_str = json.dumps(v)
            if len(metadata_str) > 5000:  # 5KB limite para metadata
                raise ValueError("Metadata excede o limite de 5KB")
        
        return v


class PersonaResponse(PersonaBase):
    """Modelo de resposta para Persona"""
    id: str = Field(..., description="ID único da persona")
    agent_id: str = Field(..., description="ID do agente proprietário")
    created_at: datetime = Field(..., description="Data de criação")
    updated_at: datetime = Field(..., description="Data da última atualização")
    version: int = Field(..., description="Versão atual da persona")
    
    class Config:
        from_attributes = True


class PersonaListResponse(BaseModel):
    """Modelo de resposta para listagem de Personas"""
    personas: list[PersonaResponse] = Field(..., description="Lista de personas")
    total: int = Field(..., description="Total de personas")
    page: int = Field(..., description="Página atual")
    per_page: int = Field(..., description="Itens por página")
    has_next: bool = Field(..., description="Tem próxima página")
    has_prev: bool = Field(..., description="Tem página anterior")


def _is_valid_markdown(content: str) -> bool:
    """
    Validação básica de Markdown
    Verifica se o conteúdo contém elementos básicos de markdown
    """
    if not content:
        return False
    
    # Verificar se contém pelo menos um caractere válido
    if not content.strip():
        return False
    
    # Verificar se não contém caracteres de controle inválidos
    invalid_chars = ['\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07', 
                     '\x08', '\x0b', '\x0c', '\x0e', '\x0f', '\x10', '\x11', '\x12', 
                     '\x13', '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a', 
                     '\x1b', '\x1c', '\x1d', '\x1e', '\x1f']
    
    for char in invalid_chars:
        if char in content:
            return False
    
    # Verificar se contém pelo menos um elemento de markdown válido
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
    
    # Se não contém nenhum padrão de markdown, ainda é válido se for texto simples
    for pattern in markdown_patterns:
        if re.search(pattern, content, re.MULTILINE | re.DOTALL):
            return True
    
    # Texto simples também é válido
    return True