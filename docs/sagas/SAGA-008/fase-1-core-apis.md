# SAGA-008 - Fase 1: Core APIs
## 🎯 Objetivo da Fase
Implementar os endpoints básicos para edição de persona, incluindo validação e modelos Pydantic fundamentais.

## 📋 Tarefas da Fase

### 1.1 Estrutura Base dos Endpoints
- [ ] Criar router `src/api/routers/persona.py`
- [ ] Implementar endpoint `PUT /api/agents/{agent_id}/persona`
- [ ] Implementar endpoint `GET /api/agents/{agent_id}/persona` (já existe, verificar)
- [ ] Adicionar router ao app principal em `src/api/app.py`

### 1.2 Modelos Pydantic
- [ ] Criar `src/models/persona.py` com:
  - [ ] `PersonaUpdateRequest` - Request para atualizar persona
  - [ ] `PersonaUpdateResponse` - Response da atualização
  - [ ] `PersonaGetResponse` - Response para buscar persona
  - [ ] `PersonaErrorResponse` - Response de erro

### 1.3 Validação Básica
- [ ] Criar `src/services/persona_validator.py` com:
  - [ ] Validação de tamanho máximo (50KB)
  - [ ] Validação de string não vazia
  - [ ] Validação de markdown básico (opcional)
  - [ ] Validação de agente existente

### 1.4 Serviço de Persona
- [ ] Criar `src/services/persona_service.py` com:
  - [ ] `update_persona(agent_id, persona_content)` - Atualizar persona
  - [ ] `get_persona(agent_id)` - Buscar persona atual
  - [ ] `validate_agent_exists(agent_id)` - Validar agente
  - [ ] Integração com MongoDB

### 1.5 Testes Unitários
- [ ] Criar `tests/test_persona_validator.py`
- [ ] Criar `tests/test_persona_service.py`
- [ ] Criar `tests/test_persona_endpoints.py`
- [ ] Implementar testes para cenários de sucesso e erro

## 🔧 Implementação Detalhada

### Endpoint PUT /api/agents/{agent_id}/persona
```python
@router.put("/{agent_id}/persona")
async def update_persona(
    agent_id: str,
    request: PersonaUpdateRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    # 1. Validar agente existe
    # 2. Validar persona content
    # 3. Atualizar no MongoDB
    # 4. Retornar resposta
```

### Validações Implementadas
- **Tamanho**: Máximo 50KB
- **Conteúdo**: String não vazia
- **Agente**: Deve existir na collection `agents`
- **Formato**: Markdown válido (opcional)

### Estrutura de Resposta
```json
{
  "success": true,
  "persona": "conteúdo da persona",
  "updated_at": "2025-01-19T10:30:00Z",
  "agent_id": "agent_123"
}
```

## ⚠️ Riscos e Mitigações

### Riscos Identificados
- **Performance**: Validação de markdown pode ser lenta
- **Concorrência**: Múltiplas edições simultâneas
- **Validação**: Persona malformada pode quebrar frontend

### Mitigações
- Usar validação assíncrona para markdown
- Implementar validação de agente antes de processar
- Validação rigorosa de entrada

## ✅ Critérios de Sucesso

### Funcionais
- [ ] Endpoint PUT funcionando corretamente
- [ ] Validação impedindo dados inválidos
- [ ] Resposta < 200ms para operações normais
- [ ] Tratamento de erros robusto

### Técnicos
- [ ] Cobertura de testes > 80%
- [ ] Código seguindo padrões do projeto
- [ ] Logs estruturados implementados
- [ ] Documentação da API atualizada

## 📊 Estimativas

- **Tempo Total**: 8 horas
- **Complexidade**: Média
- **Dependências**: Nenhuma (fase inicial)

## 🔄 Próxima Fase
Após conclusão desta fase, prosseguir para **Fase 2: Versionamento** que implementará histórico de versões e limpeza automática.

---
**Status**: 📝 Planejado  
**Data**: 2025-01-19  
**Responsável**: Desenvolvedor Backend  
**Duração Estimada**: 8 horas