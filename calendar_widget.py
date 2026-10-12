import sys
import os
import json
import datetime
import requests
from icalendar import Calendar
from PyQt6 import QtCore, QtGui, QtWidgets
import ctypes

CONFIG_FILE = "calendar_config.json"

# One UI 컬러 팔레트
PRESET_COLORS = {
    "파랑": ("rgba(10, 132, 255, 0.35)", "#0A84FF"),
    "빨강": ("rgba(255, 69, 58, 0.35)", "#FF453A"),
    "초록": ("rgba(48, 209, 88, 0.35)", "#30D158"),
    "주황": ("rgba(255, 159, 10, 0.35)", "#FF9F0A"),
    "보라": ("rgba(191, 90, 242, 0.35)", "#BF5AF2"),
    "노랑": ("rgba(255, 214, 10, 0.35)", "#FFD60A"),
    "분홍": ("rgba(255, 55, 95, 0.35)", "#FF375F"),
    "하늘": ("rgba(100, 210, 255, 0.35)", "#64D2FF"),
    "회색": ("rgba(142, 142, 147, 0.35)", "#8E8E93"),
}

DEFAULT_EVENT_COLOR = ("rgba(44, 117, 255, 0.30)", "#2C75FF")

def expand_recurrence(dtstart, rrule_val, exdates, range_start, range_end):
    dates = []
    try:
        base_date = dtstart.date() if isinstance(dtstart, datetime.datetime) else dtstart
        rrule_str = rrule_val.to_ical().decode("utf-8") if hasattr(rrule_val, "to_ical") else str(rrule_val)
        params = dict(item.split("=", 1) for item in rrule_str.split(";") if "=" in item)
        params = {k.upper(): v for k, v in params.items()}

        freq = params.get("FREQ", "DAILY").upper()
        interval = int(params.get("INTERVAL", 1))
        count = int(params.get("COUNT", 999999))

        until_date = None
        if "UNTIL" in params:
            u = params["UNTIL"]
            try:
                until_date = datetime.date(int(u[:4]), int(u[4:6]), int(u[6:8]))
            except Exception:
                pass

        if freq == "DAILY":
            cur = base_date
            c = 0
            if cur < range_start and interval > 0:
                steps = (range_start - cur).days // interval
                cur += datetime.timedelta(days=steps * interval)
                c += steps

            while cur <= range_end and c < count:
                if until_date and cur > until_date:
                    break
                if cur >= range_start and cur not in exdates:
                    dates.append(cur)
                cur += datetime.timedelta(days=interval)
                c += 1

        elif freq == "WEEKLY":
            cur = base_date
            c = 0
            while cur <= range_end and c < count:
                if until_date and cur > until_date:
                    break
                if cur >= range_start and cur not in exdates:
                    dates.append(cur)
                cur += datetime.timedelta(weeks=interval)
                c += 1
        else:
            if range_start <= base_date <= range_end and base_date not in exdates:
                dates.append(base_date)

    except Exception:
        base_date = dtstart.date() if isinstance(dtstart, datetime.datetime) else dtstart
        if range_start <= base_date <= range_end:
            dates.append(base_date)

    return dates

class Win32Helper:
    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_LAYERED = 0x00080000

    @staticmethod
    def set_click_through(hwnd, enabled=True):
        style = ctypes.windll.user32.GetWindowLongW(hwnd, Win32Helper.GWL_EXSTYLE)
        if enabled:
            style |= (Win32Helper.WS_EX_TRANSPARENT | Win32Helper.WS_EX_LAYERED)
        else:
            style &= ~Win32Helper.WS_EX_TRANSPARENT
        ctypes.windll.user32.SetWindowLongW(hwnd, Win32Helper.GWL_EXSTYLE, style)

class DayCell(QtWidgets.QFrame):
    def __init__(self, date_val, parent_cal):
        super().__init__()
        self.date_val = date_val
        self.parent_cal = parent_cal

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.parent_cal.open_day_dialog(self.date_val)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        self.parent_cal.mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.parent_cal.mouseMoveEvent(event)

