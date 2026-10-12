import sys
import os
import json
import datetime
import requests
from icalendar import Calendar
from PyQt6 import QtCore, QtGui, QtWidgets
import ctypes

CONFIG_FILE = "calendar_config.json"

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

        # 크기 조절 시 자동 저장을 위한 타이머
        self.save_timer = QtCore.QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_current_size)

        self.init_window()
        self.init_ui()
        self.init_tray()

        # 10분마다 iCal 일정 자동 새로고침
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

        # 우측 하단 크기 조절 손잡이 (Size Grip)
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
            # 손잡이를 항상 우측 맨 아래에 배치
            self.size_grip.move(self.width() - 26, self.height() - 26)
            self.size_grip.raise_()
        if hasattr(self, 'save_timer'):
            # 조절이 멈추고 0.5초 뒤 크기 자동 저장
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
                    lbl_day.setStyleSheet("color: rgba(255, 255, 255, 0.2); font-size: 13px; font-weight: bold;")
                    cell_layout.addWidget(lbl_day)
                    cell.setStyleSheet("""
                        #DayBox {
                            background-color: rgba(255, 255, 255, 0.02);
                            border-radius: 14px;
                            border: 1px solid rgba(255, 255, 255, 0.02);
                        }
                    """)
                elif day_counter <= days_in_month:
                    this_date = datetime.date(year, month, day_counter)
                    lbl_day = QtWidgets.QLabel(str(day_counter))
                    is_today = (this_date == today)

                    if is_today:
                        lbl_day.setStyleSheet("""
                            color: #FFFFFF;
                            background-color: #0072DE;
                            border-radius: 8px;
                            padding: 2px 7px;
                            font-size: 12px;
                            font-weight: bold;
                        """)
                        cell.setStyleSheet("""
                            #DayBox {
                                background-color: rgba(0, 114, 222, 0.12);
                                border-radius: 14px;
                                border: 1.5px solid rgba(0, 114, 222, 0.5);
                            }
                        """)
                    else:
                        color = "#FF453A" if col == 0 else ("#0A84FF" if col == 6 else "#E5E5EA")
                        lbl_day.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")
                        cell.setStyleSheet("""
                            #DayBox {
                                background-color: rgba(255, 255, 255, 0.04);
                                border-radius: 14px;
                                border: 1px solid rgba(255, 255, 255, 0.03);
                            }
                        """)

                    cell_layout.addWidget(lbl_day)

                    ev_list = self.events.get(this_date, [])
                    for ev in ev_list[:2]:
                        ev_lbl = QtWidgets.QLabel(f" {ev}")
                        ev_lbl.setStyleSheet("""
                            background-color: rgba(44, 117, 255, 0.32);
                            color: #FFFFFF;
                            border-left: 3px solid #2C75FF;
                            border-radius: 4px;
                            font-size: 11px;
                            padding: 2px 4px;
                        """)
                        cell_layout.addWidget(ev_lbl)

                    if len(ev_list) > 2:
                        more_lbl = QtWidgets.QLabel(f"+{len(ev_list)-2}개")
                        more_lbl.setStyleSheet("color: #8E8E93; font-size: 10px;")
                        cell_layout.addWidget(more_lbl)

                    day_counter += 1
                else:
                    lbl_day = QtWidgets.QLabel(str(next_month_counter))
                    lbl_day.setStyleSheet("color: rgba(255, 255, 255, 0.2); font-size: 13px; font-weight: bold;")
                    cell_layout.addWidget(lbl_day)
                    cell.setStyleSheet("""
                        #DayBox {
                            background-color: rgba(255, 255, 255, 0.02);
                            border-radius: 14px;
                            border: 1px solid rgba(255, 255, 255, 0.02);
                        }
                    """)
                    next_month_counter += 1

                self.grid.addWidget(cell, row, col)

    def prev_month(self):
        m = self.current_date.month - 1
        y = self.current_date.year
        if m < 1:
            m = 12
            y -= 1
        self.current_date = datetime.date(y, m, 1)
        self.update_header()
        self.render_calendar()

    def next_month(self):
        m = self.current_date.month + 1
        y = self.current_date.year
        if m > 12:
            m = 1
            y += 1
        self.current_date = datetime.date(y, m, 1)
        self.update_header()
        self.render_calendar()

    def go_today(self):
        self.current_date = datetime.date.today()
        self.update_header()
        self.render_calendar()

    def fetch_ical_events(self):
        url = self.config.get("ical_url", "").strip()
        if not url:
            return
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                cal = Calendar.from_ical(res.text)
                new_events = {}
                for component in cal.walk():
                    if component.name == "VEVENT":
                        summary = str(component.get("summary", "일정"))
                        dtstart = component.get("dtstart").dt
                        if isinstance(dtstart, datetime.datetime):
                            dtstart = dtstart.date()
                        new_events.setdefault(dtstart, []).append(summary)
                self.events = new_events
                self.render_calendar()
        except Exception:
            pass

    def init_tray(self):
        self.tray = QtWidgets.QSystemTrayIcon(self)
        icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView)
        self.tray.setIcon(icon)

        menu = QtWidgets.QMenu()
        act_toggle = menu.addAction("클릭 관통(투과) 모드 켜기/끄기")
        act_toggle.triggered.connect(self.toggle_click_through)

        act_url = menu.addAction("구글 캘린더 iCal 주소 설정")
        act_url.triggered.connect(self.set_ical_url)

        act_size = menu.addAction("창 크기 직접 설정 (가로x세로)")
        act_size.triggered.connect(self.set_window_size)

        act_opacity = menu.addAction("투명도 변경")
        act_opacity.triggered.connect(self.change_opacity)

        menu.addSeparator()
        act_quit = menu.addAction("프로그램 종료")
        act_quit.triggered.connect(QtWidgets.QApplication.instance().quit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def toggle_click_through(self):
        self.click_through_enabled = not self.click_through_enabled
        hwnd = int(self.winId())
        Win32Helper.set_click_through(hwnd, self.click_through_enabled)
        msg = "클릭 관통 모드 활성화 (아이콘 통과 클릭 가능)" if self.click_through_enabled else "클릭 관통 해제 (캘린더 조작 가능)"
        self.tray.showMessage("One UI Calendar", msg, QtWidgets.QSystemTrayIcon.MessageIcon.Information, 2000)

    def set_ical_url(self):
        url, ok = QtWidgets.QInputDialog.getText(self, "iCal 설정", "구글 캘린더 비공개 iCal 주소를 입력하세요:", text=self.config.get("ical_url", ""))
        if ok and url:
            self.config["ical_url"] = url.strip()
            self.save_config()
            self.fetch_ical_events()

    def set_window_size(self):
        text, ok = QtWidgets.QInputDialog.getText(
            self, "창 크기 설정", "가로x세로 픽셀을 입력하세요 (예: 1300x850):",
            text=f"{self.width()}x{self.height()}"
        )
        if ok and text:
            try:
                parts = text.lower().replace(" ", "").split("x")
                w, h = int(parts[0]), int(parts[1])
                if w >= 500 and h >= 400:
                    self.resize(w, h)
                    self.save_current_size()
            except Exception:
                pass

    def change_opacity(self):
        val, ok = QtWidgets.QInputDialog.getInt(self, "투명도 조절", "투명도 비율 (30 ~ 100%):", int(self.config.get("opacity", 0.85) * 100), 30, 100, 5)
        if ok:
            op = val / 100.0
            self.config["opacity"] = op
            self.save_config()
            self.main_frame.setStyleSheet(self.get_container_style(op))

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == QtCore.Qt.MouseButton.LeftButton and hasattr(self, '_drag_pos'):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    cal = OneUICalendar()
    cal.show()
    sys.exit(app.exec())
