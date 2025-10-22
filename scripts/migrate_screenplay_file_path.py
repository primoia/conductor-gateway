#!/usr/bin/env python3
"""
Migration script to add filePath field to existing screenplays.
This script adds the filePath field as None to all existing screenplays that don't have it.
"""

import sys
import os
from datetime import datetime

# Add src directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pymongo import MongoClient
from src.config.settings import MONGODB_CONFIG


def migrate_screenplay_file_path():
    """Add filePath field to existing screenplays."""
    
    # Connect to MongoDB
    mongodb_url = MONGODB_CONFIG['url'].replace('@mongodb:', '@localhost:')
    client = MongoClient(mongodb_url)
    db = client[MONGODB_CONFIG['database']]
    collection = db['screenplays']
    
    print("=" * 80)
    print("🔄 MIGRAÇÃO: Adicionando campo filePath aos roteiros existentes")
    print("=" * 80)
    print()
    
    # Step 1: Count screenplays without filePath field
    print("1️⃣ Verificando roteiros sem campo filePath...")
    screenplays_without_file_path = collection.count_documents({
        "filePath": {"$exists": False}
    })
    print(f"   📊 Roteiros sem filePath: {screenplays_without_file_path}")
    
    if screenplays_without_file_path == 0:
        print("   ✅ Todos os roteiros já possuem o campo filePath")
        print()
        print("=" * 80)
        print("✅ MIGRAÇÃO DESNECESSÁRIA - JÁ CONCLUÍDA!")
        print("=" * 80)
        return
    
    # Step 2: Add filePath field to screenplays that don't have it
    print("2️⃣ Adicionando campo filePath aos roteiros existentes...")
    result = collection.update_many(
        {"filePath": {"$exists": False}},
        {"$set": {"filePath": None}}
    )
    
    print(f"   📊 Roteiros atualizados: {result.modified_count}")
    print(f"   ✅ Campo filePath adicionado com sucesso")
    print()
    
    # Step 3: Verify migration
    print("3️⃣ Verificando migração...")
    remaining_without_file_path = collection.count_documents({
        "filePath": {"$exists": False}
    })
    
    if remaining_without_file_path == 0:
        print("   ✅ Migração concluída com sucesso!")
        print(f"   📊 Total de roteiros migrados: {result.modified_count}")
    else:
        print(f"   ⚠️  Ainda existem {remaining_without_file_path} roteiros sem filePath")
        print("   ❌ Migração pode ter falhado parcialmente")
    
    print()
    
    # Step 4: Show statistics
    print("4️⃣ Estatísticas finais...")
    total_screenplays = collection.count_documents({})
    screenplays_with_file_path = collection.count_documents({
        "filePath": {"$exists": True}
    })
    screenplays_with_null_file_path = collection.count_documents({
        "filePath": None
    })
    screenplays_with_value_file_path = collection.count_documents({
        "filePath": {"$ne": None, "$exists": True}
    })
    
    print(f"   📊 Total de roteiros: {total_screenplays}")
    print(f"   📊 Roteiros com campo filePath: {screenplays_with_file_path}")
    print(f"   📊 Roteiros com filePath = null: {screenplays_with_null_file_path}")
    print(f"   📊 Roteiros com filePath preenchido: {screenplays_with_value_file_path}")
    print()
    
    # Close connection
    client.close()
    
    print("=" * 80)
    print("✅ MIGRAÇÃO CONCLUÍDA COM SUCESSO!")
    print("=" * 80)
    print()
    print("Resumo:")
    print(f"  - Roteiros migrados: {result.modified_count}")
    print(f"  - Campo filePath adicionado como null para roteiros existentes")
    print(f"  - Novos roteiros podem usar o campo filePath normalmente")
    print()


if __name__ == '__main__':
    try:
        migrate_screenplay_file_path()
        print("🎉 Migração executada com sucesso!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ ERRO NA MIGRAÇÃO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)