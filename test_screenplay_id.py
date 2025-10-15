#!/usr/bin/env python3
"""
Script de teste para verificar se as modificações do screenplay_id estão funcionando corretamente.
Este script testa os endpoints modificados do conductor-gateway.
"""

import json
import requests
import time

# Configuração do teste
BASE_URL = "http://localhost:5006"  # Ajuste conforme necessário
TEST_SCREENPLAY_ID = "test_screenplay_12345"

def test_create_agent_instance():
    """Testa a criação de uma instância de agente com screenplay_id."""
    print("🧪 Testando criação de instância com screenplay_id...")
    
    payload = {
        "instance_id": f"test_instance_{int(time.time())}",
        "agent_id": "ScreenplayAssistant_Agent",
        "position": {"x": 100, "y": 200},
        "screenplay_id": TEST_SCREENPLAY_ID,
        "status": "pending"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/agents/instances", json=payload)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Instância criada com sucesso!")
            print(f"   - Instance ID: {result['instance']['instance_id']}")
            print(f"   - Screenplay ID: {result['instance'].get('screenplay_id', 'NÃO ENCONTRADO')}")
            return result['instance']['instance_id']
        else:
            print(f"❌ Erro na criação: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Erro na requisição: {e}")
        return None

def test_execute_agent(instance_id):
    """Testa a execução de um agente com screenplay_id."""
    print(f"\n🧪 Testando execução de agente com instance_id: {instance_id}")
    
    payload = {
        "input_text": "Teste de execução com screenplay_id",
        "instance_id": instance_id,
        "screenplay_id": TEST_SCREENPLAY_ID,
        "context_mode": "stateless"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/agents/ScreenplayAssistant_Agent/execute", json=payload)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Agente executado com sucesso!")
            print(f"   - Status: {result.get('status')}")
            print(f"   - Instance ID: {result.get('instance_id')}")
            return True
        else:
            print(f"❌ Erro na execução: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Erro na requisição: {e}")
        return False

def test_backward_compatibility():
    """Testa compatibilidade com document_id (campo antigo)."""
    print(f"\n🧪 Testando compatibilidade com document_id...")
    
    payload = {
        "input_text": "Teste de compatibilidade com document_id",
        "instance_id": f"test_instance_compat_{int(time.time())}",
        "document_id": TEST_SCREENPLAY_ID,  # Usando o campo antigo
        "context_mode": "stateless"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/agents/ScreenplayAssistant_Agent/execute", json=payload)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Compatibilidade com document_id funcionando!")
            print(f"   - Status: {result.get('status')}")
            return True
        else:
            print(f"❌ Erro na compatibilidade: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Erro na requisição: {e}")
        return False

def main():
    """Executa todos os testes."""
    print("🚀 Iniciando testes do screenplay_id no conductor-gateway")
    print("=" * 60)
    
    # Teste 1: Criação de instância
    instance_id = test_create_agent_instance()
    
    if instance_id:
        # Teste 2: Execução de agente
        test_execute_agent(instance_id)
    
    # Teste 3: Compatibilidade com document_id
    test_backward_compatibility()
    
    print("\n" + "=" * 60)
    print("🏁 Testes concluídos!")

if __name__ == "__main__":
    main()