# UI for the SeisWare project comparison tool

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from typing import Dict, List
import os
import pyodbc
from collections import defaultdict
from PIL import Image, ImageTk
from SWCompare import load_project_database_paths, get_available_sql_driver
from PathEditorDialog import PathEditorDialog


class TwoListSelector(ttk.Frame):
    """Reusable two-list selector widget"""
    def __init__(self, parent, left_label="Available", right_label="Selected"):
        super().__init__(parent)
        
        # Load icon images and store as instance variables to prevent garbage collection
        icon_dir = os.path.join(os.path.dirname(__file__), "icons")
        self.select_img = ImageTk.PhotoImage(Image.open(os.path.join(icon_dir, "select.ico")).resize((24, 24)))
        self.deselect_img = ImageTk.PhotoImage(Image.open(os.path.join(icon_dir, "deselect.ico")).resize((24, 24)))
        self.select_all_img = ImageTk.PhotoImage(Image.open(os.path.join(icon_dir, "selectall.ico")).resize((24, 24)))
        self.deselect_all_img = ImageTk.PhotoImage(Image.open(os.path.join(icon_dir, "deselectall.ico")).resize((24, 24)))
        
        # Left list
        left_frame = ttk.Frame(self)
        left_frame.pack(side="left", fill="both", expand=True)
        ttk.Label(left_frame, text=f"{left_label}:").pack()
        
        left_scroll = ttk.Scrollbar(left_frame)
        left_scroll.pack(side="right", fill="y")
        self.left_list = tk.Listbox(left_frame, selectmode="extended", 
                                     yscrollcommand=left_scroll.set, height=20)
        self.left_list.pack(side="left", fill="both", expand=True)
        left_scroll.config(command=self.left_list.yview)
        
        # Center buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(side="left", padx=10)
        ttk.Button(btn_frame, image=self.select_img, command=self.move_right).pack(pady=5)
        ttk.Button(btn_frame, image=self.deselect_img, command=self.move_left).pack(pady=5)
        ttk.Button(btn_frame, image=self.select_all_img, command=self.move_all_right).pack(pady=5)
        ttk.Button(btn_frame, image=self.deselect_all_img, command=self.move_all_left).pack(pady=5)
        
        # Right list
        right_frame = ttk.Frame(self)
        right_frame.pack(side="left", fill="both", expand=True)
        ttk.Label(right_frame, text=f"{right_label}:").pack()
        
        right_scroll = ttk.Scrollbar(right_frame)
        right_scroll.pack(side="right", fill="y")
        self.right_list = tk.Listbox(right_frame, selectmode="extended",
                                      yscrollcommand=right_scroll.set, height=20)
        self.right_list.pack(side="left", fill="both", expand=True)
        right_scroll.config(command=self.right_list.yview)
    
    def move_right(self):
        for idx in reversed(self.left_list.curselection()):
            item = self.left_list.get(idx)
            self.right_list.insert(tk.END, item)
            self.left_list.delete(idx)
    
    def move_left(self):
        for idx in reversed(self.right_list.curselection()):
            item = self.right_list.get(idx)
            self.left_list.insert(tk.END, item)
            self.right_list.delete(idx)
        self._resort_left()
    
    def move_all_right(self):
        for item in self.left_list.get(0, tk.END):
            self.right_list.insert(tk.END, item)
        self.left_list.delete(0, tk.END)
    
    def move_all_left(self):
        for item in self.right_list.get(0, tk.END):
            self.left_list.insert(tk.END, item)
        self.right_list.delete(0, tk.END)
        self._resort_left()
    
    def _resort_left(self):
        items = sorted(self.left_list.get(0, tk.END))
        self.left_list.delete(0, tk.END)
        for item in items:
            self.left_list.insert(tk.END, item)
    
    def get_right_items(self):
        return list(self.right_list.get(0, tk.END))
    
    def set_left_items(self, items):
        self.left_list.delete(0, tk.END)
        for item in sorted(items):
            self.left_list.insert(tk.END, item)


