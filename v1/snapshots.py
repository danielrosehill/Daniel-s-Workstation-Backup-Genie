import sys
import json
import subprocess
import time
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QTextEdit, QProgressBar, QVBoxLayout, QWidget, QLabel, QDialog, QFileDialog
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QRunnable, QThreadPool, pyqtSignal, QObject

APPROVED_SN = "ADD-YOUR-SN"
LAST_RUN_FILE = "last_run.json"
BACKUP_TIMEOUT = 3600  # 1 hour timeout

class WorkerSignals(QObject):
    update_progress = pyqtSignal(int)
    update_output = pyqtSignal(str)
    finished = pyqtSignal()

class BackupWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()

    def run(self):
        try:
            process = subprocess.Popen(['sudo', './snapshot.sh'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            start_time = time.time()
            for line in process.stdout:
                self.signals.update_output.emit(line.strip())
                if "Formatting" in line:
                    self.signals.update_progress.emit(25)
                elif "mounted successfully" in line:
                    self.signals.update_progress.emit(50)
                elif "Starting backup" in line:
                    self.signals.update_progress.emit(75)
                elif "Backup completed successfully" in line:
                    self.signals.update_progress.emit(100)
                if time.time() - start_time > BACKUP_TIMEOUT:
                    process.terminate()
                    self.signals.update_output.emit("Backup process timed out after 1 hour.")
                    break
            process.wait()
            self.save_last_run()
        except Exception as e:
            self.signals.update_output.emit(f"Error: {str(e)}")
        finally:
            self.signals.finished.emit()

    def save_last_run(self):
        last_run = {"date": datetime.now().isoformat()}
        with open(LAST_RUN_FILE, 'w') as f:
            json.dump(last_run, f)

class UserManualDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("User Manual")
        self.setFixedSize(400, 300)

        layout = QVBoxLayout()

        title = QLabel("Approved SNs")
        title.setFont(QFont("OCR A Extended", 16))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        sn_label = QLabel(f"Approved Serial Number: {APPROVED_SN}")
        sn_label.setFont(QFont("Consolas", 12))
        layout.addWidget(sn_label)

        methodology = QLabel("Backup Methodology: Incremental BTRFS Snapshots")
        methodology.setFont(QFont("Consolas", 12))
        methodology.setWordWrap(True)
        layout.addWidget(methodology)

        last_run = self.get_last_run()
        last_run_label = QLabel(f"Last Run: {last_run}")
        last_run_label.setFont(QFont("Consolas", 12))
        layout.addWidget(last_run_label)

        self.setLayout(layout)

    def get_last_run(self):
        try:
            with open(LAST_RUN_FILE, 'r') as f:
                data = json.load(f)
            return data['date']
        except FileNotFoundError:
            return "Never"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Daniel's Workstation Backup Genie - V1")
        self.setGeometry(100, 100, 800, 700)
        self.setStyleSheet("background-color: #008080;")

        layout = QVBoxLayout()

        title_label = QLabel("Daniel's Workstation Backup Genie")
        title_label.setFont(QFont("OCR A Extended", 24))
        title_label.setStyleSheet("color: yellow; background-color: #800080;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        subtitle_label = QLabel("Because like food, it's better to be looking AT backups than for them\n- especially when your operating system is toast!")
        subtitle_label.setFont(QFont("Consolas", 12))
        subtitle_label.setStyleSheet("color: #FFD700;")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)

        bold_text = QLabel("BTRFS to BTRFS backup utility with SN verification on target device. Run as sudo.")
        bold_text.setFont(QFont("Consolas", 12))
        bold_text.setStyleSheet("color: #FFFFFF;")
        bold_text.setAlignment(Qt.AlignCenter)
        bold_text.setWordWrap(True)
        layout.addWidget(bold_text)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Lucida Console", 12))
        self.output_text.setStyleSheet("background-color: black; color: lime; border: 2px solid yellow;")
        layout.addWidget(self.output_text)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid grey;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #00FF00;
                width: 10px;
                margin: 1px;
            }
        """)
        layout.addWidget(self.progress_bar)

        button_layout = QHBoxLayout()
        self.user_manual_button = QPushButton("User Manual")
        self.user_manual_button.setFont(QFont("Consolas", 12, QFont.Bold))
        self.user_manual_button.setStyleSheet("background-color: #4CAF50; color: white; border: 2px solid #45a049;")
        self.user_manual_button.clicked.connect(self.show_user_manual)
        button_layout.addWidget(self.user_manual_button)

        self.open_file_manager_button = QPushButton("Open File Manager")
        self.open_file_manager_button.setFont(QFont("Consolas", 12, QFont.Bold))
        self.open_file_manager_button.setStyleSheet("background-color: #4CAF50; color: white; border: 2px solid #45a049;")
        self.open_file_manager_button.clicked.connect(self.open_file_manager)
        button_layout.addWidget(self.open_file_manager_button)

        layout.addLayout(button_layout)

        self.start_button = QPushButton("Start Backup")
        self.start_button.setFont(QFont("Consolas", 16, QFont.Bold))
        self.start_button.setStyleSheet("background-color: #FF00FF; color: white; border: 3px solid #FFFF00;")
        self.start_button.clicked.connect(self.start_backup)
        layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop Backup")
        self.stop_button.setFont(QFont("Consolas", 16, QFont.Bold))
        self.stop_button.setStyleSheet("background-color: #FF0000; color: white; border: 3px solid #FFFF00;")
        self.stop_button.clicked.connect(self.stop_backup)
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)

        footer_label = QLabel("Created by Daniel in collaboration with Claude, an AI assistant by Anthropic - V1")
        footer_label.setFont(QFont("Consolas", 10))
        footer_label.setStyleSheet("color: #CCCCCC;")
        footer_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.threadpool = QThreadPool()
        self.backup_worker = None

    def show_user_manual(self):
        dialog = UserManualDialog(self)
        dialog.exec_()

    def open_file_manager(self):
        try:
            # Try to open the default file manager
            subprocess.Popen(['xdg-open', '/mnt'])
        except:
            try:
                # If that fails, try to open Dolphin
                subprocess.Popen(['dolphin', '/mnt'])
            except:
                # If both fail, show an error message
                self.update_output("Failed to open file manager. Please open it manually.")

    def start_backup(self):
        self.backup_worker = BackupWorker()
        self.backup_worker.signals.update_progress.connect(self.update_progress)
        self.backup_worker.signals.update_output.connect(self.update_output)
        self.backup_worker.signals.finished.connect(self.on_backup_finished)
        self.threadpool.start(self.backup_worker)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def stop_backup(self):
        if self.backup_worker:
            self.threadpool.clear()
            self.update_output("Backup stopped by user.\n")
            self.on_backup_finished()

    def on_backup_finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_output(self, text):
        self.output_text.append(text)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())