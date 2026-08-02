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

import pygame

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

MAX_PASSWORD_ATTEMPTS = 4
CORRECT_PASSWORD = "HAPPINESS"

# Закреплённая шапка — отображается статично сверху во ВСЕХ состояниях,
# включая BOOT и PASSWORD (они делят один и тот же экран/буфер — текст
# загрузки и запрос пароля идут последовательно на одном месте под шапкой).
HEADER_BANNER = (
    "========== ROBCO INDUSTRIES UNIFIED OPERATING SYSTEM ==========\n"
    "============ COPYRIGHT 2075-2077 ROBCO INDUSTRIES ============="
)
HEADER_LINE_COUNT = len(HEADER_BANNER.split("\n"))
HEADER_GAP_LINES = 1  # пустая строка-отступ между шапкой и прокручиваемым текстом

FOREMANS_LOG_DIR = os.path.join("FalloutDocuments", "Foreman's Log")

# Звуки — реальные файлы из проекта, лежат в папке media/ рядом с main.py.
# Регистр в именах сохранён как есть (важно на Linux — там ФС регистрозависима).
SOUND_DIR = "media"
SOUND_FILES = {
    "clicking": "FalloutSoundClicking.mp3",  # печать текста (лупом, пока идёт анимация)
    "clack": "FalloutSoundClack.mp3",        # каждое нажатие клавиши игроком
    "complete": "FalloutSoundComplete.wav",  # успешное действие (сохранение, дверь, соединение)
    "error": "FalloutSoundError.wav",        # неверный пароль, ошибка, неизвестная команда
    "unlocked": "FalloutSoundUnlocked.wav",  # верный пароль, доступ разрешён
}

FINANCIAL_REPORT_TEXT = (
    "КВАРТАЛЬНЫЙ ХОЗЯЙСТВЕННЫЙ ОТЧЁТ\n"
    "----------------------------\n"
    "Внутренняя информация корпорации Vault-Tec.\n"
    "Уровень доступа: БИЛЛ ВАССОН\n\n"
    "[Замените этот текст своими игровыми материалами]"
)

