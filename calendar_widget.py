import sys
import os
import json
import datetime
from PyQt6 import QtCore, QtGui, QtWidgets
import ctypes

# Google Calendar API 라이브러리
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CONFIG_FILE = "calendar_config.json"
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

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

def is_recurring_on_date(rec_rule, target_date):
    try:
        start_date = datetime.date.fromisoformat(rec_rule.get("start_date", ""))
    except Exception:
        return False

    if target_date < start_date:
        return False

    repeat_type = rec_rule.get("repeat", "반복 안함")
    diff_days = (target_date - start_date).days

    if repeat_type == "1일 간격":
        return True
    elif repeat_type == "2일 간격":
        return diff_days % 2 == 0
    elif repeat_type == "3일 간격":
        return diff_days % 3 == 0
    elif repeat_type == "4일 간격":
        return diff_days % 4 == 0
    elif repeat_type == "5일 간격":
        return diff_days % 5 == 0
    elif repeat_type == "6일 간격":
        return diff_days % 6 == 0
    elif repeat_type == "7일 간격":
        return diff_days % 7 == 0
    elif repeat_type == "1달 간격":
        if target_date.day == start_date.day:
            return True
        next_day = target_date + datetime.timedelta(days=1)
        if next_day.day == 1 and start_date.day > target_date.day:
            return True
        return False
    elif repeat_type == "1년 간격":
        return target_date.month == start_date.month and target_date.day == start_date.day
    return False

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
        self.setFixedSize(450, 520)
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
                background-color: rgba(0, 0, 0, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                color: white;
                font-size: 13px;
                padding: 6px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 6px;
                margin-bottom: 3px;
            }
            QListWidget::item:selected {
                background-color: rgba(255, 255, 255, 0.15);
            }
            QCheckBox {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: bold;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QtWidgets.QLabel(f"📅 {self.target_date.strftime('%Y년 %m월 %d일')} 일정")
        title.setStyleSheet("font-size: 17px; font-weight: bold;")
        layout.addWidget(title)

        self.list_widget = QtWidgets.QListWidget()
        layout.addWidget(self.list_widget)

        self.input_text = QtWidgets.QLineEdit()
        self.input_text.setPlaceholderText("새 일정 입력 (예: 당직, 회의, 약속)")
        self.input_text.returnPressed.connect(self.add_event)
        layout.addWidget(self.input_text)

        control_row = QtWidgets.QHBoxLayout()
        self.combo_repeat = QtWidgets.QComboBox()
        for opt in ["반복 안함", "1일 간격", "2일 간격", "3일 간격", "4일 간격", "5일 간격", "6일 간격", "7일 간격", "1달 간격", "1년 간격"]:
            self.combo_repeat.addItem(opt)

        self.combo_color = QtWidgets.QComboBox()
        for c in ["파랑", "빨강", "초록", "주황", "보라", "노랑", "분홍", "하늘", "회색"]:
            self.combo_color.addItem(c)

        btn_add = QtWidgets.QPushButton("일정 추가")
        btn_add.clicked.connect(self.add_event)

        control_row.addWidget(self.combo_repeat, 3)
        control_row.addWidget(self.combo_color, 2)
        control_row.addWidget(btn_add, 2)
        layout.addLayout(control_row)

        self.chk_google = QtWidgets.QCheckBox("🌐 스마트폰(구글 캘린더)에 즉시 동기화")
        self.chk_google.setChecked(True)
        layout.addWidget(self.chk_google)

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

        # 1. 구글 캘린더 일정 (삭제 가능)
        g_events = self.parent_cal.google_events.get(self.target_date, [])
        for gev in g_events:
            title = gev.get("summary", "(제목 없음)")
            ev_id = gev.get("id")
            item = QtWidgets.QListWidgetItem(f"🌐 [구글 동기화] {title}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, ("google", ev_id, title))
            self.list_widget.addItem(item)

        # 2. PC 단일 일정
        local_map = self.parent_cal.config.get("local_events", {})
        for idx, lev in enumerate(local_map.get(self.date_str, [])):
            t = lev.get("title", "") if isinstance(lev, dict) else str(lev)
            c = lev.get("color", "파랑") if isinstance(lev, dict) else "파랑"
            item = QtWidgets.QListWidgetItem(f"💻 [PC전용] [{c}] {t}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, ("single", idx, t))
            self.list_widget.addItem(item)

        # 3. PC 반복 일정
        for rec in self.parent_cal.config.get("recurring_events", []):
            if is_recurring_on_date(rec, self.target_date):
                t = rec.get("title", "")
                c = rec.get("color", "파랑")
                rep = rec.get("repeat", "")
                r_id = rec.get("id")
                item = QtWidgets.QListWidgetItem(f"🔁 [PC반복] [{rep}][{c}] {t}")
                item.setData(QtCore.Qt.ItemDataRole.UserRole, ("recurring", r_id, t))
                self.list_widget.addItem(item)

    def add_event(self):
        txt = self.input_text.text().strip()
        if not txt:
            return

        chosen_color = self.combo_color.currentText()
        chosen_repeat = self.combo_repeat.currentText()
        sync_google = self.chk_google.isChecked()

        if sync_google and self.parent_cal.service:
            # 구글 캘린더에 직접 등록 (스마트폰 즉시 반영)
            success = self.parent_cal.create_google_event(txt, self.target_date, chosen_repeat)
            if success:
                self.input_text.clear()
                self.load_items()
                return

        # 체크 해제했거나 구글 미연결 시 PC 로컬에 저장
        if chosen_repeat == "반복 안함":
            local_map = self.parent_cal.config.setdefault("local_events", {})
            local_map.setdefault(self.date_str, []).append({"title": txt, "color": chosen_color})
        else:
            rec_list = self.parent_cal.config.setdefault("recurring_events", [])
            rec_list.append({
                "id": str(datetime.datetime.now().timestamp()),
                "title": txt,
                "color": chosen_color,
                "repeat": chosen_repeat,
                "start_date": self.date_str
            })

        self.parent_cal.save_config()
        self.parent_cal.render_calendar()
        self.input_text.clear()
        self.load_items()

    def delete_selected(self):
        curr = self.list_widget.currentItem()
        if not curr:
            return
        data = curr.data(QtCore.Qt.ItemDataRole.UserRole)
        if not data:
            return

        action_type, target_id, title = data

        if action_type == "google":
            reply = QtWidgets.QMessageBox.question(
                self, "구글 일정 삭제",
                f"스마트폰(구글 캘린더)에서도 '{title}' 일정을 완전히 삭제하시겠습니까?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                if self.parent_cal.delete_google_event(target_id):
                    self.load_items()
        elif action_type == "single":
            local_map = self.parent_cal.config.get("local_events", {})
            if self.date_str in local_map:
                try:
                    local_map[self.date_str].pop(target_id)
                    if not local_map[self.date_str]:
                        del local_map[self.date_str]
                    self.parent_cal.save_config()
                    self.parent_cal.render_calendar()
                    self.load_items()
                except Exception:
                    pass
        elif action_type == "recurring":
            reply = QtWidgets.QMessageBox.question(
                self, "반복 일정 삭제",
                f"'{title}' PC 반복 일정을 전체 삭제하시겠습니까?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                rec_list = self.parent_cal.config.get("recurring_events", [])
                self.parent_cal.config["recurring_events"] = [r for r in rec_list if r.get("id") != target_id]
                self.parent_cal.save_config()
                self.parent_cal.render_calendar()
                self.load_items()

class OneUICalendar(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.config = self.load_config()
        self.google_events = {}
        self.service = None
        self.current_date = datetime.date.today()
        self.click_through_enabled = self.config.get("click_through", False)

        self.save_timer = QtCore.QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_current_geometry)

        self.init_window()
        self.init_ui()
        self.init_tray()

        # 구글 API 인증 및 일정 로드
        QtCore.QTimer.singleShot(150, self.setup_google_auth)

        # 5분마다 최신 구글 일정 자동 동기화
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.fetch_google_events)
        self.timer.start(5 * 60 * 1000)

        if self.click_through_enabled:
            QtCore.QTimer.singleShot(300, self.apply_initial_click_through)

    def load_config(self):
        default = {
            "opacity": 0.85,
            "width": 1100,
            "height": 750,
            "x": None,
            "y": None,
            "click_through": False,
            "default_color": "회색",
            "local_events": {},
            "recurring_events": [],
            "custom_colors": {
                "조사": "주황",
                "당직": "빨강",
                "야간": "빨강",
                "비번": "회색",
                "휴무": "초록",
                "주간": "파랑"
            }
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    default.update(loaded)
            except Exception:
                pass
        return default

    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def save_current_geometry(self):
        self.config["width"] = self.width()
        self.config["height"] = self.height()
        self.config["x"] = self.x()
        self.config["y"] = self.y()
        self.save_config()

    def setup_google_auth(self):
        if not os.path.exists(CREDENTIALS_FILE):
            self.tray.showMessage(
                "구글 인증 안내",
                "프로그램 폴더에 credentials.json 파일이 필요합니다.",
                QtWidgets.QSystemTrayIcon.MessageIcon.Warning, 3000
            )
            return

        try:
            creds = None
            if os.path.exists(TOKEN_FILE):
                try:
                    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                except Exception:
                    creds = None

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                    except Exception:
                        creds = None
                if not creds:
                    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                    creds = flow.run_local_server(port=0)

                with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())

            self.service = build("calendar", "v3", credentials=creds)
            self.fetch_google_events()
            self.tray.showMessage("One UI Calendar", "구글 캘린더 양방향 연동이 활성화되었습니다.", QtWidgets.QSystemTrayIcon.MessageIcon.Information, 2000)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "구글 연동 오류", f"구글 계정 연결 중 문제가 발생했습니다:\n{e}")

    def fetch_google_events(self):
        if not self.service:
            return
        try:
            today = datetime.date.today()
            start_date = today - datetime.timedelta(days=90)
            end_date = today + datetime.timedelta(days=200)

            time_min = datetime.datetime.combine(start_date, datetime.time.min).isoformat() + "Z"
            time_max = datetime.datetime.combine(end_date, datetime.time.max).isoformat() + "Z"

            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            items = events_result.get('items', [])
            new_events = {}

            for item in items:
                summary = item.get('summary', '(제목 없음)')
                ev_id = item.get('id')
                start = item.get('start', {})
                end = item.get('end', {})

                if 'date' in start:
                    s_d = datetime.date.fromisoformat(start['date'])
                    e_d = datetime.date.fromisoformat(end.get('date', start['date']))
                    curr = s_d
                    if s_d == e_d:
                        new_events.setdefault(s_d, []).append({'id': ev_id, 'summary': summary})
                    else:
                        while curr < e_d:
                            new_events.setdefault(curr, []).append({'id': ev_id, 'summary': summary})
                            curr += datetime.timedelta(days=1)
                elif 'dateTime' in start:
                    dt = datetime.datetime.fromisoformat(start['dateTime'])
                    new_events.setdefault(dt.date(), []).append({'id': ev_id, 'summary': summary})

            self.google_events = new_events
            self.render_calendar()
        except Exception:
            pass

    def create_google_event(self, title, target_date, repeat_type="반복 안함"):
        if not self.service:
            return False
        try:
            start_str = target_date.strftime("%Y-%m-%d")
            end_str = (target_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            body = {
                'summary': title,
                'start': {'date': start_str},
                'end': {'date': end_str},
            }

            rrule_map = {
                "1일 간격": "RRULE:FREQ=DAILY;INTERVAL=1",
                "2일 간격": "RRULE:FREQ=DAILY;INTERVAL=2",
                "3일 간격": "RRULE:FREQ=DAILY;INTERVAL=3",
                "4일 간격": "RRULE:FREQ=DAILY;INTERVAL=4",
                "5일 간격": "RRULE:FREQ=DAILY;INTERVAL=5",
                "6일 간격": "RRULE:FREQ=DAILY;INTERVAL=6",
                "7일 간격": "RRULE:FREQ=WEEKLY;INTERVAL=1",
                "1달 간격": "RRULE:FREQ=MONTHLY;INTERVAL=1",
                "1년 간격": "RRULE:FREQ=YEARLY;INTERVAL=1",
            }
            if repeat_type in rrule_map:
                body['recurrence'] = [rrule_map[repeat_type]]

            self.service.events().insert(calendarId='primary', body=body).execute()
            self.fetch_google_events()
            return True
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "구글 등록 오류", f"구글 일정 등록에 실패했습니다:\n{e}")
            return False

    def delete_google_event(self, event_id):
        if not self.service:
            return False
        try:
            self.service.events().delete(calendarId='primary', eventId=event_id).execute()
            self.fetch_google_events()
            return True
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "구글 삭제 오류", f"구글 일정 삭제에 실패했습니다:\n{e}")
            return False

    def get_event_color(self, summary):
        s = str(summary).strip()
        custom_map = self.config.get("custom_colors", {})
        for keyword, color_name in custom_map.items():
            if keyword in s:
                if color_name in PRESET_COLORS:
                    return PRESET_COLORS[color_name]
        def_color_name = self.config.get("default_color", "회색")
        return PRESET_COLORS.get(def_color_name, DEFAULT_EVENT_COLOR)

    def init_window(self):
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.WindowStaysOnBottomHint |
            QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(600, 450)
        self.resize(self.config.get("width", 1100), self.config.get("height", 750))

        x = self.config.get("x")
        y = self.config.get("y")
        if x is not None and y is not None:
            self.move(int(x), int(y))

    def apply_initial_click_through(self):
        hwnd = int(self.winId())
        Win32Helper.set_click_through(hwnd, True)

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

        self.grid = QtWidgets.QGridLayout()
        self.grid.setSpacing(8)
        layout.addLayout(self.grid, 1)

        outer_layout.addWidget(self.main_frame)

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

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, 'save_timer'):
            self.save_timer.start(500)

    def update_header(self):
        self.header_title.setText(f"{self.current_date.year}년 {self.current_date.month}월")

    def open_day_dialog(self, target_date):
        dlg = DayEventDialog(target_date, self)
        dlg.exec()

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

        local_events = self.config.get("local_events", {})
        recurring_events = self.config.get("recurring_events", [])

        for r in range(6):
            self.grid.setRowStretch(r, 1)
        for c in range(7):
            self.grid.setColumnStretch(c, 1)

        day_counter = 1
        next_month_counter = 1

        for row in range(6):
            for col in range(7):
                idx = row * 7 + col

                if idx < start_weekday:
                    p_day = prev_month_days - (start_weekday - idx - 1)
                    p_date = (first_day - datetime.timedelta(days=start_weekday - idx))
                    cell = DayCell(p_date, self)
                    cell_layout = QtWidgets.QVBoxLayout(cell)
                    cell_layout.setContentsMargins(8, 8, 8, 8)
                    cell_layout.setSpacing(4)
                    cell_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

                    lbl_day = QtWidgets.QLabel(str(p_day))
                    lbl_day.setStyleSheet("color: rgba(255, 255, 255, 0.2); font-size: 13px; font-weight: bold;")
                    cell_layout.addWidget(lbl_day)
                    cell.setStyleSheet("""
                        DayCell {
                            background-color: rgba(255, 255, 255, 0.02);
                            border-radius: 14px;
                            border: 1px solid rgba(255, 255, 255, 0.02);
                        }
                    """)
                elif day_counter <= days_in_month:
                    this_date = datetime.date(year, month, day_counter)
                    cell = DayCell(this_date, self)
                    cell_layout = QtWidgets.QVBoxLayout(cell)
                    cell_layout.setContentsMargins(8, 8, 8, 8)
                    cell_layout.setSpacing(4)
                    cell_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

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
                            DayCell {
                                background-color: rgba(0, 114, 222, 0.12);
                                border-radius: 14px;
                                border: 1.5px solid rgba(0, 114, 222, 0.5);
                            }
                        """)
                    else:
                        color = "#FF453A" if col == 0 else ("#0A84FF" if col == 6 else "#E5E5EA")
                        lbl_day.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")
                        cell.setStyleSheet("""
                            DayCell {
                                background-color: rgba(255, 255, 255, 0.04);
                                border-radius: 14px;
                                border: 1px solid rgba(255, 255, 255, 0.03);
                            }
                            DayCell:hover {
                                background-color: rgba(255, 255, 255, 0.08);
                                border: 1px solid rgba(255, 255, 255, 0.1);
                            }
                        """)

                    cell_layout.addWidget(lbl_day)

                    rendered_items = []
                    # 1. 구글 캘린더 일정
                    for gev in self.google_events.get(this_date, []):
                        title = gev.get("summary", "")
                        bg_col, border_col = self.get_event_color(title)
                        rendered_items.append((title, bg_col, border_col))

                    # 2. PC 단일 일정
                    d_str = this_date.strftime("%Y-%m-%d")
                    for lev in local_events.get(d_str, []):
                        t = lev.get("title", "") if isinstance(lev, dict) else str(lev)
                        c = lev.get("color", "파랑") if isinstance(lev, dict) else "파랑"
                        bg_col, border_col = PRESET_COLORS.get(c, DEFAULT_EVENT_COLOR)
                        rendered_items.append((t, bg_col, border_col))

                    # 3. PC 반복 일정
                    for rec in recurring_events:
                        if is_recurring_on_date(rec, this_date):
                            t = rec.get("title", "")
                            c = rec.get("color", "파랑")
                            bg_col, border_col = PRESET_COLORS.get(c, DEFAULT_EVENT_COLOR)
                            rendered_items.append((t, bg_col, border_col))

                    for title, bg_col, border_col in rendered_items[:2]:
                        ev_lbl = QtWidgets.QLabel(f" {title}")
                        ev_lbl.setStyleSheet(f"""
                            background-color: {bg_col};
                            color: #FFFFFF;
                            border-left: 3px solid {border_col};
                            border-radius: 4px;
                            font-size: 11px;
                            padding: 2px 4px;
                            font-weight: 500;
                        """)
                        cell_layout.addWidget(ev_lbl)

                    if len(rendered_items) > 2:
                        more_lbl = QtWidgets.QLabel(f"+{len(rendered_items)-2}개")
                        more_lbl.setStyleSheet("color: #8E8E93; font-size: 10px;")
                        cell_layout.addWidget(more_lbl)

                    day_counter += 1
                else:
                    n_date = datetime.date(year + (month // 12), (month % 12) + 1, next_month_counter)
                    cell = DayCell(n_date, self)
                    cell_layout = QtWidgets.QVBoxLayout(cell)
                    cell_layout.setContentsMargins(8, 8, 8, 8)
                    cell_layout.setSpacing(4)
                    cell_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

                    lbl_day = QtWidgets.QLabel(str(next_month_counter))
                    lbl_day.setStyleSheet("color: rgba(255, 255, 255, 0.2); font-size: 13px; font-weight: bold;")
                    cell_layout.addWidget(lbl_day)
                    cell.setStyleSheet("""
                        DayCell {
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

    def init_tray(self):
        self.tray = QtWidgets.QSystemTrayIcon(self)
        icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView)
        self.tray.setIcon(icon)

        menu = QtWidgets.QMenu()

        self.act_toggle = menu.addAction("클릭 관통(투과) 모드")
        self.act_toggle.setCheckable(True)
        self.act_toggle.setChecked(self.click_through_enabled)
        self.act_toggle.triggered.connect(self.toggle_click_through)

        act_auth = menu.addAction("구글 계정 재연동 (로그인)")
        act_auth.triggered.connect(self.re_authenticate)

        act_def_color = menu.addAction("기본 일정 색상 변경")
        act_def_color.triggered.connect(self.set_default_color)

        act_color_config = menu.addAction("일정 색상 설정 (메모장 열기)")
        act_color_config.triggered.connect(self.open_color_config)

        act_refresh = menu.addAction("일정 즉시 새로고침 (수동 동기화)")
        act_refresh.triggered.connect(self.reload_all)

        act_size = menu.addAction("창 크기 직접 설정 (가로x세로)")
        act_size.triggered.connect(self.set_window_size)

        act_opacity = menu.addAction("투명도 변경")
        act_opacity.triggered.connect(self.change_opacity)

        menu.addSeparator()
        act_quit = menu.addAction("프로그램 종료")
        act_quit.triggered.connect(QtWidgets.QApplication.instance().quit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def re_authenticate(self):
        if os.path.exists(TOKEN_FILE):
            try:
                os.remove(TOKEN_FILE)
            except Exception:
                pass
        self.setup_google_auth()

    def set_default_color(self):
        color_keys = list(PRESET_COLORS.keys())
        cur_color = self.config.get("default_color", "회색")
        cur_idx = color_keys.index(cur_color) if cur_color in color_keys else 0

        item, ok = QtWidgets.QInputDialog.getItem(
            self, "기본 일정 색상 변경",
            "키워드가 일치하지 않는 일반 일정의 기본 색상을 선택하세요:",
            color_keys, cur_idx, False
        )
        if ok and item:
            self.config["default_color"] = item
            self.save_config()
            self.render_calendar()

    def open_color_config(self):
        self.save_config()
        try:
            os.system(f'notepad.exe "{os.path.abspath(CONFIG_FILE)}"')
        except Exception:
            pass

    def reload_all(self):
        self.config = self.load_config()
        self.fetch_google_events()
        self.render_calendar()
        self.tray.showMessage("One UI Calendar", "구글 일정을 최신 상태로 새로고침했습니다.", QtWidgets.QSystemTrayIcon.MessageIcon.Information, 1500)

    def toggle_click_through(self):
        self.click_through_enabled = not self.click_through_enabled
        self.config["click_through"] = self.click_through_enabled
        self.save_config()

        hwnd = int(self.winId())
        Win32Helper.set_click_through(hwnd, self.click_through_enabled)

        if hasattr(self, 'act_toggle'):
            self.act_toggle.setChecked(self.click_through_enabled)

        msg = "클릭 관통 모드 활성화" if self.click_through_enabled else "클릭 관통 해제 (일정 입력 가능)"
        self.tray.showMessage("One UI Calendar", msg, QtWidgets.QSystemTrayIcon.MessageIcon.Information, 1500)

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
                    self.save_current_geometry()
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
    try:
        app = QtWidgets.QApplication(sys.argv)
        cal = OneUICalendar()
        cal.show()
        sys.exit(app.exec())
    except Exception as e:
        import traceback
        QtWidgets.QMessageBox.critical(None, "오류 안내", f"실행 중 오류가 발생했습니다:\n{traceback.format_exc()}")
