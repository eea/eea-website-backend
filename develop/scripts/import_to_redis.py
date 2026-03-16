#!/usr/bin/env python3
"""
Import v6-new_urls.csv into Redis
Key: old_url
Value: new_url
"""

import argparse
import csv
import sys
from pathlib import Path

try:
    import redis  # type: ignore
except ImportError:
    print("Error: redis module not installed", file=sys.stderr)
    print("Please install it with: pip install redis", file=sys.stderr)
    sys.exit(1)


def import_to_redis(
    csv_file,
    redis_host='localhost',
    redis_port=6379,
    redis_db=0,
    redis_password=None,
    key_prefix='',
    cleanup=False
):
    """
    Import CSV redirects into Redis.

    Args:
        csv_file: Path to CSV file
        redis_host: Redis host (default: localhost)
        redis_port: Redis port (default: 6379)
        redis_db: Redis database number (default: 0)
        redis_password: Redis password (default: None)
        key_prefix: Prefix for Redis keys (default: '')
        cleanup: Delete existing keys with prefix before importing (default: False)
    """
    # Connect to Redis
    print(f"Connecting to Redis at {redis_host}:{redis_port} (db: {redis_db})...")
    try:
        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True
        )
        # Test connection
        r.ping()
        print("  Connected successfully")
    except redis.ConnectionError as e:
        print(f"Error: Could not connect to Redis: {e}", file=sys.stderr)
        sys.exit(1)

    # Cleanup existing keys if requested
    if cleanup:
        print(f"Cleaning up existing keys with prefix '{key_prefix}'...")
        pattern = f"{key_prefix}*" if key_prefix else "*"
        existing_keys = r.keys(pattern)
        if existing_keys:
            deleted_count = r.delete(*existing_keys)
            print(f"  Deleted {deleted_count} existing keys")
        else:
            print("  No existing keys found")

    # Read CSV and import to Redis
    print(f"Reading {csv_file}...")
    imported_count = 0
    empty_new_url_count = 0
    invalid_new_url_count = 0

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        # Use pipeline for better performance
        pipe = r.pipeline()
        batch_size = 1000
        batch_count = 0

        for row in reader:
            old_url = row['old_url']
            new_url = row['new_url'].strip()

            # Validate new_url: must be a valid path (starts with /) or URL (starts with http)
            # If not valid, set to empty string
            if new_url and not (new_url.startswith('/') or new_url.startswith('http://') or new_url.startswith('https://')):
                invalid_new_url_count += 1
                new_url = ''

            # Store in Redis with key prefix
            key = f"{key_prefix}{old_url}"

            # Store the new_url value (even if empty)
            pipe.set(key, new_url)
            batch_count += 1
            imported_count += 1

            if not new_url:
                empty_new_url_count += 1

            # Execute batch
            if batch_count >= batch_size:
                pipe.execute()
                pipe = r.pipeline()
                batch_count = 0
                print(f"  Imported {imported_count} entries...", end='\r')

        # Execute remaining items
        if batch_count > 0:
            pipe.execute()

    print("\nImport complete!")
    print("\nSummary:")
    print(f"  Total entries imported: {imported_count}")
    print(f"  Entries with empty new_url: {empty_new_url_count}")
    if invalid_new_url_count > 0:
        print(f"  Invalid URLs converted to empty: {invalid_new_url_count}")
    print(f"  Entries with redirects: {imported_count - empty_new_url_count}")
    if key_prefix:
        print(f"  Redis key prefix: '{key_prefix}'")
    else:
        print("  Redis key prefix: (none)")

    # Show some example keys
    print("\nExample keys in Redis:")
    keys = r.keys(f"{key_prefix}*")
    for key in sorted(keys)[:5]:
        value = r.get(key)
        display_value = value if value else '(empty)'
        print(f"  {key} -> {display_value}")

    if len(keys) > 5:
        print(f"  ... and {len(keys) - 5} more keys")


def main():
    """Main function to import CSV to Redis."""
    parser = argparse.ArgumentParser(
        description='Import CSV file into Redis'
    )
    parser.add_argument(
        'file',
        help='CSV file to import (e.g., v6-new_urls.csv)'
    )
    parser.add_argument(
        '--host',
        default='localhost',
        help='Redis host (default: localhost)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=6379,
        help='Redis port (default: 6379)'
    )
    parser.add_argument(
        '--db',
        type=int,
        default=0,
        help='Redis database number (default: 0)'
    )
    parser.add_argument(
        '--password',
        default=None,
        help='Redis password (default: None)'
    )
    parser.add_argument(
        '--prefix',
        default='',
        help='Key prefix (default: empty string)'
    )
    parser.add_argument(
        '--cleanup',
        action='store_true',
        help='Delete existing keys with prefix before importing (fresh start)'
    )

    args = parser.parse_args()

    # Get file path
    script_dir = Path(__file__).parent
    csv_file = script_dir / args.file

    # Check input file exists
    if not csv_file.exists():
        print(f"Error: {csv_file} not found", file=sys.stderr)
        sys.exit(1)

    # Import to Redis
    import_to_redis(
        csv_file,
        redis_host=args.host,
        redis_port=args.port,
        redis_db=args.db,
        redis_password=args.password,
        key_prefix=args.prefix,
        cleanup=args.cleanup
    )


if __name__ == '__main__':
    main()
