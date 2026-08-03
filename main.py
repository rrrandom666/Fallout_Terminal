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

# --------------------------------------------------------------------------
# Конфигурация внешнего вида
# --------------------------------------------------------------------------
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

BLOOM_DOWNSCALE = 0.18
BLOOM_ALPHA = 70
SCANLINE_SPACING = 3
SCANLINE_ALPHA = 40
VIGNETTE_ALPHA_MAX = 90

TYPEWRITER_CHARS_PER_FRAME = 2
SCROLL_STEP = 3  # строк за одно нажатие/повтор стрелки

# --- Всякоразные переменные --------------------------------------
MAX_PASSWORD_ATTEMPTS = 4
CORRECT_PASSWORD = "HAPPINESS"
AUTH_SUCCESS_DELAY_SECONDS = 2.5   # после верного пароля, перед главным меню

# --------------------------------------------------------------------------
# Определение подключённых флешек — общий механизм, не привязанный к
# конкретному модулю. Опрос дисков идёт постоянно (не только на экране
# пароля); что делать с новым диском — решает уже конкретный обработчик
# (см. _check_hack_module_on_drives). Так проще добавить другие сценарии
# чтения флешки позже, без завязки на файл-маркер.
# --------------------------------------------------------------------------
DRIVE_POLL_INTERVAL = 1.0  # как часто проверять список смонтированных дисков (сек)

# --------------------------------------------------------------------------
# Модуль взлома пароля — НЕ часть штатного интерфейса системы авторизации.
# Активируется только когда во время экрана пароля к компьютеру
# подключается флешка (голодиск-эксплойт) с файлом-маркером на борту.
# Попытки взлома тратят тот же лимит, что и обычный ввод пароля — с точки
# зрения системы это ровно то же самое "неверная попытка авторизации".
# --------------------------------------------------------------------------
ENABLE_HACK_MODULE_DETECTION = True         # реагировать ли на маркер флешки
HACK_MODULE_MARKER_FILENAME = "robco_hack.module"  # файл-маркер в корне флешки

# Резервный ручной запуск — если реальной флешки нет под рукой (тест, показ),
# либо это способ, которым голодиск-HID сам "впечатывает" триггер в поле пароля.
HACK_MODULE_TRIGGER_PASSWORD = "ICEBREAKER"

HACK_WORD_POOL = [
    "ВОЙНА", "ГОРОД", "ОГОНЬ", "БРОНЯ", "ВОЛНА", "ЩЕПКА", "ПАТРОН", "БУНКЕР",
    "МЕТАЛЛ", "МУТАНТ", "РЕАКТОР", "ПУСТОШЬ", "ОСКОЛОК", "ГЕЙГЕР", "ОБЛОМОК",
    "КИСЛОТА", "РАДИАЦИЯ", "УБЕЖИЩЕ", "СКАФАНДР",
]
HACK_CANDIDATES_COUNT = 6
LOCKOUT_DELAY_SECONDS = 2.5        # после исчерпания попыток пароля, перед выключением
MENU_CLOSE_DELAY_SECONDS = 2.0     # после "0. Закрыть терминал", перед выключением
GAME_YEAR = 2276                       
UNAUTHORIZED_USER_LABEL = "АНОНИМ"     
AUTHORIZED_USER_LABEL = "БИЛЛ ВАССОН"  
# ---------------------------------------------------------------------------

MONTH_ABBR_RU = [
    "ЯНВ", "ФЕВ", "МАР", "АПР", "МАЯ", "ИЮН",
    "ИЮЛ", "АВГ", "СЕН", "ОКТ", "НОЯ", "ДЕК",
]
TIMEZONE_GMT3 = datetime.timezone(datetime.timedelta(hours=3))

# Закреплённая шапка — отображается статично сверху во всех состояниях
HEADER_BANNER = (
    "================ ROBCO INDUSTRIES UNIFIED OPERATING SYSTEM ================\n"
    "================== COPYRIGHT 2075-2077 ROBCO INDUSTRIES ==================="
)
HEADER_LINE_COUNT = len(HEADER_BANNER.split("\n")) + 1  # +1 — строка статуса (дата/пользователь)
HEADER_GAP_LINES = 1  # пустая строка-отступ между шапкой и прокручиваемым текстом

