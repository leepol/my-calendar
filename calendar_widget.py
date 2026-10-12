import sys
import os
import json
import datetime
import requests
from icalendar import Calendar
from dateutil.rrule import rrulestr
from PyQt6 import QtCore, QtGui, QtWidgets
import ctypes

CONFIG_FILE = "calendar_config.json"

# One UI 파스텔 컬러 팔레트 (배경 투명도 / 테두리 포인트)
ONE_UI_PALETTE = [
    {"bg": "rgba(10, 132, 255, 0.28)", "border": "#0A84FF"},   # 블루
    {"bg": "rgba(48, 209, 88, 0.25)", "border": "#30D158"},    # 민트/그린
    {"bg": "rgba(255, 159, 10, 0.28)", "border": "#FF9F0A"},   # 오렌지
    {"bg": "rgba(191, 90, 242, 0.28)", "border": "#BF5AF2"},   # 퍼플
    {"bg": "rgba(255, 69, 58, 0.28)", "border": "#FF453A"},    # 코랄/레드
    {"bg": "rgba(100, 210, 255, 0.28)", "border": "#64D2FF"},  # 시안
    {"bg": "rgba(255, 214, 10, 0.28)", "border": "#FFD60A"},   # 옐로우
    {"bg": "rgba(255, 55, 95, 0.28)", "border": "#FF375F"},    # 핑크
]

def get_event_color(summary):
    s = summary.strip().lower()
    # 주요 키워드 우선 매핑
    if any(k in s for k in ["당직", "야간", "철야", "근무", "중요", "마감"]):
        return "rgba(255, 69, 58, 0.32)", "#FF453A"
    if any(k in s for k in ["휴무", "비번", "휴가", "연차", "쉬는날"]):
        return "rgba(48, 209, 88, 0.28)", "#30D158"
    if any(k in s for k in ["생일", "기념일", "축하"]):
        return "rgba(255, 55, 95, 0.32)", "#FF375F"
    if any(k in s for k in ["회의", "미팅", "약속"]):
        return "rgba(255, 159, 10, 0.32)", "#FF9F0A"
    if any(k in s for k in ["운동", "헬스", "러닝", "수영"]):
        return "rgba(100, 210, 255, 0.30)", "#64D2FF"

    # 일정 제목 해시값 기반 고유 색상 배정 (동일한 일정은 항상 같은 색상 유지)
    idx = abs(hash(summary)) % len(ONE_UI_PALETTE)
    return ONE_UI_PALETTE[idx]["bg"], ONE_UI_PALETTE[idx]["border"]

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

