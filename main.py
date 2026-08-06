"""
Vault-Tec / RobCo Terminal — Pygame edition with CRT bloom/scanline effects.

Запуск:
    pip install pygame
    pip install paho-mqtt      # опционально, для чата с мастером по сети
    python3 main.py

Звук: ожидает файлы в папке media/ рядом с main.py — см. SOUND_FILES ниже.
Если файлов нет или аудио недоступно — приложение просто работает без звука.

Сборка в отдельный exe/бинарник (позже, на целевой машине):
    pip install pyinstaller
    pyinstaller --onefile --windowed --add-data "FalloutDocuments:FalloutDocuments" --add-data "media:media" main.py

Управление:
    Цифры + Enter — выбор пункта меню (как в оригинальном RobCo-терминале)
    Стрелки вверх/вниз — прокрутка текста, если он не помещается на экран
    Esc  — назад / отмена ввода
    В чате с мастером: просто печатаете текст и жмёте Enter, "exit" — выход из чата
"""

import os
import sys
import time
import queue
import datetime
import random
import re
import shutil
import json

import pygame

# --------------------------------------------------------------------------
# Опциональный psutil (определение подключённой флешки с модулем взлома).
# Если библиотеки нет — автоопределение просто выключено, остаётся
# резервный ручной триггер (см. HACK_MODULE_TRIGGER_PASSWORD).
# --------------------------------------------------------------------------
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


# --------------------------------------------------------------------------
# Опциональный MQTT (чат с мастером). Если библиотеки нет или брокер
# недоступен — приложение не падает, а работает в локальном тестовом
# режиме (эхо ответов), чтобы можно было разрабатывать/тестировать без
# развёрнутой сети на полигоне.
# --------------------------------------------------------------------------
try:
    import paho.mqtt.client as mqtt
    MQTT_LIB_AVAILABLE = True
except ImportError:
    MQTT_LIB_AVAILABLE = False

MQTT_BROKER_HOST = os.environ.get("VAULT_MQTT_HOST", "192.168.4.1")
MQTT_BROKER_PORT = 1883
TERMINAL_ID = os.environ.get("VAULT_TERMINAL_ID", "terminal_1")
TOPIC_TO_MASTER = f"vault/{TERMINAL_ID}/to_master"
TOPIC_FROM_MASTER = f"vault/{TERMINAL_ID}/from_master"

# ==========================================================================
# Конфигурация внешнего вида
# ==========================================================================
TEST_MODE = os.environ.get("TERMINAL_TEST_MODE") == "1"  # для автосмоук-теста, см. низ файла
DEVMODE = os.environ.get("TERMINAL_DEVMODE", "1") == "0"  # True: пропустить пароль-игру при загрузке

RENDER_W, RENDER_H = 960, 600      # внутреннее низкое разрешение рендера (даёт характерную "чанковость")
WINDOW_W, WINDOW_H = 1280, 800     # реальный размер окна, рендер растягивается до него
FONT_SIZE = 20
LINE_SPACING = 8
MARGIN = 28
FPS = 30

COLOR_BG = (4, 10, 4)
COLOR_TEXT = (69, 255, 90)
COLOR_DIM = (25, 100, 35)
COLOR_CURSOR = (140, 255, 150)
COLOR_HIGHLIGHT = (200, 255, 210)  # подсветка выделенной строки в дереве голодиска

BLOOM_DOWNSCALE = 0.18
BLOOM_ALPHA = 70
SCANLINE_SPACING = 3
SCANLINE_ALPHA = 40
VIGNETTE_ALPHA_MAX = 90

TYPEWRITER_CHARS_PER_FRAME = 2
SCROLL_STEP = 3  # строк за одно нажатие/повтор стрелки

# ==========================================================================
# Конфигурация терминала 
# ==========================================================================

# --------------------------------------------------------------------------
# Авторизация
# --------------------------------------------------------------------------
MAX_PASSWORD_ATTEMPTS = 4
UNAUTHORIZED_USER_LABEL = "АНОНИМ"

# --------------------------------------------------------------------------
# Определение подключённых флешек 
# --------------------------------------------------------------------------
DRIVE_POLL_INTERVAL = 1.0  

# --------------------------------------------------------------------------
# Модуль взлома пароля
# --------------------------------------------------------------------------
ENABLE_HACK_MODULE_DETECTION = True         # реагировать ли на маркер флешки
HACK_MODULE_MARKER_FILENAME = "robco_hack.module"  # файл-маркер в корне флешки
HACK_MODULE_TRIGGER_PASSWORD = "ICEBREAKER"

# --------------------------------------------------------------------------
# Задержки
# --------------------------------------------------------------------------
AUTH_SUCCESS_DELAY_SECONDS = 2.5   
LOCKOUT_DELAY_SECONDS = 2.5        
MENU_CLOSE_DELAY_SECONDS = 2.0     

# --------------------------------------------------------------------------
# Время
# --------------------------------------------------------------------------
GAME_YEAR = 2276                       
MONTH_ABBR_RU = [
    "ЯНВ", "ФЕВ", "МАР", "АПР", "МАЯ", "ИЮН",
    "ИЮЛ", "АВГ", "СЕН", "ОКТ", "НОЯ", "ДЕК",
]
TIMEZONE_GMT3 = datetime.timezone(datetime.timedelta(hours=3))      

# -------------------------------------------------------------------------
# Учётные записи пользователей терминала
# -------------------------------------------------------------------------
# "level" — уровень доступа: "user", "admin" или "owner".
#   owner — доступ ко всем пунктам меню, включённым в настройках выше,
#           и ко всем папкам «Журнал» всех пользователей.
#   admin — доступ ко всем пунктам меню, кроме чата со S.C.O.P.E.
#   user  — доступ только к пунктам, формируемым папкой data/, к чтению
#           голодисков и к собственной папке в «Журнале». Доступ к прочим
#           пунктам (формируемым самим main.py) можно дать отдельным
#           пользователям точечно через MENU_ITEM_EXTRA_USER_IDS ниже.
USER_ACCOUNTS = [
    {"id": "bill_wasson",   "name": "БИЛЛ ВАССОН",  "password": "HAPPINESS", "level": "owner"},
    {"id": "lucy_maclean",  "name": "ЛЮСИ МАКЛИН",  "password": "OKEYDOKEY", "level": "user"},
    {"id": "cooper_howard", "name": "КУПЕР ГОВАРД", "password": "FAMILY",    "level": "admin"},
]
ACCESS_LEVEL_RANK = {"user": 0, "admin": 1, "owner": 2}
MENU_ITEM_MIN_LEVEL = {
    "door_control": "admin",
    "chat": "owner",
    "system": "admin",
    "map": "user"
}
MENU_ITEM_EXTRA_USER_IDS = {
    "door_control": [],
    "chat": [],
    "system": [],
    "map": []
}

SYSTEM_SUBFOLDER_LABELS = {
    "actions": "Действия пользователей",
    "profiles": "Профили пользователей",
    "door_control": "Управление дверьми",
    "chat": "Чат со S.C.O.P.E.",
    "disk_reader": "Чтение голодисков",
    "system": "Система",
    "map": "Карта"
}

ACCESS_DENIED_MESSAGE = "ДОСТУП ЗАПРЕЩЁН\nНедостаточно прав"

# -------------------------------------------------------------------------
# Закреплённая шапка
# -------------------------------------------------------------------------
HEADER_BANNER = (
    "================ ROBCO INDUSTRIES UNIFIED OPERATING SYSTEM ================\n"
    "================== COPYRIGHT 2075-2077 ROBCO INDUSTRIES ==================="
)
HEADER_LINE_COUNT = len(HEADER_BANNER.split("\n")) + 1  # +1 — строка статуса (дата/пользователь)
HEADER_GAP_LINES = 1  # пустая строка-отступ между шапкой и прокручиваемым текстом

# -------------------------------------------------------------------------
# Директории
# -------------------------------------------------------------------------
JOURNAL_DIR = "journal"
CHAT_HISTORY_DIR = "chat_history"
DATA_DIR = "data"
SYSTEM_DIR = "system"
MAP_MARKERS_DIR = "map_markers"

# -------------------------------------------------------------------------
# Включаемые модули меню
# -------------------------------------------------------------------------
ENABLE_DOOR_CONTROL = True
ENABLE_CHAT = True
ENABLE_DISK_READER = True
ENABLE_SYSTEM = True
ENABLE_MAP = True

# --------------------------------------------------------------------------
# Интерфейс чтения-записи голодисков
# --------------------------------------------------------------------------
DISK_READER_LINE_H_EXTRA = 4  # доп. межстрочный интервал для дерева файлов
DISK_READER_COL_GAP = 24      # зазор между колонками терминала и голодиска

# -------------------------------------------------------------------------
# Звуки
# -------------------------------------------------------------------------
SOUND_DIR = "media"
SOUND_FILES = {
    "clicking": "FalloutSoundClicking.mp3",  # печать текста (лупом, пока идёт анимация)
    "clack": "FalloutSoundClack.mp3",        # каждое нажатие клавиши игроком
    "complete": "FalloutSoundComplete.wav",  # успешное действие
    "error": "FalloutSoundError.wav",        # неверный пароль, ошибка, неизвестная команда
    "unlocked": "FalloutSoundUnlocked.wav",  # верный пароль, доступ разрешён
}

# --------------------------------------------------------------------------
# Заставка перед загрузкой терминала (картинка + музыка + прогресс-бар)
# --------------------------------------------------------------------------
SPLASH_IMAGE_PATH = os.path.join("images", "splash.png")
SPLASH_MUSIC_PATH = os.path.join("media", "maybe.mp3")

SPLASH_TICK_MIN = 0.02       # обычная задержка между приростом на 1% (сек)
SPLASH_TICK_MAX = 0.06
SPLASH_STALL_CHANCE = 0.12   # вероятность "зависания" на случайном проценте
SPLASH_STALL_MIN = 0.25
SPLASH_STALL_MAX = 0.7
SPLASH_HOLD_AT_100 = 0.6     # пауза на 100%, прежде чем перейти к загрузке
SPLASH_BAR_WIDTH = 420
SPLASH_BAR_HEIGHT = 22

#--------------------------------------------------------------------------
# Карта
#--------------------------------------------------------------------------
MAP_IMAGE_PATH = os.path.join("images", "map.png")
MAP_BOUNDS_PATH = os.path.join("images", "map_bounds.json")
TERMINAL_LAT = 59.929407
TERMINAL_LON = 30.368455
MAP_ZOOM_LEVEL = 0.015

COLOR_MAP_MARKER = (255, 200, 50)  
COLOR_MAP_ROUTE = (255, 50, 50)    
COLOR_MAP_TERMINAL = (255, 50, 50)

# =========================================================================
# Функции для мини-игры взлома
# =========================================================================
def calculate_positional_matches(guess, correct):
    """Подсчёт совпадений букв по позиции (как в классическом Fallout)."""
    guess = guess.upper()
    correct = correct.upper()
    matches = 0
    for i in range(min(len(guess), len(correct))):
        if guess[i] == correct[i]:
            matches += 1
    return matches

WORD_BANK = [
    "CONSIST", "ROAMING", "GAINING", "FARMING", "STERILE", "ENGLISH",
    "FENCING", "MANKIND", "MORNING", "HEALING", "LEAVING", "CORRECT",
    "JESSICA", "CONTACT", "NUCLEAR", "SCIENCE", "CONTROL", "FALLOUT",
    "DISABLE", "UPGRADE", "SYSTEMS", "NETWORK", "PROCESS", "PROGRAM",
    "DIGITAL", "MACHINE", "KEYCARD", "SCANNER", "CHAMBER", "REACTOR",
    "TESTING", "HUNTING", "COOKING", "WALKING", "SITTING", "TALKING",
    "WRITING", "READING", "WORKING", "PLAYING", "WINNING", "RUNNING"
]

# =========================================================================
# Визуальные эффекты
# =========================================================================
def make_bloom(surface):
    """Дешёвый bloom через downscale -> upscale со сглаживанием."""
    w, h = surface.get_size()
    sw, sh = max(1, int(w * BLOOM_DOWNSCALE)), max(1, int(h * BLOOM_DOWNSCALE))
    small = pygame.transform.smoothscale(surface, (sw, sh))
    bloom = pygame.transform.smoothscale(small, (w, h))
    bloom.set_alpha(BLOOM_ALPHA)
    return bloom


def make_scanlines(w, h):
    overlay = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(0, h, SCANLINE_SPACING):
        pygame.draw.line(overlay, (0, 0, 0, SCANLINE_ALPHA), (0, y), (w, y))
    return overlay


def make_vignette(w, h):
    """Затемнение к краям экрана, считается один раз при старте."""
    overlay = pygame.Surface((w, h), pygame.SRCALPHA)
    max_dist = ((w / 2) ** 2 + (h / 2) ** 2) ** 0.5
    step = 8
    for y in range(0, h, step):
        for x in range(0, w, step):
            dx, dy = x - w / 2, y - h / 2
            dist = (dx * dx + dy * dy) ** 0.5
            alpha = int(VIGNETTE_ALPHA_MAX * (dist / max_dist) ** 2)
            if alpha > 2:
                pygame.draw.rect(overlay, (0, 0, 0, min(alpha, 255)), (x, y, step, step))
    return overlay


# --------------------------------------------------------------------------
# Буфер вывода с эффектом печатной машинки (не блокирует основной цикл)
# --------------------------------------------------------------------------
class OutputBuffer:
    def __init__(self, max_visible_lines):
        self.lines = []           # уже полностью показанные строки
        self.pending_text = ""    # текст, который ещё печатается по символам
        self.max_visible_lines = max_visible_lines
        self.scroll_offset = 0    # 0 = показываем самый низ (последние строки)

    def push(self, text, instant=False):
        self.scroll_offset = 0  # новый текст — всегда переезжаем к последним строкам
        if instant:
            self.lines.extend(text.split("\n"))
        else:
            if self.pending_text:
                self.pending_text += "\n" + text
            else:
                self.pending_text = text

    def clear(self):
        self.lines = []
        self.pending_text = ""
        self.scroll_offset = 0

    def update(self):
        for _ in range(TYPEWRITER_CHARS_PER_FRAME):
            if not self.pending_text:
                break
            ch = self.pending_text[0]
            self.pending_text = self.pending_text[1:]
            if not self.lines:
                self.lines.append("")
            if ch == "\n":
                self.lines.append("")
            else:
                self.lines[-1] += ch

    def is_typing(self):
        return len(self.pending_text) > 0

    def skip_typing(self):
        """Мгновенно долить весь ожидающий текст (по Enter/клику, если надоело ждать)."""
        if self.pending_text:
            self.lines.extend(self.pending_text.split("\n"))
            if not self.lines:
                self.lines = [""]
            self.pending_text = ""

    def scroll(self, delta, max_lines=None):
        """delta > 0 — пролистать вверх (к старому тексту),
        delta < 0 — пролистать вниз (к свежему тексту)."""
        n = self.max_visible_lines if max_lines is None else max_lines
        max_offset = max(0, len(self.lines) - n)
        self.scroll_offset = min(max_offset, max(0, self.scroll_offset + delta))

    def visible_lines(self, max_lines=None):
        n = self.max_visible_lines if max_lines is None else max_lines
        if n <= 0:
            return []
        if self.scroll_offset <= 0:
            return self.lines[-n:]
        end = len(self.lines) - self.scroll_offset
        start = max(0, end - n)
        return self.lines[start:end]

    def has_more_above(self, max_lines=None):
        n = self.max_visible_lines if max_lines is None else max_lines
        end = len(self.lines) - self.scroll_offset
        return max(0, end - n) > 0

    def has_more_below(self):
        return self.scroll_offset > 0


