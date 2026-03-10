# app.py
# Windows (desktop) - Python + PySide6
# App com interface para escolher horário/moedas e rodar em segundo plano no System Tray.
# No horário agendado, abre uma janela flutuante (topmost) com as cotações (base BRL).
#
# Instale:
#   pip install PySide6 requests
#
# Execute:
#   python app.py

import sys
import json
import threading
from datetime import datetime, timedelta

from pathlib import Path

import requests
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Signal, QObject
from PySide6.QtGui import QFont, QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QLineEdit, QMessageBox, QFrame,
    QSystemTrayIcon, QMenu, QStyle
)

CONFIG_FILE = "config.json"
AVAILABLE_COINS = ["USD", "EUR", "GBP", "ARS", "JPY", "CAD", "AUD", "BTC"]


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if "time" not in cfg:
            cfg["time"] = "09:00"
        if "coins" not in cfg or not isinstance(cfg["coins"], list):
            cfg["coins"] = ["USD", "EUR"]
        return cfg
    except Exception:
        return {"time": "09:00", "coins": ["USD", "EUR"]}


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def fetch_quotes(coins):
    pairs = ",".join([f"{c}-BRL" for c in coins])
    url = f"https://economia.awesomeapi.com.br/json/last/{pairs}"
    data = requests.get(url, timeout=10).json()

    rows = []
    for c in coins:
        key = f"{c}BRL"
        q = data.get(key)
        if not q:
            continue
        bid = float(q.get("bid"))
        rows.append((c, bid))
    return rows


def next_trigger_datetime(hhmm: str) -> datetime:
    now = datetime.now()
    hour, minute = map(int, hhmm.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def fmt_brl(v: float) -> str:
    s = f"{v:,.4f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


class ToastOverlay(QWidget):
    def __init__(self, title: str, lines: list[str], duration_ms: int = 12000):
        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)

        t = QLabel(title)
        t.setFont(QFont("Segoe UI", 12, QFont.Bold))
        t.setObjectName("title")

        body = QLabel("\n".join(lines) if lines else "Sem dados.")
        body.setFont(QFont("Segoe UI", 11))
        body.setObjectName("body")
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("Fechar")
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)

        card_layout.addWidget(t)
        card_layout.addWidget(body)
        card_layout.addLayout(btn_row)

        root.addWidget(card)

        self.setStyleSheet("""
            QFrame#card {
                background: rgba(22, 22, 28, 245);
                border: 2px solid rgba(255,255,255,60);
                border-radius: 14px;
            }
            QLabel#title { color: white; }
            QLabel#body  { color: rgba(255,255,255,220); }
            QPushButton#closeBtn {
                background: rgba(255,255,255,22);
                color: white;
                border: 1px solid rgba(255,255,255,35);
                padding: 6px 12px;
                border-radius: 10px;
            }
            QPushButton#closeBtn:hover { background: rgba(255,255,255,32); }
        """)

        QTimer.singleShot(duration_ms, self.fade_out)

        self.setWindowOpacity(0.0)
        self.anim_in = QPropertyAnimation(self, b"windowOpacity")
        self.anim_in.setDuration(220)
        self.anim_in.setStartValue(0.0)
        self.anim_in.setEndValue(1.0)
        self.anim_in.setEasingCurve(QEasingCurve.OutCubic)

        self.anim_out = QPropertyAnimation(self, b"windowOpacity")
        self.anim_out.setDuration(220)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)
        self.anim_out.setEasingCurve(QEasingCurve.InCubic)
        self.anim_out.finished.connect(self.close)

    def showEvent(self, event):
        super().showEvent(event)
        self.adjustSize()

        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + screen.width() - self.width() - 16
        y = screen.y() + 16
        self.move(x, y)

        self.raise_()
        self.activateWindow()
        self.anim_in.start()

    def fade_out(self):
        if self.isVisible():
            self.anim_out.start()


class Bridge(QObject):
    toast = Signal(str, list)