class ExpandablePanel(ttk.Frame):
    """Expandable panel widget for displaying seismic line details"""
    def __init__(self, parent, title, content_builder):
        super().__init__(parent)
        self.content_builder = content_builder
        self.expanded = False
        
        # Header frame with title and expand button
        header = ttk.Frame(self, relief="raised", borderwidth=1)
        header.pack(fill="x", padx=2, pady=2)
        
        self.toggle_btn = ttk.Button(header, text="▶", width=3, command=self.toggle)
        self.toggle_btn.pack(side="left", padx=5)
        
        ttk.Label(header, text=title, font=("TkDefaultFont", 10, "bold")).pack(side="left", padx=5, fill="x", expand=True)
        
        # Content frame (initially hidden)
        self.content_frame = ttk.Frame(self)
        
    def toggle(self):
        if self.expanded:
            self.content_frame.pack_forget()
            self.toggle_btn.config(text="▶")
            self.expanded = False
        else:
            self.content_frame.pack(fill="both", expand=True, padx=20, pady=5)
            if not self.content_frame.winfo_children():
                self.content_builder(self.content_frame)
            self.toggle_btn.config(text="▼")
            self.expanded = True


class SelectionPage(ttk.Frame):
    """Page 1: Project selection"""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.db_info = {}
        
        # XML file selection
        file_group = ttk.LabelFrame(self, text="SeisWare Project List", padding=10)
        file_group.pack(fill="x", padx=10, pady=10)
        
        username = os.getenv('USERNAME')
        default_path = rf"C:\Users\{username}\AppData\Roaming\SeisWare\SeisWare\Support\ProjectList.xml"
        self.path_var = tk.StringVar(value=default_path)
        ttk.Entry(file_group, textvariable=self.path_var, width=60).pack(side="left", padx=5)
        ttk.Button(file_group, text="Browse", command=self._browse).pack(side="left", padx=5)
        ttk.Button(file_group, text="Load", command=self._load).pack(side="left")
        
        # Project selector
        selector_group = ttk.LabelFrame(self, text="Choose Projects", padding=10)
        selector_group.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.selector = TwoListSelector(selector_group, "Available Projects", "Selected Projects")
        self.selector.pack(fill="both", expand=True)
        
        # Bottom controls
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=10)
        
        self.status = tk.StringVar(value="Loading project list...")
        ttk.Label(bottom, textvariable=self.status).pack(side="left")
        ttk.Button(bottom, text="Compare", command=self._compare).pack(side="right")
        
        # Auto-load the default project file after widget creation
        self.after(100, self._auto_load)
    
    def _auto_load(self):
        """Automatically load the default project file on startup"""
        path = self.path_var.get()
        if os.path.exists(path):
            try:
                self.db_info = load_project_database_paths(path)
                self.selector.set_left_items(self.db_info.keys())
                self.status.set(f"Loaded {len(self.db_info)} projects")
            except Exception as e:
                self.status.set(f"Failed to auto-load: {str(e)[:50]}")
                print(f"Auto-load error: {e}")
        else:
            self.status.set("Default project file not found - click Load to select")
    
    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select ProjectList.xml",
            filetypes=[("XML", "*.xml"), ("All", "*.*")]
        )
        if path:
            self.path_var.set(path)
    
    def _load(self):
        path = self.path_var.get()
        if not os.path.exists(path):
            messagebox.showerror("Error", f"File not found:\n{path}")
            return
        
        try:
            self.db_info = load_project_database_paths(path)
            self.selector.set_left_items(self.db_info.keys())
            self.status.set(f"Loaded {len(self.db_info)} projects")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load:\n{e}")
    
    def _compare(self):
        selected = self.selector.get_right_items()
        if len(selected) < 2:
            messagebox.showwarning("Warning", "Select at least 2 projects")
            return
        
        self.app.run_comparison(selected, self.db_info)


