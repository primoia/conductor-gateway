# 🔧 Plano Backend: Gerenciamento de Roteiros - Persistência de Caminho

## 🎯 Objetivo
Implementar suporte ao campo `filePath` no backend Conductor para persistir e gerenciar caminhos completos de arquivos markdown de roteiros.

## 📋 Contexto
O sistema atual de persistência de roteiros não inclui o caminho completo do arquivo em disco. É necessário:

1. **Modelo de Dados**: Adicionar campo `filePath` ao modelo de roteiro
2. **Persistência**: Atualizar repositórios para salvar/carregar `filePath`
3. **API**: Modificar endpoints para incluir `filePath` nas operações CRUD
4. **Validação**: Implementar validação de segurança para caminhos de arquivo

## 🔍 Análise da Arquitetura Atual

### Estrutura de Persistência Identificada:
- `FileSystemStateRepository` - Persistência em sistema de arquivos
- `MongoStateRepository` - Persistência em MongoDB
- `AgentStorageService` - Serviço de gerenciamento de artefatos
- `Screenplay` - Modelo de dados de roteiros

### Repositórios de Estado:
- `src/infrastructure/storage/filesystem_repository.py`
- `src/infrastructure/storage/mongo_repository.py`
- `src/ports/state_repository.py`

## 📝 Checklist de Implementação

### Fase 1: Modelo de Dados
- [ ] **1.1** Adicionar campo `file_path: Optional[str]` ao modelo `Screenplay`
- [ ] **1.2** Atualizar interface `IScreenplay` para incluir `file_path`
- [ ] **1.3** Modificar serialização JSON/YAML para incluir `file_path`
- [ ] **1.4** Atualizar validação de dados para `file_path`

### Fase 2: Persistência Filesystem
- [ ] **2.1** Modificar `FileSystemStateRepository.save_screenplay()` para incluir `file_path`
- [ ] **2.2** Atualizar `FileSystemStateRepository.load_screenplay()` para carregar `file_path`
- [ ] **2.3** Implementar validação de caminho de arquivo seguro
- [ ] **2.4** Adicionar método `validate_file_path()` para segurança

### Fase 3: Persistência MongoDB
- [ ] **3.1** Modificar `MongoStateRepository.save_screenplay()` para incluir `file_path`
- [ ] **3.2** Atualizar `MongoStateRepository.load_screenplay()` para carregar `file_path`
- [ ] **3.3** Criar índice MongoDB para consultas por `file_path`
- [ ] **3.4** Implementar migração de dados existentes

### Fase 4: API e Serviços
- [ ] **4.1** Atualizar `AgentStorageService` para gerenciar `file_path`
- [ ] **4.2** Modificar endpoints de roteiros para incluir `file_path`
- [ ] **4.3** Implementar validação de `file_path` nas APIs
- [ ] **4.4** Adicionar logs de auditoria para operações de arquivo

### Fase 5: Segurança e Validação
- [ ] **5.1** Implementar validação contra path traversal attacks
- [ ] **5.2** Adicionar sanitização de caminhos de arquivo
- [ ] **5.3** Implementar verificação de permissões de arquivo
- [ ] **5.4** Adicionar rate limiting para operações de arquivo

### Fase 6: Migração e Compatibilidade
- [ ] **6.1** Criar script de migração para roteiros existentes
- [ ] **6.2** Implementar fallback para roteiros sem `file_path`
- [ ] **6.3** Adicionar testes de compatibilidade com versões anteriores
- [ ] **6.4** Documentar mudanças na API

## 🔧 Especificações Técnicas

### Modelo de Dados Atualizado:
```python
@dataclass
class Screenplay:
    id: str
    name: str
    content: str
    version: int
    created_at: datetime
    updated_at: datetime
    file_path: Optional[str] = None  # NOVO CAMPO
```

### Validação de Caminho:
```python
def validate_file_path(file_path: str) -> bool:
    """Valida se o caminho do arquivo é seguro."""
    # Verificar path traversal
    if '..' in file_path or file_path.startswith('/'):
        return False
    # Verificar extensão permitida
    if not file_path.endswith(('.md', '.txt')):
        return False
    return True
```

### Endpoint Atualizado:
```python
@router.post("/screenplays")
async def create_screenplay(screenplay: ScreenplayCreate):
    # Incluir validação de file_path
    if screenplay.file_path and not validate_file_path(screenplay.file_path):
        raise HTTPException(400, "Invalid file path")
    # ... resto da implementação
```

## 🎨 Arquivos a Modificar

### Principais:
- `src/ports/state_repository.py` - Interface de repositório
- `src/infrastructure/storage/filesystem_repository.py` - Implementação filesystem
- `src/infrastructure/storage/mongo_repository.py` - Implementação MongoDB
- `src/core/services/agent_storage_service.py` - Serviço de gerenciamento

### Secundários:
- Modelos de dados de roteiros
- Endpoints de API
- Scripts de migração
- Testes unitários e de integração

## ⚠️ Considerações de Segurança

1. **Path Traversal**: Validar caminhos para evitar `../` e caminhos absolutos
2. **Extensões**: Permitir apenas `.md` e `.txt`
3. **Permissões**: Verificar permissões de leitura/escrita
4. **Sanitização**: Limpar caracteres perigosos nos caminhos
5. **Auditoria**: Logar todas as operações de arquivo

## 🔄 Estratégia de Migração

### Fase 1: Adição do Campo
- Adicionar `file_path` como campo opcional
- Manter compatibilidade com roteiros existentes
- Implementar validação básica

### Fase 2: Migração de Dados
- Criar script para popular `file_path` de roteiros existentes
- Implementar fallback para roteiros sem `file_path`
- Testar migração em ambiente de desenvolvimento

### Fase 3: Validação e Segurança
- Implementar validações de segurança
- Adicionar logs de auditoria
- Testes de penetração para path traversal

## 🎯 Critérios de Sucesso

- [ ] Campo `file_path` é persistido corretamente em ambos os repositórios
- [ ] APIs retornam `file_path` nas operações CRUD
- [ ] Validação de segurança impede ataques de path traversal
- [ ] Migração funciona sem perda de dados
- [ ] Compatibilidade com versões anteriores é mantida
- [ ] Performance não é impactada significativamente

## 📊 Estimativa de Esforço
- **Tempo estimado**: 6-8 horas
- **Complexidade**: Alta (mudanças em múltiplas camadas)
- **Dependências**: Frontend precisa ser atualizado após conclusão

## 🔗 Dependências
- Frontend deve aguardar conclusão deste plano
- Testes de integração devem validar fluxo completo
- Documentação da API deve ser atualizada