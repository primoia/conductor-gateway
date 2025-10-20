from typing import Dict, Any, List, Optional
from datetime import datetime
import re
import json

from ..models.persona_version import PersonaVersionCreate, PersonaVersionUpdate


class PersonaVersionValidator:
    """Validador para operações de versionamento de persona"""
    
    def __init__(self):
        self.max_content_size = 50 * 1024  # 50KB
        self.max_metadata_size = 5 * 1024  # 5KB
        self.max_change_description_length = 1000
        self.max_versions_per_agent = 1000
    
    def validate_version_creation(self, version_data: PersonaVersionCreate) -> Dict[str, Any]:
        """
        Valida dados para criação de versão de persona
        
        Args:
            version_data: Dados da versão a ser criada
            
        Returns:
            Dict com resultado da validação
        """
        errors = []
        warnings = []
        
        # Validar agent_id
        if not version_data.agent_id or not isinstance(version_data.agent_id, str):
            errors.append("agent_id é obrigatório e deve ser uma string")
        elif not self._is_valid_agent_id(version_data.agent_id):
            errors.append("agent_id deve ser um ID válido")
        
        # Validar número da versão
        if not isinstance(version_data.version, int) or version_data.version < 1:
            errors.append("version deve ser um inteiro positivo")
        elif version_data.version > self.max_versions_per_agent:
            errors.append(f"version não pode ser maior que {self.max_versions_per_agent}")
        
        # Validar timestamp
        if not isinstance(version_data.timestamp, datetime):
            errors.append("timestamp deve ser um objeto datetime")
        elif version_data.timestamp > datetime.utcnow():
            warnings.append("timestamp está no futuro")
        
        # Validar dados da persona
        if not version_data.data or not isinstance(version_data.data, dict):
            errors.append("data é obrigatório e deve ser um dicionário")
        else:
            data_validation = self._validate_persona_data(version_data.data)
            errors.extend(data_validation.get("errors", []))
            warnings.extend(data_validation.get("warnings", []))
        
        # Validar metadata
        if version_data.metadata:
            metadata_validation = self._validate_metadata(version_data.metadata)
            errors.extend(metadata_validation.get("errors", []))
            warnings.extend(metadata_validation.get("warnings", []))
        
        # Validar change_description
        if version_data.change_description:
            if not isinstance(version_data.change_description, str):
                errors.append("change_description deve ser uma string")
            elif len(version_data.change_description) > self.max_change_description_length:
                errors.append(f"change_description não pode ter mais de {self.max_change_description_length} caracteres")
        
        # Validar created_by
        if version_data.created_by:
            if not isinstance(version_data.created_by, str):
                errors.append("created_by deve ser uma string")
            elif not self._is_valid_user_id(version_data.created_by):
                warnings.append("created_by não parece ser um ID de usuário válido")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def validate_version_update(self, update_data: PersonaVersionUpdate) -> Dict[str, Any]:
        """
        Valida dados para atualização de versão de persona
        
        Args:
            update_data: Dados para atualização
            
        Returns:
            Dict com resultado da validação
        """
        errors = []
        warnings = []
        
        # Validar metadata
        if update_data.metadata is not None:
            metadata_validation = self._validate_metadata(update_data.metadata)
            errors.extend(metadata_validation.get("errors", []))
            warnings.extend(metadata_validation.get("warnings", []))
        
        # Validar change_description
        if update_data.change_description is not None:
            if not isinstance(update_data.change_description, str):
                errors.append("change_description deve ser uma string")
            elif len(update_data.change_description) > self.max_change_description_length:
                errors.append(f"change_description não pode ter mais de {self.max_change_description_length} caracteres")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def validate_version_comparison(self, version1: int, version2: int) -> Dict[str, Any]:
        """
        Valida parâmetros para comparação de versões
        
        Args:
            version1: Número da primeira versão
            version2: Número da segunda versão
            
        Returns:
            Dict com resultado da validação
        """
        errors = []
        warnings = []
        
        # Validar números de versão
        if not isinstance(version1, int) or version1 < 1:
            errors.append("version1 deve ser um inteiro positivo")
        
        if not isinstance(version2, int) or version2 < 1:
            errors.append("version2 deve ser um inteiro positivo")
        
        if version1 == version2:
            warnings.append("Comparando versão com ela mesma")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def validate_version_restore(self, version: int, create_backup: bool = True) -> Dict[str, Any]:
        """
        Valida parâmetros para restauração de versão
        
        Args:
            version: Número da versão para restaurar
            create_backup: Se deve criar backup
            
        Returns:
            Dict com resultado da validação
        """
        errors = []
        warnings = []
        
        # Validar número da versão
        if not isinstance(version, int) or version < 1:
            errors.append("version deve ser um inteiro positivo")
        
        # Validar create_backup
        if not isinstance(create_backup, bool):
            errors.append("create_backup deve ser um booleano")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def validate_cleanup_parameters(self, keep_versions: int) -> Dict[str, Any]:
        """
        Valida parâmetros para limpeza de versões antigas
        
        Args:
            keep_versions: Número de versões para manter
            
        Returns:
            Dict com resultado da validação
        """
        errors = []
        warnings = []
        
        # Validar keep_versions
        if not isinstance(keep_versions, int) or keep_versions < 1:
            errors.append("keep_versions deve ser um inteiro positivo")
        elif keep_versions > self.max_versions_per_agent:
            warnings.append(f"keep_versions é muito alto, considerando {self.max_versions_per_agent}")
        elif keep_versions < 10:
            warnings.append("keep_versions muito baixo, pode resultar em perda de dados")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def _validate_persona_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Valida dados da persona"""
        errors = []
        warnings = []
        
        # Verificar se contém content
        if "content" not in data:
            errors.append("data deve conter o campo 'content'")
        else:
            content = data["content"]
            
            # Validar tipo do content
            if not isinstance(content, str):
                errors.append("content deve ser uma string")
            else:
                # Validar tamanho do content
                content_size = len(content.encode('utf-8'))
                if content_size > self.max_content_size:
                    errors.append(f"content não pode ter mais de {self.max_content_size} bytes")
                elif content_size > self.max_content_size * 0.8:
                    warnings.append("content está próximo do limite de tamanho")
                
                # Validar se é markdown válido
                markdown_validation = self._validate_markdown_content(content)
                if not markdown_validation["valid"]:
                    warnings.extend(markdown_validation["warnings"])
        
        # Validar outros campos opcionais
        for key, value in data.items():
            if key == "content":
                continue
            
            if not isinstance(key, str):
                errors.append(f"Chave '{key}' deve ser uma string")
            elif not self._is_valid_field_name(key):
                warnings.append(f"Chave '{key}' não segue convenção de nomenclatura")
            
            if isinstance(value, str) and len(value) > 1000:
                warnings.append(f"Campo '{key}' é muito longo")
        
        return {
            "errors": errors,
            "warnings": warnings
        }
    
    def _validate_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Valida metadados da versão"""
        errors = []
        warnings = []
        
        # Validar tamanho dos metadados
        metadata_size = len(json.dumps(metadata).encode('utf-8'))
        if metadata_size > self.max_metadata_size:
            errors.append(f"metadata não pode ter mais de {self.max_metadata_size} bytes")
        elif metadata_size > self.max_metadata_size * 0.8:
            warnings.append("metadata está próximo do limite de tamanho")
        
        # Validar campos específicos
        if "tags" in metadata:
            tags = metadata["tags"]
            if not isinstance(tags, list):
                errors.append("tags deve ser uma lista")
            else:
                for i, tag in enumerate(tags):
                    if not isinstance(tag, str):
                        errors.append(f"tag[{i}] deve ser uma string")
                    elif len(tag) > 50:
                        warnings.append(f"tag[{i}] é muito longa")
        
        if "priority" in metadata:
            priority = metadata["priority"]
            if not isinstance(priority, (int, float)):
                errors.append("priority deve ser um número")
            elif priority < 0 or priority > 10:
                warnings.append("priority deve estar entre 0 e 10")
        
        return {
            "errors": errors,
            "warnings": warnings
        }
    
    def _validate_markdown_content(self, content: str) -> Dict[str, Any]:
        """Valida se o conteúdo é markdown válido"""
        warnings = []
        
        # Verificar se contém elementos markdown básicos
        markdown_patterns = [
            r'^#+\s',  # Headers
            r'\*\*.*?\*\*',  # Bold
            r'\*.*?\*',  # Italic
            r'`.*?`',  # Code
            r'\[.*?\]\(.*?\)',  # Links
            r'^\s*[-*+]\s',  # Lists
            r'^\s*\d+\.\s',  # Numbered lists
        ]
        
        has_markdown = any(re.search(pattern, content, re.MULTILINE) for pattern in markdown_patterns)
        
        if not has_markdown:
            warnings.append("Conteúdo não parece conter elementos markdown")
        
        # Verificar se há caracteres especiais problemáticos
        if '\x00' in content:
            warnings.append("Conteúdo contém caracteres nulos")
        
        if content.count('\n') > 1000:
            warnings.append("Conteúdo tem muitas quebras de linha")
        
        return {
            "valid": True,
            "warnings": warnings
        }
    
    def _is_valid_agent_id(self, agent_id: str) -> bool:
        """Valida se o agent_id é válido"""
        if not agent_id or len(agent_id) < 3:
            return False
        
        # Verificar se contém apenas caracteres válidos
        if not re.match(r'^[a-zA-Z0-9_-]+$', agent_id):
            return False
        
        return True
    
    def _is_valid_user_id(self, user_id: str) -> bool:
        """Valida se o user_id é válido"""
        if not user_id or len(user_id) < 3:
            return False
        
        # Verificar se contém apenas caracteres válidos
        if not re.match(r'^[a-zA-Z0-9_-]+$', user_id):
            return False
        
        return True
    
    def _is_valid_field_name(self, field_name: str) -> bool:
        """Valida se o nome do campo é válido"""
        if not field_name or len(field_name) < 1:
            return False
        
        # Verificar se contém apenas caracteres válidos
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', field_name):
            return False
        
        return True
    
    def validate_pagination_parameters(
        self, 
        page: int, 
        per_page: int, 
        sort_by: str, 
        sort_order: str
    ) -> Dict[str, Any]:
        """Valida parâmetros de paginação"""
        errors = []
        warnings = []
        
        # Validar page
        if not isinstance(page, int) or page < 1:
            errors.append("page deve ser um inteiro positivo")
        elif page > 1000:
            warnings.append("page muito alto, pode impactar performance")
        
        # Validar per_page
        if not isinstance(per_page, int) or per_page < 1:
            errors.append("per_page deve ser um inteiro positivo")
        elif per_page > 100:
            errors.append("per_page não pode ser maior que 100")
        elif per_page > 50:
            warnings.append("per_page alto pode impactar performance")
        
        # Validar sort_by
        valid_sort_fields = ["version", "timestamp", "created_at", "updated_at"]
        if sort_by not in valid_sort_fields:
            errors.append(f"sort_by deve ser um dos seguintes: {', '.join(valid_sort_fields)}")
        
        # Validar sort_order
        if sort_order not in ["asc", "desc"]:
            errors.append("sort_order deve ser 'asc' ou 'desc'")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }


# Instância global do validador
persona_version_validator = PersonaVersionValidator()