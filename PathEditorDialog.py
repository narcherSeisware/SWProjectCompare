import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import threading

# Add the path to SeisWare SDK if needed
# sys.path.append(r'C:\Program Files\Seisware\SeisWare\bin')

try:
    import SeisWare
    from SWConnect import SWconnect
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    print("Warning: SeisWare SDK not available. Will use direct database updates.")


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
        self.geometry("1200x600")
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        self._create_widgets()
        self._show_loading_screen()
        
        # Start loading in background after a brief delay to ensure loading screen is visible
        self.after(50, lambda: threading.Thread(target=self._load_line_paths_thread, daemon=True).start())
    
    def _show_loading_screen(self):
        """Show a loading overlay while connecting to projects"""
        # Create overlay frame
        self.loading_frame = ttk.Frame(self)
        self.loading_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        
        # Semi-transparent background effect (use a light gray)
        canvas = tk.Canvas(self.loading_frame, bg='#f0f0f0', highlightthickness=0)
        canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        
        # Center content
        center_frame = ttk.Frame(self.loading_frame)
        center_frame.place(relx=0.5, rely=0.5, anchor='center')
        
        ttk.Label(center_frame, text="Connecting to projects...", 
                 font=("TkDefaultFont", 12, "bold")).pack(pady=(0, 20))
        
        self.loading_progress = ttk.Progressbar(center_frame, mode='indeterminate', length=300)
        self.loading_progress.pack(pady=10)
        self.loading_progress.start()
        
        self.loading_status = tk.StringVar(value="Initializing...")
        ttk.Label(center_frame, textvariable=self.loading_status).pack(pady=10)
    
    def _hide_loading_screen(self):
        """Hide the loading overlay"""
        if hasattr(self, 'loading_frame'):
            self.loading_progress.stop()
            self.loading_frame.destroy()
    
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
        
        ttk.Button(toolbar, text="Refresh", command=self._refresh_paths).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Clear All Changes", command=self._clear_changes).pack(side="left")
        
        # SDK status indicator
        sdk_status = "Using SeisWare SDK" if SDK_AVAILABLE else "Using Direct DB Access"
        ttk.Label(toolbar, text=sdk_status, foreground="green" if SDK_AVAILABLE else "orange").pack(side="right", padx=10)
        
        # Global folder selector (above grid)
        folder_frame = ttk.LabelFrame(self, text="Apply Folder to All Projects", padding=10)
        folder_frame.pack(fill="x", padx=10, pady=5)
        
        self.global_folder_var = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.global_folder_var, width=60).pack(side="left", padx=5)
        ttk.Button(folder_frame, text="...", width=3, command=self._browse_global_folder).pack(side="left", padx=5)
        ttk.Button(folder_frame, text="Apply to All", command=self._apply_to_all).pack(side="left", padx=5)
        
        # Grid container with scrollbar
        grid_container = ttk.Frame(self)
        grid_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create canvas and scrollbar
        canvas = tk.Canvas(grid_container)
        scrollbar = ttk.Scrollbar(grid_container, orient="vertical", command=canvas.yview)
        
        self.grid_frame = ttk.Frame(canvas)
        
        # Bind the frame to update canvas scroll region
        self.grid_frame.bind("<Configure>", 
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        # Create window and store the window ID
        self.canvas_window = canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Bind canvas resize to update the frame width
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(self.canvas_window, width=e.width))
        
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
    
    def _load_line_paths_thread(self):
        """Load paths in background thread"""
        try:
            self._load_line_paths()
            self.after(0, self._hide_loading_screen)
        except Exception as e:
            self.after(0, lambda: self._handle_load_error(str(e)))
    
    def _handle_load_error(self, error_msg):
        """Handle errors during loading"""
        self._hide_loading_screen()
        messagebox.showerror("Loading Error", f"Failed to load paths:\n{error_msg}")
        self.destroy()
    
    def _refresh_paths(self):
        """Refresh button clicked - show loading and reload"""
        self._show_loading_screen()
        self.changes.clear()
        threading.Thread(target=self._load_line_paths_thread, daemon=True).start()
    
    def _load_line_paths(self):
        """Load current paths from database for each project"""
        self.after(0, lambda: self.loading_status.set("Loading paths from database..."))
        self.project_data.clear()
        
        total = len(self.projects_info)
        for idx, proj_info in enumerate(self.projects_info, 1):
            project_name = proj_info['name']
            
            self.after(0, lambda p=project_name, i=idx, t=total: 
                      self.loading_status.set(f"Loading {p} ({i}/{t})..."))
            
            try:
                if SDK_AVAILABLE:
                    # Use SDK to get the file path (with retry)
                    file_path = self._load_path_with_sdk_retry(project_name)
                    self.project_data[project_name] = file_path
                else:
                    # Fallback to direct database access
                    file_path = self._load_path_from_db(proj_info)
                    self.project_data[project_name] = file_path
                    
            except Exception as e:
                print(f"Error loading {project_name}: {e}")
                self.project_data[project_name] = ""
        
        self.after(0, self._populate_grid)
        self.after(0, lambda: self.status_var.set(f"Loaded paths from {len(self.project_data)} projects"))
    
    def _load_path_with_sdk_retry(self, project_name, max_retries=2):
        """Load path using SDK with retry logic for timeout errors"""
        for attempt in range(max_retries):
            try:
                self.after(0, lambda a=attempt, p=project_name: 
                          self.loading_status.set(f"Connecting to {p} (attempt {a+1})..."))
                
                login_instance = SWconnect(project_name)
                
                # Get all seismic surveys
                surveys = SeisWare.SeismicSurveyList()
                login_instance.SeismicSurveyManager().GetAll(surveys)
                
                # Find the survey with matching LineName
                file_path = ""
                for survey in surveys:
                    if survey.Name() == self.line_name:
                        # Get volumes for this survey
                        volumes = SeisWare.SeismicVolumeList()
                        login_instance.SeismicVolumeManager().GetAllForSeismicSurvey(survey.ID(), volumes)
                        
                        if volumes.size() > 0:
                            file_path = volumes.front().FilePath()
                        break
                
                del login_instance
                return file_path
                
            except RuntimeError as e:
                error_msg = str(e)
                if "operation timed out" in error_msg.lower() and attempt < max_retries - 1:
                    print(f"Timeout on attempt {attempt + 1} for {project_name}, retrying...")
                    continue
                else:
                    print(f"Error loading {project_name} after {attempt + 1} attempts: {e}")
                    return ""
            except Exception as e:
                print(f"Unexpected error loading {project_name}: {e}")
                return ""
        
        return ""
    
    def _load_path_from_db(self, proj_info):
        """Fallback method to load path directly from database"""
        import pyodbc
        
        try:
            conn = self._connect_to_db(proj_info)
            if not conn:
                return ""
            
            cursor = conn.cursor()
            cursor.execute("""
                SELECT FileName 
                FROM dbo.SeismicFile 
                WHERE LineName = ?
            """, self.line_name)
            
            result = cursor.fetchone()
            file_path = result[0] if result and result[0] else ""
            conn.close()
            return file_path
            
        except Exception as e:
            print(f"Database error: {e}")
            return ""
    
    def _populate_grid(self):
        """Populate the grid with project names and path editors"""
        
        # Clear existing widgets
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        
        # Store entry variables for "Apply to All" functionality
        self.entry_vars = {}
        
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
            
            # Current path (read-only, allow to expand)
            display_path = current_path if len(current_path) < 70 else "..." + current_path[-67:]
            current_label = ttk.Label(self.grid_frame, text=display_path, 
                                     foreground="gray")
            current_label.grid(row=row, column=1, padx=5, pady=3, sticky="ew")
            
            # Tooltip for full path
            if current_path:
                self._create_tooltip(current_label, current_path)
            
            # New path entry (editable)
            new_path_var = tk.StringVar(value=self.changes.get(project_name, ""))
            self.entry_vars[project_name] = new_path_var  # Store for "Apply to All"
            
            entry = ttk.Entry(self.grid_frame, textvariable=new_path_var, width=60)
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
        
        # Configure column weights for horizontal expansion
        self.grid_frame.columnconfigure(0, weight=0, minsize=150)  # Project name - fixed width
        self.grid_frame.columnconfigure(1, weight=1)  # Current path - expands
        self.grid_frame.columnconfigure(2, weight=2)  # New path - expands more
        self.grid_frame.columnconfigure(3, weight=0)  # Browse button - fixed width
    
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
        """Open file browser to select new path"""
        current = path_var.get()
        initial_dir = os.path.dirname(current) if current and os.path.exists(os.path.dirname(current)) else ""
        
        filename = filedialog.askopenfilename(
            title=f"Select file for {project_name}",
            initialdir=initial_dir,
            filetypes=[
                ("SEGY files", "*.sgy *.segy"),
                ("All files", "*.*")
            ]
        )
        
        if filename:
            path_var.set(filename)
    
    def _browse_global_folder(self):
        """Open folder browser for global folder selection"""
        current = self.global_folder_var.get()
        initial_dir = current if current and os.path.exists(current) else ""
        
        folder = filedialog.askdirectory(
            title="Select folder to apply to all projects",
            initialdir=initial_dir
        )
        
        if folder:
            self.global_folder_var.set(folder)
    
    def _apply_to_all(self):
        """Apply the global folder to all project entries, constructing filenames from DB fields"""
        global_folder = self.global_folder_var.get().strip()
        
        if not global_folder:
            messagebox.showwarning("No Folder Selected", 
                "Please select a folder before applying to all projects.")
            return
        
        # Confirm action
        msg = f"Apply folder to all {len(self.entry_vars)} projects?\n\nFolder: {global_folder}\nFilenames will be generated as: LineID.DispType.ProcID.sgy"
        if not messagebox.askyesno("Confirm Apply to All", msg):
            return
        
        # Apply to all entry fields with constructed filename
        count = 0
        errors = []
        
        for project_name, entry_var in self.entry_vars.items():
            try:
                # Get the project info
                proj_info = next((p for p in self.projects_info if p['name'] == project_name), None)
                if not proj_info:
                    errors.append(f"{project_name}: Project info not found")
                    continue
                
                # Query database for LineID, DispType, and ProcID
                filename = self._construct_filename(proj_info, global_folder)
                
                if filename:
                    entry_var.set(filename)
                    count += 1
                else:
                    errors.append(f"{project_name}: Failed to retrieve DB fields")
                    
            except Exception as e:
                errors.append(f"{project_name}: {str(e)[:100]}")
        
        # Show results
        if errors:
            error_msg = "\n".join(errors[:10])  # Show first 10 errors
            if len(errors) > 10:
                error_msg += f"\n... and {len(errors) - 10} more errors"
            messagebox.showwarning("Partial Success", 
                f"Applied folder to {count} of {len(self.entry_vars)} project(s)\n\nErrors:\n{error_msg}")
        else:
            messagebox.showinfo("Success", f"Folder applied to {count} project(s)")
        
        self.status_var.set(f"Applied folder to {count} project(s)")
    
    def _construct_filename(self, proj_info, folder):
        """Construct filename from database fields: folder\\LineID.DispType.ProcID.sgy"""
        import pyodbc
        
        try:
            conn = self._connect_to_db(proj_info)
            if not conn:
                return None
            
            cursor = conn.cursor()
            
            # Query for LineID, DispType, and ProcID for this line
            cursor.execute("""
                SELECT LineID, DispType, ProcID
                FROM dbo.SeismicFile 
                WHERE LineName = ?
            """, self.line_name)
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                line_id = result[0] if result[0] else "Unknown"
                disp_type = result[1] if result[1] else "Unknown"
                proc_id = result[2] if result[2] else "Unknown"
                
                # Construct filename: LineID.DispType.ProcID.sgy
                filename = f"{line_id}.{disp_type}.{proc_id}.sgy"
                
                # Combine with folder path
                full_path = os.path.join(folder, filename)
                return full_path
            else:
                return None
                
        except Exception as e:
            print(f"Error constructing filename: {e}")
            return None
    
    def _clear_changes(self):
        """Clear all pending changes"""
        if self.changes and not messagebox.askyesno("Confirm", 
            "Clear all unsaved changes?"):
            return
        
        self.changes.clear()
        self._populate_grid()
        self.status_var.set(f"Loaded paths from {len(self.project_data)} projects")
    
    def _save_changes(self):
        """Save path changes using database (SDK doesn't support volume updates)"""
        if not self.changes:
            messagebox.showinfo("No Changes", "No paths have been modified.")
            return
        
        # Confirm changes
        msg = f"Save {len(self.changes)} path change(s)?"
        if not messagebox.askyesno("Confirm Save", msg):
            return
        
        success_count = 0
        errors = []
        
        for project_name, new_path in self.changes.items():
            try:
                # Find the project info
                proj_info = next((p for p in self.projects_info if p['name'] == project_name), None)
                if not proj_info:
                    errors.append(f"{project_name}: Project info not found")
                    continue
                
                # Use database update (with retry logic)
                success = self._save_to_db_retry(proj_info, new_path)
                if success:
                    success_count += 1
                else:
                    errors.append(f"{project_name}: Failed to update database")
                        
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
        self._refresh_paths()
    
    def _save_to_db_retry(self, proj_info, new_path, max_retries=2):
        """Save to database with retry logic"""
        import pyodbc
        
        for attempt in range(max_retries):
            try:
                conn = self._connect_to_db(proj_info)
                if not conn:
                    if attempt < max_retries - 1:
                        continue
                    return False
                
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE dbo.SeismicFile 
                    SET FileName = ? 
                    WHERE LineName = ?
                """, new_path, self.line_name)
                
                conn.commit()
                conn.close()
                return True
                
            except Exception as e:
                error_msg = str(e)
                if attempt < max_retries - 1:
                    print(f"Database save attempt {attempt + 1} failed, retrying...")
                    continue
                else:
                    print(f"Database save error after {attempt + 1} attempts: {e}")
                    return False
        
        return False
    
    def _connect_to_db(self, proj_info):
        """Connect to a project database"""
        import pyodbc
        
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