class OneUICalendar(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.config = self.load_config()
        self.events = {}
        self.current_date = datetime.date.today()
        self.click_through_enabled = False

        self.save_timer = QtCore.QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_current_size)

        self.init_window()
        self.init_ui()
        self.init_tray()

        # 10분마다 iCal 자동 동기화
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.fetch_ical_events)
        self.timer.start(10 * 60 * 1000)

        self.fetch_ical_events()

    def load_config(self):
        default = {"ical_url": "", "opacity": 0.85, "width": 1100, "height": 750}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return {**default, **json.load(f)}
            except Exception:
                pass
        return default

    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def save_current_size(self):
        self.config["width"] = self.width()
        self.config["height"] = self.height()
        self.save_config()

    def init_window(self):
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.WindowStaysOnBottomHint |
            QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(600, 450)
        self.resize(self.config.get("width", 1100), self.config.get("height", 750))

    def get_container_style(self, opacity):
        return f"""
            #MainFrame {{
                background-color: rgba(24, 24, 26, {opacity});
                border-radius: 24px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}
            QLabel {{
                background-color: transparent;
                border: none;
                font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;
            }}
        """

    def init_ui(self):
        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(15, 15, 15, 15)

        self.main_frame = QtWidgets.QFrame()
        self.main_frame.setObjectName("MainFrame")
        self.main_frame.setStyleSheet(self.get_container_style(self.config.get("opacity", 0.85)))

        layout = QtWidgets.QVBoxLayout(self.main_frame)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(12)

        # 상단 헤더
        header = QtWidgets.QHBoxLayout()
        self.header_title = QtWidgets.QLabel()
        self.header_title.setStyleSheet("color: #FFFFFF; font-size: 26px; font-weight: bold;")
        self.update_header()
        header.addWidget(self.header_title)
        header.addStretch()

        btn_prev = QtWidgets.QPushButton("<")
        btn_today = QtWidgets.QPushButton("오늘")
        btn_next = QtWidgets.QPushButton(">")

        btn_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.12);
                color: #FFFFFF;
                border: none;
                border-radius: 12px;
                padding: 6px 14px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.22);
            }
        """
        for b in (btn_prev, btn_today, btn_next):
            b.setStyleSheet(btn_style)

        btn_prev.clicked.connect(self.prev_month)
        btn_today.clicked.connect(self.go_today)
        btn_next.clicked.connect(self.next_month)

        header.addWidget(btn_prev)
        header.addWidget(btn_today)
        header.addWidget(btn_next)
        layout.addLayout(header)

        # 요일 바
        weekdays_bar = QtWidgets.QHBoxLayout()
        weekdays_bar.setContentsMargins(0, 4, 0, 4)
        days = ["일", "월", "화", "수", "목", "금", "토"]
        for i, d in enumerate(days):
            lbl = QtWidgets.QLabel(d)
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedHeight(24)
            color = "#FF453A" if i == 0 else ("#0A84FF" if i == 6 else "#98989D")
            lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")
            weekdays_bar.addWidget(lbl, 1)
        layout.addLayout(weekdays_bar)

        # 날짜 그리드
        self.grid = QtWidgets.QGridLayout()
        self.grid.setSpacing(8)
        layout.addLayout(self.grid, 1)

        outer_layout.addWidget(self.main_frame)

        # 우측 하단 크기 조절 손잡이
        self.size_grip = QtWidgets.QSizeGrip(self)
        self.size_grip.resize(20, 20)
        self.size_grip.setStyleSheet("""
            QSizeGrip {
                background-color: rgba(255, 255, 255, 0.15);
                border-radius: 4px;
                margin: 3px;
            }
            QSizeGrip:hover {
                background-color: #0072DE;
            }
        """)

        self.render_calendar()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'size_grip'):
            self.size_grip.move(self.width() - 26, self.height() - 26)
            self.size_grip.raise_()
        if hasattr(self, 'save_timer'):
            self.save_timer.start(500)

    def update_header(self):
        self.header_title.setText(f"{self.current_date.year}년 {self.current_date.month}월")

    def render_calendar(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        year = self.current_date.year
        month = self.current_date.month
        first_day = datetime.date(year, month, 1)
        start_weekday = (first_day.weekday() + 1) % 7

        days_in_month = (datetime.date(year + (month // 12), (month % 12) + 1, 1) - datetime.timedelta(days=1)).day
        prev_month_days = (first_day - datetime.timedelta(days=1)).day
        today = datetime.date.today()

        for r in range(6):
            self.grid.setRowStretch(r, 1)
        for c in range(7):
            self.grid.setColumnStretch(c, 1)

        day_counter = 1
        next_month_counter = 1

        for row in range(6):
            for col in range(7):
                idx = row * 7 + col
                cell = QtWidgets.QFrame()
                cell.setObjectName("DayBox")
                cell_layout = QtWidgets.QVBoxLayout(cell)
                cell_layout.setContentsMargins(8, 8, 8, 8)
                cell_layout.setSpacing(4)
                cell_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

                if idx < start_weekday:
                    p_day = prev_month_days - (start_weekday - idx - 1)
                    lbl_day = QtWidgets.QLabel(str(p_day))
                    lbl
