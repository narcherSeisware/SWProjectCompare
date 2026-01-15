#SW Database Seismic File Comparison Script

import SWConnect
import pyodbc
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import List, Dict
import os

def load_project_database_paths(xml_path: str) -> Dict[str, Dict[str, str]]:
    """
    Load project database information from SeisWare ProjectList.xml
    
    Returns:
        Dictionary mapping project name to database info (path, server, type)
    """
    project_db_info = {}
    
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        for project in root.findall('.//Project'):
            name_elem = project.find('Name')
            db_file_elem = project.find('DatabaseFile')
            server_elem = project.find('ServerName')
            db_type_elem = project.find('DbType')
            directory_elem = project.find('Directory')
            
            if name_elem is not None and name_elem.text:
                name = name_elem.text
                db_path = db_file_elem.text if db_file_elem is not None and db_file_elem.text else None
                server = server_elem.text if server_elem is not None else None
                db_type_text = db_type_elem.text if db_type_elem is not None else 'LocalDb'
                directory = directory_elem.text if directory_elem is not None else None
                
                # Convert DbType to numeric (1 = SQL Server, 0 = LocalDB)
                db_type = 1 if db_type_text == 'SqlServer' else 0
                
                # If no database file specified but it's LocalDB, construct the path
                if not db_path and db_type == 0 and directory:
                    db_path = os.path.join(directory, 'DB', 'db.mdf')
                
                project_db_info[name] = {
                    'path': db_path,
                    'server': server,
                    'type': db_type,
                    'directory': directory
                }
                
    except Exception as e:
        print(f"Error reading XML file: {e}")
    
    return project_db_info


def get_available_sql_driver():
    """
    Find the best available SQL Server ODBC driver
    
    Returns:
        Driver name string or None if no driver found
    """
    drivers = pyodbc.drivers()
    # Preferred order of drivers
    preferred_drivers = [
        'ODBC Driver 18 for SQL Server',
        'ODBC Driver 17 for SQL Server',
        'ODBC Driver 13 for SQL Server',
        'ODBC Driver 11 for SQL Server',
        'SQL Server Native Client 11.0',
        'SQL Server'
    ]
    
    for preferred in preferred_drivers:
        if preferred in drivers:
            return preferred
    
    return None


def compare_seismic_files(projects: List) -> Dict[str, List[str]]:
    """
    Compare seismic data across multiple SeisWare projects by querying SQL databases directly.
    
    Args:
        projects: List of SeisWare Project objects
        
    Returns:
        Dictionary mapping filename to list of project names containing that file
    """
    file_to_projects = defaultdict(list)
    line_details = {}  # Add this to store line details
    skipped_projects = []
    
    # Check for available SQL Server driver
    sql_driver = get_available_sql_driver()
    if not sql_driver:
        print("ERROR: No SQL Server ODBC driver found!")
        print("Available drivers:", pyodbc.drivers())
        return {}, {}
    
    print(f"Using SQL Server driver: {sql_driver}\n")
    
    # Add encryption settings for ODBC Driver 18
    encrypt_setting = "Encrypt=no;" if "18" in sql_driver else ""
    
    # Load database paths from XML - path is dynamic based on current user
    username = os.getenv('USERNAME')
    xml_path = rf"C:\Users\{username}\AppData\Roaming\SeisWare\SeisWare\Support\ProjectList.xml"
    project_db_info = load_project_database_paths(xml_path)
    print(f"Loaded database info for {len(project_db_info)} projects from XML\n")
    
    for project in projects:
        project_name = project.Name()
        
        # Get database info from XML
        db_info = project_db_info.get(project_name)
        if not db_info:
            print(f"Skipping {project_name} (not found in XML)")
            skipped_projects.append((project_name, "Not found in XML"))
            continue
        
        database_path = db_info.get('path')
        server_name = db_info.get('server')
        db_type = db_info.get('type')
        directory = db_info.get('directory')
        
        # Skip if no database path and no directory to construct one
        if not database_path and not directory:
            print(f"Skipping {project_name} (no database path or directory in XML)")
            skipped_projects.append((project_name, "No database path in XML"))
            continue
        
        print(f"Processing project: {project_name}")
        print(f"  Database path: {database_path}")
        print(f"  Server: {server_name}")
        print(f"  Type: {'SQL Server' if db_type == 1 else 'LocalDB'}")
        
        try:
            # Connect to database (using existing connection logic)
            conn = _connect_to_database(sql_driver, encrypt_setting, db_type, database_path, server_name, directory)
            
            if not conn:
                print(f"  Could not connect to database")
                skipped_projects.append((project_name, "Could not connect"))
                continue
            
            cursor = conn.cursor()
            
            # First, get the owner name mapping
            owner_map = {}
            try:
                cursor.execute("SELECT ID, Name FROM dbo.SeisWareUser")
                for row in cursor.fetchall():
                    owner_map[row[0]] = row[1]
                print(f"  Loaded {len(owner_map)} user names")
            except Exception as e:
                print(f"  Warning: Could not load user names: {str(e)[:100]}")
            
            # Query the SeismicLine table
            query = """
                SELECT DISTINCT LineName, OwnerID, RowChangedDate
                FROM dbo.SeismicLine
                WHERE LineName IS NOT NULL AND Active = 1
            """
            
            cursor.execute(query)
            
            count = 0
            for row in cursor.fetchall():
                filename = row[0]
                owner_id = row[1]
                last_changed = row[2]
                
                if filename:
                    file_to_projects[filename].append(project_name)
                    count += 1
                    
                    # Store line details only once (from first project that has it)
                    if filename not in line_details:
                        owner_name = owner_map.get(owner_id, f"Unknown ({owner_id})")
                        line_details[filename] = {
                            'Line Name': filename,
                            'Owner': owner_name,
                            'Last Changed': str(last_changed) if last_changed else 'N/A'
                        }
            
            print(f"  Found {count} seismic lines")
            conn.close()
            
        except pyodbc.Error as e:
            error_msg = str(e)[:200]
            print(f"  SQL Error: {error_msg}")
            skipped_projects.append((project_name, f"SQL Error: {error_msg}"))
        except Exception as e:
            error_msg = str(e)[:200]
            print(f"  Unexpected error: {error_msg}")
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
    
    return duplicates, line_details


