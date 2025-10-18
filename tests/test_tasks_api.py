#!/usr/bin/env python3
"""
Test script to validate the tasks API endpoints.
"""

import sys
import os
import requests
import json

# Configuration
BASE_URL = "http://localhost:5006"

def test_list_all_tasks():
    """Test GET /api/tasks - list all tasks"""
    print("=" * 80)
    print("🧪 TESTE 1: GET /api/tasks (listar todas as tasks)")
    print("=" * 80)

    response = requests.get(f"{BASE_URL}/api/tasks?limit=5")

    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Success: {data.get('success')}")
        print(f"📊 Total de tasks: {data.get('total')}")
        print(f"📊 Tasks retornadas: {data.get('count')}")

        if data.get('tasks'):
            print(f"\n📋 Primeira task:")
            first_task = data['tasks'][0]
            print(f"   - ID: {first_task.get('_id')}")
            print(f"   - Agent ID: {first_task.get('agent_id')}")
            print(f"   - Status: {first_task.get('status')}")
            print(f"   - Created: {first_task.get('created_at')}")
            print(f"   - Updated: {first_task.get('updated_at')}")
        print()
        return True
    else:
        print(f"❌ Erro: {response.text}")
        print()
        return False


def test_list_processing_tasks_via_tasks_endpoint():
    """Test GET /api/tasks?status=processing"""
    print("=" * 80)
    print("🧪 TESTE 2: GET /api/tasks?status=processing (via endpoint genérico)")
    print("=" * 80)

    response = requests.get(f"{BASE_URL}/api/tasks?status=processing&limit=10")

    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Success: {data.get('success')}")
        print(f"📊 Total de tasks em processing: {data.get('total')}")
        print(f"📊 Tasks retornadas: {data.get('count')}")

        if data.get('tasks'):
            print(f"\n📋 Tasks em processing:")
            for i, task in enumerate(data['tasks'], 1):
                print(f"   {i}. Agent: {task.get('agent_id')} | Status: {task.get('status')} | Created: {task.get('created_at')}")
        else:
            print("   Nenhuma task em processing encontrada")
        print()
        return True
    else:
        print(f"❌ Erro: {response.text}")
        print()
        return False


def test_list_processing_tasks_dedicated():
    """Test GET /api/tasks/processing - dedicated endpoint"""
    print("=" * 80)
    print("🧪 TESTE 3: GET /api/tasks/processing (endpoint dedicado)")
    print("=" * 80)

    response = requests.get(f"{BASE_URL}/api/tasks/processing?limit=10")

    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Success: {data.get('success')}")
        print(f"📊 Total de tasks em processing: {data.get('total')}")
        print(f"📊 Tasks retornadas: {data.get('count')}")

        if data.get('tasks'):
            print(f"\n📋 Detalhes das tasks em processing:")
            for i, task in enumerate(data['tasks'], 1):
                print(f"\n   Task {i}:")
                print(f"      - ID: {task.get('_id')}")
                print(f"      - Agent ID: {task.get('agent_id')}")
                print(f"      - Status: {task.get('status')}")
                print(f"      - CWD: {task.get('cwd')}")
                print(f"      - Timeout: {task.get('timeout')}")
                print(f"      - Created: {task.get('created_at')}")
                print(f"      - Started: {task.get('started_at')}")
                if task.get('prompt'):
                    prompt_preview = task['prompt'][:100].replace('\n', ' ')
                    print(f"      - Prompt: {prompt_preview}...")
        else:
            print("   ℹ️  Nenhuma task em processing encontrada no momento")
        print()
        return True
    else:
        print(f"❌ Erro: {response.text}")
        print()
        return False


