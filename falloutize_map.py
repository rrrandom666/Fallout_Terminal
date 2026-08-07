import osmium
from PIL import Image, ImageOps
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from shapely.geometry import Polygon, LineString, Point
import numpy as np
import os
import json
from math import radians, sin, cos, sqrt, atan2

class OSMHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.nodes = {}
        self.ways = []
        self.areas = []
        # Для графа дорог нужны не только координаты (как в self.ways —
        # они используются для отрисовки линий на картинке), а именно
        # ID узлов вдоль каждой дороги: только по ним можно понять, что
        # две разные дороги пересекаются/соединяются в общей точке.
        self.highway_ways = []

    def node(self, n):
        self.nodes[n.id] = (n.location.lon, n.location.lat)

    def way(self, w):
        if 'highway' in w.tags:
            coords = []
            node_ids = []
            for node in w.nodes:
                if node.ref in self.nodes:
                    coords.append(self.nodes[node.ref])
                    node_ids.append(node.ref)
            if len(coords) >= 2:
                self.ways.append(coords)
            if len(node_ids) >= 2:
                self.highway_ways.append(node_ids)
        elif 'building' in w.tags or 'landuse' in w.tags:
            coords = []
            for node in w.nodes:
                if node.ref in self.nodes:
                    coords.append(self.nodes[node.ref])
            if len(coords) >= 3:
                self.areas.append(coords)

def extract_map_from_osm(osm_file, output_image='map_temp.png', bbox=None):
    """
    Извлекает карту из OSM файла и сохраняет как изображение
    
    Args:
        osm_file: путь к OSM файлу
        output_image: имя выходного файла
        bbox: кортеж (min_lon, min_lat, max_lon, max_lat) для обрезки

    Returns:
        (success, bounds, handler) — handler возвращается, чтобы не
        парсить .osm файл повторно при последующем построении графа дорог
        (см. build_road_graph).
    """
    handler = OSMHandler()
    handler.apply_file(osm_file)
    
    if not handler.ways and not handler.areas:
        print("Не найдено дорог или зданий в файле OSM")
        return False, None, None
    
    # Определяем границы карты
    all_coords = []
    for way in handler.ways:
        all_coords.extend(way)
    for area in handler.areas:
        all_coords.extend(area)
    
    if not all_coords:
        print("Нет данных для отображения")
        return False, None, None
    
    coords_array = np.array(all_coords)
    
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
    else:
        min_lon, min_lat = coords_array.min(axis=0)
        max_lon, max_lat = coords_array.max(axis=0)
    
    # Создаем изображение
    fig, ax = plt.subplots(figsize=(12, 12))
    
    # Рисуем дороги
    for way in handler.ways:
        x = [coord[0] for coord in way]
        y = [coord[1] for coord in way]
        ax.plot(x, y, color='black', linewidth=1.5, alpha=0.8)
    
    # Рисуем здания и территории
    for area in handler.areas:
        polygon = Polygon(area)
        if polygon.is_valid:
            x, y = polygon.exterior.xy
            ax.fill(x, y, color='gray', alpha=0.3, edgecolor='black', linewidth=0.5)
    
    ax.set_xlim(min_lon, max_lon)
    ax.set_ylim(min_lat, max_lat)
    ax.set_aspect('equal')
    ax.axis('off')
    
    plt.savefig(output_image, dpi=100, bbox_inches='tight', pad_inches=0)
    plt.close()
    
    # Возвращаем границы для привязки
    bounds = {
        "min_lat": float(min_lat),
        "max_lat": float(max_lat),
        "min_lon": float(min_lon),
        "max_lon": float(max_lon),
        "center_lat": float((min_lat + max_lat) / 2),
        "center_lon": float((min_lon + max_lon) / 2),
        "zoom_level": float((max_lat - min_lat) / 2)
    }
    
    return True, bounds, handler

def falloutize_image(path_in, path_out):
    """
    Применяет эффект Fallout к изображению
    """
    img = Image.open(path_in).convert("L")
    img = ImageOps.autocontrast(img, cutoff=2)
    img = ImageOps.posterize(img, 3)
    img = ImageOps.invert(img)
    # Дуотон: тёмный фон -> (0, 0, 0), светлый -> (69, 255, 90)
    img = ImageOps.colorize(img, black=(0, 0, 0), white=(69, 255, 90))
    img.save(path_out)
    print(f"Изображение сохранено как {path_out}")

