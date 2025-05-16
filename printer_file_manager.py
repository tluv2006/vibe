import os
import time
import paramiko
import schedule
import boto3
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import logging
import logging.handlers
import shutil

# Configure logging with rotation
log_file = '/var/log/printer_file_manager/printer_file_manager.log'
os.makedirs(os.path.dirname(log_file), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10485760,  # 10MB
            backupCount=5
        ),
        logging.StreamHandler()
    ]
)

# Load environment variables
load_dotenv()

class PrinterFileManager:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('S3_REGION')
        )
        self.printers = [
            {
                'host': os.getenv('PRINTER1_HOST'),
                'username': os.getenv('PRINTER1_USERNAME'),
                'password': os.getenv('PRINTER1_PASSWORD'),
                'name': 'Printer1'
            },
            {
                'host': os.getenv('PRINTER2_HOST'),
                'username': os.getenv('PRINTER2_USERNAME'),
                'password': os.getenv('PRINTER2_PASSWORD'),
                'name': 'Printer2'
            }
        ]
        self.pi_host = os.getenv('PI_HOST')
        self.pi_username = os.getenv('PI_USERNAME')
        self.pi_password = os.getenv('PI_PASSWORD')
        self.pi_storage_path = os.getenv('PI_STORAGE_PATH')
        self.local_retention_days = int(os.getenv('LOCAL_RETENTION_DAYS', 7))
        self.pi_retention_days = int(os.getenv('PI_RETENTION_DAYS', 30))

    def connect_ssh(self, host, username, password):
        """Establish SSH connection to a remote host"""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(host, username=username, password=password)
            return ssh
        except Exception as e:
            logging.error(f"Failed to connect to {host}: {str(e)}")
            return None

    def transfer_files_to_pi(self):
        """Transfer files from printers to Raspberry Pi"""
        for printer in self.printers:
            try:
                ssh = self.connect_ssh(printer['host'], printer['username'], printer['password'])
                if not ssh:
                    continue

                # Define paths to monitor on the printer
                paths_to_monitor = [
                    '/usr/data/printer_data/gcodes',
                    '/usr/data/printer_data/timelapse',
                    '/usr/data/printer_data/backup'
                ]

                for path in paths_to_monitor:
                    sftp = ssh.open_sftp()
                    try:
                        files = sftp.listdir(path)
                        for file in files:
                            source_path = f"{path}/{file}"
                            file_stat = sftp.stat(source_path)
                            file_time = datetime.fromtimestamp(file_stat.st_mtime)
                            
                            # Skip if file is too new (might still be in use)
                            if datetime.now() - file_time < timedelta(hours=1):
                                continue

                            # Create destination path on Pi
                            relative_path = path.split('printer_data/')[-1]
                            pi_dest_path = f"{self.pi_storage_path}/{printer['name']}/{relative_path}"
                            
                            # Transfer to Pi
                            pi_ssh = self.connect_ssh(self.pi_host, self.pi_username, self.pi_password)
                            if pi_ssh:
                                pi_sftp = pi_ssh.open_sftp()
                                try:
                                    # Create directories if they don't exist
                                    self.mkdir_p(pi_sftp, pi_dest_path)
                                    pi_sftp.get(source_path, f"{pi_dest_path}/{file}")
                                    logging.info(f"Transferred {file} from {printer['name']} to Pi")
                                    
                                    # Delete file from printer if older than retention period
                                    if datetime.now() - file_time > timedelta(days=self.local_retention_days):
                                        sftp.remove(source_path)
                                        logging.info(f"Deleted {file} from {printer['name']}")
                                except Exception as e:
                                    logging.error(f"Error transferring {file}: {str(e)}")
                                finally:
                                    pi_sftp.close()
                                    pi_ssh.close()
                    finally:
                        sftp.close()
                ssh.close()
            except Exception as e:
                logging.error(f"Error processing {printer['name']}: {str(e)}")

    def upload_to_s3(self):
        """Upload files from Raspberry Pi to S3"""
        try:
            pi_ssh = self.connect_ssh(self.pi_host, self.pi_username, self.pi_password)
            if not pi_ssh:
                return

            sftp = pi_ssh.open_sftp()
            self._process_directory(sftp, self.pi_storage_path)
            sftp.close()
            pi_ssh.close()
        except Exception as e:
            logging.error(f"Error during S3 upload: {str(e)}")

    def _process_directory(self, sftp, directory):
        """Recursively process directories and upload files to S3"""
        try:
            files = sftp.listdir(directory)
            for file in files:
                path = f"{directory}/{file}"
                try:
                    # Check if it's a directory
                    sftp.listdir(path)
                    self._process_directory(sftp, path)
                except IOError:
                    # It's a file
                    file_stat = sftp.stat(path)
                    file_time = datetime.fromtimestamp(file_stat.st_mtime)
                    
                    # Upload files older than 1 day but younger than retention period
                    if timedelta(days=1) < datetime.now() - file_time < timedelta(days=self.pi_retention_days):
                        # Create a temporary local copy
                        temp_path = f"temp_{file}"
                        sftp.get(path, temp_path)
                        
                        # Upload to S3
                        s3_path = path.replace(self.pi_storage_path + '/', '')
                        try:
                            self.s3_client.upload_file(temp_path, os.getenv('S3_BUCKET_NAME'), s3_path)
                            logging.info(f"Uploaded {path} to S3")
                            
                            # Delete local file if it's older than retention period
                            if datetime.now() - file_time > timedelta(days=self.pi_retention_days):
                                sftp.remove(path)
                                logging.info(f"Deleted {path} from Pi")
                        finally:
                            os.remove(temp_path)
        except Exception as e:
            logging.error(f"Error processing directory {directory}: {str(e)}")

    def mkdir_p(self, sftp, remote_directory):
        """Create remote directory and parents if they don't exist"""
        if remote_directory == '/':
            return
        try:
            sftp.stat(remote_directory)
        except IOError:
            dirname = os.path.dirname(remote_directory)
            if dirname:
                self.mkdir_p(sftp, dirname)
            sftp.mkdir(remote_directory)

    def run(self):
        """Main execution function"""
        logging.info("Starting printer file manager")
        
        # Schedule tasks
        schedule.every(1).hours.do(self.transfer_files_to_pi)
        schedule.every(12).hours.do(self.upload_to_s3)
        
        # Run immediately on start
        self.transfer_files_to_pi()
        self.upload_to_s3()
        
        # Keep running
        while True:
            schedule.run_pending()
            time.sleep(60)

if __name__ == "__main__":
    manager = PrinterFileManager()
    manager.run() 