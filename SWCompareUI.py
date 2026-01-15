# UI for the SeisWare project comparison tool

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from typing import Dict, List
import os
import pyodbc
from collections import defaultdict
from PIL import Image, ImageTk
import datetime
from SWCompare import load_project_database_paths, get_available_sql_driver
from ProjectDeletionManager import ProjectDeletionManager

# Add debug output
try:
    from PathEditorDialog import PathEditorDialog
    print("PathEditorDialog imported successfully")
except Exception as e:
    print(f"Failed to import PathEditorDialog: {e}")
    import traceback
    traceback.print_exc()
    PathEditorDialog = None


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
        
        # Left side - Project Deletion Manager button with icon
        icon_dir = os.path.join(os.path.dirname(__file__), "icons")
        # Try to load Delete/Trash icon, fall back to Run icon if not available
        try:
            delete_img = ImageTk.PhotoImage(Image.open(os.path.join(icon_dir, "Delete.ico")).resize((24, 24)))
        except:
            try:
                delete_img = ImageTk.PhotoImage(Image.open(os.path.join(icon_dir, "Trash.ico")).resize((24, 24)))
            except:
                # Fallback to Run icon if Delete/Trash.ico don't exist
                delete_img = ImageTk.PhotoImage(Image.open(os.path.join(icon_dir, "Run.ico")).resize((24, 24)))
        
        deletion_btn = tk.Button(bottom, image=delete_img, text="Project Deletion Manager", compound="left",
                                command=self._open_deletion_manager, bg="SystemButtonFace", relief="ridge", bd=3,
                                font=("Arial", 12), padx=15, pady=10, activebackground="lightblue")
        deletion_btn.image = delete_img  # Keep a reference to the image
        deletion_btn.pack(side="left")
        
        # Center - Status
        self.status = tk.StringVar(value="Loading project list...")
        ttk.Label(bottom, textvariable=self.status).pack(side="left", padx=20)
        
        # Right side - Compare button
        # Load Run icon for Compare button (1.5x larger)
        run_img = ImageTk.PhotoImage(Image.open(os.path.join(icon_dir, "Run.ico")).resize((24, 24)))
        compare_btn = tk.Button(bottom, image=run_img, text="Compare projects", compound="left", 
                                command=self._compare, bg="SystemButtonFace", relief="ridge", bd=3,
                                font=("Arial", 12), padx=15, pady=10, activebackground="lightblue")
        compare_btn.image = run_img  # Keep a reference to the image
        compare_btn.pack(side="right", padx=5)
        
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
    
    def _open_deletion_manager(self):
        """Open the Project Deletion Manager dialog"""
        try:
            ProjectDeletionManager(self)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open Project Deletion Manager:\n{str(e)}")
            print(f"Project Deletion Manager error: {e}")
            import traceback
            traceback.print_exc()


