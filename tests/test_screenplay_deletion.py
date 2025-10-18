#!/usr/bin/env python3
"""
Test script to validate that deleting a screenplay also marks related agent_instances as deleted.
"""

import sys
import os
from datetime import datetime

# Add src directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pymongo import MongoClient
from src.config.settings import MONGODB_CONFIG
from src.services.screenplay_service import ScreenplayService


def test_screenplay_deletion_cascade():
    """Test that deleting a screenplay marks related agent_instances as deleted."""

    # Connect to MongoDB (use localhost instead of mongodb hostname for Docker)
    mongodb_url = MONGODB_CONFIG['url'].replace('@mongodb:', '@localhost:')
    client = MongoClient(mongodb_url)
    db = client[MONGODB_CONFIG['database']]

    print("=" * 80)
    print("🧪 TESTE: Exclusão em cascata de screenplay e agent_instances")
    print("=" * 80)
    print()

    # Initialize service
    service = ScreenplayService(db)
    agent_instances = db['agent_instances']

    # Step 1: Create a test screenplay
    print("1️⃣ Criando screenplay de teste...")
    test_screenplay = service.create_screenplay(
        name=f"Test Screenplay {datetime.now().isoformat()}",
        description="Screenplay de teste para validar exclusão em cascata",
        tags=["test", "automation"]
    )
    screenplay_id = str(test_screenplay['_id'])
    print(f"   ✅ Screenplay criado: {screenplay_id}")
    print()

    # Step 2: Create test agent_instances linked to this screenplay
    print("2️⃣ Criando agent_instances de teste...")
    test_instances = []
    for i in range(3):
        instance = {
            "instance_id": f"test-instance-{i}-{datetime.now().timestamp()}",
            "agent_id": "test-agent",
            "screenplay_id": screenplay_id,
            "position": {"x": i * 100, "y": i * 100},
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "isDeleted": False
        }
        result = agent_instances.insert_one(instance)
        test_instances.append(instance["instance_id"])
        print(f"   ✅ Instance criado: {instance['instance_id']}")
    print()

    # Step 3: Verify instances are not deleted
    print("3️⃣ Verificando que instances não estão deletados...")
    not_deleted = agent_instances.count_documents({
        "screenplay_id": screenplay_id,
        "$or": [
            {"isDeleted": False},
            {"isDeleted": {"$exists": False}}
        ]
    })
    print(f"   📊 Instances não deletados: {not_deleted}")
    assert not_deleted == 3, f"Esperado 3 instances não deletados, encontrado {not_deleted}"
    print("   ✅ Verificação OK")
    print()

    # Step 4: Delete the screenplay
    print("4️⃣ Deletando screenplay...")
    success = service.delete_screenplay(screenplay_id)
    assert success, "Falha ao deletar screenplay"
    print("   ✅ Screenplay deletado com sucesso")
    print()

    # Step 5: Verify screenplay is marked as deleted
    print("5️⃣ Verificando que screenplay está marcado como deletado...")
    deleted_screenplay = db['screenplays'].find_one({"_id": test_screenplay['_id']})
    assert deleted_screenplay is not None, "Screenplay não encontrado"
    assert deleted_screenplay.get('isDeleted') is True, "Screenplay não está marcado como deletado"
    print("   ✅ Screenplay marcado como isDeleted: true")
    print()

    # Step 6: Verify all related agent_instances are marked as deleted
    print("6️⃣ Verificando que agent_instances relacionados foram marcados como deletados...")
    deleted_instances = agent_instances.count_documents({
        "screenplay_id": screenplay_id,
        "isDeleted": True
    })
    print(f"   📊 Instances deletados: {deleted_instances}")
    assert deleted_instances == 3, f"Esperado 3 instances deletados, encontrado {deleted_instances}"
    print("   ✅ Todos os agent_instances foram marcados como isDeleted: true")
    print()

    # Cleanup: Remove test data
    print("7️⃣ Limpando dados de teste...")
    db['screenplays'].delete_one({"_id": test_screenplay['_id']})
    agent_instances.delete_many({"instance_id": {"$in": test_instances}})
    print("   ✅ Dados de teste removidos")
    print()

    # Close connection
    client.close()

    print("=" * 80)
    print("✅ TESTE PASSOU COM SUCESSO!")
    print("=" * 80)
    print()
    print("Resumo:")
    print("  - Screenplay deletado marca isDeleted: true ✅")
    print("  - Agent_instances relacionados marcados como isDeleted: true ✅")
    print()


if __name__ == '__main__':
    try:
        test_screenplay_deletion_cascade()
        print("🎉 Todos os testes passaram!")
        sys.exit(0)
    except AssertionError as e:
        print(f"❌ TESTE FALHOU: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERRO INESPERADO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
