# Atualização de Screenplay com isDeleted

Este documento demonstra como usar a API para atualizar um screenplay com `isDeleted=true` e como isso afeta os `agent_instances` relacionados.

## Funcionalidade

Quando um screenplay é atualizado com `isDeleted=true`, todos os `agent_instances` que possuem o mesmo `screenplay_id` são automaticamente marcados como `isDeleted=true` também.

## Endpoint

```
PUT /api/screenplays/{screenplay_id}
```

## Exemplo de Requisição

```bash
curl -X PUT "http://localhost:5006/api/screenplays/68f2ff93b910b667e9c31eb4" \
  -H "Content-Type: application/json" \
  -d '{
    "isDeleted": true
  }'
```

## Exemplo de Resposta

```json
{
  "id": "68f2ff93b910b667e9c31eb4",
  "name": "Meu Screenplay",
  "description": "Descrição do screenplay",
  "tags": ["teste", "exemplo"],
  "content": "# Conteúdo do Screenplay\n\nConteúdo aqui...",
  "isDeleted": true,
  "version": 2,
  "createdAt": "2025-01-15T10:30:00Z",
  "updatedAt": "2025-01-15T10:35:00Z"
}
```

## Comportamento em Cascata

Quando `isDeleted=true` é definido:

1. O screenplay é marcado como `isDeleted: true`
2. Todos os `agent_instances` com `screenplay_id` correspondente são marcados como `isDeleted: true`
3. O campo `updated_at` dos `agent_instances` é atualizado

## Restaurar Screenplay

Para restaurar um screenplay (marcar como não deletado):

```bash
curl -X PUT "http://localhost:5006/api/screenplays/68f2ff93b910b667e9c31eb4" \
  -H "Content-Type: application/json" \
  -d '{
    "isDeleted": false
  }'
```

**Nota**: Restaurar o screenplay NÃO restaura automaticamente os `agent_instances` relacionados. Eles permanecem marcados como deletados.

## Campos Disponíveis para Atualização

O endpoint `PUT /api/screenplays/{screenplay_id}` aceita os seguintes campos opcionais:

- `name`: Nome do screenplay
- `description`: Descrição do screenplay
- `tags`: Lista de tags
- `content`: Conteúdo em Markdown
- `isDeleted`: Flag de exclusão lógica (true/false)

## Logs

Quando a operação é executada, os seguintes logs são gerados:

```
INFO - Updated screenplay: {screenplay_id} (new version: {version})
INFO - Marked {count} agent_instances as deleted for screenplay: {screenplay_id}
```

ou

```
INFO - No agent_instances found for screenplay: {screenplay_id}
```