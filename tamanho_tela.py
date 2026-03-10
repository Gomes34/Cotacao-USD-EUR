import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout

class SizeViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Medidor de tamanho da janela (Qt)")

        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFont(QFont("Consolas", 22))
        self.label.setStyleSheet("padding: 18px;")

        info = QLabel(
            "Redimensione a janela.\n"
            "Anote Width/Height e depois use setFixedSize(width, height) no seu app."
        )
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("color:#555; padding: 0 18px 18px 18px;")
        info.setFont(QFont("Sans Serif", 11))

        layout = QVBoxLayout(self)
        layout.addWidget(self.label, 1)
        layout.addWidget(info, 0)

        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_text)
        self.timer.start()

        self.resize(1200, 700)
        self.update_text()

    def update_text(self):
        w = self.width()
        h = self.height()

        geo = self.geometry()  
        cw = self.contentsRect().width()   
        ch = self.contentsRect().height()

        self.label.setText(
            f"window.width  = {w}\n"
            f"window.height = {h}\n\n"
            f"geometry.w    = {geo.width()}\n"
            f"geometry.h    = {geo.height()}\n\n"
            f"contents.w    = {cw}\n"
            f"contents.h    = {ch}"
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_text()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = SizeViewer()
    w.show()
    sys.exit(app.exec())