class Main(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cotação em BRL - Agendador (Tray)")
        self.resize(520, 580)

        self.bridge = Bridge()
        self.bridge.toast.connect(self.show_overlay)

        cfg = load_config()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Agendar janela flutuante com cotações (base BRL)")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        layout.addWidget(title)

        layout.addWidget(QLabel("Horário diário (HH:MM):"))
        self.time_edit = QLineEdit(cfg["time"])
        self.time_edit.setPlaceholderText("Ex: 09:30")
        layout.addWidget(self.time_edit)

        layout.addWidget(QLabel("Moedas:"))
        self.checks = {}
        for c in AVAILABLE_COINS:
            cb = QCheckBox(c)
            cb.setChecked(c in cfg["coins"])
            self.checks[c] = cb
            layout.addWidget(cb)

        btns = QHBoxLayout()
        self.save_btn = QPushButton("Salvar e Agendar")
        self.test_btn = QPushButton("Testar Agora")
        btns.addWidget(self.save_btn)
        btns.addWidget(self.test_btn)
        layout.addLayout(btns)

        self.status = QLabel("")
        layout.addWidget(self.status)

        layout.addWidget(QLabel(
            "Dica: ao fechar (X), o app vai para a bandeja do sistema e continua rodando."
        ))

        self.save_btn.clicked.connect(self.save_and_schedule)
        self.test_btn.clicked.connect(self.test_now)

        self.next_dt = None
        self.refresh_next()

        self.tick = QTimer(self)
        self.tick.timeout.connect(self.check_schedule)
        self.tick.start(1000)

        self.toast_widget = None

        # --- System Tray ---
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.warning(self, "Aviso", "System Tray não disponível neste sistema.")
            self.tray = None
        else:
            self.tray = QSystemTrayIcon(self)
            # Ícone padrão do sistema (não precisa arquivo .ico)
            icon = QApplication.style().standardIcon(QStyle.SP_ComputerIcon)
            self.tray.setIcon(icon)
            self.tray.setToolTip("Cotação em BRL (rodando em segundo plano)")

            menu = QMenu()
            act_show = QAction("Abrir", self)
            act_test = QAction("Testar agora", self)
            act_quit = QAction("Sair", self)

            act_show.triggered.connect(self.show_main)
            act_test.triggered.connect(self.test_now)
            act_quit.triggered.connect(self.exit_app)

            menu.addAction(act_show)
            menu.addAction(act_test)
            menu.addSeparator()
            menu.addAction(act_quit)

            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self.on_tray_activated)
            self.tray.show()

    # ---- Tray behavior ----
    def closeEvent(self, event):
        # Em vez de fechar, esconde e deixa no tray
        if self.tray:
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Rodando em segundo plano",
                "O app continua ativo na bandeja do sistema.\nClique com o botão direito no ícone para opções.",
                QSystemTrayIcon.Information,
                4000
            )
        else:
            super().closeEvent(event)

    def on_tray_activated(self, reason):
        # Clique esquerdo: abrir/mostrar
        if reason == QSystemTrayIcon.Trigger:
            self.show_main()

    def show_main(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def exit_app(self):
        # Fechar de verdade
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    # ---- App logic ----
    def selected_coins(self):
        return [c for c, cb in self.checks.items() if cb.isChecked()]

    def refresh_next(self):
        cfg = load_config()
        self.next_dt = next_trigger_datetime(cfg["time"])
        self.status.setText(f"Próximo disparo: {self.next_dt.strftime('%d/%m %H:%M')}")

    def save_and_schedule(self):
        hhmm = self.time_edit.text().strip()
        try:
            datetime.strptime(hhmm, "%H:%M")
        except ValueError:
            QMessageBox.critical(self, "Erro", "Horário inválido. Use HH:MM (ex: 09:30).")
            return

        coins = self.selected_coins()
        if not coins:
            QMessageBox.critical(self, "Erro", "Selecione pelo menos uma moeda.")
            return

        save_config({"time": hhmm, "coins": coins})
        self.refresh_next()

        if self.tray:
            self.tray.showMessage(
                "Agendado",
                f"Horário: {hhmm}\nMoedas: {', '.join(coins)}",
                QSystemTrayIcon.Information,
                3000
            )
        else:
            QMessageBox.information(self, "OK", "Agendamento salvo.")

    def show_overlay(self, title: str, lines: list):
        if self.toast_widget is not None and self.toast_widget.isVisible():
            self.toast_widget.close()

        self.toast_widget = ToastOverlay(title, [str(x) for x in lines], duration_ms=12000)
        self.toast_widget.show()

    def test_now(self):
        threading.Thread(target=self.run_job, daemon=True).start()

    def run_job(self):
        cfg = load_config()
        coins = cfg.get("coins", [])
        now = datetime.now().strftime("%H:%M")

        if not coins:
            self.bridge.toast.emit("Configuração", ["Nenhuma moeda selecionada."])
            return

        try:
            rows = fetch_quotes(coins)
            lines = [f"{c}/BRL: {fmt_brl(v)}" for c, v in rows]
            if not lines:
                lines = ["Sem dados retornados pela API."]
            self.bridge.toast.emit(f"Cotações ({now})", lines)
        except Exception as e:
            self.bridge.toast.emit("Erro ao buscar cotações", [repr(e)])

    def check_schedule(self):
        if not self.next_dt:
            return

        if datetime.now() >= self.next_dt:
            threading.Thread(target=self.run_job, daemon=True).start()
            self.refresh_next()
def resource_path(relative: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative
    # Aqui a base é src/
    return Path(__file__).resolve().parent / relative

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Em apps com tray, isso evita fechar quando todas janelas são escondidas.
    app.setQuitOnLastWindowClosed(False)
    
    icon_path = resource_path("icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    else:
        print(f"[WARN] Ícone global não encontrado: {icon_path}")

    w = Main()
    w.show()

    sys.exit(app.exec())