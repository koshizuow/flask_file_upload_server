import os
from flask import Flask, request, render_template, send_from_directory, redirect, url_for, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Read the upload folder from the environment variable, with a fallback for local development
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')

# Optional upload size limit in bytes; requests above it get a 413. No limit when unset.
max_content_length = os.environ.get('MAX_CONTENT_LENGTH')
if max_content_length:
    app.config['MAX_CONTENT_LENGTH'] = int(max_content_length)

# Ensure upload folder exists on startup
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_file_extension(filename):
    return os.path.splitext(filename)[1]

def get_file_list(folder_path):
    # Avoid chdir() to prevent race conditions in multi-threaded environments
    try:
        file_list = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
        return [{'name': f, 'type': get_file_extension(f)[1:].lower(), 'path': os.path.join(folder_path, f)} for f in file_list]
    except OSError as e:
        flash(f'Error reading files: {str(e)}')
        return []

def get_file_time(file):
    return os.path.getmtime(file['path'])

def get_unique_filename(folder, filename):
    """
    Return a filename that does not conflict with existing files in `folder`.
    If filename exists, append a numeric counter before the extension, e.g.:
      myfile.txt -> myfile (1).txt -> myfile (2).txt ...
    This avoids overwriting existing files with the same name.
    """
    base, ext = os.path.splitext(filename)
    candidate = filename
    i = 1
    full_path = os.path.join(folder, candidate)
    # Loop until we find a filename that does not exist
    while os.path.exists(full_path):
        candidate = f"{base} ({i}){ext}"
        full_path = os.path.join(folder, candidate)
        i += 1
    return candidate

def sanitize_filename(filename):
    """
    Reduce a client-supplied filename to a safe single path component.
    Unlike werkzeug's secure_filename this keeps non-ASCII characters.
    Returns None if nothing usable is left.
    """
    # Treat both separators alike so Windows-style paths are stripped too
    name = filename.replace('\\', '/')
    name = os.path.basename(name)
    # Drop NUL and other control characters
    name = ''.join(c for c in name if c.isprintable()).strip()
    if name in ('', '.', '..'):
        return None
    return name

def is_inside_upload_folder(path):
    upload_folder_abs = os.path.abspath(app.config['UPLOAD_FOLDER'])
    return os.path.commonpath([upload_folder_abs, os.path.abspath(path)]) == upload_folder_abs

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Handle file upload(s)
        files = request.files.getlist('file')
        for file in files:
            if file.filename:  # Ensure filename is not empty
                filename = sanitize_filename(file.filename)
                if filename is None:
                    flash('Invalid filename')
                    continue
                # Use unique filename to avoid overwriting existing files
                unique_name = get_unique_filename(app.config['UPLOAD_FOLDER'], filename)
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
                if not is_inside_upload_folder(save_path):
                    flash('Invalid file path')
                    continue
                file.save(save_path)
    # Build file list for display
    file_list_decoded = get_file_list(UPLOAD_FOLDER)
    file_list_decoded.sort(key=get_file_time, reverse=True)
    return render_template('index.html', files=file_list_decoded)

@app.route('/uploads/<filename>')
def download_file(filename):
    # Protect against path traversal attacks
    if '..' in filename or filename.startswith('/'):
        flash('Invalid filename')
        return redirect(url_for('index'))
    # Ensure the requested file is inside the upload folder
    file_path = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    upload_folder_abs = os.path.abspath(app.config['UPLOAD_FOLDER'])
    if not file_path.startswith(upload_folder_abs):
        flash('Invalid file path')
        return redirect(url_for('index'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/delete/<filename>', methods=['GET', 'POST'])
def delete_file(filename):
    if request.method == 'POST':
        # Protect against path traversal in delete operation
        if '..' in filename or filename.startswith('/'):
            flash('Invalid filename')
            return redirect(url_for('index'))
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        # Additional validation to ensure deletion stays within upload folder
        file_path_abs = os.path.abspath(file_path)
        upload_folder_abs = os.path.abspath(app.config['UPLOAD_FOLDER'])
        if not file_path_abs.startswith(upload_folder_abs):
            flash('Invalid file path')
            return redirect(url_for('index'))
        if os.path.exists(file_path):
            os.remove(file_path)
        else:
            flash('File not found')
    return redirect(url_for('index'))

@app.route('/healthz')
def health_check():
    return {'status': 'ok'}, 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)