JOURNAL_DIR = "journal"
CHAT_HISTORY_DIR = "chat_history"
DATA_DIR = "data"

# Включаемые модули меню — легко выключить, если на конкретной игре не нужны
ENABLE_DOOR_CONTROL = True
ENABLE_CHAT = True

# Звуки
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


# --------------------------------------------------------------------------
# Визуальные эффекты
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Приложение
# --------------------------------------------------------------------------
class TerminalApp:
    STATE_SPLASH = "SPLASH"
    STATE_BOOT = "BOOT"
    STATE_PASSWORD = "PASSWORD"
    STATE_HACK_MINIGAME = "HACK_MINIGAME"
    STATE_AUTH_SUCCESS = "AUTH_SUCCESS"
    STATE_CLOSING = "CLOSING"
    STATE_MAIN_MENU = "MAIN_MENU"
    STATE_LOG_LIST = "LOG_LIST"
    STATE_LOG_VIEW = "LOG_VIEW"
    STATE_LOG_NEW = "LOG_NEW"
    STATE_DATA_LIST = "DATA_LIST"
    STATE_DATA_VIEW = "DATA_VIEW"
    STATE_DOOR = "DOOR"
    STATE_CHAT_MENU = "CHAT_MENU"
    STATE_CHAT_HISTORY_LIST = "CHAT_HISTORY_LIST"
    STATE_CHAT_HISTORY_VIEW = "CHAT_HISTORY_VIEW"
    STATE_CHAT = "CHAT"
    STATE_CHAT_SAVED = "CHAT_SAVED"

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

        # Модуль взлома (запускается только с внешней флешки; попытки —
        # общие с обычным вводом пароля, self.password_attempts_used)
        self.hack_candidates = []
        self.hack_answer = ""

        # Определение флешек — общий механизм (см. константы выше)
        self._last_drive_poll_at = 0.0
        self._known_mount_points = set()
        if PSUTIL_AVAILABLE:
            try:
                self._known_mount_points = {p.mountpoint for p in psutil.disk_partitions(all=False)}
            except Exception:
                self._known_mount_points = set()

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
            self._enter_main_menu()
        else:
            self._enter_password()

    def _enter_password(self, extra_message=None):
        self.state = self.STATE_PASSWORD
        attempts_left = MAX_PASSWORD_ATTEMPTS - self.password_attempts_used
        if extra_message:
            text = f"{extra_message}\n"
        else:
            text = "ТРЕБУЕТСЯ ПАРОЛЬ\n"
        text += f"Осталось попыток: {attempts_left}\nВведите пароль:\n"
        self.output.push(text)

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
                self._launch_hack_module()
                return

    def _launch_hack_module(self):
        pool_by_length = {}
        for word in HACK_WORD_POOL:
            pool_by_length.setdefault(len(word), []).append(word)
        eligible = [words for words in pool_by_length.values() if len(words) >= 4]
        words = random.choice(eligible)
        count = min(HACK_CANDIDATES_COUNT, len(words))
        self.hack_candidates = random.sample(words, count)
        self.hack_answer = random.choice(self.hack_candidates)
        self._render_hack_screen(intro=True)

    def _render_hack_screen(self, intro=False, feedback=None):
        self.state = self.STATE_HACK_MINIGAME
        attempts_left = MAX_PASSWORD_ATTEMPTS - self.password_attempts_used
        lines = []
        if intro:
            lines.append("ОБНАРУЖЕНО ПОСТОРОННЕЕ УСТРОЙСТВО.")
            lines.append("Запущен несанкционированный модуль взлома пароля.\n")
        if feedback:
            lines.append(feedback + "\n")
        lines.append(f"Попыток: {attempts_left}\n")
        items = [(str(i), w) for i, w in enumerate(self.hack_candidates, 1)]
        lines.append(self._format_menu_lines(items))
        self.output.push("\n".join(lines))

    def _enter_main_menu(self):
        self.state = self.STATE_MAIN_MENU
        self.fixed_header = True
        self.output.clear()

        actions = [("Журнал", self._enter_log_list)]
        if ENABLE_DOOR_CONTROL:
            actions.append(("Управление дверьми", self._enter_door_control))
        if ENABLE_CHAT:
            actions.append(("Чат со S.C.O.P.E.", self._enter_chat_menu))
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

    def _list_log_entries(self):
        try:
            entries = [f for f in os.listdir(JOURNAL_DIR) if f.lower().endswith(".md")]
            entries.sort()
        except FileNotFoundError:
            entries = []
        return entries

    def _enter_log_list(self):
        self.state = self.STATE_LOG_LIST
        self.fixed_header = True
        self.output.clear()
        self.log_entries = self._list_log_entries()
        if not self.log_entries:
            items = [("1", "Создать запись"), ("0", "В Главное Меню")]
            self.output.push(
                "\nЗаписей в журнале нет.\n\n" + self._format_menu_lines(items) + "\n"
            )
            return
        items = [(str(i), os.path.splitext(entry)[0]) for i, entry in enumerate(self.log_entries, 1)]
        items.append((str(len(self.log_entries) + 1), "Создать новую запись"))
        items.append(("0", "В Главное Меню"))
        text = "\n===Журнал===\n\n" + self._format_menu_lines(items) + "\n"
        self.output.push(text)

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
        path = os.path.join(JOURNAL_DIR, filename)
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
        os.makedirs(JOURNAL_DIR, exist_ok=True)
        filepath = os.path.join(JOURNAL_DIR, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            self._play("complete")
            self.output.push(f"\nЗапись сохранена как '{filename}'.")
        except OSError as e:
            self._play("error")
            self.output.push(f"\nОшибка при сохранении записи: {e}")

    def _enter_door_control(self):
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

    # -------------------------------------------------------------- чат-ИИ
    MQTT_CONNECT_GRACE_SECONDS = 3.0

    def _enter_chat_menu(self):
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

        if self.state == self.STATE_PASSWORD:
            if text.upper() == HACK_MODULE_TRIGGER_PASSWORD:
                # Резервный ручной запуск — не является штатным пунктом
                # авторизации, см. комментарий у константы выше.
                self._launch_hack_module()
                return
            if text.upper() == CORRECT_PASSWORD:
                self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
                self._play("unlocked")
                self.current_user = AUTHORIZED_USER_LABEL
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
                self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
                self._play("error")
                self._enter_password(extra_message="НЕВЕРНЫЙ ПАРОЛЬ")
            return

        if self.state == self.STATE_HACK_MINIGAME:
            if text.isdigit():
                idx = int(text)
                if 1 <= idx <= len(self.hack_candidates):
                    guess = self.hack_candidates[idx - 1]
                    if guess == self.hack_answer:
                        self._play("unlocked")
                        self.current_user = AUTHORIZED_USER_LABEL
                        self.state = self.STATE_AUTH_SUCCESS
                        self.output.push(
                            "\nВЗЛОМ УСПЕШЕН.\nПАРОЛЬ ПОДОБРАН.\n"
                            f"Вы авторизованы как: {self.current_user}\n",
                            instant=True,
                        )
                        self._schedule(AUTH_SUCCESS_DELAY_SECONDS, self._enter_main_menu)
                        return
                    matches = sum(1 for a, b in zip(guess, self.hack_answer) if a == b)
                    self.password_attempts_used += 1
                    attempts_left = MAX_PASSWORD_ATTEMPTS - self.password_attempts_used
                    self._play("error")
                    if attempts_left <= 0:
                        self.state = self.STATE_CLOSING
                        self.output.push("\nДОСТУП ЗАПРЕЩЁН\nВыключение...\n", instant=True)
                        self._schedule(LOCKOUT_DELAY_SECONDS, self._quit)
                    else:
                        self._render_hack_screen(
                            feedback=f"НЕВЕРНО. Совпадений: {matches}/{len(self.hack_answer)}."
                        )
            return

        if self.state in (self.STATE_CLOSING, self.STATE_AUTH_SUCCESS):
            return  # ввод игнорируем

        if self.state == self.STATE_MAIN_MENU:
            self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
            self._handle_main_menu(text)
            return

        if self.state == self.STATE_LOG_LIST:
            self.output.push(f">[{self.current_user}]: {text}\n", instant=True)
            if not self.log_entries:
                # Пустой журнал: 1 — создать запись, 0 — назад в главное меню
                if text == "1":
                    self._start_new_log_entry()
                elif text == "0" or text == "":
                    self._enter_main_menu()
                return
            if text == "0" or text == "":
                self._enter_main_menu()
            elif text.isdigit():
                choice = int(text)
                if 1 <= choice <= len(self.log_entries):
                    self._open_log_entry(self.log_entries[choice - 1])
                elif choice == len(self.log_entries) + 1:
                    self._start_new_log_entry()
            return

        if self.state == self.STATE_LOG_VIEW:
            self._enter_log_list()
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
            elif text:
                self._send_chat_message(text)
            return

        if self.state == self.STATE_CHAT_SAVED:
            self._enter_chat_menu()
            return

    def _handle_main_menu(self, text):
        if text == "0":
            self.state = self.STATE_CLOSING
            self.output.push("\nЗавершение сеанса...\nВыключение...\n")
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
                self._enter_log_list()
                return
            self._new_log_title = text
            self.output.push("\nВведите запись. Напишите END в конце:")
            return
        if text.upper() == "END":
            content = "\n".join(self.new_log_lines)
            self._save_new_log_entry(self._new_log_title, content)
            self._new_log_title = None
            self.new_log_lines = []
            self._enter_log_list()
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
            if event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.key == pygame.K_UP:
                self.output.scroll(SCROLL_STEP, self._current_max_lines())
            elif event.key == pygame.K_DOWN:
                self.output.scroll(-SCROLL_STEP, self._current_max_lines())
            elif event.key == pygame.K_RETURN:
                self._play("clack")
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
            # Сюда же в будущем можно добавить другие обработчики новых
            # дисков — например, чтение содержимого голодиска без маркера.
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
            # Момент нажатия уже обработан в handle_event — здесь только
            # отслеживаем длительность удержания для последующего автоповтора.
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

        bar_x = (RENDER_W - SPLASH_BAR_WIDTH) // 2
        bar_y = RENDER_H - 90

        # Полупрозрачная тёмная подложка под текст и прогресс-бар,
        # чтобы они не терялись на светлых участках картинки.
        panel_padding = 16
        panel_width = SPLASH_BAR_WIDTH + panel_padding * 2
        panel_top = bar_y - self.font.get_linesize() - 6 - panel_padding
        panel_height = (bar_y + SPLASH_BAR_HEIGHT) - panel_top + panel_padding
        panel_x = (RENDER_W - panel_width) // 2
        panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 160))
        surf.blit(panel, (panel_x, panel_top))

        label = f"ЗАГРУЗКА {self.splash_progress:03d}%"

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

    def render(self):
        surf = self.render_surface
        surf.fill(COLOR_BG)

        if self.state == self.STATE_SPLASH:
            self._render_splash(surf)
            scaled = pygame.transform.smoothscale(surf, (WINDOW_W, WINDOW_H))
            self.window.blit(scaled, (0, 0))
            pygame.display.flip()
            return

        y = MARGIN
        line_h = self.font.get_linesize() + LINE_SPACING
        n = self._current_max_lines()

        if self.fixed_header:
            # Шапка закреплена сверху и не является частью прокручиваемого буфера —
            # рисуется каждый кадр напрямую, независимо от output.lines.
            for header_line in HEADER_BANNER.split("\n"):
                header_surf = self.font.render(header_line, True, COLOR_TEXT)
                surf.blit(header_surf, (MARGIN, y))
                y += line_h

            # Строка статуса: дата слева, пользователь справа, одна строка.
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
        y += line_h  # строка под индикатор всегда резервируется, даже если он не показан

        visible = self.output.visible_lines(n)
        for line in visible:
            text_surf = self.font.render(line, True, COLOR_TEXT)
            surf.blit(text_surf, (MARGIN, y))
            y += line_h

        if self.output.has_more_below():
            indicator = self.font.render("v Листать вниз v", True, COLOR_DIM)
            surf.blit(indicator, (MARGIN, y))
        y += line_h  # аналогично резервируем строку снизу

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
