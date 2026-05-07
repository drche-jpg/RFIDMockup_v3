# Generate the Python Tkinter GUI script
python_gui_code = """import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import qrcode
import os

def select_file():
    filename = filedialog.askopenfilename(title="Select Inventory File", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
    file_path_var.set(filename)

def select_folder():
    foldername = filedialog.askdirectory(title="Select Output Folder")
    folder_path_var.set(foldername)

def generate_qrs():
    csv_file = file_path_var.get()
    output_dir = folder_path_var.get()

    if not csv_file or not output_dir:
        messagebox.showwarning("Input Error", "Please select both a CSV file and an output folder.")
        return

    try:
        df = pd.read_csv(csv_file)
        count = 0
        for index, row in df.iterrows():
            # Check if Storage Bin exists in the columns
            if 'Storage Bin' not in df.columns:
                messagebox.showerror("Error", "The CSV file must contain a 'Storage Bin' column.")
                return
                
            storage_bin = str(row['Storage Bin'])
            
            # Skip empty rows
            if pd.isna(storage_bin) or storage_bin.strip() in ['nan', '']:
                continue
                
            # Define the static URL for the physical storage bin
            tag_id = f"TAG-{storage_bin.strip()}"
            
            # Note: Changed URL format slightly so it works with the standalone HTML file via URL parameters
            static_url = f"https://logistics-portal.local/portal.html?tag={tag_id}"
            
            # Generate the QR code image
            qr = qrcode.make(static_url)
            
            # Save the image to the output folder
            file_name = f"{tag_id}.png"
            file_path = os.path.join(output_dir, file_name)
            qr.save(file_path)
            count += 1
            
        messagebox.showinfo("Success", f"Successfully generated {count} QR code(s) in:\\n{output_dir}")
        
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred:\\n{str(e)}")

# Set up the main window
root = tk.Tk()
root.title("RFID QR Code Generator")
root.geometry("500x250")
root.configure(padx=20, pady=20)

file_path_var = tk.StringVar()
folder_path_var = tk.StringVar()

# Title Label
tk.Label(root, text="Material QR Code Generator", font=("Arial", 14, "bold")).pack(pady=(0, 15))

# File Selection
frame1 = tk.Frame(root)
frame1.pack(fill="x", pady=5)
tk.Label(frame1, text="1. Select CSV Data:", width=15, anchor="w").pack(side="left")
tk.Entry(frame1, textvariable=file_path_var, width=30).pack(side="left", padx=5)
tk.Button(frame1, text="Browse", command=select_file).pack(side="left")

# Folder Selection
frame2 = tk.Frame(root)
frame2.pack(fill="x", pady=5)
tk.Label(frame2, text="2. Save QRs To:", width=15, anchor="w").pack(side="left")
tk.Entry(frame2, textvariable=folder_path_var, width=30).pack(side="left", padx=5)
tk.Button(frame2, text="Browse", command=select_folder).pack(side="left")

# Generate Button
tk.Button(root, text="Generate QR Codes", command=generate_qrs, bg="#003366", fg="white", font=("Arial", 12)).pack(pady=20)

root.mainloop()
"""

with open("generate_qrs_gui.py", "w", encoding="utf-8") as f:
    f.write(python_gui_code)