# ==========================================================================
# Системный логгер
# ==========================================================================
class SystemLogger:
    def __init__(self, system_dir):
        self.system_dir = system_dir
        self.log_file = None
        self.log_path = None
        self.chat_logging = False  # Флаг: идёт ли логирование чата
        self.session_start = None
        
    def start_session(self, user_name, user_id):
        """Начинает новую сессию логирования."""
        self.session_start = datetime.datetime.now(TIMEZONE_GMT3)
        self.chat_logging = False
        
        # Создаём имя файла: ГГГГ-ММ-ДД_ЧЧ-ММ-СС.md
        filename = f"{GAME_YEAR:04d}-{self.session_start.month:02d}-{self.session_start.day:02d}_" \
                   f"{self.session_start.hour:02d}-{self.session_start.minute:02d}-{self.session_start.second:02d}.md"
        
        # Создаём папку actions если её нет
        actions_dir = os.path.join(self.system_dir, "actions")
        os.makedirs(actions_dir, exist_ok=True)
        
        self.log_path = os.path.join(actions_dir, filename)
        
        # Записываем начало сессии
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write(f"# СЕССИЯ ТЕРМИНАЛА\n\n")
            f.write(f"**Дата:** {self._format_datetime(self.session_start)}\n")
            f.write(f"**Пользователь:** {user_name} ({user_id})\n")
            f.write(f"**Статус:** АКТИВНА\n\n")
            f.write("---\n\n")
            f.write("## ЖУРНАЛ ДЕЙСТВИЙ\n\n")
    
    def _format_datetime(self, dt):
        """Форматирует дату и время."""
        month = MONTH_ABBR_RU[dt.month - 1]
        return f"{dt.day:02d} {month} {dt.year} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"
    
    def _format_timestamp(self, dt):
        """Форматирует временную метку для лога."""
        month = MONTH_ABBR_RU[dt.month - 1]
        return f"{dt.day:02d} {month} {dt.year} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"
    
    def log(self, speaker, message, is_system=False, is_user_input=False, instant=False):
        """Записывает событие в лог.
        
        Args:
            speaker: Имя говорящего (пользователь или "SYSTEM")
            message: Сообщение
            is_system: Если True, speaker заменяется на "SYSTEM"
            is_user_input: Если True, это ввод пользователя
            instant: Если True, пишем в файл немедленно
        """
        if not self.log_path or not os.path.exists(self.log_path):
            return
        
        # Если идёт логирование чата, игнорируем все записи
        if self.chat_logging:
            return
        
        now = datetime.datetime.now(TIMEZONE_GMT3)
        timestamp = self._format_timestamp(now)
        
        # Определяем тип записи
        if is_system:
            prefix = "[SYSTEM]"
        elif is_user_input:
            prefix = f"[{speaker}]"
        else:
            prefix = f"[{speaker}]"
        
        # Формируем запись
        entry = f"**{timestamp}** {prefix}: {message}\n"
        
        # Записываем в файл
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    
    def start_chat_logging(self):
        """Начинает логирование чата (приостанавливает обычное логирование)."""
        self.chat_logging = True
        self.log("SYSTEM", "Начало сеанса чата со S.C.O.P.E.", is_system=True)
    
    def stop_chat_logging(self):
        """Завершает логирование чата (возобновляет обычное логирование)."""
        self.chat_logging = False
        self.log("SYSTEM", "Завершение сеанса чата со S.C.O.P.E.", is_system=True)

# ===========================================================================
# Отметки карты
# ===========================================================================

