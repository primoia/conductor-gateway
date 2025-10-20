# SAGA-008: API de Edição de Persona no Conductor Gateway

## 📋 Context & Background

O conductor-gateway atualmente serve como BFF (Backend for Frontend) para o sistema Conductor, fornecendo APIs para gerenciamento de agentes, instâncias e execução de tarefas. A funcionalidade de edição de persona foi implementada no frontend (conductor-web), mas o backend precisa de endpoints específicos para suportar essa funcionalidade de forma robusta e segura.

**Situação Atual:**
- O gateway já possui endpoint `/api/agents/context/{instance_id}` que retorna persona
- A persona é armazenada no MongoDB na collection `agents` como `persona.content`
- Não existe endpoint para atualizar a persona de um agente
- O frontend precisa de APIs para persistir alterações de persona

**Problema:**
- Falta de endpoints para edição de persona no BFF
- Ausência de validação e versionamento de persona
- Sem controle de permissões para edição de persona
- Falta de histórico de alterações de persona

## 🎯 Objectives

**Objetivo Principal:**
Implementar APIs completas para edição de persona no conductor-gateway, permitindo que o frontend persista alterações de forma segura e controlada.

**Objetivos Específicos:**
1. Criar endpoint para atualizar persona de agente
2. Implementar validação de persona (formato, tamanho, conteúdo)
3. Adicionar versionamento de persona com histórico
4. Criar endpoint para recuperar histórico de alterações
5. Implementar controle de permissões básico
6. Adicionar endpoint para backup/restore de persona

## 🔍 Scope

**In Scope:**
- Endpoint `PUT /api/agents/{agent_id}/persona` para atualizar persona
- Endpoint `GET /api/agents/{agent_id}/persona/history` para histórico
- Endpoint `POST /api/agents/{agent_id}/persona/backup` para backup
- Endpoint `POST /api/agents/{agent_id}/persona/restore` para restore
- Validação de persona (markdown válido, tamanho máximo)
- Versionamento automático com timestamps
- Logging de alterações para auditoria
- Middleware de validação de persona
- Modelos Pydantic para request/response

**Out of Scope:**
- Interface de usuário (já implementada no frontend)
- Autenticação/autorização avançada (usar sistema existente)
- Sincronização em tempo real (WebSocket)
- Backup automático em cloud
- Validação de conteúdo semântico da persona

## 💡 Proposed Solution

**Arquitetura:**
```
Frontend (conductor-web) 
    ↓ HTTP API
Conductor Gateway (BFF)
    ↓ MongoDB Operations
MongoDB Collections:
    - agents (persona atual)
    - persona_history (histórico de versões)
    - persona_backups (backups manuais)
```

**Endpoints Propostos:**

1. **Atualizar Persona:**
   ```
   PUT /api/agents/{agent_id}/persona
   Body: { "persona": "markdown content", "reason": "optional reason" }
   Response: { "success": true, "version": "1.2.3", "updated_at": "ISO8601" }
   ```

2. **Histórico de Persona:**
   ```
   GET /api/agents/{agent_id}/persona/history?limit=50&offset=0
   Response: { "versions": [...], "total": 100 }
   ```

3. **Backup de Persona:**
   ```
   POST /api/agents/{agent_id}/persona/backup
   Body: { "name": "backup name", "description": "optional" }
   Response: { "backup_id": "uuid", "created_at": "ISO8601" }
   ```

4. **Restore de Persona:**
   ```
   POST /api/agents/{agent_id}/persona/restore
   Body: { "backup_id": "uuid" }
   Response: { "success": true, "restored_to": "version" }
   ```

**Validações:**
- Persona deve ser string não vazia
- Tamanho máximo: 50KB
- Deve conter markdown válido (opcional)
- Verificar se agente existe antes de atualizar

## 📦 Deliverables

1. **Novos Endpoints:**
   - `PUT /api/agents/{agent_id}/persona` - Atualizar persona
   - `GET /api/agents/{agent_id}/persona/history` - Histórico de versões
   - `POST /api/agents/{agent_id}/persona/backup` - Criar backup
   - `POST /api/agents/{agent_id}/persona/restore` - Restaurar backup

