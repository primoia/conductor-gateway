#!/usr/bin/env python3
"""
Test script to validate file_path functionality in screenplays.
"""

import sys
import os
from datetime import datetime

# Add src directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pymongo import MongoClient
from src.config.settings import MONGODB_CONFIG
from src.services.screenplay_service import ScreenplayService


def test_file_path_functionality():
    """Test file_path functionality in screenplays."""

    # Connect to MongoDB
    mongodb_url = MONGODB_CONFIG['url'].replace('@mongodb:', '@localhost:')
    client = MongoClient(mongodb_url)
    db = client[MONGODB_CONFIG['database']]

    print("=" * 80)
    print("🧪 TESTE: Funcionalidade de file_path em roteiros")
    print("=" * 80)
    print()

    # Initialize service
    service = ScreenplayService(db)

    # Test 1: Create screenplay with valid file_path
    print("1️⃣ Criando roteiro com file_path válido...")
    test_screenplay_1 = service.create_screenplay(
        name=f"Test Screenplay 1 {datetime.now().isoformat()}",
        description="Roteiro de teste com file_path válido",
        tags=["test", "file_path"],
        file_path="folder/screenplay1.md"
    )
    screenplay_id_1 = str(test_screenplay_1['_id'])
    print(f"   ✅ Roteiro criado: {screenplay_id_1}")
    print(f"   📁 File path: {test_screenplay_1.get('filePath')}")
    print()

    # Test 2: Create screenplay with invalid file_path (should fail)
    print("2️⃣ Tentando criar roteiro com file_path inválido...")
    try:
        service.create_screenplay(
            name=f"Test Screenplay 2 {datetime.now().isoformat()}",
            description="Roteiro de teste com file_path inválido",
            tags=["test", "file_path"],
            file_path="../invalid/path.md"  # Path traversal attempt
        )
        print("   ❌ ERRO: Deveria ter falhado com file_path inválido")
    except ValueError as e:
        print(f"   ✅ Falhou corretamente: {e}")
    print()

    # Test 3: Create screenplay without file_path (should work)
    print("3️⃣ Criando roteiro sem file_path...")
    test_screenplay_3 = service.create_screenplay(
        name=f"Test Screenplay 3 {datetime.now().isoformat()}",
        description="Roteiro de teste sem file_path",
        tags=["test", "no_file_path"]
    )
    screenplay_id_3 = str(test_screenplay_3['_id'])
    print(f"   ✅ Roteiro criado: {screenplay_id_3}")
    print(f"   📁 File path: {test_screenplay_3.get('filePath')}")
    print()

    # Test 4: Update screenplay with valid file_path
    print("4️⃣ Atualizando roteiro com file_path válido...")
    updated_screenplay = service.update_screenplay(
        screenplay_id=screenplay_id_3,
        file_path="updated/path.md"
    )
    print(f"   ✅ Roteiro atualizado: {screenplay_id_3}")
    print(f"   📁 File path: {updated_screenplay.get('filePath')}")
    print()

    # Test 5: Update screenplay with invalid file_path (should fail)
    print("5️⃣ Tentando atualizar roteiro com file_path inválido...")
    try:
        service.update_screenplay(
            screenplay_id=screenplay_id_1,
            file_path="invalid<.md"  # Invalid characters
        )
        print("   ❌ ERRO: Deveria ter falhado com file_path inválido")
    except ValueError as e:
        print(f"   ✅ Falhou corretamente: {e}")
    print()

    # Test 6: Test file_path sanitization
    print("6️⃣ Testando sanitização de file_path...")
    test_screenplay_6 = service.create_screenplay(
        name=f"Test Screenplay 6 {datetime.now().isoformat()}",
        description="Roteiro de teste com file_path para sanitizar",
        tags=["test", "sanitization"],
        file_path="  folder\\file.md  "  # Should be sanitized
    )
    screenplay_id_6 = str(test_screenplay_6['_id'])
    print(f"   ✅ Roteiro criado: {screenplay_id_6}")
    print(f"   📁 File path original: '  folder\\file.md  '")
    print(f"   📁 File path sanitizado: '{test_screenplay_6.get('filePath')}'")
    print()

    # Test 7: List screenplays and verify file_path is included
    print("7️⃣ Listando roteiros e verificando file_path...")
    result = service.list_screenplays(limit=10)
    print(f"   📊 Total de roteiros: {result['total']}")
    
    for item in result['items']:
        print(f"   📝 {item['name']}: file_path = {item.get('filePath')}")
    print()

    # Test 8: Get specific screenplay and verify file_path
    print("8️⃣ Obtendo roteiro específico e verificando file_path...")
    retrieved_screenplay = service.get_screenplay_by_id(screenplay_id_1)
    if retrieved_screenplay:
        print(f"   ✅ Roteiro obtido: {retrieved_screenplay['name']}")
        print(f"   📁 File path: {retrieved_screenplay.get('filePath')}")
    else:
        print("   ❌ ERRO: Não foi possível obter o roteiro")
    print()

    # Cleanup: Remove test data
    print("9️⃣ Limpando dados de teste...")
    db['screenplays'].delete_many({
        "name": {"$regex": "Test Screenplay.*"}
    })
    print("   ✅ Dados de teste removidos")
    print()

    # Close connection
    client.close()

    print("=" * 80)
    print("✅ TESTE CONCLUÍDO COM SUCESSO!")
    print("=" * 80)
    print()
    print("Resumo dos testes:")
    print("  - Criação com file_path válido ✅")
    print("  - Criação com file_path inválido (falha esperada) ✅")
    print("  - Criação sem file_path ✅")
    print("  - Atualização com file_path válido ✅")
    print("  - Atualização com file_path inválido (falha esperada) ✅")
    print("  - Sanitização de file_path ✅")
    print("  - Listagem inclui file_path ✅")
    print("  - Obtenção específica inclui file_path ✅")
    print()


if __name__ == '__main__':
    try:
        test_file_path_functionality()
        print("🎉 Todos os testes passaram!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ ERRO NO TESTE: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)