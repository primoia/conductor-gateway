# Conductor Gateway

Gateway de alta performance que serve como ponte entre aplicacoes web e o sistema de execucao de agentes do Conductor, com API REST, streaming SSE e servidor MCP.

## Responsabilidades
- Expor execucao de agentes via API REST com streaming SSE
- Prover servidor MCP com ferramentas CLI do Conductor
- Gerenciar screenplays, personas e conversas
- Executar monitoramento automatizado via Councilor (scheduler)
- Suportar multiplos provedores de IA (OpenAI, Anthropic, Groq, Gemini, Ollama)

## Stack
- Python 3.11+ / FastAPI + Uvicorn
- MongoDB com Motor (async)
- LangChain (multi-provider AI)
- MCP (Model Context Protocol)
