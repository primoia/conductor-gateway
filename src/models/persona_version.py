from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from bson import ObjectId


class PersonaVersionBase(BaseModel):
    """Modelo base para versões de persona"""
    version: int = Field(..., description="Número da versão")
    timestamp: datetime = Field(..., description="Data e hora da criação da versão")
    data: Dict[str, Any] = Field(..., description="Dados da persona na versão")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadados adicionais da versão")
    created_by: Optional[str] = Field(None, description="Usuário que criou a versão")
    change_description: Optional[str] = Field(None, description="Descrição das mudanças")


class PersonaVersionCreate(PersonaVersionBase):
    """Modelo para criação de versão de persona"""
    agent_id: str = Field(..., description="ID do agente")
    
    @validator('agent_id')
    def validate_agent_id(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError('agent_id deve ser uma string válida')
        return v
    
    @validator('data')
    def validate_data(cls, v):
        if not v or not isinstance(v, dict):
            raise ValueError('data deve ser um dicionário válido')
        if 'content' not in v:
            raise ValueError('data deve conter o campo content')
        return v


class PersonaVersionUpdate(BaseModel):
    """Modelo para atualização de versão de persona"""
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadados adicionais da versão")
    change_description: Optional[str] = Field(None, description="Descrição das mudanças")


class PersonaVersionResponse(PersonaVersionBase):
    """Modelo de resposta para versão de persona"""
    id: str = Field(..., description="ID da versão")
    agent_id: str = Field(..., description="ID do agente")
    
    class Config:
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }


class PersonaVersionListResponse(BaseModel):
    """Modelo de resposta para lista de versões"""
    versions: List[PersonaVersionResponse] = Field(..., description="Lista de versões")
    total: int = Field(..., description="Total de versões")
    page: int = Field(..., description="Página atual")
    per_page: int = Field(..., description="Itens por página")
    total_pages: int = Field(..., description="Total de páginas")


class PersonaVersionCompareRequest(BaseModel):
    """Modelo para comparação de versões"""
    version1: int = Field(..., description="Número da primeira versão")
    version2: int = Field(..., description="Número da segunda versão")
    
    @validator('version1', 'version2')
    def validate_version_numbers(cls, v):
        if not isinstance(v, int) or v < 1:
            raise ValueError('Número da versão deve ser um inteiro positivo')
        return v


class PersonaVersionCompareResponse(BaseModel):
    """Modelo de resposta para comparação de versões"""
    version1: PersonaVersionResponse = Field(..., description="Primeira versão")
    version2: PersonaVersionResponse = Field(..., description="Segunda versão")
    differences: List[Dict[str, Any]] = Field(..., description="Lista de diferenças encontradas")
    summary: Dict[str, Any] = Field(..., description="Resumo da comparação")


class PersonaVersionRestoreRequest(BaseModel):
    """Modelo para restauração de versão"""
    version: int = Field(..., description="Número da versão para restaurar")
    create_backup: bool = Field(True, description="Criar backup da versão atual antes de restaurar")
    
    @validator('version')
    def validate_version_number(cls, v):
        if not isinstance(v, int) or v < 1:
            raise ValueError('Número da versão deve ser um inteiro positivo')
        return v


class PersonaVersionRestoreResponse(BaseModel):
    """Modelo de resposta para restauração de versão"""
    success: bool = Field(..., description="Indica se a restauração foi bem-sucedida")
    message: str = Field(..., description="Mensagem de resultado")
    restored_version: PersonaVersionResponse = Field(..., description="Versão restaurada")
    backup_created: Optional[PersonaVersionResponse] = Field(None, description="Backup criado (se aplicável)")


class PersonaVersionStatsResponse(BaseModel):
    """Modelo de resposta para estatísticas de versionamento"""
    agent_id: str = Field(..., description="ID do agente")
    total_versions: int = Field(..., description="Total de versões")
    latest_version: int = Field(..., description="Última versão")
    first_version_date: datetime = Field(..., description="Data da primeira versão")
    last_version_date: datetime = Field(..., description="Data da última versão")
    average_versions_per_day: float = Field(..., description="Média de versões por dia")
    storage_size_bytes: int = Field(..., description="Tamanho total em bytes")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }