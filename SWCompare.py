#SW Database Seismic File Comparison Script

import SWConnect
import pyodbc
from collections import defaultdict
from typing import List, Dict

def compare_seismic_files(projects: List) -> Dict[str, List[str]]:
    """
    Compare seismic data across multiple SeisWare projects by querying SQL databases directly.
    
    Args:
        projects: List of SeisWare Project objects
        
    Returns:
        Dictionary mapping filename to list of project names containing that file
    """
    file_to_projects = defaultdict(list)
    skipped_projects = []
    
    for project in projects:
        project_name = project.Name()
        database_name = project.DatabaseName()
        server_name = project.ServerName()
        
        # Try to get database path for LocalDB projects
        if not database_name and project.DatabaseType() != 1:
            # Try alternate methods to get database info
            try:
                # Check if there's a Path() method
                if hasattr(project, 'Path'):
                    project_path = project.Path()
                    if project_path:
                        # Construct typical LocalDB path
                        database_name = f"{project_path}\\DB\\db.mdf"
                        print(f"  Constructed LocalDB path: {database_name}")
            except:
                pass
        
        if not database_name:
            print(f"Skipping {project_name} (missing database name)")
            skipped_projects.append((project_name, "Missing database name"))
            continue
        
        print(f"Processing project: {project_name}")
        print(f"  Raw database name: {database_name}")
        
        # Try to fix corrupted database names (missing backslashes)
        # Pattern: MnarcherTablelandDepth(shared) -> M:\narcher\TablelandDepth(shared)\DB\db.mdf
        if database_name and not ('\\' in database_name or ':' in database_name):
            import re
            # Check if it starts with a drive letter pattern (e.g., Mnarcher, Ctemp)
            match = re.match(r'^([A-Z])([a-z]+)', database_name)
            if match:
                drive = match.group(1)
                first_folder = match.group(2)  # e.g., 'narcher'
                rest = database_name[len(drive) + len(first_folder):]  # Everything after first folder
                
                # Reconstruct as Drive:\FirstFolder\Rest\DB\db.mdf (standard SeisWare structure)
                reconstructed = f"{drive}:\\{first_folder}\\{rest}\\DB\\db.mdf"
                print(f"  Attempting to reconstruct path: {reconstructed}")
                database_name = reconstructed
        
        # Skip if database name still looks corrupted
        if ' ' in database_name and '\\' not in database_name and ':' not in database_name and not database_name.endswith('.mdf'):
            print(f"  Skipping - database name appears corrupted (no path separators)")
            skipped_projects.append((project_name, "Corrupted database name"))
            continue
        
        try:
            # Determine connection string based on database type
            if project.DatabaseType() == 1:  # SQL Server
                if not server_name:
                    print(f"Skipping {project_name} (missing server name)")
                    skipped_projects.append((project_name, "Missing server name"))
                    continue
                print(f"  Type: SQL Server (Server: {server_name})")
                
                # If database_name is a file path, attach it
                if '\\' in database_name or ':' in database_name or database_name.endswith('.mdf'):
                    print(f"  Detected as MDF file path")
                    
                    # Try multiple connection strategies
                    connection_successful = False
                    
                    # Strategy 1: Try LocalDB
                    try:
                        conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER=(localdb)\\MSSQLLocalDB;AttachDbFilename={database_name};Integrated Security=true;"
                        print(f"  Attempting LocalDB connection...")
                        conn = pyodbc.connect(conn_str, timeout=10)
                        connection_successful = True
                    except Exception as localdb_error:
                        print(f"  LocalDB failed: {str(localdb_error)[:100]}")
                    
                    # Strategy 2: Try original server with AttachDbFilename
                    if not connection_successful:
                        try:
                            conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server_name};AttachDbFilename={database_name};Trusted_Connection=yes;"
                            print(f"  Trying original server with attach...")
                            conn = pyodbc.connect(conn_str, timeout=10)
                            connection_successful = True
                        except Exception as attach_error:
                            print(f"  Attach failed: {str(attach_error)[:100]}")
                    
                    # Strategy 3: Extract database name from path and try regular connection
                    if not connection_successful:
                        import os
                        # Get the project folder name from path (e.g., TablelandDepth(shared))
                        path_parts = database_name.replace('\\DB\\db.mdf', '').split('\\')
                        logical_db_name = path_parts[-1] if path_parts else None
                        
                        if logical_db_name:
                            try:
                                conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server_name};DATABASE={logical_db_name};Trusted_Connection=yes;"
                                print(f"  Trying logical database name: {logical_db_name}")
                                conn = pyodbc.connect(conn_str, timeout=10)
                                connection_successful = True
                            except Exception as logical_error:
                                print(f"  Logical name failed: {str(logical_error)[:100]}")
                    
                    if not connection_successful:
                        raise Exception("All connection strategies failed")
                else:
                    # Regular database name
                    print(f"  Detected as database name")
                    conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server_name};DATABASE={database_name};Trusted_Connection=yes;"
                    print(f"  Attempting connection...")
                    conn = pyodbc.connect(conn_str, timeout=10)
            else:  # LocalDB
                print(f"  Type: LocalDB")
                # LocalDB connection string format
                if '\\' in database_name or ':' in database_name or database_name.endswith('.mdf'):
                    conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER=(localdb)\\MSSQLLocalDB;AttachDbFilename={database_name};Integrated Security=true;"
                else:
                    conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER=(localdb)\\MSSQLLocalDB;DATABASE={database_name};Trusted_Connection=yes;"
                print(f"  Attempting connection...")
                conn = pyodbc.connect(conn_str, timeout=10)
            
            # Query the SeismicLine table
            query = """
                SELECT DISTINCT LineName 
                FROM dbo.SeismicLine
                WHERE LineName IS NOT NULL AND Active = 1
            """
            
            cursor = conn.cursor()
            cursor.execute(query)
            
            count = 0
            for row in cursor.fetchall():
                filename = row[0]
                if filename:
                    file_to_projects[filename].append(project_name)
                    count += 1
            
            print(f"  Found {count} seismic lines")
            conn.close()
            
        except pyodbc.Error as e:
            error_msg = str(e)[:200]
            print(f"SQL Error reading project {project_name}: {error_msg}")
            skipped_projects.append((project_name, f"SQL Error: {error_msg}"))
        except Exception as e:
            error_msg = str(e)[:200]
            print(f"Unexpected error with project {project_name}: {error_msg}")
            skipped_projects.append((project_name, f"Error: {error_msg}"))
    
    # Print summary of skipped projects
    if skipped_projects:
        print(f"\n\n=== Skipped {len(skipped_projects)} project(s) ===")
        for proj_name, reason in skipped_projects:
            print(f"  {proj_name}: {reason}")
    
    # Filter to only duplicates (files in more than one project)
    duplicates = {
        filename: projects 
        for filename, projects in file_to_projects.items() 
        if len(projects) > 1
    }
    
    return duplicates


def main():
    # Example usage
    project_list = SWConnect.SWprojlist()
    for project in project_list:
        print("\n" + project.Name())
        if project.DatabaseType() == 1:
            print("    SQL Server Database: " + project.DatabaseName())
        else:
            print("    Localdb")
        if not project.ServerName():
            print("    Server Error")
        else:
            print("    Server Name: " + project.ServerName())
    
    print("\nSearching for duplicate seismic files across projects...")
    duplicates = compare_seismic_files(project_list)
    
    if duplicates:
        print(f"\nFound {len(duplicates)} duplicate file(s):\n")
        for filename, projects in duplicates.items():
            print(f"File: {filename}")
            print(f"  Found in {len(projects)} project(s):")
            for proj in projects:
                print(f"    - {proj}")
            print()
    else:
        print("\nNo duplicate files found.")


if __name__ == "__main__":
    main()