class MapMarker:
    def __init__(self, lat, lon, text, marker_id=None):
        self.lat = lat
        self.lon = lon
        self.text = text
        self.id = marker_id or str(int(time.time() * 1000))
    
    def to_dict(self):
        return {
            "id": self.id,
            "lat": self.lat,
            "lon": self.lon,
            "text": self.text
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(data["lat"], data["lon"], data["text"], data["id"])
    
    @classmethod
    def from_file(cls, filepath):
        """Загружает отметку из .md файла"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Парсим формат:
            # ---
            # lat: 55.7522
            # lon: 37.6156
            # ---
            # Текст отметки
            lines = content.strip().split("\n")
            lat = None
            lon = None
            text = ""
            in_header = False
            header_ended = False
            
            for line in lines:
                if line.strip() == "---":
                    if not in_header:
                        in_header = True
                    else:
                        header_ended = True
                    continue
                
                if not header_ended and in_header:
                    if "lat:" in line:
                        lat = float(line.split(":")[1].strip())
                    elif "lon:" in line:
                        lon = float(line.split(":")[1].strip())
                elif header_ended:
                    text += line + "\n"
            
            text = text.strip()
            if lat is not None and lon is not None:
                return cls(lat, lon, text, os.path.splitext(os.path.basename(filepath))[0])
        except Exception as e:
            print(f"Ошибка загрузки отметки {filepath}: {e}")
        return None
    
    def save(self, directory):
        """Сохраняет отметку в .md файл"""
        os.makedirs(directory, exist_ok=True)
        filename = f"{self.id}.md"
        filepath = os.path.join(directory, filename)
        
        content = f"""---
lat: {self.lat:.6f}
lon: {self.lon:.6f}
---
{self.text}"""
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

class MapMarkersManager:
    def __init__(self, directory):
        self.directory = directory
        self.markers = []
        self.load_markers()
    
    def load_markers(self):
        """Загружает все отметки из папки"""
        self.markers = []
        if not os.path.exists(self.directory):
            return
        
        for filename in os.listdir(self.directory):
            if filename.endswith(".md"):
                filepath = os.path.join(self.directory, filename)
                marker = MapMarker.from_file(filepath)
                if marker:
                    self.markers.append(marker)
    
    def add_marker(self, lat, lon, text):
        """Добавляет новую отметку"""
        marker = MapMarker(lat, lon, text)
        marker.save(self.directory)
        self.markers.append(marker)
        return marker
    
    def remove_marker(self, marker_id):
        """Удаляет отметку по ID"""
        for i, marker in enumerate(self.markers):
            if marker.id == marker_id:
                filepath = os.path.join(self.directory, f"{marker_id}.md")
                if os.path.exists(filepath):
                    os.remove(filepath)
                del self.markers[i]
                return True
        return False
    
    def get_markers_in_view(self, lat_min, lat_max, lon_min, lon_max):
        """Возвращает отметки в заданном прямоугольнике"""
        return [m for m in self.markers 
                if lat_min <= m.lat <= lat_max and lon_min <= m.lon <= lon_max]
    
    def copy_from_holotape(self, source_path):
        """Копирует отметку с голодиска"""
        marker = MapMarker.from_file(source_path)
        if marker:
            # Проверяем, нет ли уже такой отметки
            for existing in self.markers:
                if existing.id == marker.id:
                    return False
            marker.save(self.directory)
            self.markers.append(marker)
            return True
        return False

# ===========================================================================
# Приложение
# ===========================================================================
class TerminalApp:
    STATE_SPLASH = "SPLASH"
    STATE_BOOT = "BOOT"
    STATE_USER_SELECT = "USER_SELECT"
    STATE_PASSWORD = "PASSWORD"
    STATE_HACK_MINIGAME = "HACK_MINIGAME"
    STATE_AUTH_SUCCESS = "AUTH_SUCCESS"
    STATE_CLOSING = "CLOSING"
    STATE_MAIN_MENU = "MAIN_MENU"
    STATE_LOG_USER_LIST = "LOG_USER_LIST"
    STATE_LOG_LIST = "LOG_LIST"
    STATE_LOG_VIEW = "LOG_VIEW"
    STATE_LOG_NEW = "LOG_NEW"
    STATE_DATA_LIST = "DATA_LIST"
    STATE_DATA_VIEW = "DATA_VIEW"
    STATE_DOOR = "DOOR"
    STATE_DISK_READER = "DISK_READER"
    STATE_CHAT_MENU = "CHAT_MENU"
    STATE_CHAT_HISTORY_LIST = "CHAT_HISTORY_LIST"
    STATE_CHAT_HISTORY_VIEW = "CHAT_HISTORY_VIEW"
    STATE_CHAT = "CHAT"
    STATE_CHAT_SAVED = "CHAT_SAVED"
    STATE_SYSTEM_MENU = "SYSTEM_MENU"
    STATE_SYSTEM_VIEW = "SYSTEM_VIEW"
    STATE_SYSTEM_PROFILES = "SYSTEM_PROFILES"
    STATE_SYSTEM_PROFILE_VIEW = "SYSTEM_PROFILE_VIEW"
    STATE_SYSTEM_ACTIONS = "SYSTEM_ACTIONS"
    STATE_SYSTEM_ACTION_VIEW = "SYSTEM_ACTION_VIEW"
    STATE_MAP = "MAP"
    STATE_MAP_MARKER_INPUT = "MAP_MARKER_INPUT"

    def __init__(self):
        pygame.init()
        # Глобальный key-repeat намеренно НЕ включаем: он повторял бы и Enter,
        # что при удержании кнопки приводило к каскаду лишних отправок формы
        # (пустой ввод трактуется многими меню как "0"/"назад"). Повтор нужен
        # только для стрелок прокрутки — реализован вручную в update().
        pygame.display.set_caption("ROBCO INDUSTRIES (TM) TERMLINK")
        self.window = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.render_surface = pygame.Surface((RENDER_W, RENDER_H))
        self.clock = pygame.time.Clock()

        self.font = pygame.font.SysFont("couriernew,consolas,menlo,monospace", FONT_SIZE)
        line_h = self.font.get_linesize() + LINE_SPACING
        SCROLL_INDICATOR_ROWS = 2  # "ещё текст выше" + "ещё текст ниже" — резервируем всегда

        # Без закреплённой шапки (BOOT/PASSWORD) — вся высота под прокрутку.
        self.max_visible_lines_full = max(
            1, (RENDER_H - MARGIN * 2 - line_h - SCROLL_INDICATOR_ROWS * line_h) // line_h
        )

        # С закреплённой шапкой — сверху вычитаем место под неё + отступ.
        header_reserved = (HEADER_LINE_COUNT + HEADER_GAP_LINES) * line_h
        self.max_visible_lines_header = max(
            1,
            (RENDER_H - MARGIN * 2 - line_h - header_reserved - SCROLL_INDICATOR_ROWS * line_h) // line_h,
        )

        self.output = OutputBuffer(self.max_visible_lines_full)
        self.input_text = ""
        self.cursor_visible = True
        self.cursor_timer = 0.0

        # Ручной повтор для удержания стрелок вверх/вниз (см. update())
        self._scroll_hold_start = None
        self._scroll_next_repeat_at = 0.0
        SCROLL_REPEAT_DELAY = 0.4   # пауза перед началом автоповтора (сек)
        SCROLL_REPEAT_INTERVAL = 0.04  # интервал между повторами (сек)
        self._scroll_repeat_delay = SCROLL_REPEAT_DELAY
        self._scroll_repeat_interval = SCROLL_REPEAT_INTERVAL

        self.scanlines = make_scanlines(RENDER_W, RENDER_H)
        self.vignette = make_vignette(RENDER_W, RENDER_H)

        self.state = self.STATE_BOOT
        self.fixed_header = False  # True — рисуем шапку статично сверху (не часть прокрутки)
        self.door_status = "ЗАКРЫТА"
        self.log_entries = []
        self.new_log_lines = []
        self.chat_history_entries = []
        self.chat_transcript = []
        self.main_menu_actions = []
        self.data_entries = []
        self.current_data_category = None

        # Авторизация
        self.password_attempts_used = 0
        self.current_user = UNAUTHORIZED_USER_LABEL
        self.current_user_id = None
        self.current_user_level = None
        self.pending_user = None          # выбранный, но ещё не подтверждённый паролем аккаунт
        self.current_log_owner_id = None  # чей журнал сейчас просматриваем (актуально для owner)
        self._ensure_user_journal_dirs()

        # Модуль взлома (запускается только с внешней флешки; попытки —
        # общие с обычным вводом пароля, self.password_attempts_used)
        self.hack_correct_password = ""
        self.hack_display = []
        self.hack_bonus_codes = []
        self.hack_all_content = []
        self.hack_attempts = 0
        self.hack_guess_history = []
        self.hack_state = "INACTIVE"  # INACTIVE, ACTIVE, SUCCESS, FAILED
        self.hack_initial_render = True
        self.hack_restore_smiley = ""  # Какой смайл восстанавливает попытку

        # Определение флешек — общий механизм (см. константы выше)
        self._last_drive_poll_at = 0.0
        self._known_mount_points = set()
        if PSUTIL_AVAILABLE:
            try:
                self._known_mount_points = {p.mountpoint for p in psutil.disk_partitions(all=False)}
            except Exception:
                self._known_mount_points = set()

        # Интерфейс чтения-записи голодисков
        self.disk_reader_mount = None
        self.disk_reader_focus = "terminal"  # "terminal" | "holotape"
        self.disk_reader_cursor = {"terminal": 0, "holotape": 0}
        self.disk_reader_rows = {"terminal": [], "holotape": []}
        self.disk_reader_status = ""
        self._last_disk_reader_check_at = 0.0

        # Отложенные действия (даём прочитать сообщение перед переходом/выключением)
        self._pending_callback = None
        self._pending_callback_at = None

        # Сеть (чат с мастером)
        self.mqtt_client = None
        self.mqtt_connected = False
        self.incoming_queue = queue.Queue()
        self._chat_status_resolved = True
        self._chat_connect_deadline = 0.0

        self.running = True
        self._frame_count = 0

        # ---------------------------------------------------------- звук
        self.sound_enabled = True
        self.sounds = {}
        self.typing_channel = None
        self._typing_loop_active = False
        try:
            pygame.mixer.init()
            for name, filename in SOUND_FILES.items():
                path = os.path.join(SOUND_DIR, filename)
                try:
                    self.sounds[name] = pygame.mixer.Sound(path)
                except (pygame.error, FileNotFoundError) as e:
                    print(f"[звук] не удалось загрузить {path}: {e}")
            self.typing_channel = pygame.mixer.Channel(0)
        except pygame.error as e:
            print(f"[звук] аудио недоступно, работаю без звука: {e}")
            self.sound_enabled = False

        self.splash_progress = 0
        self.splash_next_tick_at = 0.0
        self.splash_image = None
        try:
            img = pygame.image.load(SPLASH_IMAGE_PATH)
            self.splash_image = pygame.transform.smoothscale(img.convert_alpha(), (RENDER_W, RENDER_H))
        except (pygame.error, FileNotFoundError) as e:
            print(f"[заставка] не удалось загрузить {SPLASH_IMAGE_PATH}: {e}")

        self._enter_splash()

        # Системный логгер
        self.system_logger = SystemLogger(SYSTEM_DIR)

        # Создаём системную папку и её структуру
        self._initialize_system_folder()

        # Карта
        self.map_image = None
        self.map_bounds = None
        self.map_view_lat = TERMINAL_LAT
        self.map_view_lon = TERMINAL_LON
        self.map_zoom = MAP_ZOOM_LEVEL
        self.map_markers = MapMarkersManager(MAP_MARKERS_DIR)
        self.map_selected_marker = None
        self.map_route_target = None
        self.map_marker_input = ""
        self.map_state = "VIEW"

        # Загружаем карту
        self._load_map_image()
        self._load_map_bounds()

    # -------------------------------------------------------------- звук
    def _play(self, name):
        if not self.sound_enabled:
            return
        snd = self.sounds.get(name)
        if snd is None:
            return
        try:
            snd.play()
        except pygame.error:
            pass

    def _sync_typing_loop(self, is_typing):
        """Крутит клик-луп ('clicking'), пока идёт анимация печати текста,
        и останавливает его, как только текст полностью показан."""
        if not self.sound_enabled or self.typing_channel is None:
            return
        snd = self.sounds.get("clicking")
        if snd is None:
            return
        if is_typing and not self._typing_loop_active:
            try:
                self.typing_channel.play(snd, loops=-1)
                self._typing_loop_active = True
            except pygame.error:
                pass
        elif not is_typing and self._typing_loop_active:
            try:
                self.typing_channel.stop()
            except pygame.error:
                pass
            self._typing_loop_active = False
    # ------------------------------------------------------------- заставка
    def _enter_splash(self):
        self.state = self.STATE_SPLASH
        self.fixed_header = False
        self.splash_progress = 0
        self.splash_next_tick_at = time.time() + random.uniform(SPLASH_TICK_MIN, SPLASH_TICK_MAX)

        if self.sound_enabled:
            try:
                pygame.mixer.music.load(SPLASH_MUSIC_PATH)
                pygame.mixer.music.play(loops=-1)
            except (pygame.error, FileNotFoundError) as e:
                print(f"[заставка] не удалось загрузить музыку {SPLASH_MUSIC_PATH}: {e}")

    def _update_splash(self):
        if self.splash_progress >= 100:
            return
        now = time.time()
        if now < self.splash_next_tick_at:
            return
        self.splash_progress += 1
        if self.splash_progress >= 100:
            self.splash_progress = 100
            self._schedule(SPLASH_HOLD_AT_100, self._leave_splash)
            return
        if random.random() < SPLASH_STALL_CHANCE:
            delay = random.uniform(SPLASH_STALL_MIN, SPLASH_STALL_MAX)
        else:
            delay = random.uniform(SPLASH_TICK_MIN, SPLASH_TICK_MAX)
        self.splash_next_tick_at = now + delay

    def _leave_splash(self):
        if self.sound_enabled:
            try:
                pygame.mixer.music.fadeout(400)
            except pygame.error:
                pass
        self._boot()

    def _skip_splash(self):
        if self.state != self.STATE_SPLASH:
            return
        self._leave_splash()

    def _initialize_system_folder(self):
        """Создаёт системную папку и её структуру согласно конфигурации."""
        if not ENABLE_SYSTEM:
            return
    
        # Создаём основную папку
        os.makedirs(SYSTEM_DIR, exist_ok=True)
    
        # Создаём файл "Сведения о системе.md"
        system_info_path = os.path.join(SYSTEM_DIR, "Сведения о системе.md")
        if not os.path.exists(system_info_path):
            with open(system_info_path, "w", encoding="utf-8") as f:
                f.write("""# СВЕДЕНИЯ О СИСТЕМЕ

## Терминальная система ROBCO Industries (TM)

**Версия ОС:** ROBCO OS v2.3.1 (2077)
**Кодовое имя:** "Vault-Tec Secure"
**Архитектура:** RobCo TERMLINK v4

---

### Аппаратное обеспечение

**Процессор:** RobCo R-32 (32-бит, 16 МГц)
**Память:** 64 КБ ОЗУ (расширяемая до 256 КБ)
**Хранилище:** Голографический накопитель (1 ТБ)
**Дисплей:** Монохромный TFT, 960x600

---

### Системные модули

| Модуль                 | Статус  | Версия |
|------------------------|---------|--------|
| Ядро ОС                | АКТИВЕН | 2.3.1  |
| Сеть терминалов        | АКТИВНА | 1.4.0  |
| Протоколы безопасности | АКТИВНЫ | 3.0.0  |
| Интерфейс голодисков   | АКТИВЕН | 2.1.0  |

---

### Служебная информация
Хэш-сумма ядра: 0x7F3A9B1C
Контрольная сумма: 0xDEADBEEF
Время работы: непрерывно с 2075 года
""")
    
        # Создаём папку actions
        actions_dir = os.path.join(SYSTEM_DIR, "actions")
        os.makedirs(actions_dir, exist_ok=True)
    
        # Создаём папку profiles
        profiles_dir = os.path.join(SYSTEM_DIR, "profiles")
        os.makedirs(profiles_dir, exist_ok=True)
    
        # Создаём профили пользователей
        for account in USER_ACCOUNTS:
            profile_path = os.path.join(profiles_dir, f"{account['id']}.md")
            if not os.path.exists(profile_path):
                with open(profile_path, "w", encoding="utf-8") as f:
                    f.write(f"""# ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ

## {account['name']}

**ID:** {account['id']}
**Уровень доступа:** {account['level']}
**Статус:** АКТИВЕН

---

### Права доступа

{f'''
- Полный доступ ко всем системам
- Управление пользователями
- Доступ к логам всех пользователей
''' if account['level'] == 'owner' else f'''
- Стандартный доступ к системе
- Доступ к собственному журналу
- Чтение голодисков
''' if account['level'] == 'user' else f'''
- Административный доступ
- Управление дверьми
- Доступ к системным файлам
'''}

---

### Хэш-ключ
{''.join(random.choices('0123456789ABCDEF', k=32))}

""")
    
        # Создаём системные файлы для каждого компонента
        components = []
        if ENABLE_DOOR_CONTROL:
            components.append(("door_control", "Управление дверьми"))
        if ENABLE_CHAT:
            components.append(("chat", "Чат со S.C.O.P.E."))
        if ENABLE_DISK_READER:
            components.append(("disk_reader", "Чтение голодисков"))
        if ENABLE_SYSTEM:
            components.append(("system", "Система"))
    
        for comp_id, comp_name in components:
            comp_dir = os.path.join(SYSTEM_DIR, comp_id)
            os.makedirs(comp_dir, exist_ok=True)
        
            # Создаём файл конфигурации компонента
            config_path = os.path.join(comp_dir, "config.md")
            if not os.path.exists(config_path):
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(f"""# СИСТЕМНЫЙ ФАЙЛ КОМПОНЕНТА

## {comp_name}

**Идентификатор:** {comp_id}
**Версия:** 1.0.{random.randint(0, 9)}
**Статус:** ЗАГРУЖЕН

---

### Параметры

```ini
[component]
id = {comp_id}
name = {comp_name}
enabled = true
version = 1.0.{random.randint(0, 9)}
priority = {random.randint(1, 10)}
```

### Библиотеки зависимостей

lib_{comp_id}.so (v{random.randint(1, 3)}.{random.randint(0, 9)})
lib_robco_core.so (v2.3.1)
lib_vault_network.so (v1.4.0)

### Журнал загрузки

[SYSTEM] Загрузка компонента {comp_id}...
[SYSTEM] Проверка целостности...
[SYSTEM] OK
[SYSTEM] Загрузка зависимостей...
[SYSTEM] OK
[SYSTEM] Компонент {comp_name} загружен.

""")

        #Удаляем лишние папки компонентов
        existing_comps = set()
        for item in os.listdir(SYSTEM_DIR):
            item_path = os.path.join(SYSTEM_DIR, item)
            if os.path.isdir(item_path):
                existing_comps.add(item)
        
        #Удаляем лишние папки (кроме actions, profiles и известных компонентов)
        known_folders = {"actions", "profiles"}
        for comp_id, _ in components:
            known_folders.add(comp_id)

        for folder in existing_comps:
            if folder not in known_folders:
                try:
                    shutil.rmtree(os.path.join(SYSTEM_DIR, folder))
                except OSError:
                    pass

    def _load_map_image(self):
        """Загружает изображение карты"""
        map_path = os.path.join("images", "map.png")
        try:
            img = pygame.image.load(map_path)
            self.map_image = pygame.transform.smoothscale(img, (RENDER_W, RENDER_H))
        except (pygame.error, FileNotFoundError):
            print(f"[карта] не удалось загрузить {map_path}")
            self.map_image = None
    
    def _load_map_bounds(self):
        """Загружает привязку карты из JSON файла"""
        try:
            with open(MAP_BOUNDS_PATH, 'r', encoding='utf-8') as f:
                self.map_bounds = json.load(f)
            print(f"[карта] загружена привязка: {self.map_bounds}")
        
            # Устанавливаем зум на основе границ карты
            if self.map_bounds:
                lat_range = self.map_bounds["max_lat"] - self.map_bounds["min_lat"]
                lon_range = self.map_bounds["max_lon"] - self.map_bounds["min_lon"]
                self.map_zoom = max(lat_range, lon_range) / 2
                print(f"[карта] установлен зум: {self.map_zoom:.6f}")
            
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[карта] не удалось загрузить привязку {MAP_BOUNDS_PATH}: {e}")
            self.map_bounds = None
    
    def _get_effective_bounds(self):
        """Текущее окно камеры (позиция + зум), обрезанное по границам загруженной карты."""
        half = self.map_zoom
        lat_min = self.map_view_lat - half
        lat_max = self.map_view_lat + half
        lon_min = self.map_view_lon - half
        lon_max = self.map_view_lon + half
        if self.map_bounds:
            lat_min = max(lat_min, self.map_bounds["min_lat"])
            lat_max = min(lat_max, self.map_bounds["max_lat"])
            lon_min = max(lon_min, self.map_bounds["min_lon"])
            lon_max = min(lon_max, self.map_bounds["max_lon"])
            if lat_min >= lat_max:
                lat_min, lat_max = self.map_bounds["min_lat"], self.map_bounds["max_lat"]
            if lon_min >= lon_max:
                lon_min, lon_max = self.map_bounds["min_lon"], self.map_bounds["max_lon"]
        return lat_min, lat_max, lon_min, lon_max

    def _clamp_map_view(self):
        """Не даёт камере полностью уйти за пределы загруженной карты."""
        if not self.map_bounds:
            return
        self.map_view_lat = min(max(self.map_view_lat, self.map_bounds["min_lat"]), self.map_bounds["max_lat"])
        self.map_view_lon = min(max(self.map_view_lon, self.map_bounds["min_lon"]), self.map_bounds["max_lon"])

    def _map_image_subsurface_for_view(self, lat_min, lat_max, lon_min, lon_max):
        """Вырезает и масштабирует нужный фрагмент карты под текущее окно камеры."""
        if not self.map_image:
            return None
        if not self.map_bounds:
            return self.map_image

        img_w, img_h = self.map_image.get_size()
        b_lat_min, b_lat_max = self.map_bounds["min_lat"], self.map_bounds["max_lat"]
        b_lon_min, b_lon_max = self.map_bounds["min_lon"], self.map_bounds["max_lon"]

        x1 = (lon_min - b_lon_min) / (b_lon_max - b_lon_min) * img_w
        x2 = (lon_max - b_lon_min) / (b_lon_max - b_lon_min) * img_w
        y1 = (b_lat_max - lat_max) / (b_lat_max - b_lat_min) * img_h
        y2 = (b_lat_max - lat_min) / (b_lat_max - b_lat_min) * img_h

        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2 = min(img_w, max(x1 + 1, int(x2)))
        y2 = min(img_h, max(y1 + 1, int(y2)))

        try:
            crop = self.map_image.subsurface((x1, y1, x2 - x1, y2 - y1))
            return pygame.transform.smoothscale(crop.copy(), (RENDER_W, RENDER_H))
        except ValueError:
            return self.map_image
    
    def _world_to_screen(self, lat, lon):
        lat_min, lat_max, lon_min, lon_max = self._get_effective_bounds()
        if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
            return None, None
        margin = 20
        screen_w = RENDER_W - margin * 2
        screen_h = RENDER_H - margin * 2
        x = margin + ((lon - lon_min) / (lon_max - lon_min)) * screen_w
        y = margin + ((lat_max - lat) / (lat_max - lat_min)) * screen_h
        return int(x), int(y)

    def _screen_to_world(self, screen_x, screen_y):
        lat_min, lat_max, lon_min, lon_max = self._get_effective_bounds()
        margin = 20
        screen_w = RENDER_W - margin * 2
        screen_h = RENDER_H - margin * 2
        lat = lat_max - ((screen_y - margin) / screen_h) * (lat_max - lat_min)
        lon = lon_min + ((screen_x - margin) / screen_w) * (lon_max - lon_min)
        return lat, lon

    def _enter_map(self):
        """Вход в раздел Карта"""
        if not self._can_access_item("map"):
            self._deny_access()
            return
    
        self.state = self.STATE_MAP
        self.fixed_header = False
        self.map_state = "VIEW"
        self.map_selected_marker = None
        self.map_route_target = None
        self.map_marker_input = ""
        self.output.clear()
        self.output.push("=== КАРТА ОКРЕСТНОСТЕЙ ===\n")
        self.output.push("Управление:\n")
        self.output.push("[←→↑↓] - перемещение [+/-] - масштаб [Enter] - отметка\n")
        self.output.push("[R] - маршрут [Esc] - выход\n")

    def _render_map(self, surf):
        lat_min, lat_max, lon_min, lon_max = self._get_effective_bounds()

        view_surf = self._map_image_subsurface_for_view(lat_min, lat_max, lon_min, lon_max)
        if view_surf:
            surf.blit(view_surf, (0, 0))
        else:
            surf.fill((10, 20, 10))
            text = self.font.render("Карта не загружена", True, COLOR_TEXT)
            surf.blit(text, (RENDER_W//2 - text.get_width()//2, RENDER_H//2))

        visible_markers = self.map_markers.get_markers_in_view(lat_min, lat_max, lon_min, lon_max)
    
        for marker in visible_markers:
            x, y = self._world_to_screen(marker.lat, marker.lon)
            if x is None:
                continue
        
            # Рисуем кружок (amber)
            radius = 6
            pygame.draw.circle(surf, (255, 200, 50, 180), (x, y), radius)
            pygame.draw.circle(surf, (255, 200, 50), (x, y), radius, 1)
        
            # Подпись
            label = marker.text[:20]
            label_surf = self.font.render(label, True, (255, 200, 50))
            surf.blit(label_surf, (x + radius + 4, y - label_surf.get_height()//2))
    
        # Рисуем маршрут
        if self.map_route_target:
            tx, ty = self._world_to_screen(self.map_route_target.lat, self.map_route_target.lon)
            if tx is not None:
                # Пунктирная линия от центра
                cx, cy = self._world_to_screen(self.map_view_lat, self.map_view_lon)
                if cx is not None:
                    self._draw_dashed_line(surf, (cx, cy), (tx, ty), (255, 50, 50))
    
        # Рисуем позицию терминала (красная стрелка)
        tx, ty = self._world_to_screen(TERMINAL_LAT, TERMINAL_LON)
        if tx is not None:
            self._draw_terminal_marker(surf, tx, ty)
    
        # Отображаем подсказки
        y = RENDER_H - 30
        hint = f"Позиция: {self.map_view_lat:.4f}, {self.map_view_lon:.4f} | Зум: {self.map_zoom:.3f}"
        hint_surf = self.font.render(hint, True, COLOR_DIM)
        surf.blit(hint_surf, (10, y))
    
        # Отображаем информацию о выбранной отметке
        if self.map_selected_marker:
            info = f"Выбрано: {self.map_selected_marker.text}"
            info_surf = self.font.render(info, True, COLOR_HIGHLIGHT)
            surf.blit(info_surf, (RENDER_W - info_surf.get_width() - 10, y))
    
        # Если вводим текст отметки
        if self.map_state == "ADD_MARKER_TEXT":
            self._render_marker_input(surf)

    def _draw_dashed_line(self, surf, start, end, color, dash_length=10, gap_length=10):
        """Рисует пунктирную линию"""
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = (dx**2 + dy**2) ** 0.5
        if length == 0:
            return
    
        steps = int(length / (dash_length + gap_length))
        for i in range(steps):
            t1 = i / steps
            t2 = (i + 0.5) / steps
            x1 = int(start[0] + dx * t1)
            y1 = int(start[1] + dy * t1)
            x2 = int(start[0] + dx * t2)
            y2 = int(start[1] + dy * t2)
            pygame.draw.line(surf, color, (x1, y1), (x2, y2), 2)

    def _draw_terminal_marker(self, surf, x, y):
        """Рисует маркер позиции терминала (красная стрелка)"""
        size = 12
        points = [
            (x, y - size),
            (x - size//2, y + size//2),
            (x, y + size//4),
            (x + size//2, y + size//2),
        ]
        pygame.draw.polygon(surf, (255, 50, 50), points)
        pygame.draw.polygon(surf, (255, 100, 100), points, 1)

    def _render_marker_input(self, surf):
        """Рендерит ввод текста отметки"""
        # Полупрозрачный фон
        overlay = pygame.Surface((RENDER_W, RENDER_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surf.blit(overlay, (0, 0))
    
        # Поле ввода
        box_x = RENDER_W//2 - 200
        box_y = RENDER_H//2 - 80
        box_w = 400
        box_h = 160
    
        pygame.draw.rect(surf, (69, 255, 90), (box_x, box_y, box_w, box_h), 2)
        pygame.draw.rect(surf, (4, 10, 4), (box_x+2, box_y+2, box_w-4, box_h-4))
    
        # Заголовок
        title = self.font.render("ВВЕДИТЕ ТЕКСТ ОТМЕТКИ", True, COLOR_TEXT)
        surf.blit(title, (RENDER_W//2 - title.get_width()//2, box_y + 10))
    
        # Текст ввода
        cursor = "_" if self.cursor_visible else " "
        input_text = self.map_marker_input + cursor
        input_surf = self.font.render(input_text[:40], True, COLOR_TEXT)
        surf.blit(input_surf, (box_x + 20, box_y + 50))
    
        # Подсказка
        hint = self.font.render("Enter - подтвердить | Esc - отмена", True, COLOR_DIM)
        surf.blit(hint, (RENDER_W//2 - hint.get_width()//2, box_y + 100))

    # ---------------------------------------------------------------- boot
    def _boot(self):
        self.fixed_header = True
        self.output.push(
            "Добро пожаловать в терминальную сеть ROBCO Industries (TM)\n"
            "-------------------------------\n"
            "[Инициализация...             ]\n"
            "[Загрузка системы...          ]\n"
            "[Запуск протоколов...         ]\n"
            "[Подключение к базам данных...]\n"
            "ПОДКЛЮЧЕНО\n"
        )
        if DEVMODE:
            # В режиме разработки пропускаем выбор пользователя и пароль —
            # авторизуемся первым аккаунтом из списка, чтобы был полный
            # доступ ко всем пунктам меню при тестировании.
            self.pending_user = USER_ACCOUNTS[0]
            self._apply_authenticated_user(self.pending_user)
            self._enter_main_menu()
        else:
            self._enter_user_select()

    def _ensure_user_journal_dirs(self):
        """Создаёт папку журнала для каждого известного пользователя, чтобы
        листинг и сохранение записей не спотыкались об отсутствующие папки."""
        for account in USER_ACCOUNTS:
            path = os.path.join(JOURNAL_DIR, account["id"])
            try:
                os.makedirs(path, exist_ok=True)
            except OSError:
                pass

    def _apply_authenticated_user(self, account):
        self.current_user = account["name"]
        self.current_user_id = account["id"]
        self.current_user_level = account["level"]

    def _can_access_item(self, item_key):
        """Проверка доступа к пункту меню, формируемому самим main.py (не
        папками data/ и journal/, и не чтением голодисков — те доступны
        всем уровням доступа без исключений)."""
        if self.current_user_level == "owner":
            return True
        min_level = MENU_ITEM_MIN_LEVEL.get(item_key, "user")
        if self.current_user_level is not None and ACCESS_LEVEL_RANK.get(self.current_user_level, -1) \
                >= ACCESS_LEVEL_RANK.get(min_level, 0):
            return True
        if self.current_user_id in MENU_ITEM_EXTRA_USER_IDS.get(item_key, []):
            return True
        return False

    def _deny_access(self):
        self._play("error")
        self.output.push(f"\n{ACCESS_DENIED_MESSAGE}\n")

    def _enter_user_select(self):
        self.state = self.STATE_USER_SELECT
        self.fixed_header = True
        self.pending_user = None
        self.output.clear()
        items = [(str(i), acc["name"]) for i, acc in enumerate(USER_ACCOUNTS, 1)]
        text = "ВЫБЕРИТЕ ПОЛЬЗОВАТЕЛЯ\n\n" + self._format_menu_lines(items) + "\n"
        self.output.push(text)

    def _enter_password(self, extra_message=None):
        self.state = self.STATE_PASSWORD
        self.fixed_header = True
        attempts_left = MAX_PASSWORD_ATTEMPTS - self.password_attempts_used
        user_name = self.pending_user["name"] if self.pending_user else ""
        if extra_message:
            text = f"{extra_message}\n"
        else:
            text = f"ПОЛЬЗОВАТЕЛЬ: {user_name}\nВВЕДИТЕ ПАРОЛЬ\n"
        text += f"ПОПЫТОК ОСТАЛОСЬ: " + "■ " * attempts_left + "\nВведите пароль:\n"
        self.output.push(text)
        self.system_logger.start_session(self.current_user, self.current_user_id)

    # ------------------------------------------------------ флешки (общее)
    def _poll_removable_drives(self):
        """Чисто техническое обнаружение новых смонтированных дисков — не
        привязано к экрану пароля и ничего не знает про маркеры/модули.
        Возвращает список путей монтирования, появившихся с прошлого опроса
        (пустой список, если опрос ещё не пора делать или ничего нового)."""
        if not PSUTIL_AVAILABLE:
            return []
        now = time.time()
        if now - self._last_drive_poll_at < DRIVE_POLL_INTERVAL:
            return []
        self._last_drive_poll_at = now
        try:
            current_mounts = {p.mountpoint for p in psutil.disk_partitions(all=False)}
        except Exception:
            return []
        new_mounts = current_mounts - self._known_mount_points
        self._known_mount_points = current_mounts
        return sorted(new_mounts)

    # ------------------------------------------------------- модуль взлома
    def _check_hack_module_on_drives(self, new_mounts):
        """Реагирует на новые диски, только если терминал сейчас на экране
        пароля. Само приложение не предлагает этот путь пользователю — оно
        лишь честно замечает физическое вторжение постороннего устройства."""
        if not ENABLE_HACK_MODULE_DETECTION or self.state != self.STATE_PASSWORD:
            return
        for mount in new_mounts:
            marker_path = os.path.join(mount, HACK_MODULE_MARKER_FILENAME)
            if os.path.isfile(marker_path):
                self.output.push("Запускаю режим взлома пароля с внешнего носителя...\n", instant=True)
                self._schedule(LOCKOUT_DELAY_SECONDS, self._launch_hack_module)
                return

    # ------------------------------------------------- чтение голодисков
    def _check_disk_reader_autoopen(self, new_mounts):
        """Если игрок стоит в главном меню (ничем конкретным не занят) и
        вставляет голодиск — сразу открываем интерфейс чтения-записи, без
        похода в подменю. Из любого другого состояния — только вручную,
        через пункт меню, чтобы не выдёргивать игрока посреди дела."""
        if not (ENABLE_DISK_READER and new_mounts):
            return
        if self.state != self.STATE_MAIN_MENU:
            return
        self._enter_disk_reader()

    def _pick_holotape_mount(self):
        """Находит ТЕКУЩИЙ голодиск."""
        if not PSUTIL_AVAILABLE:
            return None
    
        try:
            partitions = psutil.disk_partitions(all=False)
        
            for p in partitions:
                # Пропускаем системные диски
                if p.mountpoint in ('/', '/boot', '/System/Volumes/Data'):
                    continue
            
                # Проверяем по признаку съёмности (работает на всех ОС)
                if 'removable' in p.opts:
                    return p.mountpoint
            
                # macOS: внешние диски в /Volumes/
                if sys.platform == 'darwin' and p.mountpoint.startswith('/Volumes/'):
                    if p.mountpoint != '/Volumes' and not p.mountpoint.startswith(('/System/', '/private/')):
                        return p.mountpoint
            
                # Linux: диски в /media/ или /mnt/
                if sys.platform == 'linux' and p.mountpoint.startswith(('/media/', '/mnt/')):
                    return p.mountpoint
            
                # Windows: любой диск кроме C:
                if sys.platform == 'win32':
                    if p.mountpoint and not p.mountpoint.upper().startswith('C:'):
                        return p.mountpoint
        
        except Exception as e:
            print(f"[ошибка] при определении диска: {e}")
    
        return None

    def _poll_disk_reader_mount(self):
        now = time.time()
        if now - self._last_disk_reader_check_at < DRIVE_POLL_INTERVAL:
            return
        self._last_disk_reader_check_at = now
        mount = self._pick_holotape_mount()
        if mount != self.disk_reader_mount:
            self.disk_reader_mount = mount
            self.disk_reader_cursor["holotape"] = 0
            self._disk_reader_rebuild("holotape")

    def _enter_disk_reader(self):
        self.state = self.STATE_DISK_READER
        self.fixed_header = False
        self.disk_reader_focus = "terminal"
        self.disk_reader_cursor = {"terminal": 0, "holotape": 0}
        self.disk_reader_status = ""
        self.disk_reader_mount = self._pick_holotape_mount()
        self._last_disk_reader_check_at = time.time()
        self._disk_reader_rebuild("terminal")
        self._disk_reader_rebuild("holotape")

    def _walk_dir_rows(self, root, depth, visited=None, max_depth=3):
        """Рекурсивно строит строки дерева для одной директории.
        Ограничиваем глубину обхода для предотвращения зависаний.
        Фильтруем скрытые и системные файлы/папки."""
        if visited is None:
            visited = set()
    
        # Жёсткое ограничение глубины
        if depth > max_depth:
            return []
    
        # Получаем реальный путь
        try:
            real_path = os.path.realpath(root)
        except OSError:
            return []
    
        # Если уже посещали этот путь — выходим
        if real_path in visited:
            return []
        visited.add(real_path)
    
        rows = []
        try:
            with os.scandir(root) as it:
                entries = sorted(it, key=lambda e: e.name)
        except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
            return rows
    
        dirs = []
        files = []
        for entry in entries:
            try:
                name = entry.name
            
                # Фильтрация скрытых и системных файлов/папок
                if self._is_hidden_or_system(name):
                    continue
            
                # Проверяем, не симлинк ли это на родительский путь
                try:
                    real_sub = os.path.realpath(entry.path)
                    if real_sub in visited:
                        continue
                except OSError:
                    continue
            
                if entry.is_dir(follow_symlinks=False):
                    # Проверяем, что это действительно директория
                    try:
                        if os.path.isdir(entry.path):
                            dirs.append(entry.name)
                    except OSError:
                        continue
                else:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            files.append(entry.name)
                    except OSError:
                        continue
            except OSError:
                continue
    
        indent = "  " * depth
        for d in dirs[:100]:  # Ограничиваем количество папок на уровне
            rows.append({"text": f"{indent}{d}/", "selectable": False, "abs": None, "rel": None})
            sub_root = os.path.join(root, d)
            for row in self._walk_dir_rows(sub_root, depth + 1, visited, max_depth):
                if row["rel"] is not None:
                    row["rel"] = os.path.join(d, row["rel"])
                rows.append(row)
    
        for f in files[:500]:  # Ограничиваем количество файлов
            rows.append({
                "text": f"{indent}{f}",
                "selectable": True,
                "abs": os.path.join(root, f),
                "rel": f,
            })
        return rows

    def _build_terminal_tree_rows(self):
        """Строит дерево терминала для интерфейса чтения голодисков — но
        только из тех разделов и папок, к которым у текущего пользователя
        есть доступ. Журнал показывает только собственную папку (кроме
        owner, которому доступны все — с именами пользователей вместо
        технических ID папок), а История чатов не показывается вовсе,
        если у пользователя нет доступа к разделу «Чат со S.C.O.P.E.»
        (см. _can_access_item). Так голодиск не превращается в обходной
        путь к данным, закрытым в обычном меню."""
        rows = []

        rows.append({"text": "Журнал/", "selectable": False, "abs": None, "rel": None})
        if self.current_user_level == "owner":
            # Отдельная папка на каждого пользователя, подписанная именем,
            # а не техническим ID (bill_wasson, lucy_maclean, ...).
            for acc in USER_ACCOUNTS:
                rows.append({"text": f"  {acc['name']}/", "selectable": False, "abs": None, "rel": None})
                sub_root = os.path.join(JOURNAL_DIR, acc["id"])
                for row in self._walk_dir_rows(sub_root, 2, set()):
                    if row["rel"] is not None:
                        row["rel"] = os.path.join("Журнал", acc["id"], row["rel"])
                    rows.append(row)
        elif self.current_user_id:
            own_root = os.path.join(JOURNAL_DIR, self.current_user_id)
            for row in self._walk_dir_rows(own_root, 1, set()):
                if row["rel"] is not None:
                    row["rel"] = os.path.join("Журнал", row["rel"])
                rows.append(row)

        sections = [("Данные", DATA_DIR)]
        if self._can_access_item("chat"):
            sections.append(("История чатов", CHAT_HISTORY_DIR))

        for label, root in sections:
            rows.append({"text": f"{label}/", "selectable": False, "abs": None, "rel": None})
            for row in self._walk_dir_rows(root, 1, set()):
                if row["rel"] is not None:
                    row["rel"] = os.path.join(label, row["rel"])
                rows.append(row)

        if self._can_access_item("map"):
            rows.append({"text": "Отметки карты/", "selectable": False, "abs": None, "rel": None})
            if os.path.exists(MAP_MARKERS_DIR):
                # Сортируем отметки по имени
                markers = sorted(self.map_markers.markers, key=lambda m: m.text)
                for marker in markers:
                    rows.append({
                        "text": f"  {marker.text[:30]}",
                        "selectable": True,
                        "abs": os.path.join(MAP_MARKERS_DIR, f"{marker.id}.md"),
                        "rel": os.path.join("Отметки карты", f"{marker.id}.md")
                    })

        if self._can_access_item("system"):
            # Как и для Журнала владельца, реальные имена подпапок (id
            # компонентов, "actions", "profiles") заменяются на подписи,
            # под которыми они показаны в системном меню — маска влияет
            # только на отображаемый текст, а не на rel/abs.
            rows.append({"text": "Система/", "selectable": False, "abs": None, "rel": None})
            try:
                sub_entries = sorted(
                    e.name for e in os.scandir(SYSTEM_DIR)
                    if not self._is_hidden_or_system(e.name)
                )
            except (FileNotFoundError, OSError):
                sub_entries = []
            for name in sub_entries:
                full_path = os.path.join(SYSTEM_DIR, name)
                if os.path.isdir(full_path):
                    display_name = SYSTEM_SUBFOLDER_LABELS.get(name, name)
                    rows.append({"text": f"  {display_name}/", "selectable": False, "abs": None, "rel": None})
                    for row in self._walk_dir_rows(full_path, 2, set()):
                        if row["rel"] is not None:
                            row["rel"] = os.path.join("Система", name, row["rel"])
                        rows.append(row)
                else:
                    rows.append({
                        "text": f"  {name}",
                        "selectable": True,
                        "abs": full_path,
                        "rel": os.path.join("Система", name),
                    })
        return rows

    def _build_holotape_tree_rows(self):
        if not self.disk_reader_mount or not os.path.isdir(self.disk_reader_mount):
            return []
        return self._walk_dir_rows(self.disk_reader_mount, 0, set())

    def _disk_reader_rebuild(self, side):
        if side == "terminal":
            self.disk_reader_rows["terminal"] = self._build_terminal_tree_rows()
        else:
            self.disk_reader_rows["holotape"] = self._build_holotape_tree_rows()
        selectable_count = len(self._disk_reader_selectable(side))
        if selectable_count == 0:
            self.disk_reader_cursor[side] = 0
        else:
            self.disk_reader_cursor[side] = min(self.disk_reader_cursor[side], selectable_count - 1)

    def _disk_reader_selectable(self, side):
        return [r for r in self.disk_reader_rows[side] if r["selectable"]]

    def _disk_reader_move_cursor(self, delta):
        side = self.disk_reader_focus
        count = len(self._disk_reader_selectable(side))
        if count == 0:
            return
        self.disk_reader_cursor[side] = max(0, min(count - 1, self.disk_reader_cursor[side] + delta))

    def _disk_reader_switch_focus(self):
        self.disk_reader_focus = "holotape" if self.disk_reader_focus == "terminal" else "terminal"

    def _disk_reader_copy_selected(self):
        src_side = self.disk_reader_focus
        dst_side = "holotape" if src_side == "terminal" else "terminal"
        selectable = self._disk_reader_selectable(src_side)
        idx = self.disk_reader_cursor[src_side]
        if not selectable or not (0 <= idx < len(selectable)):
            self.disk_reader_status = "Нечего копировать — выберите файл."
            self._play("error")
            return

        row = selectable[idx]
        src_path = row["abs"]

        if src_side == "terminal":
            if not self.disk_reader_mount:
                self.disk_reader_status = "Голодиск не подключён."
                self._play("error")
                return
            dst_path = os.path.join(self.disk_reader_mount, row["rel"])
        else:
            rel = row["rel"]
            parts = rel.split(os.sep)
            top = parts[0]
            rest_parts = parts[1:]
            if top == "История чатов" and not self._can_access_item("chat"):
                # Голодиск может называть свои папки как угодно — имя само
                # по себе не даёт права записи в закрытый раздел.
                self.disk_reader_status = "Недостаточно прав для этого раздела."
                self._play("error")
                return
            if top == "Отметки карты":
                # Копируем отметку с голодиска на терминал
                if self.map_markers.copy_from_holotape(src_path):
                    self.disk_reader_status = "Отметка скопирована на терминал"
                    self._play("complete")
                    self._disk_reader_rebuild("terminal")
                    return
                else:
                    self.disk_reader_status = "Отметка уже существует или ошибка"
                    self._play("error")
                    return
            if top == "Журнал":
                # Импорт всегда идёт в собственный журнал текущего
                # пользователя — доступа на запись в чужие папки журнала
                # с голодиска нет ни у кого, кроме как в свою же. Любые
                # промежуточные сегменты пути (ID/имя пользователя из
                # дерева owner'а) отбрасываем, берём только имя файла.
                dst_root = os.path.join(JOURNAL_DIR, self.current_user_id) if self.current_user_id else JOURNAL_DIR
                rest_parts = [os.path.basename(rel)]
            elif top == "История чатов":
                dst_root = CHAT_HISTORY_DIR
            elif top == "Данные":
                dst_root = DATA_DIR
            else:
                # Неизвестная структура на голодиске — кладём как есть внутрь
                # data/, верхняя папка голодиска станет новой категорией меню.
                dst_root = DATA_DIR
                rest_parts = parts
            dst_rel = os.path.join(*rest_parts) if rest_parts else os.path.basename(rel)
            dst_path = os.path.join(dst_root, dst_rel)

        try:
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(src_path, dst_path)
        except OSError as e:
            self.disk_reader_status = f"Ошибка копирования: {e}"
            self._play("error")
            return

        self._play("complete")
        self.disk_reader_status = f"Скопировано: {os.path.basename(src_path)}"
        self._disk_reader_rebuild(dst_side)

    def _render_disk_reader(self, surf):
        line_h = self.font.get_linesize() + LINE_SPACING
        col_width = (RENDER_W - MARGIN * 2 - DISK_READER_COL_GAP) // 2
        left_x = MARGIN
        right_x = MARGIN + col_width + DISK_READER_COL_GAP

        title = "ИНТЕРФЕЙС ПЕРЕДАЧИ ДАННЫХ"
        title_surf = self.font.render(title, True, COLOR_TEXT)
        surf.blit(title_surf, (MARGIN, MARGIN))

        header_y = MARGIN + line_h * 2
        left_label = "► ТЕРМИНАЛ" if self.disk_reader_focus == "terminal" else "  Терминал"
        right_label = "► ГОЛОДИСК" if self.disk_reader_focus == "holotape" else "  Голодиск"
        surf.blit(self.font.render(left_label, True, COLOR_TEXT), (left_x, header_y))
        surf.blit(self.font.render(right_label, True, COLOR_TEXT), (right_x, header_y))

        content_top = header_y + line_h * 2
        bottom_reserved = line_h * 4
        max_rows = max(1, (RENDER_H - content_top - bottom_reserved) // line_h)

        for side, x in (("terminal", left_x), ("holotape", right_x)):
            rows = self.disk_reader_rows[side]
            selectable = self._disk_reader_selectable(side)
            cursor_idx = self.disk_reader_cursor[side]

            if side == "holotape" and not self.disk_reader_mount:
                msg = self.font.render("Ожидание подключения голодиска...", True, COLOR_TEXT)
                surf.blit(msg, (x, content_top))
                continue

            if not rows:
                msg = self.font.render("(пусто)", True, COLOR_DIM)
                surf.blit(msg, (x, content_top))
                continue

            # Индекс текущей выделенной строки в общем списке rows (с папками)
            cursor_row_index = 0
            if selectable and 0 <= cursor_idx < len(selectable):
                target = selectable[cursor_idx]
                cursor_row_index = rows.index(target)

            start = max(0, min(max(0, len(rows) - max_rows), cursor_row_index - max_rows // 2))
            visible_rows = rows[start:start + max_rows]

            y = content_top
            for row in visible_rows:
                is_cursor = (
                    row["selectable"]
                    and self.disk_reader_focus == side
                    and selectable
                    and 0 <= cursor_idx < len(selectable)
                    and selectable[cursor_idx] is row
                )
                text = ("► " if is_cursor else "  ") + row["text"]
                color = COLOR_HIGHLIGHT if is_cursor else COLOR_TEXT
                text_surf = self.font.render(text[:60], True, color)
                surf.blit(text_surf, (x, y))
                y += line_h

        footer_y = RENDER_H - bottom_reserved + line_h
        hint = "[Enter] Копировать   [←/→] Колонка   [↑/↓] Курсор   [Esc] В главное меню"
        hint_surf = self.font.render(hint, True, COLOR_TEXT)
        surf.blit(hint_surf, (MARGIN, footer_y))
        if self.disk_reader_status:
            status_surf = self.font.render(self.disk_reader_status[:90], True, COLOR_TEXT)
            surf.blit(status_surf, (MARGIN, footer_y + line_h))

    def _is_hidden_or_system(self, name):
        """Проверяет, является ли файл/папка скрытым или системным."""
        # Unix-скрытые (начинаются с .)
        if name.startswith('.'):
            return True
    
        # Системные папки и файлы (общие для всех ОС)
        system_names = {
            # Windows
            'System Volume Information',
            '$Recycle.Bin',
            'RECYCLER',
            'RECYCLED',
            'pagefile.sys',
            'hiberfil.sys',
            'swapfile.sys',
            'Thumbs.db',
            'desktop.ini',
            'Program Files',
            'Program Files (x86)',
            'ProgramData',
            'Windows',
            # macOS
            '.DS_Store',
            '.Trashes',
            '.fseventsd',
            '.Spotlight-V100',
            '.TemporaryItems',
            # Linux
            'lost+found',
        }
        if name in system_names:
            return True
    
        # Windows-скрытые системные папки (заканчиваются на $)
        if name.endswith('$'):
            return True
    
        return False

    def _launch_hack_module(self):
        """Запуск мини-игры взлома пароля."""

        # Генерируем случайный пароль из WORD_BANK
        self.hack_correct_password = random.choice(WORD_BANK)
        
        # Выбираем другие слова для отображения
        others = [w for w in WORD_BANK if w != self.hack_correct_password]
        display_passwords = random.sample(others, random.randint(5, 9)) + [self.hack_correct_password]
        random.shuffle(display_passwords)
        
        # Генерируем отображение терминала
        self.hack_display, self.hack_bonus_codes, self.hack_all_content = self._generate_hack_display(display_passwords)
        self.hack_attempts = MAX_PASSWORD_ATTEMPTS - self.password_attempts_used
        self.hack_guess_history = []
        self.hack_state = "ACTIVE"
        self.fixed_header = False
        self.hack_initial_render = True  # Флаг для первого рендера
        
        self._render_hack_screen()

    def _generate_hack_display(self, passwords):
        """Генерирует отображение терминала для мини-игры взлома."""
        display = []
        display.append("")
        display.append("ВВЕДИТЕ ПАРОЛЬ")
        display.append("")
        
        filler_words = [
            "LOADING", "NETWORK", "SYSTEMS", "UPGRADE", "PROCESS",
            "CONTROL", "REACTOR", "SCANNER", "MACHINE", "DIGITAL",
            "PROGRAM", "CHAMBER", "TESTING", "HEALTHY", "CONTACT"
        ]
        
        # Очищаем список паролей
        passwords = list(set(passwords))  # Удаляем дубликаты
        passwords = [w for w in passwords if w != ""]  # Удаляем пустые строки
        
        # Берем только слова из WORD_BANK
        correct = [w for w in passwords if w in WORD_BANK]
        
        # Выбираем до 16 слов для отображения
        used_words = random.sample(correct, min(len(correct), 16))
        
        # Добавляем filler-слова, если нужно
        word_count = min(16, len(used_words) + len(filler_words))
        if len(used_words) < word_count:
            available_fillers = [w for w in filler_words if w not in used_words]
            needed = word_count - len(used_words)
            used_words += random.sample(available_fillers, min(needed, len(available_fillers)))
        
        # Создаем контент с добавлением случайных символов
        all_content = [("word", (w + self._generate_random_chars(12 - len(w)))[:12]) for w in used_words]
        
        # Бонусные смайлы
        smileys = [":-)", ":-|", ":-0", ":-D", ":-/", "^-^", ";-)", "'0'", "0_0", ">_<", "-_-", "D_D"]
        selected_smileys = random.sample(smileys, 4)  # Выбираем 4 случайных смайла

        # Выбираем один смайл для восстановления попытки (первый из выбранных)
        restore_smiley = selected_smileys[0]
        
        # Добавляем смайлы в контент
        for smiley in selected_smileys:
            entry = smiley + self._generate_random_chars(12 - len(smiley))
            all_content.append(("smiley", entry[:12]))
        
        # Определяем активные бонусные коды (смайлы) и запоминаем, какой восстанавливает попытку
        active_bonus_inputs = []
        self.hack_restore_smiley = restore_smiley  # Сохраняем, какой смайл восстанавливает попытку
        for entry in all_content:
            if entry[0] == "smiley":
                smiley = entry[1][:3]
                if smiley in selected_smileys:
                    active_bonus_inputs.append(smiley)
        
        # Заполняем до 32 записей случайными строками
        def is_valid_random_string(s):
            return all(s[i] != s[i+1] or s[i] != s[i+2] for i in range(len(s) - 2))
        
        while len(all_content) < 32:
            s = self._generate_random_chars(12)
            while not is_valid_random_string(s):
                s = self._generate_random_chars(12)
            all_content.append(("random", s))
        
        random.shuffle(all_content)
        
        # Формируем строки отображения
        content_index = 0
        for line in range(16):
            addr1 = f"0x{0xF4F0 + line * 20:04X}"
            addr2 = f"0x{0xF4F0 + line * 20 + 14:04X}"
            content1 = all_content[content_index][1][:12]
            content_index += 1
            content2 = all_content[content_index][1][:12]
            content_index += 1
            display.append(f"{addr1} {content1.ljust(12)}  {addr2} {content2}")
        
        display.append("")
        return display, active_bonus_inputs, all_content

    def _generate_random_chars(self, length):
        """Генерирует случайные спецсимволы."""
        special_chars = "+#*$&)(=!?<>-_.,;:/"
        return ''.join(random.choice(special_chars) for _ in range(length))

    def _generate_new_bonus_string(self):
        """Генерирует новую случайную строку для замены бонусного кода."""
        special_chars = "+#*$&)(=!?<>-_.,;:/"
        while True:
            s = ''.join(random.choice(special_chars) for _ in range(12))
            if all(s[i] != s[i+1] or s[i] != s[i+2] for i in range(len(s)-2)):
                return s

    def _render_hack_screen(self):
        """Отображает экран мини-игры взлома."""
        self.state = self.STATE_HACK_MINIGAME
        
        # Строим строки для вывода
        lines_to_push = []
        
        # Копируем базовый дисплей
        for line in self.hack_display:
            lines_to_push.append(line)
        
        # Добавляем информацию о попытках в начало
        attempts_line = "ОСТАЛОСЬ ПОПЫТОК: " + "■ " * self.hack_attempts
        lines_to_push.insert(2, attempts_line)
        lines_to_push.insert(3, "")
        
        # Добавляем историю попыток в конец
        for guess, match in self.hack_guess_history[-8:]:
            lines_to_push.append("")
            lines_to_push.append("")
            lines_to_push.append(" " * 43 + f">{guess}")
            if match != "":  # Для бонусов match содержит сообщение
                lines_to_push.append(" " * 43 + f">{match}")
            else:
                lines_to_push.append(" " * 43 + f">Неверно")
        
        # Добавляем подсказку по управлению
        lines_to_push.append("")
        lines_to_push.append("Введите пароль:")
        
        # Очищаем и выводим
        self.output.clear()
        # При первом рендере используем instant=False, иначе instant=True
        self.output.push("\n".join(lines_to_push), instant=not self.hack_initial_render)
        self.hack_initial_render = False

    def _try_hack_guess(self, text):
        """Проверяет введённое слово/код."""
        if not text:
            return
        
        # Проверка на бонусный смайл
        if text in self.hack_bonus_codes:
            # Проверяем, является ли этот смайл тем, что восстанавливает попытку
            is_attempt_restore = (text == self.hack_restore_smiley)
            
            if is_attempt_restore:
                # Восстанавливаем попытку (но не выше 4)
                if self.hack_attempts < 4:
                    self.hack_attempts += 1
                self._play("complete")
                self.hack_guess_history.append((f"[БОНУС] {text}", "Попытка восстановлена"))
                # После использования смайла восстановления, больше не будет восстановлений
                self.hack_restore_smiley = ""
            else:
                # Убираем лишнее слово
                self._play("complete")
                # Находим и заменяем первое попавшееся слово на точки
                word_replaced = False
                for i in range(len(self.hack_display)):
                    if i >= 3:  # Пропускаем первые строки (заголовки)
                        parts = self.hack_display[i].split()
                        if len(parts) >= 4:
                            # Проверяем первую колонку
                            col1 = parts[1].strip()
                            if col1 and any(col1.startswith(word) for word in WORD_BANK):
                                if not col1.startswith(self.hack_correct_password):
                                    parts[1] = "............".ljust(12)
                                    self.hack_display[i] = f"{parts[0]} {parts[1]}  {parts[2]} {parts[3]}"
                                    word_replaced = True
                                    break
                            # Проверяем вторую колонку
                            col2 = parts[3].strip()
                            if col2 and any(col2.startswith(word) for word in WORD_BANK):
                                if not col2.startswith(self.hack_correct_password):
                                    parts[3] = "............".ljust(12)
                                    self.hack_display[i] = f"{parts[0]} {parts[1]}  {parts[2]} {parts[3]}"
                                    word_replaced = True
                                    break
                if word_replaced:
                    self.hack_guess_history.append((f"[БОНУС] {text}", "Убрана обманка"))
                else:
                    self.hack_guess_history.append((f"[БОНУС] {text}", "Нет слов для удаления"))
            
            # Удаляем использованный смайл из списка бонусов
            self.hack_bonus_codes.remove(text)
            self._render_hack_screen()
            return
        
        # Проверка пароля (остальной код без изменений)
        matches = calculate_positional_matches(text, self.hack_correct_password)
        self.hack_guess_history.append((text, f"{matches}/{len(self.hack_correct_password)} совпадений"))
        self.hack_attempts -= 1
        
        if text == self.hack_correct_password:
            self.hack_state = "SUCCESS"
            self._play("unlocked")
            if self.pending_user is None:
                self.pending_user = USER_ACCOUNTS[0]
            self._apply_authenticated_user(self.pending_user)
            
            self.output.clear()
            display_lines = self.hack_display[:]
            display_lines.append("".ljust(43) + f">{text}")
            display_lines.append("".ljust(43) + f">{matches}/{len(self.hack_correct_password)} совпадений")
            display_lines.append("".ljust(43) + ">Пароль принят")
            display_lines.append("")
            display_lines.append(f">Вы авторизованы как: {self.current_user}")
            
            self.output.push("\n".join(display_lines), instant=True)
            self._schedule(AUTH_SUCCESS_DELAY_SECONDS, self._enter_main_menu)
            
        elif self.hack_attempts <= 0:
            self.hack_state = "FAILED"
            self._play("error")
            
            self.output.clear()
            display_lines = self.hack_display[:]
            display_lines.append("".ljust(43) + ">Доступ запрещен")
            display_lines.append("".ljust(43) + ">ТЕРМИНАЛ ЗАБЛОКИРОВАН")
            display_lines.append("".ljust(43) + f">Правильный пароль: {self.hack_correct_password}")
            
            self.output.push("\n".join(display_lines), instant=True)
            self.state = self.STATE_CLOSING
            self._schedule(LOCKOUT_DELAY_SECONDS, self._quit)
            
        else:
            self._play("error")
            self._render_hack_screen()

    def _handle_hack_input(self, text):
        """Обрабатывает ввод в мини-игре взлома."""
        if self.hack_state == "SUCCESS" or self.hack_state == "FAILED":
            return
        
        if text:
            self._try_hack_guess(text.upper().strip())

    def _enter_main_menu(self):
        self.state = self.STATE_MAIN_MENU
        self.fixed_header = True
        self.output.clear()

        actions = [("Журнал", self._enter_log_list)]
        if ENABLE_DOOR_CONTROL:
            actions.append(("Управление дверьми", self._enter_door_control))
        if ENABLE_CHAT:
            actions.append(("Чат со S.C.O.P.E.", self._enter_chat_menu))
        if ENABLE_DISK_READER:
            actions.append(("Чтение голодисков", self._enter_disk_reader))
        if ENABLE_SYSTEM:
            actions.append(("Система", self._enter_system_menu))
        if ENABLE_MAP:
            actions.append(("Карта", self._enter_map))
        for category in self._list_data_categories():
            actions.append((category, lambda c=category: self._enter_data_category(c)))
        self.main_menu_actions = actions

        items = [(str(i), label) for i, (label, _) in enumerate(actions, 1)]
        items.append(("0", "Закрыть терминал"))
        self.output.push(self._format_menu_lines(items) + "\n")

    def _list_data_categories(self):
        try:
            entries = [
                d for d in os.listdir(DATA_DIR)
                if os.path.isdir(os.path.join(DATA_DIR, d))
            ]
            entries.sort()
        except FileNotFoundError:
            entries = []
        return entries

    def _list_data_entries(self, category):
        folder = os.path.join(DATA_DIR, category)
        try:
            entries = [f for f in os.listdir(folder) if f.lower().endswith(".md")]
            entries.sort()
        except FileNotFoundError:
            entries = []
        return entries

    def _enter_data_category(self, category):
        self.state = self.STATE_DATA_LIST
        self.fixed_header = True
        self.output.clear()
        self.current_data_category = category
        self.data_entries = self._list_data_entries(category)
        if not self.data_entries:
            items = [("0", "Назад")]
            self.output.push(
                f"\n==={category}===\n\nВ этом разделе пока нет записей.\n\n"
                + self._format_menu_lines(items) + "\n"
            )
            return
        items = [(str(i), os.path.splitext(entry)[0]) for i, entry in enumerate(self.data_entries, 1)]
        items.append(("0", "Назад"))
        text = f"\n==={category}===\n\n" + self._format_menu_lines(items) + "\n"
        self.output.push(text)

    def _open_data_entry(self, filename):
        self.state = self.STATE_DATA_VIEW
        self.fixed_header = True
        self.output.clear()
        path = os.path.join(DATA_DIR, self.current_data_category, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.output.push(f"\n[{filename}]\n\n{content}\n\n[Нажмите Enter, чтобы вернуться...]")
        except FileNotFoundError:
            self.output.push("\nФайл не найден.\n[Нажмите Enter, чтобы вернуться...]")

    def _account_name_by_id(self, user_id):
        for acc in USER_ACCOUNTS:
            if acc["id"] == user_id:
                return acc["name"]
        return user_id

    def _list_log_entries(self, user_id):
        folder = os.path.join(JOURNAL_DIR, user_id)
        try:
            entries = [f for f in os.listdir(folder) if f.lower().endswith(".md")]
            entries.sort()
        except FileNotFoundError:
            entries = []
        return entries

    def _enter_log_list(self):
        # owner видит журналы всех пользователей через промежуточный список;
        # остальные уровни доступа сразу попадают в свою собственную папку.
        if self.current_user_level == "owner":
            self._enter_log_user_list()
        else:
            self._enter_log_list_for_user(self.current_user_id)

    def _enter_log_user_list(self):
        self.state = self.STATE_LOG_USER_LIST
        self.fixed_header = True
        self.output.clear()
        items = [(str(i), acc["name"]) for i, acc in enumerate(USER_ACCOUNTS, 1)]
        items.append(("0", "В Главное Меню"))
        text = "\n===Журнал: выберите пользователя===\n\n" + self._format_menu_lines(items) + "\n"
        self.output.push(text)

    def _enter_log_list_for_user(self, user_id):
        self.state = self.STATE_LOG_LIST
        self.fixed_header = True
        self.output.clear()
        self.current_log_owner_id = user_id
        self.log_entries = self._list_log_entries(user_id)
        owner_name = self._account_name_by_id(user_id)
        if not self.log_entries:
            items = [("1", "Создать запись"), ("0", "Назад")]
            self.output.push(
                f"\n===Журнал: {owner_name}===\n\nЗаписей в журнале нет.\n\n"
                + self._format_menu_lines(items) + "\n"
            )
            return
        items = [(str(i), os.path.splitext(entry)[0]) for i, entry in enumerate(self.log_entries, 1)]
        items.append((str(len(self.log_entries) + 1), "Создать новую запись"))
        items.append(("0", "Назад"))
        text = f"\n===Журнал: {owner_name}===\n\n" + self._format_menu_lines(items) + "\n"
        self.output.push(text)

    def _log_list_back(self):
        """Куда вернуться из списка записей журнала: owner — к выбору
        пользователя, остальные уровни доступа — сразу в главное меню."""
        if self.current_user_level == "owner":
            self._enter_log_user_list()
        else:
            self._enter_main_menu()

    def _start_new_log_entry(self):
        self.state = self.STATE_LOG_NEW
        self.fixed_header = True
        self.output.clear()
        self.new_log_lines = []
        self._new_log_title = None
        self.output.push("\n=== Создать новую запись ===\nЗаголовок:")

    def _open_log_entry(self, filename):
        self.state = self.STATE_LOG_VIEW
        self.fixed_header = True
        self.output.clear()
        path = os.path.join(JOURNAL_DIR, self.current_log_owner_id, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.output.push(f"\n[{filename}]\n\n{content}\n\n[Нажмите Enter, чтобы вернуться...]")
        except FileNotFoundError:
            self.output.push("\nФайл не найден.\n[Нажмите Enter, чтобы вернуться...]")

    def _save_new_log_entry(self, title, content):
        safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).rstrip()
        if not safe_title:
            safe_title = "untitled"
        filename = f"{safe_title}.md"
        folder = os.path.join(JOURNAL_DIR, self.current_log_owner_id)
        os.makedirs(folder, exist_ok=True)
        filepath = os.path.join(folder, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            self._play("complete")
            self.output.push(f"\nЗапись сохранена как '{filename}'.")
        except OSError as e:
            self._play("error")
            self.output.push(f"\nОшибка при сохранении записи: {e}")

    def _enter_door_control(self):
        if not self._can_access_item("door_control"):
            self._deny_access()
            return
        self.state = self.STATE_DOOR
        self.fixed_header = True
        self.output.clear()
        items = [("1", "Открыть дверь"), ("2", "Закрыть дверь"), ("0", "В Главное Меню")]
        text = (
            "\n===Интерфейс контроля защищённых дверей MaxLock===\n"
            f"СТАТУС: {self.door_status}\n\n"
            + self._format_menu_lines(items) + "\n"
        )
        self.output.push(text)

    def _enter_system_menu(self):
        """Вход в системное меню."""
        if not self._can_access_item("system"):
            self._deny_access()
            return
    
        self.state = self.STATE_SYSTEM_MENU
        self.fixed_header = True
        self.output.clear()
    
        # Логируем вход в системное меню
        self.system_logger.log(self.current_user, "Вход в системное меню", is_user_input=False)
    
        items = [
            ("1", "Сведения о системе"),
            ("2", "Действия пользователей"),
            ("3", "Профили пользователей")
        ]
        next_num = 4
        components = []
        if ENABLE_DOOR_CONTROL:
            components.append(("door_control", "Управление дверьми"))
        if ENABLE_CHAT:
            components.append(("chat", "Чат со S.C.O.P.E."))
        if ENABLE_DISK_READER:
            components.append(("disk_reader", "Чтение голодисков"))
    
        for comp_id, comp_name in components:
            items.append((str(next_num), comp_name))
            next_num += 1
    
        items.append(("0", "В Главное Меню"))

        text = "\n===СИСТЕМА===\n\n" + self._format_menu_lines(items) + "\n"
        self.output.push(text)

    def _enter_system_view(self, category):
        """Просмотр системного файла."""
        self.state = self.STATE_SYSTEM_VIEW
        self.fixed_header = True
        self.output.clear()

        if category == "info":
            path = os.path.join(SYSTEM_DIR, "Сведения о системе.md")
            self.system_logger.log(self.current_user, "Просмотр сведений о системе", is_user_input=False)
        else:
            comp_path = os.path.join(SYSTEM_DIR, category, "config.md")
            path = comp_path
            self.system_logger.log(self.current_user, f"Просмотр системного файла компонента: {category}", is_user_input=False)

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.output.push(f"\n{content}\n\n[Нажмите Enter, чтобы вернуться...]")
        except FileNotFoundError:
            self.output.push("\nФайл не найден.\n[Нажмите Enter, чтобы вернуться...]")

    def _enter_system_profiles(self):
        """Вход в список профилей пользователей."""
        self.state = self.STATE_SYSTEM_PROFILES
        self.fixed_header = True
        self.output.clear()
    
        self.system_logger.log(self.current_user, "Просмотр списка профилей", is_user_input=False)
    
        profiles_dir = os.path.join(SYSTEM_DIR, "profiles")
        try:
            profiles = [f for f in os.listdir(profiles_dir) if f.endswith(".md")]
            profiles.sort()
        except FileNotFoundError:
            profiles = []
    
        if not profiles:
            items = [("0", "Назад")]
            self.output.push("\n===ПРОФИЛИ ПОЛЬЗОВАТЕЛЕЙ===\n\nНет сохранённых профилей.\n\n" + self._format_menu_lines(items) + "\n")
            return
    
        items = []
        for i, p in enumerate(profiles, 1):
            user_id = os.path.splitext(p)[0]
            # Находим имя пользователя по ID
            user_name = user_id
            for acc in USER_ACCOUNTS:
                if acc["id"] == user_id:
                    user_name = acc["name"]
                    break
            items.append((str(i), user_name))
        items.append(("0", "Назад"))
        text = "\n===ПРОФИЛИ ПОЛЬЗОВАТЕЛЕЙ===\n\n" + self._format_menu_lines(items) + "\n"
        self.output.push(text)

    def _view_system_profile(self, filename):
        """Просмотр профиля пользователя."""
        self.state = self.STATE_SYSTEM_PROFILE_VIEW
        self.fixed_header = True
        self.output.clear()
    
        user_id = os.path.splitext(filename)[0]
        self.system_logger.log(self.current_user, f"Просмотр профиля: {user_id}", is_user_input=False)
    
        path = os.path.join(SYSTEM_DIR, "profiles", filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.output.push(f"\n{content}\n\n[Нажмите Enter, чтобы вернуться...]")
        except FileNotFoundError:
            self.output.push("\nФайл не найден.\n[Нажмите Enter, чтобы вернуться...]")

    def _enter_system_actions(self):
        """Вход в список логов действий."""
        self.state = self.STATE_SYSTEM_ACTIONS
        self.fixed_header = True
        self.output.clear()
    
        self.system_logger.log(self.current_user, "Просмотр списка логов", is_user_input=False)
    
        actions_dir = os.path.join(SYSTEM_DIR, "actions")
        try:
            logs = [f for f in os.listdir(actions_dir) if f.endswith(".md")]
            logs.sort(reverse=True)  # Свежие сверху
        except FileNotFoundError:
            logs = []
    
        if not logs:
            items = [("0", "Назад")]
            self.output.push("\n===ДЕЙСТВИЯ ПОЛЬЗОВАТЕЛЕЙ===\n\nНет сохранённых логов.\n\n" + self._format_menu_lines(items) + "\n")
            return
    
        items = [(str(i+1), os.path.splitext(l)[0]) for i, l in enumerate(logs)]
        items.append(("0", "Назад"))
        text = "\n===ДЕЙСТВИЯ ПОЛЬЗОВАТЕЛЕЙ===\n\n" + self._format_menu_lines(items) + "\n"
        self.output.push(text)

    def _view_system_action(self, filename):
        """Просмотр лога действий."""
        self.state = self.STATE_SYSTEM_ACTION_VIEW
        self.fixed_header = True
        self.output.clear()
    
        self.system_logger.log(self.current_user, f"Просмотр лога: {filename}", is_user_input=False)
    
        path = os.path.join(SYSTEM_DIR, "actions", filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.output.push(f"\n{content}\n\n[Нажмите Enter, чтобы вернуться...]")
        except FileNotFoundError:
            self.output.push("\nФайл не найден.\n[Нажмите Enter, чтобы вернуться...]")

    # -------------------------------------------------------------- чат-ИИ
    MQTT_CONNECT_GRACE_SECONDS = 3.0

    def _enter_chat_menu(self):
        if not self._can_access_item("chat"):
            self._deny_access()
            return
        self.state = self.STATE_CHAT_MENU
        self.fixed_header = True
        self.output.clear()
        items = [("1", "История чатов"), ("2", "Новый чат"), ("0", "В Главное Меню")]
        text = "\n===Чат со S.C.O.P.E.===\n\n" + self._format_menu_lines(items) + "\n"
        self.output.push(text)

    def _list_chat_history_entries(self):
        try:
            entries = [f for f in os.listdir(CHAT_HISTORY_DIR) if f.lower().endswith(".md")]
            entries.sort(reverse=True)  # свежие сеансы сверху
        except FileNotFoundError:
            entries = []
        return entries

    def _enter_chat_history_list(self):
        self.state = self.STATE_CHAT_HISTORY_LIST
        self.fixed_header = True
        self.output.clear()
        self.chat_history_entries = self._list_chat_history_entries()
        if not self.chat_history_entries:
            items = [("0", "Назад")]
            self.output.push(
                "\n===История чатов===\n\nИстория чата пуста.\n\n" + self._format_menu_lines(items) + "\n"
            )
            return
        items = [(str(i), os.path.splitext(entry)[0]) for i, entry in enumerate(self.chat_history_entries, 1)]
        items.append(("0", "Назад"))
        text = "\n===История чатов===\n\n" + self._format_menu_lines(items) + "\n"
        self.output.push(text)

    def _open_chat_history_entry(self, filename):
        self.state = self.STATE_CHAT_HISTORY_VIEW
        self.fixed_header = True
        self.output.clear()
        path = os.path.join(CHAT_HISTORY_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.output.push(f"\n[{filename}]\n\n{content}\n\n[Нажмите Enter, чтобы вернуться...]")
        except FileNotFoundError:
            self.output.push("\nФайл не найден.\n[Нажмите Enter, чтобы вернуться...]")

    def _save_chat_history(self):
        self.state = self.STATE_CHAT_SAVED
        if not self.chat_transcript:
            self.output.push(
                "\n[Сеанс завершён без сообщений]\n\n"
                "[Нажмите Enter, чтобы вернуться...]"
            )
            return
        now = datetime.datetime.now(TIMEZONE_GMT3)
        filename = f"{GAME_YEAR:04d}-{now.month:02d}-{now.day:02d}_{now.hour:02d}-{now.minute:02d}-{now.second:02d}.md"
        os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)
        filepath = os.path.join(CHAT_HISTORY_DIR, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n\n".join(self.chat_transcript) + "\n")
            self._play("complete")
            self.output.push(
                f"\nИстория чата сохранена в {filename}.\n\n[Нажмите Enter, чтобы вернуться...]"
            )
        except OSError as e:
            self._play("error")
            self.output.push(
                f"\nОшибка сохранения истории чата: {e}\n\n[Нажмите Enter, чтобы вернуться...]"
            )

    def _enter_chat(self):
        self.chat_transcript = []
        self.state = self.STATE_CHAT
        self.fixed_header = True
        self.output.clear()
        self.system_logger.start_chat_logging()
        self.output.push("\n[Подключение к S.C.O.P.E...]\n", instant=True)
        self._chat_status_resolved = False
        self._chat_connect_deadline = time.time() + self.MQTT_CONNECT_GRACE_SECONDS

        if not MQTT_LIB_AVAILABLE:
            self.output.push(
                "paho-mqtt not installed. Running in LOCAL TEST MODE (echo replies).\n"
                "Install with: pip install paho-mqtt\n"
                "Введите сообщение ('exit' для отключения).\n"
            )
            self._chat_status_resolved = True
            return

        self._mqtt_connect()

    def _mqtt_connect(self):
        """Неблокирующее подключение: connect_async() не ждёт ответа сети,
        реальная попытка соединения идёт в фоновом потоке loop_start()."""
        if not MQTT_LIB_AVAILABLE or self.mqtt_client is not None:
            return
        try:
            client = mqtt.Client()

            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    self.mqtt_connected = True
                    client.subscribe(TOPIC_FROM_MASTER)
                else:
                    self.mqtt_connected = False

            def on_disconnect(client, userdata, rc):
                self.mqtt_connected = False

            def on_message(client, userdata, msg):
                self.incoming_queue.put(msg.payload.decode("utf-8", errors="replace"))

            client.on_connect = on_connect
            client.on_disconnect = on_disconnect
            client.on_message = on_message

            client.connect_async(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=15)
            client.loop_start()
            self.mqtt_client = client
        except Exception:
            self.mqtt_client = None
            self.mqtt_connected = False
            self._chat_status_resolved = True

    def _poll_chat_status(self):
        """Вызывается каждый кадр, пока мы в чате и статус ещё не объявлен
        пользователю — ждём либо успешного connect, либо истечения таймаута
        на попытку, и только тогда один раз печатаем итог."""
        if self.state != self.STATE_CHAT or self._chat_status_resolved:
            return
        if self.mqtt_connected:
            self._play("complete")
            self.output.push("Соединение установлено. Введите сообщение ('exit' для отключения).\n", instant=True)
            self._chat_status_resolved = True
        elif time.time() >= self._chat_connect_deadline:
            self.output.push(
                "Не удалось связаться со S.C.O.P.E.\n" 
                "Запущен ТЕСТОВЫЙ РЕЖИМ (эхо-ответы).\n"
                "Введите сообщение ('exit' для отключения).\n"
            )
            self._chat_status_resolved = True

    def _mqtt_disconnect(self):
        if self.mqtt_client is not None:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except Exception:
                pass
        self.mqtt_client = None
        self.mqtt_connected = False
        self._chat_status_resolved = True

    def _send_chat_message(self, text):
        self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
        self.chat_transcript.append(f"**{self.current_user}:** {text}")
        if self.mqtt_connected and self.mqtt_client is not None:
            try:
                self.mqtt_client.publish(TOPIC_TO_MASTER, text, qos=1)
            except Exception:
                self._play("error")
                self.output.push("[Соединение потеряно. Сообщение не отправлено.]\n", instant=True)
        else:
            # локальный тестовый режим — просто эхо, чтобы было что смотреть
            self.incoming_queue.put(f"(test echo) {text}")

    def _poll_chat_incoming(self):
        while not self.incoming_queue.empty():
            text = self.incoming_queue.get()
            self.output.push(f"[S.C.O.P.E.]: {text}\n")
            self.chat_transcript.append(f"**S.C.O.P.E.:** {text}")

    # -------------------------------------------------------------- ввод
    def handle_submit(self, raw_text):
        text = raw_text.strip()

        if self.state == self.STATE_USER_SELECT:
            if text.isdigit():
                idx = int(text)
                if 1 <= idx <= len(USER_ACCOUNTS):
                    self.pending_user = USER_ACCOUNTS[idx - 1]
                    self.password_attempts_used = 0
                    self._enter_password()
                    return
            self._play("error")
            self.output.push("\nНеизвестная команда.\n")
            return

        if self.state == self.STATE_PASSWORD:
            if self.pending_user is None:
                self.pending_user = USER_ACCOUNTS[0]
            if text.upper() == HACK_MODULE_TRIGGER_PASSWORD:
                # Резервный ручной запуск — не является штатным пунктом
                # авторизации, см. комментарий у константы выше.
                self._launch_hack_module()
                return
            if text.upper() == self.pending_user["password"]:
                self.output.push(f">[{self.pending_user['name']}]: {text}\n", instant=True)
                self._play("unlocked")
                self._apply_authenticated_user(self.pending_user)
                self.state = self.STATE_AUTH_SUCCESS
                self.output.push(f"ПАРОЛЬ ПРИНЯТ\nВы авторизованы как: {self.current_user}\n", instant=True)
                self._schedule(AUTH_SUCCESS_DELAY_SECONDS, self._enter_main_menu)
                return
            self.password_attempts_used += 1
            attempts_left = MAX_PASSWORD_ATTEMPTS - self.password_attempts_used
            if attempts_left <= 0:
                self._play("error")
                self.state = self.STATE_CLOSING
                self.output.push("\nДОСТУП ЗАПРЕЩЁН\nВыключение...\n", instant=True)
                self._schedule(LOCKOUT_DELAY_SECONDS, self._quit)
            else:
                self.output.push(f">[{self.pending_user['name']}]: {text}\n", instant=True)
                self._play("error")
                self._enter_password(extra_message="НЕВЕРНЫЙ ПАРОЛЬ")
            return

        if self.state == self.STATE_HACK_MINIGAME:
            self._handle_hack_input(text)
            return

        if self.state in (self.STATE_CLOSING, self.STATE_AUTH_SUCCESS):
            return  # ввод игнорируем

        if self.state == self.STATE_MAIN_MENU:
            self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
            self.system_logger.log(self.current_user, text, is_user_input=True)
            self._handle_main_menu(text)
            return

        if self.state == self.STATE_LOG_USER_LIST:
            self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
            if text == "0" or text == "":
                self._enter_main_menu()
            elif text.isdigit():
                choice = int(text)
                if 1 <= choice <= len(USER_ACCOUNTS):
                    self._enter_log_list_for_user(USER_ACCOUNTS[choice - 1]["id"])
            return

        if self.state == self.STATE_LOG_LIST:
            self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
            if not self.log_entries:
                # Пустой журнал: 1 — создать запись, 0 — назад
                if text == "1":
                    self._start_new_log_entry()
                elif text == "0" or text == "":
                    self._log_list_back()
                return
            if text == "0" or text == "":
                self._log_list_back()
            elif text.isdigit():
                choice = int(text)
                if 1 <= choice <= len(self.log_entries):
                    self._open_log_entry(self.log_entries[choice - 1])
                elif choice == len(self.log_entries) + 1:
                    self._start_new_log_entry()
            return

        if self.state == self.STATE_LOG_VIEW:
            self._enter_log_list_for_user(self.current_log_owner_id)
            return

        if self.state == self.STATE_LOG_NEW:
            self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
            self._handle_log_new_input(text)
            return

        if self.state == self.STATE_DATA_LIST:
            self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
            if text == "0" or text == "":
                self._enter_main_menu()
            elif text.isdigit():
                choice = int(text)
                if 1 <= choice <= len(self.data_entries):
                    self._open_data_entry(self.data_entries[choice - 1])
            return

        if self.state == self.STATE_DATA_VIEW:
            self._enter_data_category(self.current_data_category)
            return

        if self.state == self.STATE_DOOR:
            self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
            if text == "1":
                self.door_status = "ОТКРЫТА"
                self._play("complete")
                self._enter_door_control()
            elif text == "2":
                self.door_status = "ЗАКРЫТА"
                self._play("complete")
                self._enter_door_control()
            elif text == "0" or text == "":
                self._enter_main_menu()
            return
        
        if self.state == self.STATE_SYSTEM_MENU:
            self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
            if text == "0" or text == "":
                self._enter_main_menu()
                return
            elif text == "1":
                self._enter_system_view("info")
                return
            elif text == "2":
                self._enter_system_actions()
                return
            elif text == "3":
                self._enter_system_profiles()
                return
            elif text.isdigit():
                choice = int(text)
                components = []
                if ENABLE_DOOR_CONTROL:
                    components.append(("door_control", "Управление дверьми"))
                if ENABLE_CHAT:
                    components.append(("chat", "Чат со S.C.O.P.E."))
                if ENABLE_DISK_READER:
                    components.append(("disk_reader", "Чтение голодисков"))
        
                if 4 <= choice <= 3 + len(components):
                    comp_index = choice - 4
                    if 0 <= comp_index < len(components):
                        comp_id = components[comp_index][0]
                        self._enter_system_view(comp_id)
                        return
                else:
                    self._play("error")
                    self.output.push("\nНеизвестная команда.\n")
                    return
            else:
                self._play("error")
                self.output.push("\nНеизвестная команда.\n")
                return

        if self.state == self.STATE_SYSTEM_VIEW:
            self._enter_system_menu()
            return

        if self.state == self.STATE_SYSTEM_PROFILES:
            if text == "0" or text == "":
                self._enter_system_menu()
            elif text.isdigit():
                choice = int(text)
                profiles_dir = os.path.join(SYSTEM_DIR, "profiles")
                try:
                    profiles = [f for f in os.listdir(profiles_dir) if f.endswith(".md")]
                    profiles.sort()
                    if 1 <= choice <= len(profiles):
                        self._view_system_profile(profiles[choice - 1])
                except FileNotFoundError:
                    self.output.push("\nОшибка: папка profiles не найдена.\n")
                    return
            return

        if self.state == self.STATE_SYSTEM_PROFILE_VIEW:
            self._enter_system_profiles()
            return

        if self.state == self.STATE_SYSTEM_ACTIONS:
            if text == "0" or text == "":
                self._enter_system_menu()
            elif text.isdigit():
                choice = int(text)
                actions_dir = os.path.join(SYSTEM_DIR, "actions")
                try:
                    logs = [f for f in os.listdir(actions_dir) if f.endswith(".md")]
                    logs.sort(reverse=True)
                    if 1 <= choice <= len(logs):
                        self._view_system_action(logs[choice - 1])
                except FileNotFoundError:
                    self.output.push("\nОшибка: папка actions не найдена.\n")
                    return
            return

        if self.state == self.STATE_SYSTEM_ACTION_VIEW:
            self._enter_system_actions()
            return

        if self.state == self.STATE_CHAT_MENU:
            if text == "1":
                self._enter_chat_history_list()
            elif text == "2":
                self._enter_chat()
            elif text == "0" or text == "":
                self._enter_main_menu()
            else:
                self._play("error")
                self.output.push("\nНеизвестная команда.\n")
            return

        if self.state == self.STATE_CHAT_HISTORY_LIST:
            if text == "0" or text == "":
                self._enter_chat_menu()
            elif text.isdigit():
                choice = int(text)
                if 1 <= choice <= len(self.chat_history_entries):
                    self._open_chat_history_entry(self.chat_history_entries[choice - 1])
            return

        if self.state == self.STATE_CHAT_HISTORY_VIEW:
            self._enter_chat_history_list()
            return

        if self.state == self.STATE_CHAT:
            if text.lower() == "exit":
                self._mqtt_disconnect()
                self._save_chat_history()
                self.system_logger.stop_chat_logging()
            elif text:
                self._send_chat_message(text)
            return

        if self.state == self.STATE_CHAT_SAVED:
            self._enter_chat_menu()
            return

        if self.state == self.STATE_MAP:
            # Если мы в режиме ввода текста отметки
            if self.map_state == "ADD_MARKER_TEXT":
                self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
                if text:
                    # Добавляем отметку в центре экрана
                    center_x = RENDER_W // 2
                    center_y = RENDER_H // 2
                    lat, lon = self._screen_to_world(center_x, center_y)
                    self.map_markers.add_marker(lat, lon, text)
                    self._play("complete")
                    self.output.push(f"\nОтметка добавлена: {text}\n")
                else:
                    self._play("error")
                    self.output.push("\nТекст не может быть пустым\n")
                self.map_state = "VIEW"
                self.map_marker_input = ""
                return
        
            # Обработка команд карты (когда НЕ в режиме ввода текста)
            self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
        
            # Команда 'r' — проложить маршрут
            if text.lower() == "r":
                if self.map_selected_marker:
                    self.map_route_target = self.map_selected_marker
                    self._play("complete")
                    self.output.push(f"\nМаршрут проложен до: {self.map_selected_marker.text}\n")
                else:
                    self._play("error")
                    self.output.push("\nСначала выберите отметку (цифрой)\n")
                return
        
            # Цифры — выбор отметки по номеру
            if text.isdigit():
                idx = int(text) - 1
                # Получаем все видимые отметки
                if self.map_bounds:
                    lat_min = self.map_bounds["min_lat"]
                    lat_max = self.map_bounds["max_lat"]
                    lon_min = self.map_bounds["min_lon"]
                    lon_max = self.map_bounds["max_lon"]
                    visible_markers = self.map_markers.get_markers_in_view(lat_min, lat_max, lon_min, lon_max)
                
                    if 0 <= idx < len(visible_markers):
                        self.map_selected_marker = visible_markers[idx]
                        self._play("clack")
                        self.output.push(f"\nВыбрана отметка: {self.map_selected_marker.text}\n")
                        return
            
                # Если дошли сюда — отметка не найдена
                self._play("error")
                self.output.push(f"\nОтметка с номером {text} не найдена\n")
                return
        
        # Если ничего не подошло
        self._play("error")
        self.output.push("\nНеизвестная команда. Используйте:\n")
        self.output.push("  [цифра] - выбрать отметку\n")
        self.output.push("  R - проложить маршрут\n")
        return

    def _handle_main_menu(self, text):
        if text == "0":
            self.state = self.STATE_CLOSING
            self.output.push("\nЗавершение сеанса...\nВыключение...\n")
            self.system_logger.log("SYSTEM", "Сессия завершена", is_system=True)
            self._schedule(MENU_CLOSE_DELAY_SECONDS, self._quit)
        elif text.isdigit() and 1 <= int(text) <= len(self.main_menu_actions):
            _, action = self.main_menu_actions[int(text) - 1]
            action()
        else:
            self._play("error")
            self.output.push("\nНеизвестная команда.\n", instant=True)

    def _handle_log_new_input(self, text):
        if not hasattr(self, "_new_log_title"):
            self._new_log_title = None
        if self._new_log_title is None:
            if not text:
                self.output.push("\nОтмена.", instant=True)
                self._enter_log_list_for_user(self.current_log_owner_id)
                return
            self._new_log_title = text
            self.output.push("\nВведите запись. Напишите END в конце:")
            return
        if text.upper() == "END":
            content = "\n".join(self.new_log_lines)
            self._save_new_log_entry(self._new_log_title, content)
            self._new_log_title = None
            self.new_log_lines = []
            self._enter_log_list_for_user(self.current_log_owner_id)
            return
        self.new_log_lines.append(text)

    # ------------------------------------------------------------- события
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            if self.state == self.STATE_SPLASH:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                    self._skip_splash()
                return
            if self.state == self.STATE_DISK_READER:
                if event.key == pygame.K_ESCAPE:
                    self._play("clack")
                    self._enter_main_menu()
                elif event.key == pygame.K_LEFT:
                    self.disk_reader_focus = "terminal"
                elif event.key == pygame.K_RIGHT:
                    self.disk_reader_focus = "holotape"
                elif event.key == pygame.K_UP:
                    self._disk_reader_move_cursor(-1)
                elif event.key == pygame.K_DOWN:
                    self._disk_reader_move_cursor(1)
                elif event.key == pygame.K_RETURN:
                    self._play("clack")
                    self._disk_reader_copy_selected()
                return
            if self.state == self.STATE_MAP:
                if event.key == pygame.K_ESCAPE:
                    self._play("clack")
                    self._enter_main_menu()
                elif event.key == pygame.K_UP:
                    self.map_view_lat += self.map_zoom * 0.1
                    self._clamp_map_view()
                elif event.key == pygame.K_DOWN:
                    self.map_view_lat -= self.map_zoom * 0.1
                    self._clamp_map_view()
                elif event.key == pygame.K_LEFT:
                    self.map_view_lon -= self.map_zoom * 0.1
                    self._clamp_map_view()
                elif event.key == pygame.K_RIGHT:
                    self.map_view_lon += self.map_zoom * 0.1
                    self._clamp_map_view()
                elif event.key == pygame.K_EQUALS or event.key == pygame.K_PLUS:
                    self.map_zoom = max(0.001, self.map_zoom * 0.9)
                elif event.key == pygame.K_MINUS:
                    self.map_zoom = min(0.5, self.map_zoom * 1.1)
                elif event.key == pygame.K_RETURN:
                    if self.map_state == "ADD_MARKER_TEXT":
                        if self.map_marker_input:
                            # Добавляем отметку в центре экрана
                            center_x = RENDER_W // 2
                            center_y = RENDER_H // 2
                            lat, lon = self._screen_to_world(center_x, center_y)
                            self.map_markers.add_marker(lat, lon, self.map_marker_input)
                            self._play("complete")
                        self.map_state = "VIEW"
                        self.map_marker_input = ""
                    else:
                        self.map_state = "ADD_MARKER_TEXT"
                        self.map_marker_input = ""
                        self._play("clack")
                elif event.key == pygame.K_r:
                    if self.map_selected_marker:
                        self.map_route_target = self.map_selected_marker
                        self._play("complete")
                    else:
                        self._play("error")
                elif event.unicode and event.unicode.isprintable() and self.map_state == "ADD_MARKER_TEXT":
                    self.map_marker_input += event.unicode
                elif event.key == pygame.K_BACKSPACE and self.map_state == "ADD_MARKER_TEXT":
                    self.map_marker_input = self.map_marker_input[:-1]
                return
            if event.key == pygame.K_ESCAPE:
                if self.state == self.STATE_HACK_MINIGAME and self.hack_state == "ACTIVE":
                    # Просто очищаем ввод
                    self.input_text = ""
                else:
                    self.running = False
            elif event.key == pygame.K_UP:
                self.output.scroll(SCROLL_STEP, self._current_max_lines())
            elif event.key == pygame.K_DOWN:
                self.output.scroll(-SCROLL_STEP, self._current_max_lines())
            elif event.key == pygame.K_RETURN:
                self._play("clack")
                if self.state == self.STATE_HACK_MINIGAME:
                    if self.output.is_typing():
                        self.output.skip_typing()
                    else:
                        submitted = self.input_text
                        self.input_text = ""
                        self.handle_submit(submitted)
                else:
                    if self.output.is_typing():
                        self.output.skip_typing()
                    else:
                        submitted = self.input_text
                        self.input_text = ""
                        self.handle_submit(submitted)
            elif event.key == pygame.K_BACKSPACE:
                self._play("clack")
                self.input_text = self.input_text[:-1]
            elif event.unicode and event.unicode.isprintable():
                self._play("clack")
                self.input_text += event.unicode

    def _format_menu_lines(self, items):
        """items — список (номер_как_строка, подпись). Пункт '0' обычно
        передаётся последним. Закрывающие скобки выравниваются пробелами
        по самому длинному пункту в этом конкретном меню."""
        max_w = max(len(f"{num}. {label}") for num, label in items)
        return "\n".join(f"[{f'{num}. {label}'.ljust(max_w)}]" for num, label in items)

    def _current_max_lines(self):
        return self.max_visible_lines_header if self.fixed_header else self.max_visible_lines_full

    def _schedule(self, delay_seconds, callback):
        """Выполнить callback() через delay_seconds. Пока действие не сработало,
        предыдущее состояние (текст на экране) остаётся видимым как есть."""
        self._pending_callback = callback
        self._pending_callback_at = time.time() + delay_seconds

    def _quit(self):
        self.running = False
    
    def _current_datetime_str(self):
        now = datetime.datetime.now(TIMEZONE_GMT3)
        month = MONTH_ABBR_RU[now.month - 1]
        return f"{now.day:02d} {month} {GAME_YEAR} {now.hour:02d}:{now.minute:02d}"

    def render_ansi_text(self, surf, text, x, y):
        """Рендерит текст с ANSI-кодами цветов."""
        parts = re.split(r'(\033\[[0-9;]*m)', text)
        current_color = COLOR_TEXT
        cx = x
        for part in parts:
            if part.startswith('\033['):
                if '97m' in part:
                    current_color = (255, 255, 255)
                elif '92m' in part:
                    current_color = COLOR_TEXT
            else:
                if part:
                    part_surf = self.font.render(part, True, current_color)
                    surf.blit(part_surf, (cx, y))
                    cx += part_surf.get_width()
        return cx

    # --------------------------------------------------------------- кадр
    def update(self, dt):
        if self.state == self.STATE_SPLASH:
            self._update_splash()
        self.output.update()
        self._sync_typing_loop(self.output.is_typing())
        self._poll_chat_incoming()
        self._poll_chat_status()
        new_mounts = self._poll_removable_drives()
        if new_mounts:
            self._check_hack_module_on_drives(new_mounts)
            self._check_disk_reader_autoopen(new_mounts)
        if self.state == self.STATE_DISK_READER:
            self._poll_disk_reader_mount()
        self._update_scroll_repeat()
        self.cursor_timer += dt
        if self.cursor_timer > 0.5:
            self.cursor_timer = 0.0
            self.cursor_visible = not self.cursor_visible

        if self._pending_callback is not None and time.time() >= self._pending_callback_at:
            callback = self._pending_callback
            self._pending_callback = None
            self._pending_callback_at = None
            callback()

    def _update_scroll_repeat(self):
        """Повтор прокрутки при удержании стрелок — реализован вручную,
        не через глобальный pygame.key.set_repeat(), чтобы не задевать Enter."""
        keys = pygame.key.get_pressed()
        held_up = keys[pygame.K_UP]
        held_down = keys[pygame.K_DOWN]

        if not (held_up or held_down):
            self._scroll_hold_start = None
            return

        now = time.time()
        if self._scroll_hold_start is None:
            self._scroll_hold_start = now
            self._scroll_next_repeat_at = now + self._scroll_repeat_delay
            return

        if now - self._scroll_hold_start >= self._scroll_repeat_delay and now >= self._scroll_next_repeat_at:
            direction = SCROLL_STEP if held_up else -SCROLL_STEP
            self.output.scroll(direction, self._current_max_lines())
            self._scroll_next_repeat_at = now + self._scroll_repeat_interval

    def _render_splash(self, surf):
        if self.splash_image is not None:
            surf.blit(self.splash_image, (0, 0))
        else:
            surf.fill(COLOR_BG)

        bar_x = (RENDER_W - SPLASH_BAR_WIDTH) // 2
        bar_y = RENDER_H - 90

        panel_padding = 16
        panel_width = SPLASH_BAR_WIDTH + panel_padding * 2
        panel_top = bar_y - self.font.get_linesize() - 6 - panel_padding
        panel_height = (bar_y + SPLASH_BAR_HEIGHT) - panel_top + panel_padding
        panel_x = (RENDER_W - panel_width) // 2
        panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 160))
        surf.blit(panel, (panel_x, panel_top))

        label = f"ЗАГРУЗКА {self.splash_progress:03d}%"
        label_surf = self.font.render(label, True, COLOR_TEXT)
        label_x = (RENDER_W - label_surf.get_width()) // 2
        surf.blit(label_surf, (label_x, bar_y - self.font.get_linesize() - 6))

        pygame.draw.rect(surf, COLOR_TEXT, (bar_x, bar_y, SPLASH_BAR_WIDTH, SPLASH_BAR_HEIGHT), width=2)
        fill_w = int((SPLASH_BAR_WIDTH - 4) * (self.splash_progress / 100))
        if fill_w > 0:
            pygame.draw.rect(surf, COLOR_TEXT, (bar_x + 2, bar_y + 2, fill_w, SPLASH_BAR_HEIGHT - 4))

        surf.blit(self.scanlines, (0, 0))
        surf.blit(self.vignette, (0, 0))

    def _render_map_message_overlay(self, surf):
        """Показывает сообщения карты (вход, выбор отметки, ошибки и т.д.) —
        иначе self.output никогда не рендерится в режиме карты."""
        line_h = self.font.get_linesize() + LINE_SPACING
        lines = self.output.visible_lines(6)
        if not lines:
            return
        panel_w = RENDER_W - MARGIN * 2
        panel_h = line_h * len(lines) + 16
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 170))
        surf.blit(panel, (MARGIN, MARGIN))
        y = MARGIN + 8
        for line in lines:
            self.render_ansi_text(surf, line, MARGIN + 8, y)
            y += line_h

    def render(self):
        surf = self.render_surface
        surf.fill(COLOR_BG)

        if self.state == self.STATE_SPLASH:
            self._render_splash(surf)
            scaled = pygame.transform.smoothscale(surf, (WINDOW_W, WINDOW_H))
            self.window.blit(scaled, (0, 0))
            pygame.display.flip()
            return

        if self.state == self.STATE_DISK_READER:
            self._render_disk_reader(surf)
            surf.blit(self.scanlines, (0, 0))
            surf.blit(self.vignette, (0, 0))
            scaled = pygame.transform.smoothscale(surf, (WINDOW_W, WINDOW_H))
            self.window.blit(scaled, (0, 0))
            pygame.display.flip()
            return
        
        if self.state == self.STATE_MAP:
            self._render_map(surf)
            # Если в режиме ввода текста отметки
            if self.map_state == "ADD_MARKER_TEXT":
                self._render_marker_input(surf)
            self._render_map_message_overlay(surf)
        
            # Применяем эффекты
            bloom = make_bloom(surf)
            surf.blit(bloom, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            surf.blit(self.scanlines, (0, 0))
            surf.blit(self.vignette, (0, 0))
        
            scaled = pygame.transform.smoothscale(surf, (WINDOW_W, WINDOW_H))
            self.window.blit(scaled, (0, 0))
            pygame.display.flip()
            return

        y = MARGIN
        line_h = self.font.get_linesize() + LINE_SPACING
        n = self._current_max_lines()

        if self.fixed_header and self.state != self.STATE_HACK_MINIGAME:
            for header_line in HEADER_BANNER.split("\n"):
                header_surf = self.font.render(header_line, True, COLOR_TEXT)
                surf.blit(header_surf, (MARGIN, y))
                y += line_h

            date_str = self._current_datetime_str()
            user_str = f"Пользователь: {self.current_user}"
            date_surf = self.font.render(date_str, True, COLOR_TEXT)
            user_surf = self.font.render(user_str, True, COLOR_TEXT)
            surf.blit(date_surf, (MARGIN, y))
            surf.blit(user_surf, (RENDER_W - MARGIN - user_surf.get_width(), y))
            y += line_h

            y += line_h * HEADER_GAP_LINES

        content_top_y = y
        if self.output.has_more_above(n):
            indicator = self.font.render("^ Листать вверх ^", True, COLOR_DIM)
            surf.blit(indicator, (MARGIN, content_top_y))
        y += line_h

        visible = self.output.visible_lines(n)
        for line in visible:
            self.render_ansi_text(surf, line, MARGIN, y)
            y += line_h

        if self.output.has_more_below():
            indicator = self.font.render("v Листать вниз v", True, COLOR_DIM)
            surf.blit(indicator, (MARGIN, y))
        y += line_h

        if not self.output.is_typing() and self.state not in (self.STATE_CLOSING, self.STATE_AUTH_SUCCESS):
            prompt = "> " + self.input_text + ("_" if self.cursor_visible else " ")
            prompt_surf = self.font.render(prompt, True, COLOR_TEXT)
            surf.blit(prompt_surf, (MARGIN, y))

        bloom = make_bloom(surf)
        surf.blit(bloom, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        surf.blit(self.scanlines, (0, 0))
        surf.blit(self.vignette, (0, 0))

        scaled = pygame.transform.smoothscale(surf, (WINDOW_W, WINDOW_H))
        self.window.blit(scaled, (0, 0))
        pygame.display.flip()

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(dt)
            self.render()

            self._frame_count += 1
            if TEST_MODE and self._frame_count > 90:
                self.running = False

        self._mqtt_disconnect()
        pygame.quit()


def main():
    app = TerminalApp()
    app.run()


if __name__ == "__main__":
    main()