def _connect_to_database(sql_driver, encrypt_setting, db_type, database_path, server_name, directory):
    """Helper function to connect to a database"""
    conn = None
    
    if db_type == 1:  # SQL Server
        if not server_name:
            return None
        
        # Try logical database name first (most reliable for already-attached databases)
        db_name = os.path.splitext(os.path.basename(database_path))[0]
        try:
            conn_str = f"DRIVER={{{sql_driver}}};SERVER={server_name};DATABASE={db_name};Trusted_Connection=yes;{encrypt_setting}"
            print(f"  Trying logical database name: {db_name}")
            conn = pyodbc.connect(conn_str, timeout=10)
        except Exception as logical_error:
            # Try attaching the MDF file
            try:
                conn_str = f"DRIVER={{{sql_driver}}};SERVER={server_name};AttachDbFilename={database_path};Trusted_Connection=yes;{encrypt_setting}"
                print(f"  Logical name failed, trying attach...")
                conn = pyodbc.connect(conn_str, timeout=10)
            except Exception as attach_error:
                # Try LocalDB as last resort
                try:
                    conn_str = f"DRIVER={{{sql_driver}}};SERVER=(localdb)\\MSSQLLocalDB;AttachDbFilename={database_path};Integrated Security=true;{encrypt_setting}"
                    print(f"  Attach failed, trying LocalDB...")
                    conn = pyodbc.connect(conn_str, timeout=10)
                except:
                    pass
    else:  # LocalDB
        # For LocalDB, use (localdb)\{server_name} format
        if server_name:
            localdb_server = f'(localdb)\\{server_name}'
        else:
            # Default to (localdb)\SeisWare_110
            localdb_server = '(localdb)\\SeisWare_110'
        
        # Extract project folder name for database name
        if directory:
            project_folder_name = os.path.basename(directory)
        else:
            path_parts = database_path.replace('\\DB\\db.mdf', '').split('\\')
            project_folder_name = path_parts[-1] if path_parts else None
        
        # Strategy 1: Try project folder name as database name
        if project_folder_name:
            try:
                conn_str = f"DRIVER={{{sql_driver}}};SERVER={localdb_server};DATABASE={project_folder_name};Integrated Security=true;{encrypt_setting}"
                print(f"  Trying project folder name as database: {project_folder_name}")
                conn = pyodbc.connect(conn_str, timeout=10)
            except Exception as folder_error:
                print(f"  Project folder name failed: {str(folder_error)[:100]}")
        
        # Strategy 2: Query the server to find the actual database name by file path
        if not conn:
            try:
                # Connect to master database to query for attached databases
                conn_str = f"DRIVER={{{sql_driver}}};SERVER={localdb_server};DATABASE=master;Integrated Security=true;{encrypt_setting}"
                master_conn = pyodbc.connect(conn_str, timeout=10)
                cursor = master_conn.cursor()
                
                # Find database by physical file path (try exact match first)
                cursor.execute("""
                    SELECT d.name 
                    FROM sys.databases d
                    INNER JOIN sys.master_files mf ON d.database_id = mf.database_id
                    WHERE mf.physical_name = ?
                    AND mf.type = 0
                """, database_path)
                
                result = cursor.fetchone()
                
                # If not found, try looking for similar paths (db.mdf vs localdb.mdf)
                if not result:
                    # Get directory path and try to find any mdf in that DB folder
                    db_folder = os.path.dirname(database_path)
                    cursor.execute("""
                        SELECT d.name, mf.physical_name
                        FROM sys.databases d
                        INNER JOIN sys.master_files mf ON d.database_id = mf.database_id
                        WHERE mf.physical_name LIKE ?
                        AND mf.type = 0
                    """, f"{db_folder}%")
                    result = cursor.fetchone()
                    if result:
                        print(f"  Found database with alternate file: {result[1]}")
                
                master_conn.close()
                
                if result:
                    actual_db_name = result[0]
                    print(f"  Found attached database: {actual_db_name} on server {localdb_server}")
                    conn_str = f"DRIVER={{{sql_driver}}};SERVER={localdb_server};DATABASE={actual_db_name};Integrated Security=true;{encrypt_setting}"
                    conn = pyodbc.connect(conn_str, timeout=10)
                else:
                    # Database not found, try attaching
                    print(f"  Database not found on {localdb_server}, trying to attach...")
                    conn_str = f"DRIVER={{{sql_driver}}};SERVER={localdb_server};AttachDbFilename={database_path};Integrated Security=true;{encrypt_setting}"
                    conn = pyodbc.connect(conn_str, timeout=10)
                    
            except Exception as query_error:
                print(f"  Query failed: {str(query_error)[:100]}")
        
        # Strategy 3: Try alternate LocalDB instances
        if not conn:
            alternate_servers = ['(localdb)\\MSSQLLocalDB', '(localdb)\\SeisWare_110', '(localdb)\\SeisWare_15', '(localdb)\\v11.0']
            for alt_server in alternate_servers:
                if alt_server != localdb_server:
                    try:
                        # First try with project folder name
                        if project_folder_name:
                            conn_str = f"DRIVER={{{sql_driver}}};SERVER={alt_server};DATABASE={project_folder_name};Integrated Security=true;{encrypt_setting}"
                            print(f"  Trying {project_folder_name} on {alt_server}...")
                            conn = pyodbc.connect(conn_str, timeout=10)
                            break
                    except:
                        try:
                            # Try querying this server
                            conn_str = f"DRIVER={{{sql_driver}}};SERVER={alt_server};DATABASE=master;Integrated Security=true;{encrypt_setting}"
                            master_conn = pyodbc.connect(conn_str, timeout=10)
                            cursor = master_conn.cursor()
                            cursor.execute("""
                                SELECT d.name 
                                FROM sys.databases d
                                INNER JOIN sys.master_files mf ON d.database_id = mf.database_id
                                WHERE mf.physical_name = ?
                                AND mf.type = 0
                            """, database_path)
                            result = cursor.fetchone()
                            master_conn.close()
                            
                            if result:
                                actual_db_name = result[0]
                                print(f"  Found on alternate server {alt_server}: {actual_db_name}")
                                conn_str = f"DRIVER={{{sql_driver}}};SERVER={alt_server};DATABASE={actual_db_name};Integrated Security=true;{encrypt_setting}"
                                conn = pyodbc.connect(conn_str, timeout=10)
                                break
                        except:
                            continue
        
        # Strategy 4: If still no connection, list what databases are available on the primary server for debugging
        if not conn:
            try:
                conn_str = f"DRIVER={{{sql_driver}}};SERVER={localdb_server};DATABASE=master;Integrated Security=true;{encrypt_setting}"
                master_conn = pyodbc.connect(conn_str, timeout=10)
                cursor = master_conn.cursor()
                cursor.execute("SELECT name FROM sys.databases WHERE name NOT IN ('master', 'tempdb', 'model', 'msdb')")
                available_dbs = [row[0] for row in cursor.fetchall()]
                master_conn.close()
                print(f"  Available databases on {localdb_server}: {available_dbs}")
                
                # Try fuzzy matching - find database names that contain the project name
                for db in available_dbs:
                    if project_folder_name and (project_folder_name.lower() in db.lower() or db.lower() in project_folder_name.lower()):
                        try:
                            conn_str = f"DRIVER={{{sql_driver}}};SERVER={localdb_server};DATABASE={db};Integrated Security=true;{encrypt_setting}"
                            print(f"  Trying fuzzy match: {db}")
                            conn = pyodbc.connect(conn_str, timeout=10)
                            break
                        except:
                            continue
            except Exception as list_error:
                print(f"  Could not list databases: {str(list_error)[:100]}")
    
    return conn


def main():
    # Example usage
    project_list = SWConnect.SWprojlist()
    
    print("\nSearching for duplicate seismic files across projects...")
    duplicates, line_details = compare_seismic_files(project_list)
    
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