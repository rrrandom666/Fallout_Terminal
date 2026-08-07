Система взлома и программирования для НРИ во вселенной Fallout
Версия: 1.0
Автор: Random

# 1. Введение
## 1.1. Концепция
Игрок выступает в роли археолога цифрового прошлого — исследует довоенные системы, восстанавливает фрагменты кода и учится программировать на архаичных языках управления инфраструктурой.

Ключевые принципы системы:

- **Реальное знание = реальная сила.** Игрок должен понимать логику кода, синтаксис команд и структуру предметной области, чтобы писать рабочие программы.

- **Прогрессия через исследование.** Чем больше игрок исследует мир, тем больше операторов и сущностей он открывает.

- **Социальное взаимодействие.** Игроки могут обмениваться знаниями, что создаёт естественную кооперацию.

- **Честная обратная связь.** Мир реагирует на программы игрока предсказуемо, но не всегда так, как ожидалось, подталкивая к экспериментам и изучению.

## 1.2. Два вектора прогрессии
1. Синтаксис (операторы): Что можно делать.

2. Семантика (сущности): С чем можно делать.

Игрок может знать все операторы, но без знания правильных имён сущностей его программы будут бесполезны. И наоборот — знание сущностей без операторов не позволяет ничего с ними делать.

# 2. Пул операторов кода
Все операторы разделены на три уровня сложности. Игрок начинает с 5 случайных операторов из базового уровня и постепенно открывает остальные через исследование, восстановление сниппетов и обмен с другими игроками.

## 2.1. Базовые операторы (15-20 шт.)
Прямое управление объектами. Не требуется логики.

| Оператор	           | Описание                           | Пример использования                 |
|----------------------|------------------------------------|--------------------------------------|
| open(entity)         | Открыть объект                     | open(door_01)                        | 
| close(entity)        | Закрыть объект                     | close(door_01).                      |
| lock(entity)         | Заблокировать объект               | lock(terminal_02)                    |
| unlock(entity)       | Разблокировать объект              | unlock(container_05)                 |
| activate(entity)     | Активировать объект (включить)     | activate(turret_03)                  |
| deactivate(entity)   | Деактивировать объект (выключить)  | deactivate(turret_03)                |
| read(entity)	       | Прочитать данные с объекта	        | read(terminal_01).                   |
| write(entity, data)  | Записать данные в объект           | write(terminal_01, "ACCESS_GRANTED") |
| send(entity, signal) | Отправить сигнал объекту           | send(security_panel, "ALERT")        |
| getState(entity)     | Получить текущее состояние объекта | getState(door_01) → "locked"         |
| wait(seconds)        | Пауза в выполнении                 | wait(10)                             |
| print(text)          | Вывести текст на терминал          | print("Door opened")                 |
| input()              | Получить ввод от пользователя      | code = input()                       |
| sleep()              | Перевести систему в спящий режим   | sleep()                              |
| reboot()             | Перезагрузить систему              | reboot()                             |
| getTime()	           | Получить системное время           | t = getTime()                        |
| compare(a, b).       | Сравнить два значения	            | compare(state, "open")               |

2.2. Продвинутые операторы (10-15 шт.) — «Логика и структуры»
Условное выполнение, циклы, функции.

Оператор	Описание	Пример использования
if (condition) { ... }	Условное выполнение	if (getState(door_01) == "locked") { unlock(door_01) }
else { ... }	Альтернативное выполнение	if (state == "open") { close() } else { open() }
for (i in range(n)) { ... }	Цикл с известным числом итераций	for (i in range(5)) { activate(turret_01 + i) }
while (condition) { ... }	Цикл с условием	while (getState(sensor) == "triggered") { wait(1) }
break	Выход из цикла	if (error == true) { break }
continue	Переход к следующей итерации	if (target == null) { continue }
function name(params) { ... }	Определение пользовательской функции	function openAllDoors() { ... }
return value	Возврат значения из функции	return getState(target)
list = [item1, item2]	Создание списка объектов	doors = [door_01, door_02, door_03]
for (item in list) { ... }	Итерация по списку	for (d in doors) { open(d) }
try { ... } except { ... }	Обработка ошибок	try { activate(turret_05) } except { print("Not found") }
and / or / not	Логические операторы	if (state == "open" and access == "admin")
2.3. Сложные операторы (5-7 шт.) — «Системный уровень»
Работа с сетью, многопоточность, инжекция кода.

