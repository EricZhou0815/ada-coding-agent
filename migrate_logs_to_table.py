#!/usr/bin/env python
"""
Migration script: Move logs from JSON text column to separate job_logs table.

This script:
1. Reads existing logs from StoryJob.logs (JSON array in text column)
2. Creates individual JobLog entries for each log
3. Preserves the legacy JSON column for rollback safety

Usage:
    python migrate_logs_to_table.py [--dry-run]

Options:
    --dry-run    Show what would be migrated without making changes
"""

import sys
import json
import argparse
from datetime import datetime, timezone
from api.database import SessionLocal, StoryJob, JobLog, Base, engine


def migrate_logs(dry_run=False):
    """Migrate logs from JSON column to job_logs table."""
    
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        # Get all jobs with logs in the legacy format
        jobs = db.query(StoryJob).all()
        total_jobs = len(jobs)
        total_logs_migrated = 0
        
        print(f"Found {total_jobs} jobs to process")
        print("=" * 60)
        
        for idx, job in enumerate(jobs, 1):
            if not job.logs or job.logs == "[]":
                continue
            
            try:
                # Parse legacy JSON logs
                legacy_logs = json.loads(job.logs)
                if not isinstance(legacy_logs, list):
                    print(f"[WARNING] Job {job.id}: logs is not an array, skipping")
                    continue
                
                # Check if already migrated
                existing_count = db.query(JobLog).filter(JobLog.job_id == job.id).count()
                if existing_count > 0:
                    print(f"[OK] Job {job.id} ({idx}/{total_jobs}): Already migrated ({existing_count} logs)")
                    continue
                
                print(f"[MIGRATE] Job {job.id} ({idx}/{total_jobs}): Migrating {len(legacy_logs)} logs...")
                
                if not dry_run:
                    # Create JobLog entries
                    for log_data in legacy_logs:
                        # Parse timestamp
                        timestamp_str = log_data.get("timestamp")
                        try:
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        except:
                            timestamp = datetime.now(timezone.utc)
                        
                        log_entry = JobLog(
                            job_id=job.id,
                            timestamp=timestamp,
                            level=log_data.get("level", "info"),
                            prefix=log_data.get("prefix", "System"),
                            message=log_data.get("message", ""),
                            meta=log_data.get("metadata", {})
                        )
                        db.add(log_entry)
                    
                    db.commit()
                    total_logs_migrated += len(legacy_logs)
                    print(f"[OK] Job {job.id}: Migrated {len(legacy_logs)} logs")
                else:
                    print(f"[DRY RUN] Would migrate {len(legacy_logs)} logs for job {job.id}")
                    total_logs_migrated += len(legacy_logs)
                
            except json.JSONDecodeError as e:
                print(f"[ERROR] Job {job.id}: Failed to parse JSON logs: {e}")
                continue
            except Exception as e:
                db.rollback()
                print(f"[ERROR] Job {job.id}: Migration failed: {e}")
                continue
        
        print("=" * 60)
        if dry_run:
            print(f"[DRY RUN] Would migrate {total_logs_migrated} total logs from {total_jobs} jobs")
            print("Run without --dry-run to apply changes")
        else:
            print(f"[SUCCESS] Migrated {total_logs_migrated} total logs from {total_jobs} jobs")
            print("\nNote: Legacy JSON logs are preserved in StoryJob.logs for rollback safety")
            print("You can drop the 'logs' column after verifying the migration")
        
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate logs to job_logs table")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without making changes")
    args = parser.parse_args()
    
    if args.dry_run:
        print("[DRY RUN MODE] - No changes will be made")
        print()
    
    migrate_logs(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