def test_filter_by_agent_id():
    """Test GET /api/tasks?agent_id=<id>"""
    print("=" * 80)
    print("🧪 TESTE 4: GET /api/tasks?agent_id=ReadmeResume_Agent")
    print("=" * 80)

    response = requests.get(f"{BASE_URL}/api/tasks?agent_id=ReadmeResume_Agent&limit=5")

    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Success: {data.get('success')}")
        print(f"📊 Total de tasks para este agent: {data.get('total')}")
        print(f"📊 Tasks retornadas: {data.get('count')}")

        if data.get('tasks'):
            print(f"\n📋 Tasks do agent 'ReadmeResume_Agent':")
            for i, task in enumerate(data['tasks'], 1):
                print(f"   {i}. Status: {task.get('status')} | Created: {task.get('created_at')}")
        print()
        return True
    else:
        print(f"❌ Erro: {response.text}")
        print()
        return False


def test_pagination():
    """Test pagination with offset and limit"""
    print("=" * 80)
    print("🧪 TESTE 5: Testando paginação (limit=2, offset=0 e offset=2)")
    print("=" * 80)

    # First page
    response1 = requests.get(f"{BASE_URL}/api/tasks?limit=2&offset=0")
    # Second page
    response2 = requests.get(f"{BASE_URL}/api/tasks?limit=2&offset=2")

    if response1.status_code == 200 and response2.status_code == 200:
        data1 = response1.json()
        data2 = response2.json()

        print(f"📄 Página 1 (offset=0):")
        print(f"   - Tasks retornadas: {data1.get('count')}")
        if data1.get('tasks'):
            for task in data1['tasks']:
                print(f"      • {task.get('_id')} - {task.get('agent_id')}")

        print(f"\n📄 Página 2 (offset=2):")
        print(f"   - Tasks retornadas: {data2.get('count')}")
        if data2.get('tasks'):
            for task in data2['tasks']:
                print(f"      • {task.get('_id')} - {task.get('agent_id')}")

        # Check if tasks are different
        ids1 = set(t['_id'] for t in data1.get('tasks', []))
        ids2 = set(t['_id'] for t in data2.get('tasks', []))

        if ids1 and ids2 and not ids1.intersection(ids2):
            print(f"\n✅ Paginação funcionando corretamente (tasks diferentes em cada página)")
        elif not ids1 or not ids2:
            print(f"\nℹ️  Não há tasks suficientes para testar paginação completa")
        else:
            print(f"\n⚠️  Aviso: Algumas tasks aparecem em ambas as páginas")

        print()
        return True
    else:
        print(f"❌ Erro ao testar paginação")
        print()
        return False


if __name__ == '__main__':
    print()
    print("=" * 80)
    print("🚀 INICIANDO TESTES DA API DE TASKS")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print()

    # Check if API is running
    try:
        health = requests.get(f"{BASE_URL}/health")
        if health.status_code != 200:
            print("❌ API não está respondendo. Certifique-se de que o servidor está rodando.")
            sys.exit(1)
        print("✅ API está online e respondendo\n")
    except requests.exceptions.ConnectionError:
        print(f"❌ Não foi possível conectar ao servidor em {BASE_URL}")
        print("   Certifique-se de que o servidor FastAPI está rodando na porta 5006")
        sys.exit(1)

    # Run tests
    results = []

    results.append(("Listar todas as tasks", test_list_all_tasks()))
    results.append(("Listar tasks em processing (via /api/tasks)", test_list_processing_tasks_via_tasks_endpoint()))
    results.append(("Listar tasks em processing (via /api/tasks/processing)", test_list_processing_tasks_dedicated()))
    results.append(("Filtrar por agent_id", test_filter_by_agent_id()))
    results.append(("Testar paginação", test_pagination()))

    # Summary
    print("=" * 80)
    print("📊 RESUMO DOS TESTES")
    print("=" * 80)

    for test_name, success in results:
        status = "✅ PASSOU" if success else "❌ FALHOU"
        print(f"{status} - {test_name}")

    total_tests = len(results)
    passed_tests = sum(1 for _, success in results if success)

    print()
    print(f"Total: {passed_tests}/{total_tests} testes passaram")
    print("=" * 80)
    print()

    if passed_tests == total_tests:
        print("🎉 Todos os testes passaram com sucesso!")
        sys.exit(0)
    else:
        print("⚠️  Alguns testes falharam")
        sys.exit(1)