# Generate the Standalone HTML Webpage
html_portal_code = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Logistics Tag Portal</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 500px; margin: auto; background: white; padding: 25px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        h2 { color: #003366; margin-top: 0; border-bottom: 2px solid #eee; padding-bottom: 10px;}
        .tag-header { background-color: #e9ecef; padding: 10px; border-radius: 4px; text-align: center; font-size: 1.2em; font-weight: bold; margin-bottom: 20px; border-left: 5px solid #cc7000; }
        
        /* Form Styles */
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; font-size: 0.9em; }
        input[type="text"], input[type="number"] { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
        
        /* Button Styles */
        button { width: 100%; padding: 12px; border: none; border-radius: 4px; font-size: 1em; cursor: pointer; margin-top: 10px; font-weight: bold; }
        .btn-primary { background-color: #003366; color: white; }
        .btn-primary:hover { background-color: #002244; }
        .btn-danger { background-color: #dc3545; color: white; }
        .btn-danger:hover { background-color: #c82333; }
        .btn-secondary { background-color: #6c757d; color: white; margin-bottom: 20px;}
        
        /* Display Data Styles */
        .data-display { background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 15px; margin-bottom: 20px; }
        .data-row { display: flex; justify-content: space-between; border-bottom: 1px solid #eee; padding: 8px 0; }
        .data-row:last-child { border-bottom: none; }
        .data-label { font-weight: bold; color: #555; }
        
        /* Utility */
        .hidden { display: none; }
        .search-box { display: flex; gap: 10px; margin-bottom: 20px; }
    </style>
</head>
<body>

<div class="container">
    <h2>Warehouse Tag Manager</h2>
    
    <div id="searchSection" class="search-box">
        <input type="text" id="manualTagInput" placeholder="Enter Tag ID (e.g. TAG-A01010)">
        <button class="btn-primary" onclick="loadManualTag()" style="width: auto; margin-top: 0;">Search</button>
    </div>

    <div id="tagInfoSection" class="hidden">
        <div class="tag-header" id="displayTagId">TAG-XXXX</div>
        
        <div id="viewMaterial" class="hidden">
            <h3 style="margin-top: 0; color: #28a745;">✓ Material Assigned</h3>
            <div class="data-display" id="materialData">
                </div>
            <button class="btn-danger" onclick="clearTag()">Clean QR (Remove Material)</button>
        </div>

        <div id="registerMaterial" class="hidden">
            <h3 style="margin-top: 0; color: #cc7000;">⚠ Tag is Empty</h3>
            <p style="font-size: 0.9em; color: #666;">Register a new material to this location.</p>
            
            <div class="form-group">
                <label>Material Number</label>
                <input type="text" id="inputMatNum" placeholder="e.g. 05.04.00.069.9">
            </div>
            <div class="form-group">
                <label>Material Description</label>
                <input type="text" id="inputDesc" placeholder="e.g. CMT PLUG...">
            </div>
            <div class="form-group">
                <label>Total Stock</label>
                <input type="number" id="inputStock" placeholder="e.g. 5">
            </div>
            <div class="form-group">
                <label>Unit of Measure</label>
                <input type="text" id="inputUnit" placeholder="e.g. EA">
            </div>
            
            <button class="btn-primary" onclick="saveTag()">Register Material</button>
        </div>
    </div>
</div>

<script>
    // Get the Tag ID from the URL (e.g., portal.html?tag=TAG-A01010)
    const urlParams = new URLSearchParams(window.location.search);
    let currentTag = urlParams.get('tag');

    // Initialize the page
    if (currentTag) {
        document.getElementById('manualTagInput').value = currentTag;
        loadTagData(currentTag);
    }

    function loadManualTag() {
        const val = document.getElementById('manualTagInput').value.trim();
        if (val) {
            currentTag = val;
            // Update URL without reloading
            window.history.pushState({}, '', '?tag=' + currentTag);
            loadTagData(currentTag);
        }
    }

    function loadTagData(tagId) {
        document.getElementById('tagInfoSection').classList.remove('hidden');
        document.getElementById('displayTagId').innerText = tagId;
        
        // We use the browser's LocalStorage to simulate a database.
        // This makes the page completely standalone.
        const storedData = localStorage.getItem(tagId);
        
        if (storedData) {
            // Tag has material
            const data = JSON.parse(storedData);
            document.getElementById('registerMaterial').classList.add('hidden');
            document.getElementById('viewMaterial').classList.remove('hidden');
            
            document.getElementById('materialData').innerHTML = `
                <div class="data-row"><span class="data-label">Material</span> <span>${data.matNum}</span></div>
                <div class="data-row"><span class="data-label">Description</span> <span>${data.desc}</span></div>
                <div class="data-row"><span class="data-label">Stock</span> <span>${data.stock} ${data.unit}</span></div>
                <div class="data-row"><span class="data-label">Last Updated</span> <span>${data.timestamp}</span></div>
            `;
        } else {
            // Tag is empty
            document.getElementById('viewMaterial').classList.add('hidden');
            document.getElementById('registerMaterial').classList.remove('hidden');
            
            // Clear inputs
            document.getElementById('inputMatNum').value = '';
            document.getElementById('inputDesc').value = '';
            document.getElementById('inputStock').value = '';
            document.getElementById('inputUnit').value = '';
        }
    }

    function saveTag() {
        const data = {
            matNum: document.getElementById('inputMatNum').value || 'N/A',
            desc: document.getElementById('inputDesc').value || 'N/A',
            stock: document.getElementById('inputStock').value || '0',
            unit: document.getElementById('inputUnit').value || 'EA',
            timestamp: new Date().toLocaleString()
        };
        
        // Save to browser memory
        localStorage.setItem(currentTag, JSON.stringify(data));
        alert('Material successfully registered to ' + currentTag);
        
        // Reload view
        loadTagData(currentTag);
    }

    function clearTag() {
        if (confirm('Are you sure you want to remove the material data from this tag? The physical QR code will remain the same.')) {
            localStorage.removeItem(currentTag);
            loadTagData(currentTag);
        }
    }
</script>

</body>
</html>
"""

with open("portal.html", "w", encoding="utf-8") as f:
    f.write(html_portal_code)

print("Files generated successfully.")