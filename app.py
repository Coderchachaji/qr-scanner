from flask import Flask, render_template, request, send_file, jsonify
import csv
import os
import pandas as pd
import re
import json

app = Flask(__name__)

# File paths
RAW_CSV_FILE = 'raw_scanned_data.csv'
PROCESSED_CSV_FILE = 'processed_crew_data.csv'

# Temporary storage to accumulate scanned fields
scanned_data = {}
expected_fields = [
    'Crew Id', 'Name', 'Crew Type', 'pass valid Upto',
    'TT No', 'DL No', 'DL Expiry Date'
]

# Initialize CSV file
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

# Reset processed CSV file (empty it)
def reset_processed_csv():
    if os.path.exists(PROCESSED_CSV_FILE):
        open(PROCESSED_CSV_FILE, 'w').close()
        with open(PROCESSED_CSV_FILE, 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=expected_fields)
            writer.writeheader()

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

            # Write to CSV when all fields are captured
            if len(scanned_data) == len(expected_fields):
                with open(RAW_CSV_FILE, 'a', newline='') as file:
                    writer = csv.DictWriter(file, fieldnames=expected_fields)
                    if file.tell() == 0:  # Add header if file is empty
                        writer.writeheader()
                    writer.writerow(scanned_data)

                # Clear accumulated data for the next entry
                scanned_data.clear()

                return jsonify({'status': 'success', 'message': 'सभी डेटा सफलतापूर्वक सहेजा गया'})

        return jsonify({'status': 'partial', 'message': 'डेटा प्राप्त हुआ, अधिक फ़ील्ड की प्रतीक्षा'})

# Process raw data into structured CSV
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

        # If processed file exists, append without duplicating headers
        if os.path.exists(PROCESSED_CSV_FILE) and os.path.getsize(PROCESSED_CSV_FILE) > 0:
            existing_df = pd.read_csv(PROCESSED_CSV_FILE)
            combined_df = pd.concat([existing_df, df], ignore_index=True)
            combined_df.to_csv(PROCESSED_CSV_FILE, index=False)
        else:
            df.to_csv(PROCESSED_CSV_FILE, index=False)

        # ✅ Clear the `RAW_CSV_FILE` only after successful processing
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

# Route to download the processed CSV
@app.route('/download')
def download():
    process_raw_data()
    if os.path.exists(PROCESSED_CSV_FILE):
        return send_file(PROCESSED_CSV_FILE, 
                         mimetype='text/csv', 
                         download_name='crew_data.csv', 
                         as_attachment=True)
    else:
        return "डाउनलोड के लिए कोई डेटा उपलब्ध नहीं है", 404

# Route to view processed data
@app.route('/view_data')
def view_data():
    process_raw_data()

    if not os.path.exists(PROCESSED_CSV_FILE):
        return render_template('view_data.html', data=[])

    try:
        df = pd.read_csv(PROCESSED_CSV_FILE)
        data = [df.columns.tolist()] + df.values.tolist()
        return render_template('view_data.html', data=data)
    except Exception as e:
        return f"डेटा पढ़ने में त्रुटि: {str(e)}", 500

# Debug route for raw data inspection
@app.route('/debug_raw')
def debug_raw():
    if os.path.exists(RAW_CSV_FILE):
        with open(RAW_CSV_FILE, 'r') as file:
            raw_content = file.read()
        return f"<pre>{raw_content}</pre>"
    return "कोई कच्चा डेटा उपलब्ध नहीं है"

# Route to manually reset raw data
@app.route('/reset_raw')
def reset_raw():
    reset_raw_csv()
    return jsonify({'status': 'success', 'message': 'कच्चा डेटा रीसेट कर दिया गया है'})

# New route to reset both CSV files
@app.route('/reset_data', methods=['POST'])
def reset_data():
    try:
        # Reset both raw and processed CSV files
        reset_raw_csv()
        reset_processed_csv()
        
        # Also clear any accumulated data
        global scanned_data
        scanned_data = {}
        
        return jsonify({'status': 'success', 'message': 'सभी डेटा सफलतापूर्वक रीसेट कर दिया गया है'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'रीसेट करने में त्रुटि: {str(e)}'}), 500

if __name__ == '__main__':
    init_raw_csv()
    app.run(debug=True)