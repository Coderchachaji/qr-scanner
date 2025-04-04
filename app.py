from flask import Flask, render_template, request, send_file, jsonify
import csv
import os
import pandas as pd
import re
import json
import sqlite3
from datetime import datetime, timedelta
import io

app = Flask(__name__)

# Database file path
DATABASE_FILE = 'crew_data.db'
RAW_CSV_FILE = 'raw_scanned_data.csv'  # Keep for temporary data collection

# Temporary storage to accumulate scanned fields
scanned_data = {}
expected_fields = [
    'Crew Id', 'Name', 'Crew Type', 'pass valid Upto',
    'TT No', 'DL No', 'DL Expiry Date'
]

# Initialize database
def init_database():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS crew_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        crew_id TEXT,
        name TEXT,
        crew_type TEXT,
        pass_valid_upto TEXT,
        tt_no TEXT,
        dl_no TEXT,
        dl_expiry_date TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

# Initialize CSV file for temporary storage
def init_raw_csv():
    if not os.path.exists(RAW_CSV_FILE):
        open(RAW_CSV_FILE, 'w').close()
    with open(RAW_CSV_FILE, 'w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=expected_fields)
        writer.writeheader()

# Reset raw CSV file (empty it)
def reset_raw_csv():
    open(RAW_CSV_FILE, 'w').close()
    with open(RAW_CSV_FILE, 'w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=expected_fields)
        writer.writeheader()

# Add data to database
def add_to_database(data):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO crew_data (crew_id, name, crew_type, pass_valid_upto, tt_no, dl_no, dl_expiry_date)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('Crew Id', ''),
        data.get('Name', ''),
        data.get('Crew Type', ''),
        data.get('pass valid Upto', ''),
        data.get('TT No', ''),
        data.get('DL No', ''),
        data.get('DL Expiry Date', '')
    ))
    
    conn.commit()
    conn.close()

# Improved /receive_data route for accumulating data
@app.route('/receive_data', methods=['POST'])
def receive_data():
    global scanned_data

    if request.method == 'POST':
        data = request.json
        
        if not data:
            return jsonify({'status': 'error', 'message': 'कोई डेटा प्राप्त नहीं हुआ'}), 400

        qr_data = data.get('qr_data', '')
        parsed_data = data.get('parsed_data', {})

        # Extract field and value from received data
        match = re.match(r'^(.*?):\s*(.*)$', qr_data.strip())
        if match:
            field, value = match.groups()
            field = field.strip()
            value = value.strip()

            if field in expected_fields:
                scanned_data[field] = value

            # Write to CSV and database when all fields are captured
            if len(scanned_data) == len(expected_fields):
                # Add to temporary CSV file
                with open(RAW_CSV_FILE, 'a', newline='') as file:
                    writer = csv.DictWriter(file, fieldnames=expected_fields)
                    if file.tell() == 0:  # Add header if file is empty
                        writer.writeheader()
                    writer.writerow(scanned_data)
                
                # Add to database for permanent storage
                add_to_database(scanned_data)

                # Clear accumulated data for the next entry
                scanned_data.clear()

                return jsonify({'status': 'success', 'message': 'सभी डेटा सफलतापूर्वक सहेजा गया'})

        return jsonify({'status': 'partial', 'message': 'डेटा प्राप्त हुआ, अधिक फ़ील्ड की प्रतीक्षा'})

# Process raw data into database
def process_raw_data():
    if not os.path.exists(RAW_CSV_FILE):
        return False

    try:
        # Check if the file has content beyond the header
        with open(RAW_CSV_FILE, 'r') as file:
            lines = file.readlines()
            if len(lines) <= 1:  # Only header or empty
                return False

        # Read the raw data
        df = pd.read_csv(RAW_CSV_FILE)
        
        # Add each row to the database
        conn = sqlite3.connect(DATABASE_FILE)
        for _, row in df.iterrows():
            data = row.to_dict()
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO crew_data (crew_id, name, crew_type, pass_valid_upto, tt_no, dl_no, dl_expiry_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get('Crew Id', ''),
                data.get('Name', ''),
                data.get('Crew Type', ''),
                data.get('pass valid Upto', ''),
                data.get('TT No', ''),
                data.get('DL No', ''),
                data.get('DL Expiry Date', '')
            ))
        conn.commit()
        conn.close()

        # Clear the `RAW_CSV_FILE` only after successful processing
        reset_raw_csv()

        return True

    except Exception as e:
        print(f"Error processing data: {str(e)}")
        return False