class ResultsPage(ttk.Frame):
    """Page 2: Display results"""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.all_results = {}
        self.line_details = {}
        
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=10, pady=10)
        
        ttk.Button(toolbar, text="← Back", command=lambda: app.show_page(0)).pack(side="left")
        
        self.count_var = tk.StringVar(value="No results")
        ttk.Label(toolbar, textvariable=self.count_var).pack(side="left", padx=20)
        
        ttk.Button(toolbar, text="Error Log", command=app.show_error_log).pack(side="left", padx=5)
        
        # View mode radio buttons
        ttk.Label(toolbar, text="View by:").pack(side="left", padx=(40, 5))
        self.view_mode = tk.StringVar(value="line")
        ttk.Radiobutton(toolbar, text="Seismic Line", variable=self.view_mode, 
                       value="line", command=self._change_view).pack(side="left")
        ttk.Radiobutton(toolbar, text="Project", variable=self.view_mode, 
                       value="project", command=self._change_view).pack(side="left", padx=(5, 20))
        
        ttk.Label(toolbar, text="Filter:").pack(side="left", padx=(20, 5))
        self.filter_var = tk.StringVar()
        self.filter_var.trace('w', lambda *args: self._apply_filter())
        ttk.Entry(toolbar, textvariable=self.filter_var, width=30).pack(side="left")
        
        # Scrollable results area
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, command=self.canvas.yview)
        self.results_frame = ttk.Frame(self.canvas)
        
        self.results_frame.bind("<Configure>", 
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.results_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        # Bind canvas resize to update the frame width
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Mouse wheel scrolling
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))
    
    def _on_canvas_configure(self, event):
        """Update the width of the frame inside the canvas to match canvas width"""
        self.canvas.itemconfig(self.canvas_frame, width=event.width)
    
    def display_results(self, results, line_details):
        self.all_results = results
        self.line_details = line_details
        self.count_var.set(f"Found {len(results)} duplicate files")
        self._apply_filter()
    
    def _change_view(self):
        """Called when view mode radio button changes"""
        self._apply_filter()
    
    def _render_results_by_line(self, results):
        """Render results grouped by seismic line"""
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        
        if not results:
            ttk.Label(self.results_frame, text="No duplicates found").pack(pady=20)
            return
        
        for filename in sorted(results.keys()):
            projects = results[filename]
            details = self.line_details.get(filename, {})
            
            def make_content(frame, fn=filename, prj=projects, det=details):
                # Details grid
                info_frame = ttk.Frame(frame)
                info_frame.pack(fill="both", expand=True, pady=5)
                
                row = 0
                for key, value in det.items():
                    ttk.Label(info_frame, text=f"{key}:", font=("TkDefaultFont", 9, "bold")).grid(
                        row=row, column=0, sticky="w", padx=5, pady=2)
                    
                    # Make Line Name clickable to open path editor for all projects
                    if key == "Line Name":
                        value_frame = ttk.Frame(info_frame)
                        value_frame.grid(row=row, column=1, sticky="w", padx=5, pady=2)
                        
                        # Create a clickable label for the line name
                        link = tk.Label(value_frame, text=value, foreground="blue", 
                                       cursor="hand2", font=("TkDefaultFont", 9, "underline"))
                        link.pack(side="left")
                        link.bind("<Button-1>", lambda e, ln=fn, projects=prj: 
                                 self._open_path_editor_multi_project(ln, projects))
                    else:
                        ttk.Label(info_frame, text=str(value)).grid(
                            row=row, column=1, sticky="w", padx=5, pady=2)
                    row += 1
                
                # Projects list (not clickable)
                ttk.Label(info_frame, text="Found in:", font=("TkDefaultFont", 9, "bold")).grid(
                    row=row, column=0, sticky="w", padx=5, pady=2)
                projects_text = ", ".join(prj)
                ttk.Label(info_frame, text=projects_text, wraplength=700).grid(
                    row=row, column=1, sticky="w", padx=5, pady=2)
            
            panel = ExpandablePanel(self.results_frame, 
                                   f"{filename} ({len(projects)} projects)", 
                                   make_content)
            panel.pack(fill="both", expand=True, pady=2, padx=5)
    
    def _render_results_by_project(self, results):
        """Render results grouped by project"""
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        
        if not results:
            ttk.Label(self.results_frame, text="No duplicates found").pack(pady=20)
            return
        
        # Invert the data structure: project -> list of lines
        project_to_lines = defaultdict(list)
        for line_name, projects in results.items():
            for project in projects:
                project_to_lines[project].append(line_name)
        
        for project_name in sorted(project_to_lines.keys()):
            lines = project_to_lines[project_name]
            
            def make_content(frame, proj=project_name, line_list=lines):
                # Lines list with details
                info_frame = ttk.Frame(frame)
                info_frame.pack(fill="both", expand=True, pady=5)
                
                for idx, line_name in enumerate(sorted(line_list)):
                    # Line name - clickable to open path editor for all projects with this line
                    line_frame = ttk.Frame(info_frame)
                    line_frame.pack(fill="x", pady=3, padx=5)
                    
                    ttk.Label(line_frame, text="• ").pack(side="left")
                    
                    # Make line name clickable - show all projects with this line
                    projects_with_line = self.all_results[line_name]
                    line_link = tk.Label(line_frame, text=line_name, foreground="blue",
                                        cursor="hand2", font=("TkDefaultFont", 9, "bold underline"))
                    line_link.pack(side="left")
                    line_link.bind("<Button-1>", lambda e, ln=line_name, prj_list=projects_with_line: 
                                  self._open_path_editor_multi_project(ln, prj_list))
                    
                    # Show which other projects also have this line
                    other_projects = [p for p in self.all_results[line_name] if p != proj]
                    if other_projects:
                        also_in = f"(also in: {', '.join(other_projects)})"
                        ttk.Label(line_frame, text=also_in, 
                                 font=("TkDefaultFont", 8), foreground="gray").pack(side="left", padx=10)
                    
                    # Line details
                    details = self.line_details.get(line_name, {})
                    if details:
                        detail_frame = ttk.Frame(info_frame)
                        detail_frame.pack(fill="x", padx=25, pady=2)
                        
                        detail_text = " | ".join([f"{k}: {v}" for k, v in details.items() if k != 'Line Name'])
                        ttk.Label(detail_frame, text=detail_text, 
                                 font=("TkDefaultFont", 8), foreground="darkblue").pack(side="left")
            
            panel = ExpandablePanel(self.results_frame, 
                                   f"{project_name} ({len(lines)} duplicate lines)", 
                                   make_content)
            panel.pack(fill="both", expand=True, pady=2, padx=5)
    
    def _open_path_editor_multi_project(self, line_name, project_list):
        """Open the path editor dialog showing the same line across multiple projects"""
        # Collect all database connection info for the projects
        projects_info = []
        for project_name in project_list:
            if project_name not in self.app.pages[0].db_info:
                continue
            
            db_info = self.app.pages[0].db_info[project_name]
            projects_info.append({
                'name': project_name,
                'driver': get_available_sql_driver(),
                'encrypt': "Encrypt=no;" if "18" in get_available_sql_driver() else "",
                'db_type': db_info['type'],
                'db_path': db_info['path'],
                'server': db_info['server'],
                'directory': db_info.get('directory', '')
            })
        
        if not projects_info:
            messagebox.showerror("Error", "No valid project database info found")
            return
        
        PathEditorDialog(self, line_name, projects_info)
    
    def _apply_filter(self):
        filter_text = self.filter_var.get().lower()
        
        if not filter_text:
            filtered = self.all_results
        else:
            filtered = {}
            for filename, projects in self.all_results.items():
                # Check if filter matches the filename
                filename_match = filter_text in filename.lower()
                # Check if filter matches any of the project names
                project_match = any(filter_text in proj.lower() for proj in projects)
                
                if filename_match or project_match:
                    filtered[filename] = projects
        
        # Update count and render based on view mode
        if self.view_mode.get() == "line":
            self.count_var.set(f"Showing {len(filtered)} of {len(self.all_results)} duplicate files")
            self._render_results_by_line(filtered)
        else:
            # Count projects that have duplicates
            project_count = len(set(proj for projects in filtered.values() for proj in projects))
            self.count_var.set(f"Showing {project_count} projects with {len(filtered)} duplicate files")
            self._render_results_by_project(filtered)