class ResultsPage(ttk.Frame):
    """Page 2: Display results"""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.all_seismic_results = {}
        self.seismic_line_details = {}
        self.all_well_results = {}
        self.well_details = {}
        self.selected_row = None
        self.current_rows = []  # Store current displayed rows for sorting
        self.sort_column = None  # Track which column is sorted
        self.sort_reverse = False  # Track sort direction
        self.sort_is_numeric = False  # Track if current sort is numeric
        
        # Toolbar - top row
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=10, pady=(10, 5))
        
        ttk.Button(toolbar, text="← Back", command=lambda: app.show_page(0)).pack(side="left")
        
        self.count_var = tk.StringVar(value="No results")
        ttk.Label(toolbar, textvariable=self.count_var).pack(side="left", padx=20)
        
        ttk.Button(toolbar, text="Error Log", command=app.show_error_log).pack(side="right", padx=5)
        
        # Toolbar - bottom row for Search
        toolbar2 = ttk.Frame(self)
        toolbar2.pack(fill="x", padx=10, pady=(5, 10))
        
        ttk.Label(toolbar2, text="Search:").pack(side="left", padx=(0, 5))
        self.filter_var = tk.StringVar()
        self.filter_var.trace('w', lambda *args: self._apply_filter())
        ttk.Entry(toolbar2, textvariable=self.filter_var, width=30).pack(side="left")
        
        # Create notebook (tab control)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        
        # Seismic tab
        self.seismic_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.seismic_frame, text="Seismic")
        
        # Create Seismic Treeview
        seismic_columns = ("Line Name", "Project Name", "File Path", "File Size", "Last Modified")
        self.seismic_tree = ttk.Treeview(self.seismic_frame, columns=seismic_columns, show="headings", height=25)
        
        # Define column headings with sort commands
        self.seismic_tree.heading("Line Name", text="Line Name", command=lambda: self._sort_by_column("Line Name", False))
        self.seismic_tree.heading("Project Name", text="Project Name", command=lambda: self._sort_by_column("Project Name", False))
        self.seismic_tree.heading("File Path", text="File Path", command=lambda: self._sort_by_column("File Path", False))
        self.seismic_tree.heading("File Size", text="File Size", command=lambda: self._sort_by_column("File Size", True))
        self.seismic_tree.heading("Last Modified", text="Last Modified", command=lambda: self._sort_by_column("Last Modified", False))
        
        self.seismic_tree.column("Line Name", width=120)
        self.seismic_tree.column("Project Name", width=150)
        self.seismic_tree.column("File Path", width=250)
        self.seismic_tree.column("File Size", width=100)
        self.seismic_tree.column("Last Modified", width=150)
        
        # Add scrollbars for seismic
        vsb_seismic = ttk.Scrollbar(self.seismic_frame, orient="vertical", command=self.seismic_tree.yview)
        hsb_seismic = ttk.Scrollbar(self.seismic_frame, orient="horizontal", command=self.seismic_tree.xview)
        self.seismic_tree.configure(yscrollcommand=vsb_seismic.set, xscrollcommand=hsb_seismic.set)
        
        # Grid layout for seismic tree and scrollbars
        self.seismic_tree.grid(row=0, column=0, sticky="nsew")
        vsb_seismic.grid(row=0, column=1, sticky="ns")
        hsb_seismic.grid(row=1, column=0, sticky="ew")
        
        self.seismic_frame.grid_rowconfigure(0, weight=1)
        self.seismic_frame.grid_columnconfigure(0, weight=1)
        
        # Bind selection event for seismic
        self.seismic_tree.bind("<<TreeviewSelect>>", self._on_row_select)
        
        # Wells tab
        self.wells_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.wells_frame, text="Wells")
        
        # Create Wells Treeview
        well_columns = ("UWI", "Well Name", "Project Name", "Last Modified")
        self.wells_tree = ttk.Treeview(self.wells_frame, columns=well_columns, show="headings", height=25)
        
        # Define column headings with sort commands
        self.wells_tree.heading("UWI", text="UWI", command=lambda: self._sort_by_column("UWI", False))
        self.wells_tree.heading("Well Name", text="Well Name", command=lambda: self._sort_by_column("Well Name", False))
        self.wells_tree.heading("Project Name", text="Project Name", command=lambda: self._sort_by_column("Project Name", False))
        self.wells_tree.heading("Last Modified", text="Last Modified", command=lambda: self._sort_by_column("Last Modified", False))
        
        self.wells_tree.column("UWI", width=200)
        self.wells_tree.column("Well Name", width=200)
        self.wells_tree.column("Project Name", width=150)
        self.wells_tree.column("Last Modified", width=150)
        
        # Add scrollbars for wells
        vsb_wells = ttk.Scrollbar(self.wells_frame, orient="vertical", command=self.wells_tree.yview)
        hsb_wells = ttk.Scrollbar(self.wells_frame, orient="horizontal", command=self.wells_tree.xview)
        self.wells_tree.configure(yscrollcommand=vsb_wells.set, xscrollcommand=hsb_wells.set)
        
        # Grid layout for wells tree and scrollbars
        self.wells_tree.grid(row=0, column=0, sticky="nsew")
        vsb_wells.grid(row=0, column=1, sticky="ns")
        hsb_wells.grid(row=1, column=0, sticky="ew")
        
        self.wells_frame.grid_rowconfigure(0, weight=1)
        self.wells_frame.grid_columnconfigure(0, weight=1)
        
        # Bind selection event for wells
        self.wells_tree.bind("<<TreeviewSelect>>", self._on_row_select)
        
        # Bottom frame for buttons
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill="x", padx=10, pady=10)
        
        # Redefine button at bottom right with icon
        icon_dir = os.path.join(os.path.dirname(__file__), "icons")
        # Try to load Edit icon, fall back to Run icon if not available
        try:
            edit_img = ImageTk.PhotoImage(Image.open(os.path.join(icon_dir, "Edit.ico")).resize((24, 24)))
        except:
            # Fallback to Run icon if Edit.ico doesn't exist
            edit_img = ImageTk.PhotoImage(Image.open(os.path.join(icon_dir, "Run.ico")).resize((24, 24)))
        
        self.redefine_btn = tk.Button(bottom_frame, image=edit_img, text="Redefine Selected", compound="left",
                                       command=self._on_redefine_click, state="disabled",
                                       bg="SystemButtonFace", relief="ridge", bd=3,
                                       font=("Arial", 12), padx=15, pady=10, activebackground="lightblue")
        self.redefine_btn.image = edit_img  # Keep a reference to prevent garbage collection
        self.redefine_btn.pack(side="right", padx=5)
    
    def _on_tab_changed(self, event):
        """Handle tab change event"""
        current_tab = self.notebook.index(self.notebook.select())
        
        if current_tab == 0:  # Seismic tab
            self.count_var.set(f"Found {len(self.all_seismic_results)} duplicate files")
            self.redefine_btn.config(state="disabled")
            self.selected_row = None
        else:  # Wells tab
            self.count_var.set(f"Found {len(self.all_well_results)} duplicate wells")
            self.redefine_btn.config(state="disabled")
            self.selected_row = None
        
        # Clear filter when switching tabs
        self.filter_var.set("")
    
    def display_results(self, seismic_results, seismic_details, well_results, well_details):
        """Display results in grid format"""
        self.all_seismic_results = seismic_results
        self.seismic_line_details = seismic_details
        self.all_well_results = well_results
        self.well_details = well_details
        
        # Set initial count
        self.count_var.set(f"Found {len(seismic_results)} duplicate files")
        
        # Apply filter to populate both tabs
        self._apply_filter()
    
    def _apply_filter(self):
        """Apply filter and populate the tree view"""
        filter_text = self.filter_var.get().lower()
        current_tab = self.notebook.index(self.notebook.select())
        
        if current_tab == 0:  # Seismic tab
            self._apply_seismic_filter(filter_text)
        else:  # Wells tab
            self._apply_wells_filter(filter_text)
    
    def _apply_seismic_filter(self, filter_text):
        """Apply filter to seismic data"""
        # Build data for display
        rows = []
        for line_name, projects in self.all_seismic_results.items():
            # Check if line name or any project matches filter
            if filter_text and not (filter_text in line_name.lower() or 
                                    any(filter_text in proj.lower() for proj in projects)):
                continue
            
            details = self.seismic_line_details.get(line_name, {})
            file_path = details.get('File Path', 'N/A')
            file_size = details.get('File Size', 'N/A')
            last_modified = details.get('Last Modified', 'N/A')
            
            # Create one row for each project that has this line
            for project_name in sorted(projects):
                rows.append({
                    'line_name': line_name,
                    'project_name': project_name,
                    'file_path': file_path,
                    'file_size': file_size,
                    'last_modified': last_modified
                })
        
        # Store rows
        self.current_rows = rows
        
        # Apply current sort if one exists, otherwise default sort
        if self.sort_column:
            self._apply_current_sort()
        else:
            self._display_seismic_rows(sorted(rows, key=lambda x: (x['line_name'], x['project_name'])))
        
        # Update count
        if filter_text:
            unique_lines = len(set(row['line_name'] for row in rows))
            self.count_var.set(f"Found {unique_lines} duplicate files")
        else:
            self.count_var.set(f"Found {len(self.all_seismic_results)} duplicate files")
    
    def _apply_wells_filter(self, filter_text):
        """Apply filter to wells data"""
        # Build data for display
        rows = []
        for uwi, projects in self.all_well_results.items():
            # Check if UWI or any project matches filter
            if filter_text and not (filter_text in uwi.lower() or 
                                    any(filter_text in proj.lower() for proj in projects)):
                continue
            
            details = self.well_details.get(uwi, {})
            well_name = details.get('Well Name', 'N/A')
            last_modified = details.get('Last Modified', 'N/A')
            
            # Create one row for each project that has this well
            for project_name in sorted(projects):
                rows.append({
                    'uwi': uwi,
                    'well_name': well_name,
                    'project_name': project_name,
                    'last_modified': last_modified
                })
        
        # Store rows
        self.current_rows = rows
        
        # Apply current sort if one exists, otherwise default sort
        if self.sort_column:
            self._apply_current_sort()
        else:
            self._display_wells_rows(sorted(rows, key=lambda x: (x['uwi'], x['project_name'])))
        
        # Update count
        if filter_text:
            unique_uwis = len(set(row['uwi'] for row in rows))
            self.count_var.set(f"Found {unique_uwis} duplicate wells")
        else:
            self.count_var.set(f"Found {len(self.all_well_results)} duplicate wells")
    
    def _display_seismic_rows(self, rows):
        """Display seismic rows in the treeview"""
        # Clear existing items
        for item in self.seismic_tree.get_children():
            self.seismic_tree.delete(item)
        
        # Insert rows into treeview
        for row in rows:
            self.seismic_tree.insert("", "end", values=(
                row['line_name'],
                row['project_name'],
                row['file_path'],
                row['file_size'],
                row['last_modified']
            ))
    
    def _display_wells_rows(self, rows):
        """Display wells rows in the treeview"""
        # Clear existing items
        for item in self.wells_tree.get_children():
            self.wells_tree.delete(item)
        
        # Insert rows into treeview
        for row in rows:
            self.wells_tree.insert("", "end", values=(
                row['uwi'],
                row['well_name'],
                row['project_name'],
                row['last_modified']
            ))
    
    def _sort_by_column(self, column, is_numeric=False):
        """Sort treeview by column. Toggle sort direction if same column clicked."""
        # If same column clicked, reverse the sort direction
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
            self.sort_is_numeric = is_numeric
        
        self._apply_current_sort()
    
    def _apply_current_sort(self):
        """Apply the current sort settings to current_rows"""
        if not self.sort_column:
            return
        
        current_tab = self.notebook.index(self.notebook.select())
        
        if current_tab == 0:  # Seismic tab
            # Map column names to dict keys
            column_key_map = {
                "Line Name": "line_name",
                "Project Name": "project_name",
                "File Path": "file_path",
                "File Size": "file_size",
                "Last Modified": "last_modified"
            }
            
            key = column_key_map.get(self.sort_column, self.sort_column.lower().replace(" ", "_"))
            
            # Sort the rows
            if hasattr(self, 'sort_is_numeric') and self.sort_is_numeric and self.sort_column == "File Size":
                # Custom sort for file size - extract numeric value
                def get_numeric_value(row):
                    file_size = row.get(key, "N/A")
                    if file_size == "N/A":
                        return 0
                    # Extract numeric value from "X.XX MB"
                    try:
                        return float(file_size.split()[0])
                    except:
                        return 0
                
                sorted_rows = sorted(self.current_rows, key=get_numeric_value, reverse=self.sort_reverse)
            else:
                # Alphanumeric sort
                sorted_rows = sorted(self.current_rows, 
                                   key=lambda x: str(x.get(key, "")).lower(),
                                   reverse=self.sort_reverse)
            
            self._display_seismic_rows(sorted_rows)
        else:  # Wells tab
            # Map column names to dict keys
            column_key_map = {
                "UWI": "uwi",
                "Well Name": "well_name",
                "Project Name": "project_name",
                "Last Modified": "last_modified"
            }
            
            key = column_key_map.get(self.sort_column, self.sort_column.lower().replace(" ", "_"))
            
            # Alphanumeric sort
            sorted_rows = sorted(self.current_rows, 
                               key=lambda x: str(x.get(key, "")).lower(),
                               reverse=self.sort_reverse)
            
            self._display_wells_rows(sorted_rows)
    
    def _on_row_select(self, event):
        """Handle row selection"""
        current_tab = self.notebook.index(self.notebook.select())
        
        if current_tab == 0:  # Seismic tab
            selection = self.seismic_tree.selection()
            self.selected_row = selection[0] if selection else None
            self.redefine_btn.config(state="normal" if self.selected_row else "disabled")
        else:  # Wells tab - always disabled
            self.selected_row = None
            self.redefine_btn.config(state="disabled")
    
    def _on_redefine_click(self):
        """Handle redefine button click"""
        if not self.selected_row:
            return
        
        # Get the line name from the selected row
        values = self.seismic_tree.item(self.selected_row)['values']
        line_name = values[0]
        
        # Get all projects that have this line
        projects = self.all_seismic_results.get(line_name, [])
        if projects:
            self._open_path_editor_multi_project(line_name, projects)
    
    def _open_path_editor_multi_project(self, line_name, project_list):
        """Open the path editor dialog showing the same line across multiple projects"""
        
        # Check if PathEditorDialog is available
        if PathEditorDialog is None:
            messagebox.showerror("Error", "PathEditorDialog module failed to load. Check console for details.")
            return
        
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
        
        try:
            PathEditorDialog(self, line_name, projects_info)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open Path Editor:\n{str(e)}")
            print(f"PathEditorDialog error: {e}")
            import traceback
            traceback.print_exc()
        

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SeisWare Project Comparison")
        self.geometry("900x800")
        
        # Set window icon
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "SeisWare.ico")
        self.iconbitmap(icon_path)
        
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
        
        # Set window icon
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "SeisWare.ico")
        log_window.iconbitmap(icon_path)
        
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
        
        # Set window icon
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "SeisWare.ico")
        progress.iconbitmap(icon_path)
        
        ttk.Label(progress, text="Analyzing projects...").pack(pady=20)
        progress_bar = ttk.Progressbar(progress, mode='indeterminate')
        progress_bar.pack(fill="x", padx=20)
        progress_bar.start()
        
        def compare_thread():
            try:
                seismic_results, seismic_details, well_results, well_details = self._compare_projects(projects, db_info)
                self.after(0, lambda: self._show_results(seismic_results, seismic_details, well_results, well_details, progress))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
                progress.destroy()
        
        threading.Thread(target=compare_thread, daemon=True).start()
    
    def _compare_projects(self, projects, db_info):
        file_to_projects = defaultdict(list)
        line_details = {}
        well_to_projects = defaultdict(list)
        well_details = {}
        
        driver = get_available_sql_driver()
        if not driver:
            raise Exception("No SQL Server driver found")
        
        encrypt = "Encrypt=no;" if "18" in driver else ""
        
        for proj_name in projects:
            info = db_info[proj_name]
            db_path = info['path']
            server = info['server']
            db_type = info['type']
            proj_directory = info.get('directory', '')
            
            if not db_path:
                self.error_log.append({
                    'project': proj_name,
                    'message': 'No database path specified'
                })
                continue
            
            try:
                conn = self._connect_db(driver, encrypt, db_type, db_path, server, proj_directory)
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
                        
                        # Resolve %ProjDir% placeholder with actual project directory
                        resolved_path = file_path
                        if file_path and '%ProjDir%' in file_path and proj_directory:
                            resolved_path = file_path.replace('%ProjDir%', proj_directory)
                        
                        # Normalize path separators to backslashes
                        if resolved_path:
                            resolved_path = resolved_path.replace('/', '\\')
                        
                        # Get file size and actual last modified date from filesystem
                        file_size = 'N/A'
                        actual_last_modified = str(last_changed) if last_changed else 'N/A'
                        
                        if resolved_path and os.path.exists(resolved_path):
                            try:
                                file_stats = os.stat(resolved_path)
                                # Convert bytes to MB
                                file_size = f"{file_stats.st_size / (1024*1024):.2f} MB"
                                # Get actual last modified date from file
                                actual_last_modified = datetime.datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                            except Exception as e:
                                print(f"Error getting file stats for {resolved_path}: {e}")
                        
                        # Use LineName as the key for comparison
                        file_to_projects[line_name].append(proj_name)
                        if line_name not in line_details:
                            line_details[line_name] = {
                                'Line Name': line_name,
                                'File Path': resolved_path if resolved_path else 'N/A',
                                'File Size': file_size,
                                'Last Modified': actual_last_modified
                            }
                    
                    # Query wells - use UWI as the unique identifier
                    try:
                        cursor.execute("""
                            SELECT DISTINCT UWI, WellName, RowChangedDate
                            FROM dbo.Well
                            WHERE UWI IS NOT NULL AND UWI != ''
                        """)
                        
                        for row in cursor.fetchall():
                            uwi = row[0]
                            well_name = row[1] if row[1] else 'N/A'
                            last_changed = row[2]
                            
                            # Use UWI as the key for comparison
                            well_to_projects[uwi].append(proj_name)
                            if uwi not in well_details:
                                well_details[uwi] = {
                                    'UWI': uwi,
                                    'Well Name': well_name,
                                    'Last Modified': str(last_changed) if last_changed else 'N/A'
                                }
                    except Exception as e:
                        print(f"Error querying wells for {proj_name}: {e}")
                    
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
        duplicate_wells = {k: v for k, v in well_to_projects.items() if len(v) > 1}
        return duplicates, line_details, duplicate_wells, well_details
    
    def _connect_db(self, driver, encrypt, db_type, db_path, server, directory):
        """Connect to a SeisWare database"""
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
    
    def _show_results(self, seismic_results, seismic_details, well_results, well_details, progress_window):
        progress_window.destroy()
        self.pages[1].display_results(seismic_results, seismic_details, well_results, well_details)
        self.show_page(1)


if __name__ == "__main__":
    app = Application()
    app.mainloop()