class DayEventDialog(QtWidgets.QDialog):
    def __init__(self, target_date, parent_cal):
        super().__init__(parent_cal)
        self.target_date = target_date
        self.parent_cal = parent_cal
        self.date_str = target_date.strftime("%Y-%m-%d")

        self.setWindowTitle(f"{self.target_date.month}월 {self.target_date.day}일 일정 관리")
        self.setFixedSize(400, 450)
        self.setStyleSheet("""
            QDialog {
                background-color: #202022;
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.15);
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Malgun Gothic', 'Segoe UI';
            }
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.08);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #0072DE;
            }
            QComboBox {
                background-color: #2C2C2E;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QComboBox QAbstractItemView {
                background-color: #2C2C2E;
                color: #FFFFFF;
                selection-background-color: #0072DE;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            QPushButton {
                background-color: #0072DE;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 14px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #0A84FF;
            }
            QListWidget {
                background-color: rgba(0, 0, 0, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                color: white;
                font-size: 13px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 7px;
                border-radius: 6px;
                margin-bottom: 2px;
            }
            QListWidget::item:selected {
                background-color: rgba(255, 255, 255, 0.15);
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QtWidgets.QLabel(f"📅 {self.target_date.strftime('%Y년 %m월 %d일')} 일정")
        title.setStyleSheet("font-size: 17px; font-weight: bold;")
        layout.addWidget(title)

        self.list_widget = QtWidgets.QListWidget()
        layout.addWidget(self.list_widget)

        input_layout = QtWidgets.QHBoxLayout()
        self.input_text = QtWidgets.QLineEdit()
        self.input_text.setPlaceholderText("새 일정 입력")
        self.input_text.returnPressed.connect(self.add_event)

        self.combo_color = QtWidgets.QComboBox()
        color_names = ["파랑", "빨강", "초록", "주황", "보라", "노랑", "분홍", "하늘", "회색"]
        for c in color_names:
            self.combo_color.addItem(c)

        btn_add = QtWidgets.QPushButton("추가")
        btn_add.clicked.connect(self.add_event)

        input_layout.addWidget(self.input_text, 3)
        input_layout.addWidget(self.combo_color, 2)
        input_layout.addWidget(btn_add, 1)
        layout.addLayout(input_layout)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_del = QtWidgets.QPushButton("선택한 일정 삭제")
        btn_del.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 69, 58, 0.2);
                color: #FF453A;
                border: 1px solid rgba(255, 69, 58, 0.4);
            }
            QPushButton:hover {
                background-color: rgba(255, 69, 58, 0.35);
            }
        """)
        btn_del.clicked.connect(self.delete_selected)

        btn_close = QtWidgets.QPushButton("닫기")
        btn_close.setStyleSheet("background-color: rgba(255, 255, 255, 0.12); color: white;")
        btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(btn_del)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        self.load_items()

    def load_items(self):
        self.list_widget.clear()
        g_events = self.parent_cal.events.get(self.target_date, [])
        for gev in g_events:
            item = QtWidgets.QListWidgetItem(f"🌐 [구글] {gev}")
            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
            item.setForeground(QtGui.QColor("#8E8E93"))
            self.list_widget.addItem(item)

        local_map = self.parent_cal.config.get("local_events", {})
        l_events = local_map.get(self.date_str, [])
        for idx, lev in enumerate(l_events):
            if isinstance(lev, dict):
                title = lev.get("title", "")
                c_name = lev.get("color", "파랑")
            else:
                title = str(lev)
                c_name = "파랑"

            item = QtWidgets.QListWidgetItem(f"📌 [{c_name}] {title}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, idx)
            self.list_widget.addItem(item)

    def add_event(self):
        txt = self.input_text.text().strip()
        if not txt:
            return

        chosen_color = self.combo_color.currentText()
        local_map = self.parent_cal.config.setdefault("local_events", {})
        local_map.setdefault(self.date_str, []).append({
            "title": txt,
            "color": chosen_color
        })
        self.parent_cal.save_config()
        self.parent_cal.render_calendar()

        self.input_text.clear()
        self.load_items()

    def delete_selected(self):
        curr = self.list_widget.currentItem()
        if not curr:
            return
        idx = curr.data(QtCore.Qt.ItemDataRole.UserRole)
        if idx is None:
            return

        local_map = self.parent_cal.config.get("local_events", {})
        if self.date_str in local_map:
            try:
                local_map[self.date_str].pop(idx)
                if not local_map[self.date_str]:
                    del local_map[self.date_str]
                self.parent_cal.save_config()
                self.parent_cal.render_calendar()
                self.load_items()
            except Exception:
                pass

class OneUICalendar(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.config = self.load_config()
        self.events = {}
        self.current_date = datetime.date.today()
        self.click_through_enabled = self.config.get("click_through", False)

        self.save_timer = QtCore.QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_current_geometry)

        self.init_window()
        self.init_ui()
        self.init_tray()

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.fetch_ical_events)
        self.timer.start(10 * 60 * 1000)

        QtCore.QTimer.singleShot(100, self.fetch_ical_events)

        if self.click_through_enabled:
            QtCore.QTimer.singleShot(250, self.apply_initial_click_through)

    def load_config(self):
        default = {
            "ical_url": "",
            "opacity": 0.85,
            "width": 1100,
            "height": 750,
            "x": None,
            "y": None,
            "click_through": False,
            "local_events": {},
            "custom