# Route for the main page
@app.route('/')
def index():
    return render_template('index.html')

# Route to trigger data processing
@app.route('/process_data')
def process_data():
    if process_raw_data():
        return jsonify({'status': 'success', 'message': 'डेटा सफलतापूर्वक प्रोसेस किया गया'})
    else:
        return jsonify({'status': 'error', 'message': 'प्रोसेस करने के लिए कोई डेटा नहीं या प्रोसेसिंग त्रुटि'}), 400

# Route to download the data as CSV
@app.route('/download')
def download():
    try:
        # Get data from database including only records from the last 30 days
        conn = sqlite3.connect(DATABASE_FILE)
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        
        query = '''
        SELECT crew_id, name, crew_type, pass_valid_upto, tt_no, dl_no, dl_expiry_date
        FROM crew_data
        WHERE created_at >= ?
        '''
        
        df = pd.read_sql_query(query, conn, params=(thirty_days_ago,))
        conn.close()
        
        # Convert column names back to match expected fields
        df.columns = ['Crew Id', 'Name', 'Crew Type', 'pass valid Upto', 'TT No', 'DL No', 'DL Expiry Date']
        
        # Create a CSV file in memory
        csv_data = io.StringIO()
        df.to_csv(csv_data, index=False)
        csv_data.seek(0)
        
        # Send the CSV file as an attachment
        return send_file(
            io.BytesIO(csv_data.getvalue().encode('utf-8')),
            mimetype='text/csv',
            download_name='crew_data.csv',
            as_attachment=True
        )
    except Exception as e:
        return f"डाउनलोड के लिए डेटा तैयार करने में त्रुटि: {str(e)}", 500

# Route to view data from database
@app.route('/view_data')
def view_data():
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        # Get data from the last 30 days
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        
        query = '''
        SELECT crew_id, name, crew_type, pass_valid_upto, tt_no, dl_no, dl_expiry_date
        FROM crew_data
        WHERE created_at >= ?
        '''
        
        df = pd.read_sql_query(query, conn, params=(thirty_days_ago,))
        conn.close()
        
        # Convert column names to match expected fields for display
        df.columns = ['Crew Id', 'Name', 'Crew Type', 'pass valid Upto', 'TT No', 'DL No', 'DL Expiry Date']
        
        data = [df.columns.tolist()] + df.values.tolist()
        return render_template('view_data.html', data=data)
    except Exception as e:
        return f"डेटा पढ़ने में त्रुटि: {str(e)}", 500

# New route to reset all data older than 30 days
@app.route('/cleanup_old_data', methods=['POST'])
def cleanup_old_data():
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        # Delete records older than 30 days
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('DELETE FROM crew_data WHERE created_at < ?', (thirty_days_ago,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return jsonify({
            'status': 'success', 
            'message': f'{deleted_count} पुराने रिकॉर्ड हटा दिए गए हैं'
        })
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': f'पुराने डेटा को हटाने में त्रुटि: {str(e)}'
        }), 500

# Route to manually reset raw data
@app.route('/reset_raw')
def reset_raw():
    reset_raw_csv()
    return jsonify({'status': 'success', 'message': 'कच्चा डेटा रीसेट कर दिया गया है'})

# Reset all data in the database
@app.route('/reset_data', methods=['POST'])
def reset_data():
    try:
        # Reset raw CSV file
        reset_raw_csv()
        
        # Clear accumulated data
        global scanned_data
        scanned_data = {}
        
        # Clear database
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM crew_data')
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'success', 'message': 'सभी डेटा सफलतापूर्वक रीसेट कर दिया गया है'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'रीसेट करने में त्रुटि: {str(e)}'}), 500

if __name__ == '__main__':
    init_database()
    init_raw_csv()
    app.run(debug=True)