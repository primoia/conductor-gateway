#!/usr/bin/env python3
"""
Script para executar os testes principais do conductor-gateway.
"""
import subprocess
import sys


def run_command(cmd, description):
    """Execute um comando e mostra o resultado."""
    print(f"\n🧪 {description}")
    print("=" * 60)

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"✅ {description} - PASSED")
            if result.stdout.strip():
                # Mostra apenas um resumo dos testes que passaram
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'passed' in line and ('warning' in line or 'failed' in line or '==' in line):
                        print(f"   {line}")
        else:
            print(f"❌ {description} - FAILED")
            print(f"Error: {result.stderr}")
            return False

        return True

    except Exception as e:
        print(f"❌ Erro ao executar: {e}")
        return False


def main():
    """Executa a suite de testes principais."""
    print("🚀 Executando testes do Conductor Gateway")
    print("=" * 60)

    # Lista de testes para executar
    test_commands = [
        (
            "poetry run pytest tests/unit/test_mcp_server.py -v --tb=short",
            "Testes do Servidor MCP"
        ),
        (
            "poetry run pytest tests/unit/test_utils.py::TestImportStructure tests/unit/test_utils.py::TestProjectStructure -v --tb=short",
            "Testes de Estrutura do Projeto"
        ),
        (
            "poetry run pytest tests/unit/test_config.py::TestConfigurationLoading::test_server_config_constants tests/unit/test_config.py::TestConfigurationLoading::test_conductor_config_constants -v --tb=short",
            "Testes de Configuração Básica"
        ),
        (
            "poetry run pytest tests/unit/test_api.py::TestHealthEndpoint -v --tb=short",
            "Testes de Health Check da API"
        ),
        (
            "poetry run pytest tests/unit/test_api.py::TestSSEStreamingEndpoints::test_start_execution_creates_job tests/unit/test_api.py::TestSSEStreamingEndpoints::test_stream_events_nonexistent_job -v --tb=short",
            "Testes Básicos de SSE Streaming"
        )
    ]

    passed = 0
    total = len(test_commands)

    for cmd, description in test_commands:
        if run_command(cmd, description):
            passed += 1
        else:
            print(f"\n⚠️  Teste falhou: {description}")

    print(f"\n📊 Resumo dos Testes")
    print("=" * 60)
    print(f"✅ Passou: {passed}/{total}")
    print(f"❌ Falhou: {total - passed}/{total}")

    if passed == total:
        print("\n🎉 Todos os testes principais passaram!")
        print("✨ O sistema está funcionalmente estável.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} teste(s) falharam.")
        print("🔧 Verifique os logs acima para mais detalhes.")
        return 1


if __name__ == "__main__":
    sys.exit(main())