#!/usr/bin/env python3
"""
Script to check and manage councilor status in MongoDB
"""
import pymongo
from pprint import pprint

# MongoDB connection
# Try localhost first (outside Docker), then mongodb (inside Docker)
import sys
MONGO_URLS = [
    "mongodb://admin:czrimr@localhost:27017/?authSource=admin",
    "mongodb://admin:czrimr@127.0.0.1:27017/?authSource=admin",
    "mongodb://admin:czrimr@mongodb:27017/?authSource=admin"
]
DB_NAME = "conductor_state"

def main():
    print("=" * 80)
    print("COUNCILOR DATABASE CHECKER")
    print("=" * 80)

    # Try to connect to MongoDB
    client = None

    for url in MONGO_URLS:
        try:
            print(f"\n🔗 Trying: {url.split('@')[1] if '@' in url else url}")
            test_client = pymongo.MongoClient(url, serverSelectionTimeoutMS=3000)
            test_client.admin.command('ping')
            client = test_client
            print(f"✅ Connected!")
            break
        except Exception as e:
            print(f"❌ Failed: {str(e)[:50]}")

    if not client:
        print("\n❌ Could not connect to MongoDB!")
        print("\nIs MongoDB running? Check: docker ps | grep mongodb")
        sys.exit(1)

    db = client[DB_NAME]
    agents_collection = db.agents

    print(f"\n📦 Connected to database: {DB_NAME}")
    print(f"📋 Collection: agents")

    # Count total agents
    total_agents = agents_collection.count_documents({})
    print(f"\n📊 Total agents in collection: {total_agents}")

    # Check for TestQuickValidation_Agent
    print("\n" + "=" * 80)
    print("Searching for: TestQuickValidation_Agent")
    print("=" * 80)

    agent = agents_collection.find_one({"agent_id": "TestQuickValidation_Agent"})

    if agent:
        print("\n✅ AGENT FOUND!")
        print("\nAgent details:")
        print("-" * 80)
        pprint(agent)
        print("-" * 80)

        is_councilor = agent.get("is_councilor", False)
        print(f"\n🏛️  is_councilor: {is_councilor}")

        if is_councilor:
            print("\n⚠️  This agent IS already marked as a councilor!")
            print("\nDo you want to reset it? (y/n): ", end="")
            response = input().strip().lower()

            if response == 'y':
                result = agents_collection.update_one(
                    {"agent_id": "TestQuickValidation_Agent"},
                    {
                        "$set": {"is_councilor": False},
                        "$unset": {"councilor_config": ""}
                    }
                )
                print(f"\n✅ Agent reset! Modified count: {result.modified_count}")
            else:
                print("\n❌ Reset cancelled")
        else:
            print("\n✅ Agent is NOT a councilor yet. You can promote it!")
    else:
        print("\n❌ AGENT NOT FOUND!")
        print("\nLet's check what agents exist:")
        print("-" * 80)

        all_agents = agents_collection.find({}, {"agent_id": 1, "name": 1, "is_councilor": 1}).limit(10)
        for idx, ag in enumerate(all_agents, 1):
            councilor_mark = "🏛️" if ag.get("is_councilor") else "  "
            print(f"{idx}. {councilor_mark} {ag.get('agent_id', 'N/A')} - {ag.get('name', 'N/A')}")

    # Check for any councilors
    print("\n" + "=" * 80)
    print("ALL COUNCILORS IN DATABASE")
    print("=" * 80)

    councilors = agents_collection.find({"is_councilor": True})
    councilor_count = agents_collection.count_documents({"is_councilor": True})

    print(f"\n📊 Total councilors: {councilor_count}")

    if councilor_count > 0:
        print("\nCouncilors found:")
        print("-" * 80)
        for idx, councilor in enumerate(councilors, 1):
            print(f"\n{idx}. Agent ID: {councilor.get('agent_id')}")
            print(f"   Name: {councilor.get('name')}")
            if 'councilor_config' in councilor:
                config = councilor['councilor_config']
                print(f"   Title: {config.get('title')}")
                print(f"   Schedule: {config.get('schedule')}")
    else:
        print("\n✅ No councilors found in database")

    print("\n" + "=" * 80)
    print("END OF REPORT")
    print("=" * 80)

    client.close()

if __name__ == "__main__":
    main()
