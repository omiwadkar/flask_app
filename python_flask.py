import os
import random
from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from flask_mail import Mail, Message
import boto3
from boto3.s3.transfer import TransferConfig

app = Flask(__name__)
app.secret_key = 'mdls llsf ykqp flnv'  # Replace with a strong secret key

# SMTP Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = ''  # Replace with your Gmail address
app.config['MAIL_PASSWORD'] = ''      # Use the generated app password here

mail = Mail(app)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

S3_BUCKET = '' # repalce with your Bucket name 


# --- SSM Helper Function for AWS Credentials ---
def get_aws_parameter(param_name):
    """
    Fetches a parameter value from AWS SSM Parameter Store.
    Ensure that the IAM role or credentials used to run this code have permission to access SSM.
    """
    ssm = boto3.client('ssm')
    response = ssm.get_parameter(Name=param_name, WithDecryption=True)
    return response['Parameter']['Value']

# Retrieve credentials from SSM Parameter Store
aws_access_key_id = get_aws_parameter('access_key')
aws_secret_access_key = get_aws_parameter('secret_access_key')
region_name = get_aws_parameter('region_name')

# Initialize S3 client with credentials fetched from SSM
s3_client = boto3.client(
    's3',
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    region_name=region_name
)

# Configure multipart upload threshold: files larger than 1 GB will use multipart upload
multipart_config = TransferConfig(multipart_threshold=1024 * 1024 * 1024)

# Store the OTPs temporarily
otp_store = {}

@app.route('/')
def home():
    if 'email' in session:
        return render_template('upload.html', email=session['email'])
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Allow any email to login
        email = request.form.get('email')

        # Generate a random 6-digit OTP
        otp = str(random.randint(100000, 999999))
        otp_store[email] = otp

        # Send the OTP via email
        try:
            msg = Message('Your OTP for Login', sender=app.config['MAIL_USERNAME'], recipients=[email])
            msg.body = f'Your OTP is: {otp}'
            mail.send(msg)
        except Exception as e:
            return f"Error sending OTP: {e}", 500

        session['pending_email'] = email  # Store the pending email in session
        return redirect(url_for('otp_verify'))

    return render_template('login.html')


@app.route('/otp', methods=['GET', 'POST'])
def otp_verify():
    if request.method == 'POST':
        entered_otp = request.form.get('otp')
        email = session.get('pending_email')

        if email in otp_store and otp_store[email] == entered_otp:
            session['email'] = email  # Log the user in
            otp_store.pop(email)  # Remove OTP after verification
            session.pop('pending_email', None)  # Clear pending email
            return redirect(url_for('home'))
        
        return "Invalid OTP. Try again.", 401

    return render_template('otp.html')


@app.route('/logout')
def logout():
    session.pop('email', None)
    return redirect(url_for('login'))

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'email' not in session:
        return redirect(url_for('login'))

    if 'file' not in request.files:
        return "No file part in the request", 400

    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400

    if file:
        file_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(file_path)

        try:
            # Use the logged-in user's email as the folder name.
            user_folder = session['email']
            # Construct the S3 key as "user_folder/filename"
            s3_key = f"{user_folder}/{file.filename}"
            
            # Use multipart upload configuration if file is greater than 500 MB
            s3_client.upload_file(file_path, S3_BUCKET, s3_key, Config=multipart_config)
            return f"File '{file.filename}' has been uploaded to folder '{user_folder}' in bucket '{S3_BUCKET}'"
        except Exception as e:
            return f"Error: {e}", 500
        finally:
            os.remove(file_path)


@app.route('/files', methods=['GET'])
def list_files():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user_folder = session['email']
        # List objects with the user's folder prefix
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=f"{user_folder}/")
        # Extract only the filename (after the slash)
        files = [obj['Key'].split('/', 1)[-1] for obj in response.get('Contents', []) if obj['Key'] != f"{user_folder}/"]
        return jsonify(files)
    except Exception as e:
        return f"Error: {e}", 500



@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        # Generate a presigned URL for file download
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': filename},
            ExpiresIn=3600  # Link expires in 1 hour
        )
        return jsonify({'url': presigned_url})
    except Exception as e:
        return f"Error: {e}", 500


if __name__ == '__main__':
    # Uncomment the following lines if you want to run the quiz application in the terminal
    # quiz.loadQuestions()
    # quiz.startQuiz()

    # Run Flask web server
    app.run(host="0.0.0.0", port=5000, debug=True)
