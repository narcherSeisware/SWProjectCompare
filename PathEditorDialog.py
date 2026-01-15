import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import pyodbc


class PathEditorDialog(tk.Toplevel):
    """Dialog for editing seismic line paths for a specific project"""
    
    def __init__(self, parent, line_name, projects_info):
        """
        Args:
            parent: Parent window
            line_name: Name of the seismic line to edit
            projects_info: List of dicts with project name and db connection details
        """
        super().__init__(parent)
        
        self.line_name = line_name
        self.projects_info = projects_info
        self.changes = {}  # Track changes: {project_name: new_path}
        self.project_data = {}  # Store current path data: {project_name: current_path}
        
        self.title(f"Edit Seismic Path - {line_name}")
        self.geometry("1000x600")
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        self._create_widgets()
        self._load_line_paths()
    
    def _create_widgets(self):
        """Create the dialog widgets"""
        
        # Header
        header = ttk.Frame(self)
        header.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(header, text=f"Line: {self.line_name}", 
                 font=("TkDefaultFont", 12, "bold")).pack(side="left")
        
        ttk.Label(header, text=f"Projects: {len(self.projects_info)}").pack(side="right")
        
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=10, pady=5)
        
        ttk.Button(toolbar, text="Refresh", command=self._load_line_paths).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Clear All Changes", command=self._clear_changes).pack(side="left")
        
        # Grid container with scrollbar
        grid_container = ttk.Frame(self)
        grid_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create canvas and scrollbar
        canvas = tk.Canvas(grid_container)
        scrollbar = ttk.Scrollbar(grid_container, orient="vertical", command=canvas.yview)
        
        self.grid_frame = ttk.Frame(canvas)
        self.grid_frame.bind("<Configure>", 
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Mouse wheel scrolling
        canvas.bind_all("<MouseWheel>", 
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        
        # Bottom buttons
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=10)
        
        self.status_var = tk.StringVar(value="Loading...")
        ttk.Label(bottom, textvariable=self.status_var).pack(side="left")
        
        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(side="right", padx=5)
        ttk.Button(bottom, text="Save Changes", command=self._save_changes).pack(side="right")
    
    def _load_line_paths(self):
        """Load current paths from database for each project"""
        self.status_var.set("Loading paths from database...")
        self.project_data.clear()
        
        for proj_info in self.projects_info:
            project_name = proj_info['name']
            
            try:
                conn = self._connect_to_db(proj_info)
                if not conn:
                    self.project_data[project_name] = ""
                    continue
                
                cursor = conn.cursor()
                
                # Get current file path for this line in this project
                cursor.execute("""
                    SELECT FileName 
                    FROM dbo.SeismicFile 
                    WHERE LineName = ?
                """, self.line_name)
                
                result = cursor.fetchone()
                file_path = result[0] if result and result[0] else ""
                self.project_data[project_name] = file_path
                
                conn.close()
                
            except Exception as e:
                print(f"Error loading {project_name}: {e}")
                self.project_data[project_name] = ""
        
        self._populate_grid()
        self.status_var.set(f"Loaded paths from {len(self.project_data)} projects")
    
    def _populate_grid(self):
        """Populate the grid with project names and path editors"""
        
        # Clear existing widgets
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        
        # Header row
        ttk.Label(self.grid_frame, text="Project Name", 
                 font=("TkDefaultFont", 9, "bold")).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Label(self.grid_frame, text="Current Path", 
                 font=("TkDefaultFont", 9, "bold")).grid(row=0, column=1, padx=5, pady=5, sticky="w")
        ttk.Label(self.grid_frame, text="New Path", 
                 font=("TkDefaultFont", 9, "bold")).grid(row=0, column=2, padx=5, pady=5, sticky="w")
        ttk.Label(self.grid_frame, text="", 
                 font=("TkDefaultFont", 9, "bold")).grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Separator(self.grid_frame, orient="horizontal").grid(
            row=1, column=0, columnspan=4, sticky="ew", pady=5)
        
        # Data rows
        row = 2
        for proj_info in self.projects_info:
            project_name = proj_info['name']
            current_path = self.project_data.get(project_name, "")
            
            # Project name (read-only)
            ttk.Label(self.grid_frame, text=project_name).grid(
                row=row, column=0, padx=5, pady=3, sticky="w")
            
            # Current path (read-only, truncated if too long)
            display_path = current_path if len(current_path) < 50 else "..." + current_path[-47:]
            current_label = ttk.Label(self.grid_frame, text=display_path, 
                                     foreground="gray")
            current_label.grid(row=row, column=1, padx=5, pady=3, sticky="w")
            
            # Tooltip for full path
            if current_path:
                self._create_tooltip(current_label, current_path)
            
            # New path entry (editable)
            new_path_var = tk.StringVar(value=self.changes.get(project_name, ""))
            entry = ttk.Entry(self.grid_frame, textvariable=new_path_var, width=50)
            entry.grid(row=row, column=2, padx=5, pady=3, sticky="ew")
            
            # Track changes
            new_path_var.trace('w', 
                lambda *args, pn=project_name, var=new_path_var: 
                    self._on_path_changed(pn, var))
            
            # Browse button
            browse_btn = ttk.Button(self.grid_frame, text="...", width=3,
                command=lambda pn=project_name, var=new_path_var: 
                    self._browse_file(pn, var))
            browse_btn.grid(row=row, column=3, padx=5, pady=3)
            
            row += 1
        
        # Configure column weights
        self.grid_frame.columnconfigure(2, weight=1)
    
    def _create_tooltip(self, widget, text):
        """Create a tooltip that shows on hover"""
        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            label = ttk.Label(tooltip, text=text, background="lightyellow", 
                            relief="solid", borderwidth=1, padding=5)
            label.pack()
            widget.tooltip = tooltip
        
        def on_leave(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()
                del widget.tooltip
        
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
    
    def _on_path_changed(self, project_name, var):
        """Track when a path is changed"""
        new_path = var.get().strip()
        if new_path:
            self.changes[project_name] = new_path
        elif project_name in self.changes:
            del self.changes[project_name]
        
        # Update status
        if self.changes:
            self.status_var.set(f"{len(self.changes)} path(s) modified")
        else:
            self.status_var.set(f"Loaded paths from {len(self.project_data)} projects")
    
    def _browse_file(self, project_name, path_var):
        """Open folder browser to select new path"""
        current = path_var.get()
        initial_dir = os.path.dirname(current) if current and os.path.exists(os.path.dirname(current)) else ""
        
        folder = filedialog.askdirectory(
            title=f"Select folder for {project_name}",
            initialdir=initial_dir
        )
        
        if folder:
            path_var.set(folder)
    
    def _clear_changes(self):
        """Clear all pending changes"""
        if self.changes and not messagebox.askyesno("Confirm", 
            "Clear all unsaved changes?"):
            return
        
        self.changes.clear()
        self._populate_grid()
        self.status_var.set(f"Loaded paths from {len(self.project_data)} projects")
    
    def _save_changes(self):
        """Save path changes to database"""
        if not self.changes:
            messagebox.showinfo("No Changes", "No paths have been modified.")
            return
        
        # Confirm changes
        msg = f"Save {len(self.changes)} path change(s) to database?"
        if not messagebox.askyesno("Confirm Save", msg):
            return
        
        success_count = 0
        errors = []
        
        for project_name, new_path in self.changes.items():
            # Find the project info
            proj_info = next((p for p in self.projects_info if p['name'] == project_name), None)
            if not proj_info:
                errors.append(f"{project_name}: Project info not found")
                continue
            
            try:
                conn = self._connect_to_db(proj_info)
                if not conn:
                    errors.append(f"{project_name}: Could not connect to database")
                    continue
                
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE dbo.SeismicFile 
                    SET FileName = ? 
                    WHERE LineName = ?
                """, new_path, self.line_name)
                
                conn.commit()
                conn.close()
                success_count += 1
                
            except Exception as e:
                errors.append(f"{project_name}: {str(e)[:100]}")
        
        # Show results
        if errors:
            error_msg = "\n".join(errors)
            messagebox.showwarning("Partial Success", 
                f"Updated {success_count} of {len(self.changes)} path(s)\n\nErrors:\n{error_msg}")
        else:
            messagebox.showinfo("Success", 
                f"Updated {success_count} path(s)")
        
        # Reload data and clear changes
        self.changes.clear()
        self._load_line_paths()
    
    def _connect_to_db(self, proj_info):
        """Connect to a project database"""
        driver = proj_info['driver']
        encrypt = proj_info['encrypt']
        db_type = proj_info['db_type']
        db_path = proj_info['db_path']
        server = proj_info['server']
        directory = proj_info['directory']
        
        # Use same connection logic as main app
        if db_type == 1:  # SQL Server
            db_name = os.path.splitext(os.path.basename(db_path))[0]
            try:
                conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={db_name};Trusted_Connection=yes;{encrypt}"
                return pyodbc.connect(conn_str, timeout=10)
            except:
                try:
                    conn_str = f"DRIVER={{{driver}}};SERVER={server};AttachDbFilename={db_path};Trusted_Connection=yes;{encrypt}"
                    return pyodbc.connect(conn_str, timeout=10)
                except:
                    return None
        else:  # LocalDB
            localdb = f'(localdb)\\{server}' if server else '(localdb)\\SeisWare_16'
            proj_name = os.path.basename(directory) if directory else None
            
            if proj_name:
                try:
                    conn_str = f"DRIVER={{{driver}}};SERVER={localdb};DATABASE={proj_name};Integrated Security=true;{encrypt}"
                    return pyodbc.connect(conn_str, timeout=10)
                except:
                    pass
            
            try:
                conn_str = f"DRIVER={{{driver}}};SERVER={localdb};DATABASE=master;Integrated Security=true;{encrypt}"
                master = pyodbc.connect(conn_str, timeout=10)
                cursor = master.cursor()
                cursor.execute("""
                    SELECT d.name FROM sys.databases d
                    INNER JOIN sys.master_files mf ON d.database_id = mf.database_id
                    WHERE mf.physical_name LIKE ? AND mf.type = 0
                """, f"{os.path.dirname(db_path)}%")
                result = cursor.fetchone()
                master.close()
                
                if result:
                    conn_str = f"DRIVER={{{driver}}};SERVER={localdb};DATABASE={result[0]};Integrated Security=true;{encrypt}"
                    return pyodbc.connect(conn_str, timeout=10)
            except:
                pass
            
            return None