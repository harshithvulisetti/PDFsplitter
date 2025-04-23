import os
import fitz  # PyMuPDF
from PyPDF2 import PdfReader, PdfWriter
from flask import Flask, request, render_template, send_file, flash, redirect, url_for, send_from_directory
import re
import shutil
import zipfile
from werkzeug.utils import secure_filename
import time
import string
import random

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['SECRET_KEY'] = 'your-secret-key'  # Needed for flash messages
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit upload size to 16MB

# Ensure upload and output directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

def generate_unique_folder(base_folder, base_name):
    """Generate a unique folder name by appending a timestamp or random string if needed."""
    sanitized_name = ''.join(c for c in base_name if c.isalnum() or c in ('_', '-')).strip()
    if not sanitized_name:
        sanitized_name = 'default_folder'
    
    folder_path = os.path.join(base_folder, sanitized_name)
    if not os.path.exists(folder_path):
        return folder_path, sanitized_name
    
    # Append timestamp and random string to avoid conflicts
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    unique_name = f"{sanitized_name}_{timestamp}_{random_suffix}"
    folder_path = os.path.join(base_folder, unique_name)
    return folder_path, unique_name

def extract_names_from_second_page(pdf_path):
    """Extracts names from the second page of the given PDF."""
    names = []
    try:
        doc = fitz.open(pdf_path)
        if len(doc) < 2:
            return names, "The PDF must have at least 2 pages."

        # Extract text from the second page
        second_page = doc.load_page(1)  # Page index starts from 0
        text = second_page.get_text("text")

        # Regex pattern to find ranked names
        pattern = re.compile(r"^([A-Za-z .]+)\s+\d+\s+BNI [A-Za-z]+", re.MULTILINE)
        matches = pattern.findall(text)

        names = [match.strip() for match in matches]
        doc.close()
        return names, None
    except Exception as e:
        return names, f"Error extracting names: {str(e)}"

def split_pdf(input_pdf_path, output_directory):
    """Splits the PDF and renames output files based on names from second page."""
    try:
        # Extract names from the second page
        names, error = extract_names_from_second_page(input_pdf_path)
        if error:
            return False, error
        if not names:
            return False, "No names were extracted from the second page."

        # Read the input PDF
        reader = PdfReader(input_pdf_path)
        total_pages = len(reader.pages)

        if total_pages < 6:
            return False, "The PDF must have at least 6 pages."

        # Process PDF pages and rename
        output_files = []
        for i, name in enumerate(names, start=1):
            new_file_name = f"{name}.pdf"
            writer = PdfWriter()

            # Add pages 1 to 4
            for j in range(4):
                writer.add_page(reader.pages[j])

            # Add the custom 5th page
            fifth_page_index = i + 4
            if fifth_page_index < total_pages:
                writer.add_page(reader.pages[fifth_page_index])

            # Save the new PDF
            output_pdf_path = os.path.join(output_directory, new_file_name)
            with open(output_pdf_path, 'wb') as output_pdf:
                writer.write(output_pdf)
            output_files.append(new_file_name)

        return True, output_files
    except Exception as e:
        return False, f"An error occurred: {str(e)}"

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Check if a file was uploaded
        if 'pdf_file' not in request.files:
            flash('No file selected.', 'error')
            return redirect(url_for('index'))

        pdf_file = request.files['pdf_file']
        output_folder_name = request.form.get('output_folder', '').strip()

        if pdf_file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('index'))

        if not output_folder_name:
            flash('Please specify an output folder name.', 'error')
            return redirect(url_for('index'))

        if pdf_file and pdf_file.filename.endswith('.pdf'):
            # Securely save the uploaded file
            filename = secure_filename(pdf_file.filename)
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            pdf_file.save(pdf_path)

            # Generate unique output folder
            output_folder_path, output_folder_name = generate_unique_folder(
                app.config['OUTPUT_FOLDER'], output_folder_name
            )
            os.makedirs(output_folder_path, exist_ok=True)

            # Split the PDF
            success, result = split_pdf(pdf_path, output_folder_path)
            if success:
                flash(f'PDF splitting complete! Files saved in folder: {output_folder_name}. Download individual files or all as a ZIP below.', 'success')
                return render_template('index.html', files=result, output_folder=output_folder_name)
            else:
                flash(result, 'error')
                return redirect(url_for('index'))

    return render_template('index.html', files=None, output_folder=None)

@app.route('/download/<output_folder>/<filename>')
def download_file(output_folder, filename):
    folder_path = os.path.join(app.config['OUTPUT_FOLDER'], output_folder)
    return send_from_directory(folder_path, filename, as_attachment=True)

@app.route('/download_zip/<output_folder>')
def download_zip(output_folder):
    folder_path = os.path.join(app.config['OUTPUT_FOLDER'], output_folder)
    zip_filename = f"{output_folder}.zip"
    zip_path = os.path.join(app.config['OUTPUT_FOLDER'], zip_filename)

    # Create a ZIP file containing all PDFs in the output folder
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.endswith('.pdf'):
                    file_path = os.path.join(root, file)
                    zipf.write(file_path, os.path.join(output_folder, file))

    return send_file(zip_path, as_attachment=True, download_name=zip_filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
