# SAGA-008 - Fase 2: Versionamento
## 🎯 Objetivo da Fase
Implementar sistema de versionamento de persona com histórico de alterações e limpeza automática de versões antigas.

## 📋 Tarefas da Fase

### 2.1 Estrutura de Versionamento
- [ ] Criar collection `persona_history` no MongoDB
- [ ] Implementar `PersonaVersionManager` em `src/services/persona_version_manager.py`
- [ ] Criar modelo `PersonaVersion` em `src/models/persona.py`
- [ ] Implementar versionamento automático no `PersonaService`

### 2.2 Endpoint de Histórico
- [ ] Implementar endpoint `GET /api/agents/{agent_id}/persona/history`
- [ ] Adicionar parâmetros de paginação (`limit`, `offset`)
- [ ] Implementar filtros por data e versão
- [ ] Criar modelo `PersonaHistoryResponse`

### 2.3 Gerenciamento de Versões
- [ ] Implementar `create_version(agent_id, persona_content, reason)` - Criar nova versão
- [ ] Implementar `get_versions(agent_id, limit, offset)` - Buscar versões
- [ ] Implementar `get_version(agent_id, version)` - Buscar versão específica
- [ ] Implementar `cleanup_old_versions(agent_id, max_versions=100)` - Limpeza automática

### 2.4 Índices e Performance
- [ ] Criar índices no MongoDB para `persona_history`:
  - [ ] Índice composto: `{agent_id: 1, created_at: -1}`
  - [ ] Índice para limpeza: `{created_at: 1}`
- [ ] Implementar cache para versões recentes
- [ ] Otimizar consultas de histórico

### 2.5 Testes de Versionamento
- [ ] Criar `tests/test_persona_version_manager.py`
- [ ] Criar `tests/test_persona_history_endpoint.py`
- [ ] Testar cenários de limpeza automática
- [ ] Testar performance com muitas versões

## 🔧 Implementação Detalhada

### Estrutura da Collection persona_history
```json
{
  "_id": "ObjectId",
  "agent_id": "agent_123",
  "version": "1.2.3",
  "persona_content": "markdown content",
  "reason": "optional reason",
  "created_at": "2025-01-19T10:30:00Z",
  "created_by": "user_id",
  "size_bytes": 1024
}
```

### Endpoint GET /api/agents/{agent_id}/persona/history
```python
@router.get("/{agent_id}/persona/history")
async def get_persona_history(
    agent_id: str,
    limit: int = 50,
    offset: int = 0,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None
):
    # 1. Validar agente existe
    # 2. Buscar versões com filtros
    # 3. Retornar resposta paginada
```

### Sistema de Versionamento
- **Versioning**: Usar timestamp + contador (ex: 1.2.3)
- **Limpeza**: Manter máximo 100 versões por agente
- **Backup**: Versão atual sempre mantida
- **Auditoria**: Log de todas as alterações

## ⚠️ Riscos e Mitigações

### Riscos Identificados
- **Performance**: Histórico pode crescer muito rapidamente
- **Storage**: Consumo excessivo de espaço em disco
- **Concorrência**: Múltiplas edições simultâneas
- **Integridade**: Perda de versões durante limpeza

### Mitigações
- Implementar limpeza automática agressiva
- Usar transações MongoDB para atomicidade
- Implementar backup antes de limpeza
- Monitorar crescimento do histórico

## ✅ Critérios de Sucesso

### Funcionais
- [ ] Histórico de versões funcionando corretamente
- [ ] Paginação implementada e testada
- [ ] Limpeza automática funcionando
- [ ] Filtros por data funcionando

### Técnicos
- [ ] Resposta < 200ms para consultas de histórico
- [ ] Cobertura de testes > 85%
- [ ] Índices otimizados implementados
- [ ] Logs de auditoria completos

### Performance
- [ ] Máximo 100 versões por agente
- [ ] Limpeza automática diária
- [ ] Consultas otimizadas com índices

## 📊 Estimativas

- **Tempo Total**: 12 horas
- **Complexidade**: Alta
- **Dependências**: Fase 1 (Core APIs) concluída

## 🔄 Próxima Fase
Após conclusão desta fase, prosseguir para **Fase 3: Backup/Restore** que implementará sistema de backup manual e restore de versões.

---
**Status**: 📝 Planejado  
**Data**: 2025-01-19  
**Responsável**: Desenvolvedor Backend  
**Duração Estimada**: 12 horas