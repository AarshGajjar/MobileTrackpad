import sys
import os
import asyncio
import qrcode
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, 
                           QVBoxLayout, QWidget, QLabel, QSystemTrayIcon, 
                           QMenu, QMessageBox, QSlider, QHBoxLayout, QGroupBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings
from PyQt6.QtGui import QIcon, QPixmap, QAction
from io import BytesIO
from PIL.ImageQt import ImageQt
import mobile_trackpad

class ServerThread(QThread):
    server_started = pyqtSignal(str)
    server_stopped = pyqtSignal()

    def __init__(self, mouse_sensitivity=3.5, scroll_sensitivity=0.1):
        super().__init__()
        self._running = False
        self.loop = None
        self.runner = None
        self.mouse_sensitivity = mouse_sensitivity
        self.scroll_sensitivity = scroll_sensitivity

    async def cleanup_server(self):
        if self.runner:
            await self.runner.cleanup()
            self.runner = None

    def run(self):
        self._running = True
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        async def start_server():
            app = mobile_trackpad.web.Application()
            app.router.add_get('/', mobile_trackpad.index_handler)
            app.router.add_get('/ws', mobile_trackpad.websocket_handler)
            
            self.runner = mobile_trackpad.web.AppRunner(app)
            await self.runner.setup()
            site = mobile_trackpad.web.TCPSite(self.runner, '0.0.0.0', 5000)
            
            await site.start()
            ip_address = mobile_trackpad.get_local_ip()
            self.server_started.emit(f"http://{ip_address}:5000")
            
            try:
                while self._running:
                    await asyncio.sleep(1)
            finally:
                await self.cleanup_server()
                self.server_stopped.emit()

        try:
            self.loop.run_until_complete(start_server())
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            self.loop.close()

    def stop(self):
        self._running = False

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.server_thread = None
        self.settings = QSettings('MobileTrackpad', 'Settings')
        self.mouse_sensitivity = float(self.settings.value('mouse_sensitivity', 3.5))
        self.scroll_sensitivity = float(self.settings.value('scroll_sensitivity', 0.1))
        
        # Keep window in taskbar but make it minimizable to tray
        self.setWindowFlags(Qt.WindowType.Window)
        
        self.init_ui()
        self.setup_system_tray()

    def init_ui(self):
        self.setWindowTitle('Mobile Trackpad')
        self.setFixedSize(300, 500)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create group box for sensitivity controls
        sensitivity_group = QGroupBox("Sensitivity Controls")
        sensitivity_layout = QVBoxLayout()

        # Mouse sensitivity control
        mouse_container = QWidget()
        mouse_layout = QHBoxLayout(mouse_container)
        mouse_label = QLabel('Mouse:')
        self.mouse_value = QLabel(f'{self.mouse_sensitivity:.1f}')
        self.mouse_slider = QSlider(Qt.Orientation.Horizontal)
        self.mouse_slider.setMinimum(10)
        self.mouse_slider.setMaximum(100)
        self.mouse_slider.setValue(int(self.mouse_sensitivity * 10))
        self.mouse_slider.valueChanged.connect(self.update_mouse_sensitivity)
        mouse_layout.addWidget(mouse_label)
        mouse_layout.addWidget(self.mouse_slider)
        mouse_layout.addWidget(self.mouse_value)

        # Scroll sensitivity control
        scroll_container = QWidget()
        scroll_layout = QHBoxLayout(scroll_container)
        scroll_label = QLabel('Scroll:')
        self.scroll_value = QLabel(f'{self.scroll_sensitivity:.2f}')
        self.scroll_slider = QSlider(Qt.Orientation.Horizontal)
        self.scroll_slider.setMinimum(1)
        self.scroll_slider.setMaximum(50)
        self.scroll_slider.setValue(int(self.scroll_sensitivity * 100))
        self.scroll_slider.valueChanged.connect(self.update_scroll_sensitivity)
        scroll_layout.addWidget(scroll_label)
        scroll_layout.addWidget(self.scroll_slider)
        scroll_layout.addWidget(self.scroll_value)

        sensitivity_layout.addWidget(mouse_container)
        sensitivity_layout.addWidget(scroll_container)
        sensitivity_group.setLayout(sensitivity_layout)
        layout.addWidget(sensitivity_group)

        # Create Start/Stop button
        self.toggle_button = QPushButton('Start Server')
        self.toggle_button.clicked.connect(self.toggle_server)
        layout.addWidget(self.toggle_button)

        # Create QR code label
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.qr_label)

        # Create status label
        self.status_label = QLabel('Server: Stopped')
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

    def setup_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon('icon.png'))
        
        # Create tray menu
        tray_menu = QMenu()
        show_action = tray_menu.addAction('Show')
        show_action.triggered.connect(self.show_window)
        quit_action = tray_menu.addAction('Quit')
        quit_action.triggered.connect(self.quit_application)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()

    def show_window(self):
        self.show()
        self.activateWindow()
        self.raise_()

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()

    def update_mouse_sensitivity(self):
        self.mouse_sensitivity = self.mouse_slider.value() / 10.0
        self.mouse_value.setText(f'{self.mouse_sensitivity:.1f}')
        self.settings.setValue('mouse_sensitivity', self.mouse_sensitivity)
        self.update_server_sensitivity()

    def update_scroll_sensitivity(self):
        self.scroll_sensitivity = self.scroll_slider.value() / 100.0
        self.scroll_value.setText(f'{self.scroll_sensitivity:.2f}')
        self.settings.setValue('scroll_sensitivity', self.scroll_sensitivity)
        self.update_server_sensitivity()

    def update_server_sensitivity(self):
        if self.server_thread and self.server_thread._running:
            # Update the HTML with new sensitivity values
            updated_html = mobile_trackpad.update_sensitivities(
                self.mouse_sensitivity, 
                self.scroll_sensitivity
            )
            # Store the updated values in the server thread
            self.server_thread.mouse_sensitivity = self.mouse_sensitivity
            self.server_thread.scroll_sensitivity = self.scroll_sensitivity    
    
    def toggle_server(self):
        if not self.server_thread:
            self.server_thread = ServerThread(self.mouse_sensitivity, self.scroll_sensitivity)
            self.server_thread.server_started.connect(self.on_server_started)
            self.server_thread.server_stopped.connect(self.on_server_stopped)
            self.server_thread.start()
            self.toggle_button.setText('Stop Server')
        else:
            self.server_thread.stop()
            self.server_thread = None
            self.toggle_button.setText('Start Server')
            self.status_label.setText('Server: Stopped')
            self.qr_label.clear()
        
    def quit_application(self):
        if self.server_thread:
            self.server_thread.stop()
        QApplication.quit()

    def on_server_started(self, url):
        self.status_label.setText(f'Server: Running\n{url}')
        self.generate_qr(url)

    def on_server_stopped(self):
        self.toggle_button.setText('Start Server')
        self.status_label.setText('Server: Stopped')
        self.qr_label.clear()

    def generate_qr(self, url):
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(url)
        qr.make(fit=True)
        qr_image = qr.make_image(fill_color="black", back_color="white")
        
        buffer = BytesIO()
        qr_image.save(buffer, format='PNG')
        qr_pixmap = QPixmap()
        qr_pixmap.loadFromData(buffer.getvalue())
        
        scaled_pixmap = qr_pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio)
        self.qr_label.setPixmap(scaled_pixmap)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "Mobile Trackpad",
            "Application minimized to system tray",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )

    def quit_application(self):
        if self.server_thread:
            self.server_thread.stop()
        QApplication.quit()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    try:
        from ctypes import windll
        myappid = 'com.mobiletrackpad.app'
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except ImportError:
        pass
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())