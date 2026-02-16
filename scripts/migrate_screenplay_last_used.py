#!/usr/bin/env python3
"""
Migration script to add lastUsedAt field to existing screenplays.
This script sets lastUsedAt = createdAt for all existing screenplays that don't have it.
"""

import sys
import os
from datetime import datetime, UTC

# Add src directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pymongo import MongoClient
from src.config.settings import MONGODB_CONFIG


def migrate_screenplay_last_used():
    """Add lastUsedAt field to existing screenplays."""

    # Connect to MongoDB
    mongodb_url = MONGODB_CONFIG['url'].replace('@mongodb:', '@localhost:')
    client = MongoClient(mongodb_url)
    db = client[MONGODB_CONFIG['database']]
    collection = db['screenplays']

    print("=" * 80)
    print("🔄 MIGRAÇÃO: Adicionando campo lastUsedAt aos roteiros existentes")
    print("=" * 80)
    print()

    # Step 1: Count screenplays without lastUsedAt field
    print("1️⃣ Verificando roteiros sem campo lastUsedAt...")
    screenplays_without_last_used = collection.count_documents({
        "lastUsedAt": {"$exists": False}
    })
    print(f"   📊 Roteiros sem lastUsedAt: {screenplays_without_last_used}")

    if screenplays_without_last_used == 0:
        print("   ✅ Todos os roteiros já possuem o campo lastUsedAt")
        print()
        print("=" * 80)
        print("✅ MIGRAÇÃO DESNECESSÁRIA - JÁ CONCLUÍDA!")
        print("=" * 80)
        return

    # Step 2: Add lastUsedAt field to screenplays that don't have it
    print("2️⃣ Adicionando campo lastUsedAt aos roteiros existentes...")
    print("   ℹ️  lastUsedAt será definido como createdAt para roteiros existentes")

    # Get all screenplays without lastUsedAt
    screenplays = collection.find({"lastUsedAt": {"$exists": False}})

    updated_count = 0
    for screenplay in screenplays:
        # Set lastUsedAt to createdAt if createdAt exists, otherwise use current time
        last_used_at = screenplay.get("createdAt", datetime.now(UTC))

        collection.update_one(
            {"_id": screenplay["_id"]},
            {"$set": {"lastUsedAt": last_used_at}}
        )
        updated_count += 1

    print(f"   📊 Roteiros atualizados: {updated_count}")
    print(f"   ✅ Campo lastUsedAt adicionado com sucesso")
    print()

    # Step 3: Verify migration
    print("3️⃣ Verificando migração...")
    remaining_without_last_used = collection.count_documents({
        "lastUsedAt": {"$exists": False}
    })

    if remaining_without_last_used == 0:
        print("   ✅ Migração concluída com sucesso!")
        print(f"   📊 Total de roteiros migrados: {updated_count}")
    else:
        print(f"   ⚠️  Ainda existem {remaining_without_last_used} roteiros sem lastUsedAt")
        print("   ❌ Migração pode ter falhado parcialmente")

    print()

    # Step 4: Show statistics
    print("4️⃣ Estatísticas finais...")
    total_screenplays = collection.count_documents({})
    screenplays_with_last_used = collection.count_documents({
        "lastUsedAt": {"$exists": True}
    })

    print(f"   📊 Total de roteiros: {total_screenplays}")
    print(f"   📊 Roteiros com campo lastUsedAt: {screenplays_with_last_used}")
    print()

    # Step 5: Verify sorting works correctly
    print("5️⃣ Verificando ordenação por lastUsedAt...")
    recent_screenplays = list(collection.find(
        {"isDeleted": False},
        {"name": 1, "lastUsedAt": 1, "createdAt": 1}
    ).sort("lastUsedAt", -1).limit(5))

    if recent_screenplays:
        print("   📋 Top 5 roteiros mais recentemente usados:")
        for i, sp in enumerate(recent_screenplays, 1):
            name = sp.get("name", "Sem nome")
            last_used = sp.get("lastUsedAt", "N/A")
            print(f"      {i}. {name} - {last_used}")

    print()

    # Close connection
    client.close()

    print("=" * 80)
    print("✅ MIGRAÇÃO CONCLUÍDA COM SUCESSO!")
    print("=" * 80)
    print()
    print("Resumo:")
    print(f"  - Roteiros migrados: {updated_count}")
    print(f"  - Campo lastUsedAt inicializado com createdAt")
    print(f"  - Novos roteiros terão lastUsedAt atualizado ao serem usados")
    print(f"  - Lista de roteiros será ordenada por lastUsedAt (mais recentes primeiro)")
    print()


if __name__ == '__main__':
    try:
        migrate_screenplay_last_used()
        print("🎉 Migração executada com sucesso!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ ERRO NA MIGRAÇÃO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