Оператор	Описание	Пример использования
scanNetwork()	Сканировать сеть и вернуть список всех подключённых устройств	devices = scanNetwork()
getLog(entity)	Получить журнал событий объекта	log = getLog(terminal_main)
override(entity, param, value)	Принудительно изменить параметр объекта (даже если защищён)	override(turret_03, "targeting", "hostile")
spawnThread(script)	Запустить скрипт в отдельном потоке	spawnThread(alarm_system)
killThread(thread_id)	Остановить поток	killThread(thread_01)
injectCode(entity, code)	Внедрить код в работающий процесс	injectCode(terminal_guard, "open(all_doors)")
listen(port, callback)	Слушать сетевой порт и реагировать на сигналы	listen(8080, onSignalReceived)
3. Система сущностей (предметная область)
Сущности — это объекты игрового мира, с которыми хакер может взаимодействовать через терминал. Знание правильных имён и атрибутов сущностей — ключевая часть прогрессии.

3.1. Структура сущности
json
{
  "name": "door_01",
  "type": "door",
  "attributes": {
    "state": ["closed", "open", "locked", "disabled", "broken"],
    "access_level": ["public", "restricted", "classified"],
    "material": ["steel", "reinforced", "blast"]
  },
  "available_actions": ["open", "close", "lock", "unlock", "getState", "override"]
}
3.2. Типы сущностей (примеры для вселенной Fallout)
Тип	Примеры сущностей	Ключевые атрибуты
Door	door_01, vault_door_main, cell_door_03	state, access_level, material
Turret	turret_03A, turret_03B, turret_05	state, ammo, targeting, health
Terminal	terminal_guard, terminal_main, terminal_engineer	state, access_level, connected_devices
Generator	generator_01, backup_gen, reactor_core	state, fuel, output
Sensor	motion_sensor_01, heat_sensor_03, pressure_sensor	state, trigger_value, current_value
Speaker	speaker_01, alarm_system, intercom	state, volume, last_message
Container	locker_05, safe_vault, ammo_box	state, contents, access_level
Light	light_01, emergency_light, siren	state, intensity, color
Network	security_hub, mainframe, satellite_relay	state, connected_nodes, bandwidth
Robot	protectron_01, mr_handy_02, sentry_bot	state, health, weapon, target
3.3. Как игрок узнаёт сущности
Способ	Описание	Пример
Сканирование сети	Используя scanNetwork()	Получает список: ["turret_03A", "turret_03B", "door_01"]
Осмотр	Используя getState(entity)	Узнаёт атрибуты объекта: state: "locked", access_level: "restricted"
Документация	Находит голодиск с технической документацией	Получает полный словарь сущностей для конкретной системы
Логи	Используя getLog(entity)	Узнаёт историю действий с объектом, имена связанных сущностей
Наблюдение	Изучает физические объекты в игре	На двери написано VAULT_DOOR_03 → пробует использовать это имя
Обмен	Получает информацию от других игроков	Импортирует сущности из чужой библиотеки
4. Стартовые знания игрока
4.1. Случайная генерация
При создании персонажа игрок получает 5 случайных операторов из базового уровня (из 15-20 доступных). У каждого игрока уникальный набор, что создаёт разные стили игры и стимулирует кооперацию.

4.2. Пример распределения
Игрок	Стартовые операторы	Стиль игры
Алиса	open, close, getState, print, wait	Исследователь-наблюдатель. Изучает окружение, но слабо влияет на него.
Боб	activate, deactivate, send, read, write	Контролёр. Управляет устройствами, но без логики и автоматизации.
Чарли	lock, unlock, sleep, reboot, input	Саботажник. Блокирует и перезагружает системы, но не может их активировать.
4.3. Начальные сущности
Игрок начинает с нулевым знанием сущностей. Он должен исследовать мир, чтобы узнать имена объектов, которыми можно управлять.

