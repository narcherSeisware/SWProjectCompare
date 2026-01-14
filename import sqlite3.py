import sqlite3
import SWConnect
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Set

def compare_seismic_files(database_paths: List[str]) -> Dict[str, List[str]]:
    """
    Compare seismic tables across multiple databases to find duplicate filenames.
    
    Args:
        database_paths: List of paths to SQLite database files
        
    Returns:
        Dictionary mapping filename to list of databases containing that file
    """
    file_to_databases = defaultdict(list)
    
    for db_path in database_paths:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Query the seismic table for filenames
            cursor.execute("SELECT DISTINCT filename FROM seismic")
            
            for row in cursor.fetchall():
                filename = row[0]
                if filename:
                    file_to_databases[filename].append(db_path)
            
            conn.close()
            
        except sqlite3.Error as e:
            print(f"Error reading {db_path}: {e}")
        except Exception as e:
            print(f"Unexpected error with {db_path}: {e}")
    
    # Filter to only duplicates (files in more than one database)
    duplicates = {
        filename: dbs 
        for filename, dbs in file_to_databases.items() 
        if len(dbs) > 1
    }
    
    return duplicates


def main():
    # Example usage
    databases = [
        "database1.db",
        "database2.db",
        "database3.db"
    ]
    
    print("Searching for duplicate seismic files across databases...")
    duplicates = compare_seismic_files(databases)
    
    if duplicates:
        print(f"\nFound {len(duplicates)} duplicate file(s):\n")
        for filename, dbs in duplicates.items():
            print(f"File: {filename}")
            print(f"  Found in {len(dbs)} databases:")
            for db in dbs:
                print(f"    - {db}")
            print()
    else:
        print("\nNo duplicate files found.")


if __name__ == "__main__":
    main()