class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SeisWare Project Comparison")
        self.geometry("900x700")
        
        self.error_log = []  # Store errors during comparison
        
        self.pages = []
        self.pages.append(SelectionPage(self, self))
        self.pages.append(ResultsPage(self, self))
        
        for page in self.pages:
            page.place(relwidth=1, relheight=1)
        
        self.show_page(0)
    
    def show_page(self, index):
        self.pages[index].tkraise()
    
    def show_error_log(self):
        """Display error log in a new window"""
        log_window = tk.Toplevel(self)
        log_window.title("Error Log")
        log_window.geometry("700x500")
        
        # Toolbar
        toolbar = ttk.Frame(log_window)
        toolbar.pack(fill="x", padx=10, pady=10)
        
        count_label = ttk.Label(toolbar, text=f"{len(self.error_log)} errors logged")
        count_label.pack(side="left")
        
        ttk.Button(toolbar, text="Clear Log", command=lambda: self._clear_log(log_window)).pack(side="right", padx=5)
        ttk.Button(toolbar, text="Copy All", command=lambda: self._copy_log()).pack(side="right")
        
        # Text widget with scrollbar
        text_frame = ttk.Frame(log_window)
        text_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")
        
        text_widget = tk.Text(text_frame, wrap="word", yscrollcommand=scrollbar.set)
        text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=text_widget.yview)
        
        # Populate with errors
        if self.error_log:
            for i, error in enumerate(self.error_log, 1):
                text_widget.insert("end", f"{i}. Project: {error['project']}\n")
                text_widget.insert("end", f"   Error: {error['message']}\n\n")
        else:
            text_widget.insert("end", "No errors logged.")
        
        text_widget.config(state="disabled")
    
    def _clear_log(self, window):
        self.error_log.clear()
        window.destroy()
        messagebox.showinfo("Log Cleared", "Error log has been cleared.")
    
    def _copy_log(self):
        """Copy error log to clipboard"""
        if not self.error_log:
            messagebox.showinfo("Empty Log", "No errors to copy.")
            return
        
        log_text = "\n".join([f"Project: {err['project']}\nError: {err['message']}\n" 
                              for err in self.error_log])
        self.clipboard_clear()
        self.clipboard_append(log_text)
        messagebox.showinfo("Copied", "Error log copied to clipboard.")
    
    def run_comparison(self, projects, db_info):
        self.error_log.clear()  # Clear previous errors
        
        progress = tk.Toplevel(self)
        progress.title("Comparing...")
        progress.geometry("400x100")
        ttk.Label(progress, text="Analyzing projects...").pack(pady=20)
        progress_bar = ttk.Progressbar(progress, mode='indeterminate')
        progress_bar.pack(fill="x", padx=20)
        progress_bar.start()
        
        def compare_thread():
            try:
                results, details = self._compare_projects(projects, db_info)
                self.after(0, lambda: self._show_results(results, details, progress))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
                progress.destroy()
        
        threading.Thread(target=compare_thread, daemon=True).start()
    
    def _compare_projects(self, projects, db_info):
        file_to_projects = defaultdict(list)
        line_details = {}
        
        driver = get_available_sql_driver()
        if not driver:
            raise Exception("No SQL Server driver found")
        
        encrypt = "Encrypt=no;" if "18" in driver else ""
        
        for proj_name in projects:
            info = db_info[proj_name]
            db_path = info['path']
            server = info['server']
            db_type = info['type']
            
            if not db_path:
                self.error_log.append({
                    'project': proj_name,
                    'message': 'No database path specified'
                })
                continue
            
            try:
                conn = self._connect_db(driver, encrypt, db_type, db_path, server, info['directory'])
                if conn:
                    cursor = conn.cursor()
                    
                    # Query seismic files - use LineName as the unique identifier for comparison
                    cursor.execute("""
                        SELECT DISTINCT LineName, FileName, RowChangedDate
                        FROM dbo.SeismicFile
                        WHERE LineName IS NOT NULL AND LineName != ''
                    """)
                    
                    for row in cursor.fetchall():
                        line_name = row[0]  # LineName is the unique identifier
                        file_path = row[1]  # FileName is the actual file path
                        last_changed = row[2]
                        
                        # Use LineName as the key for comparison
                        file_to_projects[line_name].append(proj_name)
                        if line_name not in line_details:
                            line_details[line_name] = {
                                'Line Name': line_name,
                                'File Path': file_path if file_path else 'N/A',
                                'Last Changed': str(last_changed) if last_changed else 'N/A'
                            }
                    conn.close()
                else:
                    self.error_log.append({
                        'project': proj_name,
                        'message': 'Could not connect to database'
                    })
            except Exception as e:
                self.error_log.append({
                    'project': proj_name,
                    'message': str(e)
                })
                print(f"Error with {proj_name}: {e}")
        
        duplicates = {k: v for k, v in file_to_projects.items() if len(v) > 1}
        return duplicates, line_details
    
    def _connect_db(self, driver, encrypt, db_type, db_path, server, directory):
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
    
    def _show_results(self, results, details, progress_window):
        progress_window.destroy()
        self.pages[1].display_results(results, details)
        self.show_page(1)
        
        # Show error notification if there were errors
        if self.error_log:
            msg = f"{len(self.error_log)} project(s) had errors during comparison."
            if messagebox.askyesno("Errors Occurred", f"{msg}\n\nView error log?"):
                self.show_error_log()


if __name__ == "__main__":
    app = Application()
    app.mainloop()