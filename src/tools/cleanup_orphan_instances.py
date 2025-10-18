#!/usr/bin/env python3
"""
Script para limpar agent_instances órfãos (sem screenplay_id válido).

Agent instances podem se tornar órfãos quando:
1. O screenplay ao qual estavam vinculados foi deletado
2. Foi criado sem screenplay_id
3. O screenplay_id não existe mais no banco

Este script:
- Identifica todos os agent_instances
- Verifica se o screenplay_id existe na coleção screenplays
- Remove instances órfãos (screenplay_id inexistente ou nulo)
"""

import os
import sys
from pymongo import MongoClient
from datetime import datetime

# Add parent directory to path to import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.settings import MONGODB_CONFIG


def cleanup_orphan_instances(dry_run=True):
    """
    Limpa agent_instances órfãos.

    Args:
        dry_run: Se True, apenas mostra o que seria deletado sem deletar de fato
    """
    # Connect to MongoDB
    client = MongoClient(MONGODB_CONFIG['url'])
    db = client[MONGODB_CONFIG['database']]

    agent_instances = db['agent_instances']
    screenplays = db['screenplays']

    print("🔍 Iniciando verificação de agent_instances órfãos...")
    print(f"   Modo: {'DRY RUN (simulação)' if dry_run else 'EXECUÇÃO REAL'}")
    print()

    # Get all agent instances
    total_instances = agent_instances.count_documents({})
    print(f"📊 Total de agent_instances no banco: {total_instances}")

    # Get all screenplay IDs
    valid_screenplay_ids = set()
    for screenplay in screenplays.find({}, {'id': 1, '_id': 0}):
        valid_screenplay_ids.add(screenplay.get('id'))

    print(f"📄 Total de screenplays válidos: {len(valid_screenplay_ids)}")
    print()

    # Find orphan instances
    orphans = []

    # 1. Instances without screenplay_id
    instances_without_screenplay = list(agent_instances.find({
        '$or': [
            {'screenplay_id': {'$exists': False}},
            {'screenplay_id': None},
            {'screenplay_id': ''}
        ]
    }))

    for instance in instances_without_screenplay:
        orphans.append({
            'instance_id': instance.get('instance_id'),
            'agent_id': instance.get('agent_id'),
            'screenplay_id': instance.get('screenplay_id'),
            'reason': 'Sem screenplay_id'
        })

    # 2. Instances with invalid screenplay_id
    instances_with_screenplay = agent_instances.find({
        'screenplay_id': {'$exists': True, '$ne': None, '$ne': ''}
    })

    for instance in instances_with_screenplay:
        screenplay_id = instance.get('screenplay_id')
        if screenplay_id not in valid_screenplay_ids:
            orphans.append({
                'instance_id': instance.get('instance_id'),
                'agent_id': instance.get('agent_id'),
                'screenplay_id': screenplay_id,
                'reason': 'Screenplay não existe mais'
            })

    print(f"🗑️  Órfãos encontrados: {len(orphans)}")
    print()

    if len(orphans) == 0:
        print("✅ Nenhum órfão encontrado! Banco está limpo.")
        return

    # Show orphans
    print("📋 Lista de agent_instances órfãos:")
    print("-" * 100)
    for i, orphan in enumerate(orphans[:20], 1):  # Show first 20
        print(f"{i}. Instance ID: {orphan['instance_id']}")
        print(f"   Agent ID: {orphan['agent_id']}")
        print(f"   Screenplay ID: {orphan['screenplay_id']}")
        print(f"   Motivo: {orphan['reason']}")
        print()

    if len(orphans) > 20:
        print(f"... e mais {len(orphans) - 20} órfãos")
        print()

    # Delete orphans
    if not dry_run:
        print("🗑️  Deletando órfãos...")
        orphan_ids = [o['instance_id'] for o in orphans]
        result = agent_instances.delete_many({
            'instance_id': {'$in': orphan_ids}
        })

        print(f"✅ Deletados: {result.deleted_count} agent_instances órfãos")

        # Log the cleanup
        cleanup_log = {
            'timestamp': datetime.now().isoformat(),
            'orphans_deleted': result.deleted_count,
            'orphan_details': orphans
        }

        db['cleanup_logs'].insert_one(cleanup_log)
        print(f"📝 Log de limpeza salvo na coleção 'cleanup_logs'")
    else:
        print("⚠️  DRY RUN: Nenhum dado foi deletado.")
        print("   Execute novamente com --execute para deletar de fato")

    client.close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Limpar agent_instances órfãos')
    parser.add_argument('--execute', action='store_true',
                       help='Executar limpeza de fato (sem isso, apenas simula)')

    args = parser.parse_args()

    dry_run = not args.execute

    print()
    print("=" * 100)
    print("🧹 CLEANUP DE AGENT_INSTANCES ÓRFÃOS")
    print("=" * 100)
    print()

    cleanup_orphan_instances(dry_run=dry_run)

    print()
    print("=" * 100)
    print("✅ Processo finalizado")
    print("=" * 100)
    print()
