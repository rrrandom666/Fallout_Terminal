# Vault-Tec Terminal (Pygame)

Полноценное окно терминала с bloom/scanline-эффектом, чатом с мастером
через MQTT и логикой из форкнутого `Fallout_Terminal`, перенесённой на
собственный рендер.

## Запуск на Mac (разработка/тест)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Без развёрнутого MQTT-брокера чат (пункт меню "7. Talk to Mainframe AI")
сам переключится в локальный тестовый режим — будет отвечать эхом на ваши
сообщения, чтобы можно было проверить интерфейс, не поднимая инфраструктуру.

Чтобы протестировать с реальным брокером (например, локальный Mosquitto
на том же Mac):

```bash
brew install mosquitto
brew services start mosquitto
VAULT_MQTT_HOST=127.0.0.1 python3 main.py
```

## Переменные окружения

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `VAULT_MQTT_HOST` | Адрес MQTT-брокера | `192.168.4.1` |
| `VAULT_TERMINAL_ID` | ID терминала (топики `vault/<id>/...`) | `terminal_1` |
| `TERMINAL_DEVMODE` | `1` — пропустить пароль при загрузке | `1` |
| `TERMINAL_TEST_MODE` | `1` — авто-выход через ~90 кадров (для CI/смоук-теста) | не задано |

## Управление

- Цифры + `Enter` — выбор пункта меню.
- `Enter` во время печати текста — мгновенно долить оставшийся текст (пропустить анимацию).
- `Esc` — закрыть терминал.
- В чате: обычный текст + `Enter`, `exit` — выйти из чата.

## Структура и что доделать

- **Foreman's Log** — читает/пишет `.md`-файлы в `FalloutDocuments/Foreman's Log/`,
  как в оригинальном форке. Просто положите эту папку рядом с `main.py`.
- **Financial/Safety Reports** — сейчас захардкожен текст-заглушка
  (`FINANCIAL_REPORT_TEXT`, `SAFETY_REPORT_TEXT` в начале файла) — замените
  на свои игровые материалы или на чтение из файлов, как Foreman's Log.
- **Tetris/Snake** — оставлены как заглушка (`STATE_GAME_STUB`). В оригинале
  они запускались отдельным подпроцессом; для единого рендер-пайплайна
  с bloom-эффектом их стоит переписать как ещё один `state`, рисующий
  игровое поле на том же `render_surface`, а не через `os.system(...)`.
- **Password hacking game** — сейчас заглушка (`ROBCO` или пустой ввод
  пропускает), `DEVMODE=1` по умолчанию вообще её скрывает. Оригинальную
  игру-минигру из `modules/passwordgame.py` можно адаптировать так же,
  как остальные экраны — как ещё один `state`.
- **Звуки** — пока не подключены; добавляются через `pygame.mixer`
  аналогично оригинальному скрипту (клик по вводу, ошибка, разблокировка
  и т.д.) — по одному `pygame.mixer.Sound(...)` на событие.

## Сборка в exe/бинарник (на целевой машине)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed \
    --add-data "FalloutDocuments:FalloutDocuments" \
    main.py
```

На Windows разделитель в `--add-data` — `;`, а не `:`:
```
pyinstaller --onefile --windowed --add-data "FalloutDocuments;FalloutDocuments" main.py
```

Помните: PyInstaller не кросс-компилирует — `.exe` для Windows нужно
собирать на самой Windows-машине (или в VM/CI), сборка на Mac даст
только macOS-приложение.
