import sys
import os
import json
from datetime import datetime

from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.errors import SessionPasswordNeeded, AuthKeyUnregistered, PhoneCodeInvalid
import asyncio


CONFIG_FILE = "config.json"
SESSION_NAME = "userbot"
COMMANDS = []


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"account": {}, "commands": []}


def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"account": ACC, "commands": COMMANDS}, f, ensure_ascii=False, indent=4)


ACC = load_config().get("account", {})


# ====================== ДИАЛОГИ ======================
class CodeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Код из Telegram")
        self.setFixedSize(460, 320)
        self.setStyleSheet("background:#0f0f1f;color:white;")
        l = QVBoxLayout(self)
        l.setContentsMargins(40,40,40,40)
        l.addWidget(QLabel("Введите код из Telegram", alignment=Qt.AlignmentFlag.AlignCenter,
                           styleSheet="color:#00ffff;font-size:22px;font-weight:bold;"))
        self.code = QLineEdit()
        self.code.setPlaceholderText("•••••")
        self.code.setMaxLength(8)
        self.code.setFont(QFont("Arial", 28))
        self.code.setStyleSheet("background:#1e1e2e;border:3px solid #00bfff;border-radius:20px;padding:16px;text-align:center;")
        l.addWidget(self.code, alignment=Qt.AlignmentFlag.AlignCenter)
        btn = QPushButton("Войти")
        btn.setStyleSheet("background:#00bfff;color:black;font-weight:bold;border-radius:24px;padding:18px;")
        btn.clicked.connect(self.accept)
        l.addWidget(btn)
        self.code.setFocus()


class PasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Пароль 2FA")
        self.setFixedSize(480, 340)
        self.setStyleSheet("background:#0f0f1f;color:white;")
        l = QVBoxLayout(self)
        l.setContentsMargins(40,40,40,40)
        l.addWidget(QLabel("Введите пароль от двухфакторной аутентификации",
                           alignment=Qt.AlignmentFlag.AlignCenter,
                           styleSheet="color:#ff6b6b;font-size:19px;font-weight:bold;"))
        self.pwd = QLineEdit()
        self.pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd.setStyleSheet("background:#1e1e2e;border:3px solid #ff6b6b;border-radius:20px;padding:16px;")
        l.addWidget(self.pwd)
        btn = QPushButton("Войти")
        btn.setStyleSheet("background:#ff6b6b;color:white;font-weight:bold;border-radius:24px;padding:18px;")
        btn.clicked.connect(self.accept)
        l.addWidget(btn)
        self.pwd.setFocus()