5. Механика обмена информацией
5.1. Библиотека знаний
У каждого игрока есть локальная база знаний (JSON-файл), содержащая:

Изученные операторы (с указанием уровня сложности)

Известные сущности (с их атрибутами и действиями)

Восстановленные сниппеты (готовые фрагменты кода)

5.2. Процесс обмена
Игрок копирует часть своей библиотеки на голодиск (флешку).

Другой игрок подключает этот голодиск к своему терминалу.

Терминал сравнивает содержимое с локальной библиотекой игрока.

Выводится список новой информации, доступной для импорта.

Игрок выбирает, что импортировать.

5.3. Интерфейс импорта
text
=== IMPORT PROTOCOL ===
Обнаружена библиотека: [ХАКЕР_БОБ]

Доступная для импорта информация:
[1] Оператор: for (Продвинутый) — НОВЫЙ!
[2] Оператор: if (Базовый) — УЖЕ ИЗВЕСТЕН
[3] Сущность: turret_04 (Тип: турель) — НОВАЯ!
[4] Сниппет: AutoAim_Turret (Содержит: for, if, activate) — НОВЫЙ!

Введите номера для импорта (через пробел):
> 1 3 4
ИМПОРТ ЗАВЕРШЁН. Добавлено 3 новых элемента.
5.4. Ограничения обмена
Ограничение	Описание
Пререквизиты	Нельзя импортировать операторы продвинутого уровня, если у игрока изучено менее 10 базовых операторов.
Физический доступ	Импорт сущности не даёт доступа к самому объекту в игре — игрок всё равно должен его найти.
Доверие	Игрок не может принудительно импортировать информацию — только по своему выбору.
6. Реакция вселенной и обратная связь
6.1. Принцип честной обратной связи
Мир реагирует на программы игрока предсказуемо, но не всегда так, как ожидалось. Это создаёт пространство для экспериментов и обучения.

6.2. Примеры реакций
Действие игрока	Реакция системы	Что игрок понимает
activate(turret_03)	ERROR: ENTITY NOT FOUND IN NETWORK	Неправильное имя сущности. Нужно просканировать сеть.
scanNetwork()	["turret_03A", "turret_03B", "turret_03C"]	Теперь знает правильные имена турелей.
activate(turret_03A)	ERROR: AMMO DEPLETED	Турель есть, но нет боеприпасов.
unlock(door_01)	ERROR: ACCESS_DENIED. REQUIRES ADMIN_OVERRIDE	Недостаточно прав. Нужен override.
override(door_01, "state", "open")	WARNING: OVERRIDE DETECTED. SENDING ALERT TO SECURITY HUB	override работает, но привлекает внимание.
spawnThread(open_all_doors)
injectCode(terminal_guard, "open(door_01)")	(Тишина. Дверь открывается без тревоги.)	Комбинация потоков и инжекции позволяет действовать скрытно.
6.3. Принципы проектирования реакций
Ошибки информативны. Система всегда говорит, почему команда не сработала.

Нет магии. Система не выполняет действий, которые не заложены в её логику.

Действия имеют последствия. Каждое действие (особенно override и injectCode) влияет на состояние мира.

Мир обучает. Через серию проб и ошибок игрок постепенно понимает правила системы.

7. Техническая реализация (Python)
7.1. Архитектура
text
/terminal_system/
├── main.py                 # Главный скрипт терминала
├── entities.json           # Словарь всех сущностей в игре
├── operators.py            # Логика выполнения команд
├── game_world.py           # Симулятор мира (состояние объектов)
├── player_library.json     # Библиотека знаний игрока
├── snippets/               # Папка с голодисками-сниппетами
│   ├── snippet_01.dat
│   ├── snippet_02.dat
│   └── ...
└── puzzles/                # Генератор головоломок для деобфускации
    ├── generator.py
    └── templates/