def save_bounds_json(bounds, output_file):
    """
    Сохраняет привязку карты в JSON файл
    
    Args:
        bounds: словарь с границами карты
        output_file: путь к выходному JSON файлу
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(bounds, f, indent=2, ensure_ascii=False)
    print(f"Привязка карты сохранена в {output_file}")
    print(f"Границы: {bounds['min_lat']:.6f}°N - {bounds['max_lat']:.6f}°N, "
          f"{bounds['min_lon']:.6f}°E - {bounds['max_lon']:.6f}°E")


def _haversine_m(lat1, lon1, lat2, lon2):
    """Расстояние между двумя точками на сфере (в метрах) — используется
    как вес рёбер графа дорог."""
    R = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def build_road_graph(handler, bbox=None, output_json='images/road_graph.json'):
    """
    Строит граф дорожной сети из тех же handler.highway_ways, что уже
    считаны для отрисовки дорог на картинке — второй проход по .osm не
    нужен. Граф нужен терминалу, чтобы прокладывать маршрут ПО ДОРОГАМ
    (кратчайший путь), а не прямой линией через здания.

    Формат выходного JSON:
        {
          "nodes": {"<id узла>": [lat, lon], ...},
          "adjacency": {"<id узла>": {"<id соседа>": расстояние_в_метрах, ...}, ...}
        }
    Ключи — строки (так требует JSON), терминал при загрузке приводит их
    обратно к числам. adjacency уже содержит рёбра в обе стороны — граф
    неориентированный, дороги проходимы туда-обратно.

    Args:
        handler: OSMHandler, уже применённый к .osm файлу (см. extract_map_from_osm)
        bbox: кортеж (min_lon, min_lat, max_lon, max_lat) — та же область,
              что и на итоговой картинке; way, полностью лежащие за её
              пределами, отбрасываются, чтобы граф не раздувался на весь
              возможный региональный .osm-экстракт
        output_json: путь к выходному JSON файлу
    """
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
    else:
        min_lon = min_lat = max_lon = max_lat = None

    def in_bbox(lon, lat):
        if bbox is None:
            return True
        return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat

    # Оставляем только те дороги, что хотя бы частично попадают в область
    # карты (полностью посторонние way пропускаем).
    used_ways = [
        node_ids for node_ids in handler.highway_ways
        if any(in_bbox(*handler.nodes[nid]) for nid in node_ids if nid in handler.nodes)
    ]

    nodes_out = {}
    adjacency = {}

    def ensure_node(nid):
        key = str(nid)
        if key not in nodes_out:
            lon, lat = handler.nodes[nid]
            nodes_out[key] = [lat, lon]
            adjacency[key] = {}
        return key

    edge_count = 0
    for node_ids in used_ways:
        prev_id = None
        for nid in node_ids:
            if nid not in handler.nodes:
                # Узел вне загруженного региона (бывает на границах
                # экстракта) — обрываем цепочку тут, дальше начнём заново.
                prev_id = None
                continue

            cur_key = ensure_node(nid)

            if prev_id is not None:
                prev_key = ensure_node(prev_id)
                lon1, lat1 = handler.nodes[prev_id]
                lon2, lat2 = handler.nodes[nid]
                dist = _haversine_m(lat1, lon1, lat2, lon2)
                # Одна и та же пара узлов может встретиться в нескольких
                # way (дублирующиеся/параллельные сегменты) — оставляем
                # более короткое ребро.
                if cur_key not in adjacency[prev_key] or adjacency[prev_key][cur_key] > dist:
                    if cur_key not in adjacency[prev_key]:
                        edge_count += 1
                    adjacency[prev_key][cur_key] = dist
                    adjacency[cur_key][prev_key] = dist

            prev_id = nid

    graph = {"nodes": nodes_out, "adjacency": adjacency}

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(graph, f, ensure_ascii=False)

    print(f"Граф дорог сохранён в {output_json}")
    print(f"  Узлов: {len(nodes_out)}, рёбер: {edge_count}")
    return graph


def process_osm_to_fallout(osm_file, output_file='fallout_map.png',
                           bbox=None, json_output=None, graph_output=None):
    """
    Полный процесс: OSM -> изображение -> эффект Fallout + JSON привязка
    + граф дорог для прокладки маршрута
    
    Args:
        osm_file: путь к OSM файлу
        output_file: путь к выходному PNG файлу
        bbox: кортеж (min_lon, min_lat, max_lon, max_lat) для обрезки
        json_output: путь к выходному JSON файлу привязки (если None, генерируется автоматически)
        graph_output: путь к выходному JSON файлу графа дорог (если None, генерируется автоматически)
    """
    temp_file = 'temp_map.png'
    
    # Шаг 1: Извлекаем карту из OSM (один проход — handler переиспользуем
    # ниже для графа дорог, повторно файл не читаем)
    print("Извлечение карты из OSM файла...")
    success, bounds, handler = extract_map_from_osm(osm_file, temp_file, bbox)
    if not success:
        return False
    
    # Шаг 2: Применяем эффект Fallout
    print("Применение эффекта Fallout...")
    falloutize_image(temp_file, output_file)
    
    # Шаг 3: Сохраняем привязку
    if json_output is None:
        # Генерируем имя JSON файла на основе PNG
        base_name = os.path.splitext(output_file)[0]
        json_output = f"{base_name}_bounds.json"
    
    save_bounds_json(bounds, json_output)

    # Шаг 4: Строим и сохраняем граф дорог — используем ФАКТИЧЕСКИЕ
    # границы карты (bounds), а не исходный bbox-аргумент: если bbox не
    # был задан явно, extract_map_from_osm вычислил его сам по данным.
    if graph_output is None:
        base_name = os.path.splitext(output_file)[0]
        graph_output = f"{base_name}_roads.json"

    effective_bbox = (bounds["min_lon"], bounds["min_lat"], bounds["max_lon"], bounds["max_lat"])
    print("Построение графа дорог...")
    build_road_graph(handler, bbox=effective_bbox, output_json=graph_output)
    
    # Удаляем временный файл
    try:
        os.remove(temp_file)
    except:
        pass
    
    print(f"Готово! Файлы сохранены:")
    print(f"  - Карта: {output_file}")
    print(f"  - Привязка: {json_output}")
    print(f"  - Граф дорог: {graph_output}")
    return True

def generate_map_with_bounds(osm_file, output_dir='images', 
                             center_lat=None, center_lon=None, 
                             zoom_level=None,
                             output_filename='fallout_map.png'):
    """
    Упрощённая функция для генерации карты с привязкой и графом дорог
    
    Args:
        osm_file: путь к OSM файлу
        output_dir: директория для сохранения файлов
        center_lat: широта центра (опционально)
        center_lon: долгота центра (опционально)
        zoom_level: размер области в градусах (опционально)
        output_filename: имя выходного PNG файла
    """
    # Создаём директорию, если её нет
    os.makedirs(output_dir, exist_ok=True)
    
    # Формируем пути
    output_png = os.path.join(output_dir, output_filename)
    base_name = os.path.splitext(output_filename)[0]
    output_json = os.path.join(output_dir, f"{base_name}_bounds.json")
    output_graph = os.path.join(output_dir, f"{base_name}_roads.json")
    
    # Если заданы центр и зум, создаём bbox
    bbox = None
    if center_lat is not None and center_lon is not None and zoom_level is not None:
        min_lat = center_lat - zoom_level
        max_lat = center_lat + zoom_level
        min_lon = center_lon - zoom_level
        max_lon = center_lon + zoom_level
        bbox = (min_lon, min_lat, max_lon, max_lat)
        print(f"Область карты: {min_lat:.6f}°N - {max_lat:.6f}°N, "
              f"{min_lon:.6f}°E - {max_lon:.6f}°E")
    
    # Запускаем процесс
    return process_osm_to_fallout(osm_file, output_png, bbox, output_json, output_graph)

# Пример использования
if __name__ == "__main__":
    # Замените 'your_map.osm' на путь к вашему файлу
    osm_file = 'images/map.osm'
    
    # Вариант 1: Простая генерация с автоматическими границами
    # process_osm_to_fallout(osm_file, 'images/fallout_map.png')
    
    # Вариант 2: Генерация с указанием центра и зума
    generate_map_with_bounds(
        osm_file=osm_file,
        output_dir='images',
        output_filename='map.png'
        
    )