# ====================== РЕДАКТОР КОМАНД ======================
class CommandEditor(QDialog):
    def __init__(self, cmd=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование команды")
        self.setFixedSize(560, 660)
        self.cmd = cmd.copy() if cmd else {"trigger": "", "messages": [""], "delay": 1.0}
        self.setStyleSheet("background:#0f0f1f;color:white;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20,20,20,20)

        layout.addWidget(QLabel("Триггер", styleSheet="color:#00ffff;font-weight:bold;font-size:16px;"))
        self.trigger = QLineEdit(self.cmd["trigger"])
        layout.addWidget(self.trigger)

        layout.addWidget(QLabel("Задержка (сек)", styleSheet="color:#00ffff;font-weight:bold;font-size:16px;"))
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0.1, 30)
        self.delay.setValue(self.cmd["delay"])
        layout.addWidget(self.delay)

        layout.addWidget(QLabel("Сообщения:", styleSheet="color:#00ffff;font-weight:bold;font-size:16px;"))
        self.msg_list = QListWidget()
        for m in self.cmd["messages"]:
            self.msg_list.addItem(m if m.strip() else "[пустое]")
        layout.addWidget(self.msg_list, 1)

        btns = QHBoxLayout()
        for t, f in [("+ Добавить", self.add), ("− Удалить", self.delete), ("↑", lambda: self.move(-1)), ("↓", lambda: self.move(1)), ("Редакт.", self.edit)]:
            b = QPushButton(t)
            b.clicked.connect(f)
            btns.addWidget(b)
        layout.addLayout(btns)

        bottom = QHBoxLayout()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Сохранить")
        save.setStyleSheet("background:#00ff9d;color:black;font-weight:bold;padding:16px;border-radius:16px;")
        save.clicked.connect(self.save)
        bottom.addWidget(cancel)
        bottom.addWidget(save)
        layout.addLayout(bottom)

    def add(self):
        t, ok = QInputDialog.getMultiLineText(self, "Новое сообщение", "Текст:")
        if ok: self.msg_list.addItem(t.strip() if t.strip() else "[пустое]")

    def delete(self):
        r = self.msg_list.currentRow()
        if r >= 0: self.msg_list.takeItem(r)

    def move(self, d):
        r = self.msg_list.currentRow()
        if r < 0: return
        if (d == -1 and r == 0) or (d == 1 and r >= self.msg_list.count()-1): return
        i = self.msg_list.takeItem(r)
        self.msg_list.insertItem(r + d, i)
        self.msg_list.setCurrentRow(r + d)

    def edit(self):
        i = self.msg_list.currentItem()
        if i:
            t, ok = QInputDialog.getMultiLineText(self, "Редактировать", "", i.text().replace("[пустое]", ""))
            if ok: i.setText(t.strip() if t.strip() else "[пустое]")

    def save(self):
        trig = self.trigger.text().strip()
        if not trig:
            QMessageBox.critical(self, "Ошибка", "Триггер пустой!")
            return
        msgs = [self.msg_list.item(i).text() for i in range(self.msg_list.count()) if self.msg_list.item(i).text() != "[пустое]"]
        if not msgs:
            QMessageBox.critical(self, "Ошибка", "Добавь хотя бы одно сообщение!")
            return
        new = {"trigger": trig, "messages": msgs, "delay": self.delay.value()}
        if self.cmd in COMMANDS:
            COMMANDS[COMMANDS.index(self.cmd)] = new
        else:
            COMMANDS[:] = [c for c in COMMANDS if c["trigger"] != trig]
            COMMANDS.append(new)
        save_config()
        self.accept()


# ====================== БОТ ======================
class BotThread(QThread):
    log = pyqtSignal(str)
    status = pyqtSignal(bool)
    need_code = pyqtSignal()
    need_password = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.code = None
        self.password = None
        self.client = None
        self.loop = None

    async def handler(self, client, message):
        if not message.text: return
        txt = message.text.strip()
        for cmd in COMMANDS:
            if txt == cmd["trigger"] or txt.startswith(cmd["trigger"] + " "):
                self.log.emit(f"Сработала: {cmd['trigger']}")
                try: await message.delete()
                except: pass
                if cmd["messages"]:
                    sent = await client.send_message(message.chat.id, cmd["messages"][0])
                    for t in cmd["messages"][1:]:
                        await asyncio.sleep(cmd["delay"])
                        try: await sent.edit(t)
                        except: pass
                break

    def run(self):
        global ACC
        api_id = ACC.get("api_id", "").strip()
        api_hash = ACC.get("api_hash", "").strip()
        phone = ACC.get("phone", "").strip()

        if not api_id or not api_hash or not phone:
            self.log.emit("Заполни аккаунт в настройках!")
            return

        try:
            api_id = int(api_id)
        except:
            self.log.emit("API ID должен быть числом!")
            return

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.client = Client(SESSION_NAME, api_id=api_id, api_hash=api_hash, phone_number=phone)

        async def main():
            await self.client.start()
            self.log.emit("Вход по сессии — успех!")
            self.log.emit("Userbot запущен — готов к работе!")
            self.status.emit(True)

            # Правильная регистрация обработчика
            self.client.add_handler(MessageHandler(self.handler, filters.me & filters.text))

            await asyncio.Event().wait()  # держим живым

        try:
            self.loop.run_until_complete(main())
        except Exception as e:
            self.log.emit(f"Ошибка: {e}")
        finally:
            self.status.emit(False)

    def stop(self):
        if self.client and self.loop:
            asyncio.run_coroutine_threadsafe(self.client.stop(), self.loop)


# ====================== GUI ======================
class LoveUserbot(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Love Userbot 2025")
        self.setFixedSize(1100, 720)
        self.setStyleSheet("""
            QMainWindow{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0a0a1a,stop:1 #1a1a2e);}
            QLabel#title{font-size:42px;font-weight:bold;color:#00ffff;}
            QPushButton{background:#00bfff;color:black;font-weight:bold;border-radius:20px;padding:14px;}
            QPushButton:hover{background:#00ffff;}
            QPushButton#start{background:#00ff9d;font-size:22px;padding:20px;min-width:300px;}
            QPushButton#stop{background:#ff3b5c;}
            QLineEdit,QTextEdit,QListWidget{background:#1e1e2e;border-radius:16px;padding:12px;color:white;}
            QListWidget::item:selected{background:#00ffff;color:black;}
        """)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(30,30,30,30)

        layout.addWidget(QLabel("Love Userbot 2025", objectName="title", alignment=Qt.AlignmentFlag.AlignCenter))

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        # Управление
        tab1 = QWidget()
        v1 = QVBoxLayout(tab1)
        v1.addStretch()
        self.btn_start = QPushButton("Запустить бота")
        self.btn_start.setObjectName("start")
        self.btn_start.clicked.connect(self.toggle_bot)
        v1.addWidget(self.btn_start, alignment=Qt.AlignmentFlag.AlignCenter)
        self.status_lbl = QLabel("Статус: Остановлен")
        self.status_lbl.setStyleSheet("color:#ff3b5c;font-size:22px;")
        v1.addWidget(self.status_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        v1.addWidget(self.log_box, 2)
        v1.addStretch()
        tabs.addTab(tab1, "Управление")

        # Аккаунт
        tab2 = QWidget()
        form = QFormLayout(tab2)
        form.setContentsMargins(100,60,100,60)
        self.fields = []
        for label in ["API ID:", "API Hash:", "Телефон:", "Пароль 2FA (необязательно):"]:
            l = QLabel(label)
            e = QLineEdit()
            if "Пароль" in label: e.setEchoMode(QLineEdit.EchoMode.Password)
            self.fields.append(e)
            form.addRow(l, e)
        save_btn = QPushButton("Сохранить аккаунт")
        save_btn.clicked.connect(self.save_acc)
        form.addRow("", save_btn)
        tabs.addTab(tab2, "Аккаунт")

        # Команды
        tab3 = QWidget()
        v3 = QVBoxLayout(tab3)
        v3.setContentsMargins(30,30,30,30)
        btns = QHBoxLayout()
        for text, func in [("Новая", lambda: self.edit_cmd()), ("Редакт.", lambda: self.edit_cmd(self.cur_cmd())), ("Дублировать", self.dup), ("Удалить", self.delete)]:
            b = QPushButton(text)
            b.clicked.connect(func)
            btns.addWidget(b)
        v3.addLayout(btns)
        self.cmd_list = QListWidget()
        v3.addWidget(self.cmd_list)
        tabs.addTab(tab3, "Команды")

        # О приложении
        tab4 = QWidget()
        v4 = QVBoxLayout(tab4)
        v4.addStretch()
        v4.addWidget(QLabel("Love Userbot 2025\n\nСамый красивый и мощный userbot\n\nС любовью от тебя ❤️", alignment=Qt.AlignmentFlag.AlignCenter, styleSheet="font-size:20px;color:#888;"))
        v4.addStretch()
        tabs.addTab(tab4, "О приложении")

        self.load_all()
        self.bot = BotThread()
        self.bot.log.connect(self.add_log)
        self.bot.status.connect(self.update_status)

    def add_log(self, t):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.append(f"[{ts}] {t}")

    def update_status(self, on):
        if on:
            self.status_lbl.setText("Статус: Работает")
            self.status_lbl.setStyleSheet("color:#00ff9d;font-size:22px;")
            self.btn_start.setText("Остановить")
            self.btn_start.setObjectName("stop")
        else:
            self.status_lbl.setText("Статус: Остановлен")
            self.status_lbl.setStyleSheet("color:#ff3b5c;font-size:22px;")
            self.btn_start.setText("Запустить бота")
            self.btn_start.setObjectName("start")

    def toggle_bot(self):
        if not self.bot.isRunning():
            self.bot.start()
        else:
            self.bot.stop()

    def save_acc(self):
        global ACC
        ACC = {"api_id": self.fields[0].text().strip(),
               "api_hash": self.fields[1].text().strip(),
               "phone": self.fields[2].text().strip(),
               "password": self.fields[3].text().strip() or None}
        save_config()
        self.add_log("Аккаунт сохранён")

    def load_all(self):
        global COMMANDS, ACC
        cfg = load_config()
        ACC = cfg.get("account", {})
        COMMANDS = cfg.get("commands", [])
        for i, k in enumerate(["api_id", "api_hash", "phone", "password"]):
            self.fields[i].setText(ACC.get(k, "") or "")
        self.refresh_list()

    def refresh_list(self):
        self.cmd_list.clear()
        for c in COMMANDS:
            item = QListWidgetItem(f"{c['trigger']} → {len(c['messages'])} сообщ., {c['delay']}с")
            item.setData(Qt.ItemDataRole.UserRole, c)
            self.cmd_list.addItem(item)

    def cur_cmd(self):
        i = self.cmd_list.currentItem()
        return i.data(Qt.ItemDataRole.UserRole) if i else None

    def edit_cmd(self, cmd=None):
        if CommandEditor(cmd, self).exec():
            self.refresh_list()

    def dup(self):
        c = self.cur_cmd()
        if c:
            new = c.copy()
            new["trigger"] += " (копия)"
            COMMANDS.append(new)
            save_config()
            self.refresh_list()

    def delete(self):
        c = self.cur_cmd()
        if c and QMessageBox.question(self, "Удалить", "Точно?") == QMessageBox.StandardButton.Yes:
            COMMANDS.remove(c)
            save_config()
            self.refresh_list()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = LoveUserbot()
    win.show()
    sys.exit(app.exec())