7.2. Структура entities.json
json
{
  "door_01": {
    "type": "door",
    "attributes": {
      "state": "locked",
      "access_level": "restricted",
      "material": "steel"
    },
    "available_actions": ["open", "close", "lock", "unlock", "getState", "override"],
    "connections": ["terminal_guard", "security_hub"]
  },
  "turret_03A": {
    "type": "turret",
    "attributes": {
      "state": "inactive",
      "ammo": 120,
      "targeting": "neutral",
      "health": 100
    },
    "available_actions": ["activate", "deactivate", "getState", "override", "getLog"],
    "connections": ["security_hub", "power_grid_01"]
  }
}
7.3. Логика выполнения команды (пример)
python
def execute_command(command, player):
    # Парсинг команды
    func_name, args = parse(command)
    
    # Проверка, знает ли игрок этот оператор
    if func_name not in player.known_operators:
        return "ERROR: UNKNOWN COMMAND"
    
    # Проверка, знает ли игрок сущность
    if args[0] not in player.known_entities:
        return "ERROR: ENTITY NOT FOUND IN NETWORK"
    
    # Выполнение действия
    entity = game_world.get_entity(args[0])
    result = entity.execute(func_name, args[1:])
    
    # Логирование действия
    game_world.log_action(player.name, func_name, args)
    
    return result
7.4. Симулятор мира
python
class GameWorld:
    def __init__(self):
        self.entities = load_entities("entities.json")
        self.event_log = []
        self.alert_level = 0
    
    def get_entity(self, name):
        return self.entities.get(name)
    
    def log_action(self, player, action, args):
        self.event_log.append({
            "time": getTime(),
            "player": player,
            "action": action,
            "args": args
        })
        
        # Проверка на обнаружение
        if action == "override" or action == "injectCode":
            self.alert_level += 25
            if self.alert_level >= 100:
                trigger_security_response()
8. Пример игровой сессии
Участники
Алиса (Хакер, стартовые операторы: open, close, getState, print, wait)

Боб (Хакер, стартовые операторы: activate, deactivate, send, read, write)

Сценарий
1. Алиса исследует комнату

text
Алиса: Я подхожу к терминалу и запускаю сканирование.
Терминал: > print("Scanning...")
> getState(door_01)
> "locked"
> getState(door_02)
> "closed"
Алиса узнала, что двери существуют, но не может их открыть (у неё нет unlock).

2. Алиса передаёт информацию Бобу

text
Алиса: Я записываю имена дверей на голодиск и отдаю Бобу.
Боб: Подключаю голодиск к своему терминалу.
Терминал: Обнаружены новые сущности: door_01, door_02. Импортировать?
Боб: Да.
3. Боб пробует открыть дверь

text
Боб: > unlock(door_01)
Терминал: ERROR: ACCESS_DENIED. REQUIRES ADMIN_OVERRIDE
Боб: У меня нет override...
4. Кооперация

text
Алиса: У меня есть open, но нет unlock.
Боб: У меня есть unlock, но он не работает.
Алиса: Может, нужно сначала получить доступ?
Боб: > read(terminal_guard)
Терминал: "ACCESS_LEVEL: RESTRICTED. REQUIRES PASSWORD."
Алиса: Нужно найти пароль или использовать override.
5. Поиск решения

text
Боб: Я иду к другому терминалу и нахожу голодиск с документацией.
Терминал: Обнаружен сниппет: "Admin_Override_Protocol"
Алиса: Я восстановлю его (решает головоломку с деобфускацией).
Терминал: Сниппет восстановлен. Добавлен оператор: override.
6. Успех

text
Алиса: > override(door_01, "state", "open")
Терминал: WARNING: OVERRIDE DETECTED. SENDING ALERT TO SECURITY HUB
Алиса: Чёрт, тревога! Быстро заходим!
Итог: Команда потратила 20 минут на исследование, обмен информацией и решение головоломки, но добилась результата. Тревога — расплата за использование override без скрытности (в следующий раз они попробуют injectCode или spawnThread).