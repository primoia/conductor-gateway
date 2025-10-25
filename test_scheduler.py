#!/usr/bin/env python3
"""
Test script to check if APScheduler is working
"""
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_job():
    """Test job that should run every 10 seconds"""
    logger.info(f"🔥 TEST JOB EXECUTED at {datetime.now()}")


async def main():
    # Create scheduler
    scheduler = AsyncIOScheduler(timezone='UTC')

    # Add test job that runs every 10 seconds
    scheduler.add_job(
        func=test_job,
        trigger=IntervalTrigger(seconds=10),
        id='test_job',
        name='Test Job'
    )

    # Start scheduler
    scheduler.start()
    logger.info("✅ Scheduler started")

    # List jobs
    jobs = scheduler.get_jobs()
    logger.info(f"📋 Scheduled jobs: {len(jobs)}")
    for job in jobs:
        logger.info(f"  - {job.id}: next_run={job.next_run_time}")

    # Keep running for 35 seconds to see 3 executions
    logger.info("⏳ Waiting 35 seconds to see executions...")
    await asyncio.sleep(35)

    # Shutdown
    scheduler.shutdown()
    logger.info("🛑 Scheduler stopped")


if __name__ == "__main__":
    asyncio.run(main())