2. **Modelos Pydantic:**
   - `PersonaUpdateRequest` - Request para atualizar persona
   - `PersonaUpdateResponse` - Response da atualização
   - `PersonaHistoryResponse` - Response do histórico
   - `PersonaBackupRequest` - Request para backup
   - `PersonaBackupResponse` - Response do backup

3. **Serviços:**
   - `PersonaService` - Lógica de negócio para persona
   - `PersonaValidator` - Validação de persona
   - `PersonaVersionManager` - Gerenciamento de versões

4. **Estrutura MongoDB:**
   - Collection `persona_history` para versionamento
   - Collection `persona_backups` para backups manuais
   - Índices para performance

5. **Testes:**
   - Testes unitários para serviços
   - Testes de integração para endpoints
   - Testes de validação de persona

## ⚠️ Risks & Constraints

**Riscos Técnicos:**
- **Performance:** Histórico pode crescer muito - implementar limpeza automática
- **Concorrência:** Múltiplas edições simultâneas - usar versioning otimista
- **Validação:** Persona malformada pode quebrar frontend - validação rigorosa

**Riscos de Negócio:**
- **Perda de Dados:** Edições acidentais - implementar backup automático
- **Auditoria:** Falta de rastreabilidade - logging detalhado
- **Segurança:** Edição não autorizada - validação de permissões

**Constraints:**
- **Compatibilidade:** Manter compatibilidade com frontend existente
- **Performance:** Resposta < 200ms para operações de persona
- **Storage:** Limitar crescimento do histórico (máximo 100 versões por agente)

## 🗓️ Phasing Considerations

**Fase 1: Core APIs (Sprint 1)**
- Implementar endpoint de atualização de persona
- Criar modelos Pydantic básicos
- Implementar validação simples
- Testes unitários básicos

**Fase 2: Versionamento (Sprint 2)**
- Implementar histórico de versões
- Criar endpoint de histórico
- Implementar limpeza automática de versões antigas
- Testes de integração

**Fase 3: Backup/Restore (Sprint 3)**
- Implementar sistema de backup
- Criar endpoints de backup/restore
- Implementar validação de backup
- Testes end-to-end

**Fase 4: Melhorias (Sprint 4)**
- Otimizações de performance
- Logging avançado
- Monitoramento de uso
- Documentação da API

## ✅ Success Criteria

**Critérios Técnicos:**
- ✅ Todos os endpoints funcionando com < 200ms de resposta
- ✅ Validação de persona impedindo dados malformados
- ✅ Histórico de versões funcionando corretamente
- ✅ Backup/restore funcionando sem perda de dados
- ✅ Cobertura de testes > 90%

**Critérios de Negócio:**
- ✅ Frontend pode editar persona sem erros
- ✅ Histórico de alterações visível para usuários
- ✅ Backup de persona funcionando
- ✅ Logs de auditoria completos
- ✅ Zero perda de dados durante edições

**Critérios de Qualidade:**
- ✅ Código seguindo padrões do projeto
- ✅ Documentação da API atualizada
- ✅ Logs estruturados para monitoramento
- ✅ Tratamento de erros robusto

## 🔗 Dependencies

**Dependências Internas:**
- MongoDB connection (já existente)
- FastAPI framework (já existente)
- Pydantic models (já existente)
- Logging system (já existente)

**Dependências Externas:**
- Nenhuma dependência externa adicional necessária

**Dependências de Frontend:**
- Frontend deve implementar chamadas para novos endpoints
- Frontend deve tratar novos códigos de erro
- Frontend deve implementar UI para histórico/backup

## 📚 References

**Documentação:**
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://pydantic-docs.helpmanual.io/)
- [MongoDB Python Driver](https://pymongo.readthedocs.io/)

**Código Relacionado:**
- `src/api/app.py` - Endpoints existentes
- `src/config/settings.py` - Configuração do MongoDB
- `src/models/` - Modelos existentes

**Padrões do Projeto:**
- Estrutura de endpoints em `src/api/routers/`
- Modelos Pydantic em `src/models/`
- Serviços em `src/services/`
- Testes em `tests/`

---

**Status:** 📝 Plano Criado  
**Data:** 2025-01-19  
**Autor:** Saga Planner  
**Versão:** 1.0