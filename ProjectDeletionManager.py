import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import xml.etree.ElementTree as ET
import shutil


class ProjectDeletionManager(tk.Toplevel):
    """Dialog for managing project deletion from ProjectList.xml"""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.title("Project Deletion Manager")
        self.geometry("1200x600")
        self.transient(parent)
        self.grab_set()
        
        # Set window icon
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "SeisWare.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
        
        self.xml_path = None
        self.projects = {}  # {project_name: {'data_dir': path, 'version': version, 'last_updated': date, 'size': size, 'xml_element': element}}
        self.sort_column = None
        self.sort_reverse = False
        self._is_closing = False  # Flag to prevent updates after closing
        
        self._create_widgets()
        self._auto_load_default()
        
        # Bind window close event
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _on_close(self):
        """Handle window close event"""
        self._is_closing = True
        self.destroy()
    
    def _create_widgets(self):
        """Create the dialog widgets"""
        
        # XML file selection
        file_frame = ttk.LabelFrame(self, text="SeisWare Project List", padding=10)
        file_frame.pack(fill="x", padx=10, pady=10)
        
        username = os.getenv('USERNAME')
        default_path = rf"C:\Users\{username}\AppData\Roaming\SeisWare\SeisWare\Support\ProjectList.xml"
        self.path_var = tk.StringVar(value=default_path)
        
        ttk.Entry(file_frame, textvariable=self.path_var, width=60).pack(side="left", padx=5)
        ttk.Button(file_frame, text="Browse", command=self._browse_xml).pack(side="left", padx=5)
        ttk.Button(file_frame, text="Load", command=self._load_projects).pack(side="left")
        
        # Project list with treeview
        list_frame = ttk.LabelFrame(self, text="Projects", padding=10)
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create treeview with columns
        columns = ('project', 'version', 'updated', 'size', 'directory')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings', selectmode='extended')
        
        # Define column headings and configure
        self.tree.heading('project', text='Project Name', command=lambda: self._sort_column('project'))
        self.tree.heading('version', text='Version', command=lambda: self._sort_column('version'))
        self.tree.heading('updated', text='Last Updated', command=lambda: self._sort_column('updated'))
        self.tree.heading('size', text='Folder Size', command=lambda: self._sort_column('size'))
        self.tree.heading('directory', text='Data Directory', command=lambda: self._sort_column('directory'))
        
        # Configure column widths
        self.tree.column('project', width=180, anchor='w')
        self.tree.column('version', width=80, anchor='center')
        self.tree.column('updated', width=130, anchor='center')
        self.tree.column('size', width=100, anchor='e')
        self.tree.column('directory', width=400, anchor='w')
        
        # Add scrollbars
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Grid layout for tree and scrollbars
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        # Options and actions
        action_frame = ttk.Frame(self)
        action_frame.pack(fill="x", padx=10, pady=10)
        
        # Checkbox for deleting files
        self.delete_files_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(action_frame, text="Delete files on disc", 
                       variable=self.delete_files_var).pack(side="left", padx=10)
        
        # Buttons
        button_frame = ttk.Frame(action_frame)
        button_frame.pack(side="right")
        
        ttk.Button(button_frame, text="Cancel", command=self._on_close).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Delete Selected Projects", 
                  command=self._delete_projects).pack(side="left", padx=5)
        
        # Status bar
        status_frame = ttk.Frame(self)
        status_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var, relief="sunken").pack(fill="x")
    
    def _get_folder_size(self, folder_path, sample_mode=False):
        """Calculate total size of folder in bytes
        
        Args:
            folder_path: Path to folder
            sample_mode: If True, estimate size by sampling instead of full scan
        """
        if not folder_path or not os.path.exists(folder_path):
            return 0, False  # Return (size, is_estimated)
        
        if sample_mode:
            return self._estimate_folder_size(folder_path)
        
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except (OSError, FileNotFoundError):
                        # Skip files we can't access
                        pass
        except Exception as e:
            print(f"Error calculating folder size for {folder_path}: {e}")
        
        return total_size, False  # Not estimated
    
    def _estimate_folder_size(self, folder_path):
        """Estimate folder size by sampling files
        
        This is much faster for large folders. It samples files and estimates based on:
        - Average file size in each directory
        - Total file count estimation
        """
        total_size = 0
        total_files = 0
        sampled_dirs = 0
        max_sample_files = 50  # Sample up to 50 files per directory
        
        try:
            for dirpath, dirnames, filenames in os.walk(folder_path):
                sampled_dirs += 1
                file_count = len(filenames)
                
                if file_count == 0:
                    continue
                
                # Sample files from this directory
                sample_size = min(file_count, max_sample_files)
                sample_files = filenames[:sample_size] if file_count <= max_sample_files else \
                              [filenames[i] for i in range(0, file_count, max(1, file_count // max_sample_files))][:max_sample_files]
                
                dir_sample_size = 0
                valid_samples = 0
                for filename in sample_files:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        dir_sample_size += os.path.getsize(filepath)
                        valid_samples += 1
                    except (OSError, FileNotFoundError):
                        pass
                
                # Extrapolate to full directory
                if valid_samples > 0:
                    avg_file_size = dir_sample_size / valid_samples
                    estimated_dir_size = avg_file_size * file_count
                    total_size += estimated_dir_size
                    total_files += file_count
                
                # Limit depth to avoid scanning too deep
                if sampled_dirs > 100:  # Limit to 100 directories for very large projects
                    break
            
            return int(total_size), True  # Return as estimated
            
        except Exception as e:
            print(f"Error estimating folder size for {folder_path}: {e}")
            return 0, True
    
    def _format_size(self, size_bytes, is_estimated=False):
        """Format size in bytes to human readable format
        
        Args:
            size_bytes: Size in bytes
            is_estimated: Whether this is an estimated value
        """
        if size_bytes == 0:
            return "N/A"
        
        # Convert to appropriate unit
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                size_str = f"{size_bytes:.2f} {unit}"
                return f"~{size_str}" if is_estimated else size_str
            size_bytes /= 1024.0
        
        size_str = f"{size_bytes:.2f} PB"
        return f"~{size_str}" if is_estimated else size_str
    
    def _sort_column(self, col):
        """Sort treeview by column"""
        # Toggle sort direction if clicking the same column
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False
        
        # Get all items
        items = [(self.tree.set(item, col), item) for item in self.tree.get_children('')]
        
        # Special handling for size column (sort numerically)
        if col == 'size':
            def sort_key(item):
                val = item[0]
                if val == 'N/A' or val == 'Calculating...':
                    return -1 if self.sort_reverse else float('inf')
                # Extract numeric value from formatted string (e.g., "123.45 MB")
                try:
                    # Handle estimated sizes (starting with ~)
                    val = val.lstrip('~')
                    num_str = val.split()[0]
                    num = float(num_str)
                    unit = val.split()[1]
                    # Convert to bytes for proper sorting
                    multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
                    return num * multipliers.get(unit, 1)
                except:
                    return -1 if self.sort_reverse else float('inf')
            
            items.sort(key=sort_key, reverse=self.sort_reverse)
        else:
            # Sort items
            items.sort(reverse=self.sort_reverse)
        
        # Rearrange items in sorted positions
        for index, (val, item) in enumerate(items):
            self.tree.move(item, '', index)
        
        # Update column heading to show sort direction
        for column in ('project', 'version', 'updated', 'size', 'directory'):
            heading = self.tree.heading(column)['text'].replace(' ▲', '').replace(' ▼', '')
            if column == col:
                heading += ' ▼' if self.sort_reverse else ' ▲'
            self.tree.heading(column, text=heading)
    
    def _auto_load_default(self):
        """Automatically load the default project file on startup"""
        path = self.path_var.get()
        if os.path.exists(path):
            self.after(100, self._load_projects)
    
    def _browse_xml(self):
        """Browse for ProjectList.xml file"""
        path = filedialog.askopenfilename(
            title="Select ProjectList.xml",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
            initialdir=os.path.dirname(self.path_var.get())
        )
        if path:
            self.path_var.set(path)
    
    def _load_projects(self, recalculate_sizes=True):
        """Load projects from the XML file
        
        Args:
            recalculate_sizes: If False, skip size calculation (used after deletion)
        """
        xml_path = self.path_var.get()
        
        if not os.path.exists(xml_path):
            messagebox.showerror("Error", f"File not found:\n{xml_path}")
            return
        
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            self.xml_path = xml_path
            self.xml_tree = tree
            
            # Save existing size data if not recalculating
            existing_sizes = {}
            if not recalculate_sizes:
                existing_sizes = {name: info['size'] for name, info in self.projects.items()}
            
            self.projects.clear()
            
            # Clear existing items
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            # Parse projects from XML
            project_items = []
            for project_elem in root.findall('.//Project'):
                name_elem = project_elem.find('Name')
                data_dir_elem = project_elem.find('DataDirectory')
                version_elem = project_elem.find('Version')
                updated_elem = project_elem.find('LastUpdated')
                
                if name_elem is not None:
                    project_name = name_elem.text
                    data_dir = data_dir_elem.text if data_dir_elem is not None else ""
                    version = version_elem.text if version_elem is not None else ""
                    last_updated = updated_elem.text if updated_elem is not None else ""
                    
                    # Use existing size if available and not recalculating
                    if not recalculate_sizes and project_name in existing_sizes:
                        size = existing_sizes[project_name]
                        # Check if size string contains '~' to determine if estimated
                        formatted_size = self._format_size(size, size > 0)  # Assume estimated if > 0
                    else:
                        size = 0
                        formatted_size = "Calculating..." if recalculate_sizes else "N/A"
                    
                    self.projects[project_name] = {
                        'data_dir': data_dir,
                        'version': version,
                        'last_updated': last_updated,
                        'size': size,
                        'xml_element': project_elem
                    }
                    
                    # Insert into treeview
                    item_id = self.tree.insert("", "end", values=(
                        project_name,
                        version,
                        last_updated,
                        formatted_size,
                        data_dir
                    ))
                    
                    if recalculate_sizes and size == 0:
                        project_items.append((project_name, data_dir, item_id))
            
            count = len(self.projects)
            
            if recalculate_sizes and project_items:
                self.status_var.set(f"Loaded {count} projects from {os.path.basename(xml_path)} - Estimating sizes...")
                
                # Calculate sizes in background using estimation for speed
                import threading
                def calculate_sizes():
                    for idx, (project_name, data_dir, item_id) in enumerate(project_items, 1):
                        # Check if window is closing
                        if self._is_closing:
                            break
                        
                        # Use sampling/estimation mode for faster calculation
                        size_bytes, is_estimated = self._get_folder_size(data_dir, sample_mode=True)
                        
                        # Check again before updating
                        if self._is_closing:
                            break
                        
                        self.projects[project_name]['size'] = size_bytes
                        formatted_size = self._format_size(size_bytes, is_estimated)
                        
                        # Update the tree item - wrapped in try/except for safety
                        def safe_update(iid, sz):
                            if not self._is_closing:
                                try:
                                    self.tree.set(iid, 'size', sz)
                                except:
                                    pass  # Tree view may be destroyed
                        
                        self.after(0, lambda iid=item_id, sz=formatted_size: safe_update(iid, sz))
                        
                        # Update status every 5 projects to reduce UI updates
                        if idx % 5 == 0 or idx == len(project_items):
                            def safe_status_update(i, t):
                                if not self._is_closing:
                                    try:
                                        self.status_var.set(f"Estimated sizes for {i}/{t} projects")
                                    except:
                                        pass
                            
                            self.after(0, lambda i=idx, t=len(project_items): safe_status_update(i, t))
                    
                    # Final status update
                    def final_status():
                        if not self._is_closing:
                            try:
                                self.status_var.set(f"Loaded {count} projects (sizes estimated)")
                            except:
                                pass
                    
                    self.after(0, final_status)
                
                threading.Thread(target=calculate_sizes, daemon=True).start()
            else:
                self.status_var.set(f"Loaded {count} projects")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load projects:\n{str(e)}")
            self.status_var.set("Failed to load projects")
    
    def _delete_projects(self):
        """Delete selected projects from the list and optionally from disk"""
        selected_items = self.tree.selection()
        
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select at least one project to delete.")
            return
        
        # Get selected project names and their sizes
        selected_projects = []
        total_size = 0
        for item in selected_items:
            project_name = self.tree.item(item)['values'][0]
            selected_projects.append(project_name)
            if project_name in self.projects:
                total_size += self.projects[project_name]['size']
        
        # Confirmation dialog
        delete_files = self.delete_files_var.get()
        file_warning = f"\n\nWARNING: {self._format_size(total_size)} of project data will be permanently deleted from disk!" if delete_files and total_size > 0 else ""
        
        msg = f"Delete {len(selected_projects)} project(s) from the project list?{file_warning}\n\nProjects to delete:\n"
        msg += "\n".join(f"  • {name}" for name in selected_projects)
        
        if not messagebox.askyesno("Confirm Deletion", msg, icon='warning'):
            return
        
        # Track results
        deleted_from_xml = []
        deleted_from_disk = []
        errors = []
        
        # Delete each selected project
        for project_name in selected_projects:
            try:
                project_info = self.projects[project_name]
                
                # Remove from XML
                xml_element = project_info['xml_element']
                parent = self.xml_tree.getroot()
                parent.remove(xml_element)
                deleted_from_xml.append(project_name)
                
                # Delete files if checkbox is selected
                if delete_files and project_info['data_dir']:
                    data_dir = project_info['data_dir']
                    if os.path.exists(data_dir):
                        try:
                            shutil.rmtree(data_dir)
                            deleted_from_disk.append(project_name)
                        except Exception as e:
                            errors.append(f"{project_name} (disk): {str(e)[:100]}")
                    else:
                        errors.append(f"{project_name} (disk): Directory not found - {data_dir}")
                
            except Exception as e:
                errors.append(f"{project_name} (XML): {str(e)[:100]}")
        
        # Save the modified XML
        if deleted_from_xml:
            try:
                self.xml_tree.write(self.xml_path, encoding='utf-8', xml_declaration=True)
                self.status_var.set(f"Deleted {len(deleted_from_xml)} project(s) from XML")
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save XML file:\n{str(e)}")
                return
        
        # Show results
        result_msg = f"Successfully deleted {len(deleted_from_xml)} project(s) from project list"
        
        if delete_files:
            result_msg += f"\nDeleted {len(deleted_from_disk)} project data folder(s) from disk"
            if total_size > 0:
                result_msg += f" ({self._format_size(total_size)})"
        
        if errors:
            error_detail = "\n".join(errors)
            result_msg += f"\n\nErrors encountered:\n{error_detail}"
            messagebox.showwarning("Deletion Complete with Errors", result_msg)
        else:
            messagebox.showinfo("Deletion Complete", result_msg)
        
        # Reload the project list without recalculating sizes
        self._load_projects(recalculate_sizes=False)


if __name__ == "__main__":
    # Test the dialog standalone
    root = tk.Tk()
    root.withdraw()
    dialog = ProjectDeletionManager(root)
    root.mainloop()