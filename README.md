# 3D Printer File Manager

This script automatically manages files from my Neptune 4 Pro 3D printers by transferring them to a Raspberry Pi and then to an AWS S3 bucket for archival.

## Features

- Monitors multiple Neptune 4 Pro printers for new files
- Transfers files (gcodes, timelapses, backups) to a Raspberry Pi
- Automatically uploads files to S3 for long-term storage
- Implements file retention policies for both printers and Raspberry Pi
- Handles errors gracefully with comprehensive logging
- Runs as a system service with automatic restart

## Prerequisites

- Python 3.7+
- Raspberry Pi with SSH access
- AWS S3 bucket
- Neptune 4 Pro printer(s) with SSH access
- Network connectivity between all devices

## Installation

1. Clone this repository to your Raspberry Pi:
```bash
git clone <repository-url>
cd printer-file-manager
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Copy the example environment file and edit it with your settings:
```bash
sudo cp .env.example /etc/printer-file-manager.env
sudo nano /etc/printer-file-manager.env
```

4. Configure the following in your environment file:
   - Printer IP addresses and credentials
   - Raspberry Pi credentials
   - AWS S3 credentials and bucket information
   - File retention settings

5. Set up the service:
```bash
# Create log directory
sudo mkdir -p /var/log/printer_file_manager
sudo chown pi:pi /var/log/printer_file_manager

# Copy service file
sudo cp printer_file_manager.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start the service
sudo systemctl enable printer_file_manager
sudo systemctl start printer_file_manager
```

## Service Management

Check service status:
```bash
sudo systemctl status printer_file_manager
```

View logs:
```bash
# View service logs
sudo journalctl -u printer_file_manager

# View application logs
tail -f /var/log/printer_file_manager/printer_file_manager.log
```

Stop the service:
```bash
sudo systemctl stop printer_file_manager
```

Restart the service:
```bash
sudo systemctl restart printer_file_manager
```

## Usage

Run the script:
```bash
python printer_file_manager.py
```

The script will:
- Check for new files every hour
- Transfer files older than 1 hour to the Raspberry Pi
- Upload files to S3 every 12 hours
- Delete files based on retention settings
- Log all activities to `printer_file_manager.log`

## File Retention

- Printer: Files are kept for 7 days by default
- Raspberry Pi: Files are kept for 30 days by default
- S3: Files are stored indefinitely

You can adjust these settings in the `.env` file.

## Directory Structure

Files are organized on the Raspberry Pi as follows:
```
pi_storage_path/
├── Printer1/
│   ├── gcodes/
│   ├── timelapse/
│   └── backup/
└── Printer2/
    ├── gcodes/
    ├── timelapse/
    └── backup/
```

## Logging

The script logs all activities to:
- Console output
- `printer_file_manager.log` file

## Troubleshooting

1. Check the log file for detailed error messages
2. Verify network connectivity between devices
3. Ensure SSH credentials are correct
4. Confirm AWS credentials have proper permissions

## Security Notes

- Store credentials securely in the `.env` file
- Use strong passwords for SSH access
- Consider using SSH keys instead of passwords
- Ensure AWS credentials have minimal required permissions 