SAFETY_REPORT_TEXT = (
    "ОТЧЁТ ПО БЕЗОПАСНОСТИ\n"
    "--------------------\n"
    "В текущем цикле инцидентов не выявлено.\n\n"
    "[Замените этот текст своими игровыми материалами]"
)


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
    STATE_BOOT = "BOOT"
    STATE_PASSWORD = "PASSWORD"
    STATE_CLOSING = "CLOSING"
    STATE_MAIN_MENU = "MAIN_MENU"
    STATE_FINANCIAL = "FINANCIAL"
    STATE_SAFETY = "SAFETY"
    STATE_LOG_LIST = "LOG_LIST"
    STATE_LOG_VIEW = "LOG_VIEW"
    STATE_LOG_NEW = "LOG_NEW"
    STATE_DOOR = "DOOR"
    STATE_CHAT = "CHAT"

    def __init__(self):
        pygame.init()
        pygame.key.set_repeat(400, 40)  # удержание клавиши повторяет KEYDOWN (в т.ч. для прокрутки)
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

        self.scanlines = make_scanlines(RENDER_W, RENDER_H)
        self.vignette = make_vignette(RENDER_W, RENDER_H)

        self.state = self.STATE_BOOT
        self.fixed_header = False  # True — рисуем шапку статично сверху (не часть прокрутки)
        self.door_status = "ЗАКРЫТА"
        self.log_entries = []
        self.new_log_lines = []

        # Авторизация
        self.password_attempts_used = 0

        # Отложенное закрытие терминала (даём прочитать финальное сообщение)
        self._close_at = None

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

        self._boot()

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

    # ---------------------------------------------------------------- boot
    def _boot(self):
        self.fixed_header = True
        self.output.push(
            "Добро пожаловать в терминальную сеть ROBCO Industries (TM)\n"
            "-----------------\n"
            "Инициализация...\n"
            "[Загрузка системы...]\n"
            "[Запуск протоколов...]\n"
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

    def _enter_main_menu(self):
        self.state = self.STATE_MAIN_MENU
        self.fixed_header = True
        self.output.clear()
        self.output.push(
            "Вы авторизованы как: БИЛЛ ВАССОН\n"
            "[1. Журнал                 ]\n"
            "[2. Хозяйственные отчёты   ]\n"
            "[3. Отчёты по безопасности ]\n"
            "[4. Отчёты по счастью      ]\n"
            "[5. Управление дверьми     ]\n"
            "[6. Чат со S.C.O.P.E.      ]\n"
            "[0. Закрыть терминал       ]\n"
        )

    def _list_log_entries(self):
        try:
            entries = [f for f in os.listdir(FOREMANS_LOG_DIR) if f.lower().endswith(".md")]
            entries.sort()
        except FileNotFoundError:
            entries = []
        return entries

    def _enter_log_list(self):
        self.state = self.STATE_LOG_LIST
        self.fixed_header = True
        self.output.clear()
        self.log_entries = self._list_log_entries()
        text = "\n[Журнал]\n"
        for i, entry in enumerate(self.log_entries, 1):
            text += f"\n [{i}. {os.path.splitext(entry)[0]}]"
        text += f"\n [{len(self.log_entries) + 1}. Создать новую запись]"
        text += "\n\n [0. В Главное Меню]\n"
        self.output.push(text)

    def _open_log_entry(self, filename):
        self.state = self.STATE_LOG_VIEW
        self.fixed_header = True
        self.output.clear()
        path = os.path.join(FOREMANS_LOG_DIR, filename)
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
        os.makedirs(FOREMANS_LOG_DIR, exist_ok=True)
        filepath = os.path.join(FOREMANS_LOG_DIR, filename)
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
        self.output.push(
            "\n[Интерфейс контроля защищённых дверей MaxLock]\n"
            f"СТАТУС: {self.door_status}\n\n"
            "[1. Открыть дверь ]\n"
            "[2. Закрыть дверь]\n"
            "[0. В Главное Меню]\n"
        )

    # -------------------------------------------------------------- чат-ИИ
    MQTT_CONNECT_GRACE_SECONDS = 3.0

    def _enter_chat(self):
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
        self.output.push(f">[БИЛЛ ВАСССОН]: {text}\n", instant=True)
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

    # -------------------------------------------------------------- ввод
    def handle_submit(self, raw_text):
        text = raw_text.strip()

        if self.state == self.STATE_PASSWORD:
            if text.upper() == CORRECT_PASSWORD:
                self.output.push(f">[ПОЛЬЗОВАТЕЛЬ]: {text}\n", instant=True)
                self._play("unlocked")
                self._enter_main_menu()
                return
            self.password_attempts_used += 1
            attempts_left = MAX_PASSWORD_ATTEMPTS - self.password_attempts_used
            if attempts_left <= 0:
                self._play("error")
                self.state = self.STATE_CLOSING
                self.output.push("\nДОСТУП ЗАПРЕЩЁН.\nВыключение...\n", instant=True)
                self._close_at = time.time() + 2.5
            else:
                self.output.push(f">[ПОЛЬЗОВАТЕЛЬ]: {text}\n", instant=True)
                self._play("error")
                self._enter_password(extra_message="НЕВЕРНЫЙ ПАРОЛЬ.")
            return

        if self.state == self.STATE_CLOSING:
            return  # терминал уже закрывается, ввод игнорируем

        if self.state == self.STATE_MAIN_MENU:
            self._handle_main_menu(text)
            return

        if self.state == self.STATE_FINANCIAL or self.state == self.STATE_SAFETY:
            self._enter_main_menu()
            return

        if self.state == self.STATE_LOG_LIST:
            if text == "0" or text == "":
                self._enter_main_menu()
            elif text.isdigit():
                choice = int(text)
                if 1 <= choice <= len(self.log_entries):
                    self._open_log_entry(self.log_entries[choice - 1])
                elif choice == len(self.log_entries) + 1:
                    self.state = self.STATE_LOG_NEW
                    self.fixed_header = True
                    self.output.clear()
                    self.new_log_lines = []
                    self.output.push(
                        "\n=== Создать новую запись ===\nЗаголовок:"
                    )
            return

        if self.state == self.STATE_LOG_VIEW:
            self._enter_log_list()
            return

        if self.state == self.STATE_LOG_NEW:
            self._handle_log_new_input(text)
            return

        if self.state == self.STATE_DOOR:
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

        if self.state == self.STATE_CHAT:
            if text.lower() == "exit":
                self._mqtt_disconnect()
                self._enter_main_menu()
            elif text:
                self._send_chat_message(text)
            return

    def _handle_main_menu(self, text):
        if text == "1":
            self._enter_log_list()
        elif text == "2":
            self.state = self.STATE_FINANCIAL
            self.fixed_header = True
            self.output.clear()
            self.output.push("\n" + FINANCIAL_REPORT_TEXT + "\n\n[Нажмите Enter, чтобы вернуться...]")
        elif text == "3":
            self.state = self.STATE_SAFETY
            self.fixed_header = True
            self.output.clear()
            self.output.push("\n" + SAFETY_REPORT_TEXT + "\n\n[Нажмите Enter, чтобы вернуться...]")
        elif text == "4":
            self.state = self.STATE_SAFETY
            self.fixed_header = True
            self.output.clear()
            self.output.push("\n" + SAFETY_REPORT_TEXT + "\n\n[Нажмите Enter, чтобы вернуться...]")
        elif text == "5":
            self._enter_door_control()
        elif text == "6":
            self._enter_chat()
        elif text == "0":
            self.running = False
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

    def _current_max_lines(self):
        return self.max_visible_lines_header if self.fixed_header else self.max_visible_lines_full

    # --------------------------------------------------------------- кадр
    def update(self, dt):
        self.output.update()
        self._sync_typing_loop(self.output.is_typing())
        self._poll_chat_incoming()
        self._poll_chat_status()
        self.cursor_timer += dt
        if self.cursor_timer > 0.5:
            self.cursor_timer = 0.0
            self.cursor_visible = not self.cursor_visible

        if self._close_at is not None and time.time() >= self._close_at:
            self.running = False

    def render(self):
        surf = self.render_surface
        surf.fill(COLOR_BG)

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

        if not self.output.is_typing() and self.state != self.STATE_CLOSING:
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
