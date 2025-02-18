import copy
import sys
import time
import random
from pathlib import Path
import uuid
import pandas
import psutil
from tqdm.auto import tqdm
import geopandas as gpd
import numpy as np
import math
from multiprocessing import Process, Queue
import queue
from shapely.geometry import Point, box, Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.validation import make_valid
from shapely import speedups
from ipyleaflet import Map, basemaps, basemap_to_tiles, GeoData, LayersControl, DrawControl, FullScreenControl, \
    ScaleControl, WidgetControl
from ipywidgets import HTML, RadioButtons, Layout

if speedups.available:
    speedups.enable()


def generate_file_name(filename: str):
    export_file_name = f'{time.strftime("%Y-%m-%d_%H-%M-%S")}_{str(filename)}'
    # Replace all characters in dict
    b = {' ': '', '.geojson': ''}
    for x, y in b.items():
        export_file_name = export_file_name.replace(x, y)
    return export_file_name


class Grid_Task:
    """
    One task which holds all necessary values like scanner_line_width and all specified Polygons in a MultiPolygon!
    """

    def __init__(self, scanner_line_width: float,
                 polygon_threshold: int,
                 dict_stc_tiles_long_lat: dict,
                 task_map: Map,
                 area_multipoly: MultiPolygon = None):

        # define the necessary properties
        self.scanner_line_width = scanner_line_width
        self.polygon_threshold = polygon_threshold
        self.dict_stc_tiles_long_lat = dict_stc_tiles_long_lat
        self.multipolygon: MultiPolygon = area_multipoly

        # define all interactive map properties
        self.task_polygon_color: str = self.__define_polygon_color()
        self.draw_control = self.__define_draw_control()
        self.task_map = task_map
        # self.task_map.add_control(self.draw_control)

    # setter
    def set_multipoly(self, new_multipoly: MultiPolygon = None):
        self.multipolygon = new_multipoly

    def set_task_polygon_color(self, hex_color_str: str):
        if len(hex_color_str) > 0:
            self.task_polygon_color = hex_color_str

    # getter
    def get_scanner_line_width(self):
        return self.scanner_line_width

    def get_multipoly(self):
        return self.multipolygon

    def get_task_polygon_color(self):
        return self.task_polygon_color

    # define
    def __define_polygon_color(self):
        random_number = random.randint(1118481, 16777215)
        hex_number = str(hex(random_number))
        color_hex_number = '#' + hex_number[2:]
        return color_hex_number

    def __define_draw_control(self):
        draw_control = DrawControl()
        draw_control.circle = {}
        draw_control.polyline = {}
        draw_control.circlemarker = {}
        draw_control.marker = {}
        draw_control.rectangle = {}
        draw_control.polygon = {
            "shapeOptions": {
                "fillColor": self.task_polygon_color,
                "color": self.task_polygon_color,
                "fillOpacity": 0.5
            },
            "drawError": {
                "color": "#dd253b",
                "message": "Something went wrong!"
            },
            "allowIntersection": False
        }

        # Popups
        message = HTML()
        message.value = f'<b>{self.scanner_line_width} meters</b>'
        message.placeholder = "Sensor line width"
        message.description = "Sensor line width"
        draw_control.popup = message

        return draw_control

    def confirm_areas(self):
        """
        We need to confirm the polygon choices.

        Sadly the DrawControl.data gets updated after on_draw(callfunc) finished.
        """
        print('### confirm_areas call ###\n')

        multipoly = self.__create_multipoly_from_data(self.draw_control.data)
        if not multipoly.is_empty:
            print("task multipolygon not empty, choices confirmed!")
            self.set_multipoly(multipoly)

    def __create_multipoly_from_data(self, geojson_data):
        print('### create_multipoly_from_data call ###\n')
        list_of_polys = []

        for obj in geojson_data:
            # TODO circle and rectangle should be possible too

            # Shapely Polygon
            poly_coords = []

            if obj['geometry']['type'] == 'Polygon':
                for coords in obj['geometry']['coordinates'][0][:-1][:]:
                    poly_coords.append(tuple(coords))

            if len(poly_coords) > 1:
                print('### poly_coords len > 1 ###\n', str(poly_coords))
                list_of_polys.append(Polygon(poly_coords))

        return MultiPolygon(list_of_polys)


class Grid_Generation_Task_Manager:
    """
    Create all tasks for an area which you need to set at the start.

    For each scanner_line_length you can set several MultiPolygon.

    For each one you need to create a separate task!
    """

    def __init__(self, list_of_scanner_line_widths, list_of_poly_thresholds, area_multipolygon: MultiPolygon,
                 area_name: str):
        print("Creating a grid generation task manager...")
        if check_edge_length_polygon_threshold(list_of_scanner_line_widths, list_of_poly_thresholds):

            self.area_multipoly = area_multipolygon

            # create map center for map location
            self.map_center = self.area_multipoly.centroid
            self.map_center_y, self.map_center_x = list(self.map_center.coords)[0]

            # create basic map for area of interest representation in every task
            mapnik = basemap_to_tiles(basemaps.OpenStreetMap.Mapnik)
            mapnik.base = True
            mapnik.name = 'Mapnik Layer'

            toner = basemap_to_tiles(basemaps.Stamen.Toner)
            toner.base = True
            toner.name = 'Toner Layer'

            bzh = basemap_to_tiles(basemaps.OpenStreetMap.BZH)
            bzh.base = True
            bzh.name = 'BZH layer'

            self.base_map = Map(
                layers=[mapnik, toner, bzh],
                center=(self.map_center_x, self.map_center_y),
                zoom=14,
                scroll_wheel_zoom=True
            )

            # create the area of interest overlay for the map
            # TODO take GeoData from self.area_layer which is GeoJSON and make it adjustable in a DrawControl
            area_data = {'geometry': [self.area_multipoly]}
            area_gdf = gpd.GeoDataFrame(area_data, geometry='geometry', crs=4326)
            self.area_layer = GeoData(geo_dataframe=area_gdf, style={'color': 'blue'}, name=area_name)
            self.base_map.add_layer(self.area_layer)

            # add controls
            self.base_map.add_control(LayersControl())
            self.base_map.add_control(FullScreenControl())
            self.base_map.add_control(ScaleControl(position='bottomleft'))

            # create all data and standard values
            self.list_of_tasks: list[Grid_Task] = []
            self.scanner_line_widths: list[float] = list_of_scanner_line_widths
            self.poly_thresholds: list[int] = list_of_poly_thresholds

            # calc the long/lat STC tile widths for grid generation
            stc_grid_edges_long_lat = generate_stc_grid_edges_long_lat(self.scanner_line_widths, self.area_multipoly)

            # create a task for every scanner_line_width (with its own draw_control)
            for scanner_line_width in self.scanner_line_widths:
                dict_long_lat = stc_grid_edges_long_lat[f'{scanner_line_width}']
                self.list_of_tasks.append(self.__create_task(scanner_line_width, dict_long_lat))

            # add radiobutton control
            # radiobuttons_layout = Layout(display='flex-grow')
            style = {'description_width': 'initial'}
            choose_scanner_line_width_widget = RadioButtons(
                options=list_of_scanner_line_widths,
                value=list_of_scanner_line_widths[-1],
                # layout=radiobuttons_layout,
                description='Scanner line widths:',
                style=style,
                disabled=False
            )
            for task in self.list_of_tasks:
                if task.scanner_line_width == list_of_scanner_line_widths[-1]:
                    self.base_map.add_control(task.draw_control)
            choose_scanner_line_width_widget.observe(self.__on_radiobutton_change)
            widget_control = WidgetControl(widget=choose_scanner_line_width_widget, position='topright')

            self.base_map.add_control(widget_control)

        else:
            print("Something is off! Check List of Tile Edge Lengths and its assigned List of Polygon Thresholds")
            sys.exit(1)

    def __len__(self):
        """
        Number of tasks
        """
        return len(self.list_of_tasks)

    def __create_task(self, scanner_line_width: float, dict_stc_tiles_long_lat: dict):

        poly_threshold_value = self.poly_thresholds[self.scanner_line_widths.index(scanner_line_width)]

        # task self.base_map as base for the task_map
        new_task = Grid_Task(scanner_line_width, poly_threshold_value, dict_stc_tiles_long_lat, self.base_map)

        return new_task

    def __exchange_draw_control(self, current_draw_control: DrawControl, new_draw_control: DrawControl):
        print("### Exchange Draw Control ###")
        self.base_map.remove_control(current_draw_control)
        self.base_map.add_control(new_draw_control)

    def __on_radiobutton_change(self, change):
        print("### on_radiobutton_change call ###")
        if change['name'] == 'value' and (change['new'] != change['old']):
            # print('### change ###\n', change)
            old_control = DrawControl()
            new_control = DrawControl()
            for task in self.list_of_tasks:
                if task.scanner_line_width == change['old']:
                    old_control = task.draw_control
                if task.scanner_line_width == change['new']:
                    new_control = task.draw_control
            self.__exchange_draw_control(old_control, new_control)

    def set_areas(self) -> Map:
        return self.base_map

    def extract_tasks(self):
        print('### extract_tasks call ###')
        for task in self.list_of_tasks:


            task.confirm_areas()

            # if task multipoly is not set: set it to the current value of self.area_multipoly for no specification
            if task.get_multipoly() is None:
                task.set_multipoly(self.area_multipoly)

        # sort the task list descending by its task scanner_line_width property
        self.list_of_tasks.sort(key=lambda x: x.scanner_line_width, reverse=True)

        return self.list_of_tasks


def valid_union(multipolygon: MultiPolygon):
    return make_valid(unary_union(multipolygon))


def get_long_lat_diff(square_edge_length_meter: float, startpoint_latitude: float):
    """

    :param square_edge_length_meter:
    :param startpoint_latitude:
    :return: width, height difference in longitude, latitude
    """
    earth_radius = 6378137  # earth radius, sphere

    # Coordinate offsets in radians
    new_lat_radians = square_edge_length_meter / earth_radius
    new_long_radians = square_edge_length_meter / (earth_radius * math.cos(math.pi * startpoint_latitude / 180))

    # OffsetPosition, decimal degrees
    # new_lat_decimal = startpoint_latitude + new_lat_radians * 180 / math.pi
    # new_long_decimal = startpoint_long + new_long_radians * 180 / math.pi

    # difference only, equals square_edge_length_meter in lat/long
    lat_difference = new_lat_radians * 180 / math.pi
    long_difference = new_long_radians * 180 / math.pi

    return abs(long_difference), abs(lat_difference)


def which_row_cells_within_area_boundaries(grid_area, selected_area, r, tile_height, c, tile_width,
                                           union_geo_coll=None) -> list:
    row_list_of_Polygons = []

    for idx, c0 in enumerate(c):
        c1 = c0 + tile_width
        y1 = r - tile_height
        Box_Polygon = box(c0, r, c1, y1)
        if Box_Polygon.within(grid_area) and Box_Polygon.within(selected_area):
            am_i_a_good_polygon = True
            if union_geo_coll is not None:
                if Box_Polygon.within(union_geo_coll):
                    am_i_a_good_polygon = False
                    # if new_Polygon.overlaps(union_geo_coll):
                    #     am_i_a_good_polygon = True
            if am_i_a_good_polygon:
                row_list_of_Polygons.append(Box_Polygon)

    return row_list_of_Polygons


def worker(input_queue, output_queue):
    """
    Necessary worker for python multiprocessing
    Has an Index, if needed...
    """
    for idx, func, args in iter(input_queue.get, 'STOP'):
        result = func(*args)
        output_queue.put([idx, result])


def processing_geometry_boundary_check(offset: tuple,  # (longitude_offset, latitude_offset)
                                       dict_tile_edge_lengths: dict,
                                       grid_area,
                                       selected_area,
                                       list_known_geo_coll_of_single_polys: list):
    print("Searching for a grid with offset", str(offset))
    xmin, ymin, xmax, ymax = grid_area.bounds

    # offset tuple (long, lat)
    rows = np.arange(ymin + offset[1], ymax + offset[1] + dict_tile_edge_lengths['tile_height'],
                     dict_tile_edge_lengths['tile_height'])
    rows = np.flip(rows)  # scan from top to bottom
    columns = np.arange(xmin + offset[0], xmax + offset[0] + dict_tile_edge_lengths['tile_width'],
                        dict_tile_edge_lengths['tile_width'])  # scan from left to right

    # Create queues for task input and result output
    task_queue = Queue()
    done_queue = Queue()

    num_of_processes = 2  # psutil.cpu_count(logical=False)  # cpu_count() - 1
    list_Polygons_selected_area = []

    # create tasks and push them into queue
    if len(list_known_geo_coll_of_single_polys) > 0:
        unpacked_multipoly = []
        for multipoly in list_known_geo_coll_of_single_polys:
            unpacked_multipoly.extend(list(multipoly.geoms))

        multipoly_known_geo_collections = MultiPolygon(unpacked_multipoly)
        valid_union_geo_coll = make_valid(unary_union(multipoly_known_geo_collections))

        for idx, row in enumerate(rows):
            one_task = [idx, which_row_cells_within_area_boundaries,
                        (grid_area, selected_area, row, dict_tile_edge_lengths['tile_height'], columns,
                         dict_tile_edge_lengths['tile_width'], valid_union_geo_coll)]
            task_queue.put(one_task)
    else:
        for idx, row in enumerate(rows):
            one_task = [idx, which_row_cells_within_area_boundaries,
                        (grid_area, selected_area, row, dict_tile_edge_lengths['tile_height'], columns,
                         dict_tile_edge_lengths['tile_width'])]
            task_queue.put(one_task)

    # Start worker processes
    for i in range(num_of_processes):
        Process(target=worker, args=(task_queue, done_queue)).start()

    for _ in tqdm(rows):
        try:
            list_row_Polygons = done_queue.get()
            if len(list_row_Polygons[1]) > 0:
                list_Polygons_selected_area.extend(list_row_Polygons[1])  # extend and not append to unbox received list
        except queue.Empty as e:
            print(e)

    # Tell child processes to stop
    for i in range(num_of_processes):
        task_queue.put('STOP')

    task_queue.close()
    done_queue.close()

    return MultiPolygon(list_Polygons_selected_area)


def check_real_start_points(geopandas_area_file, start_points):
    biggest_area = read_biggest_area_polygon_from_file(str(geopandas_area_file))

    start_points_list = []
    for p in start_points:
        start_points_list.append(p)

    for p in start_points_list:
        if not Point(p[0], p[1]).within(biggest_area):
            print("Given real start point", str(p), "is not inside given area", str(geopandas_area_file), "\nTry again")
            return False

    # no disturbances?
    return True


def check_edge_length_polygon_threshold(list_sensor_line_lengths, polys_threshold):
    """
    Check if count sensor lines lengths in list is equal given count of polygon thresholds.

    :param list_sensor_line_lengths: The list of one or more different sensor line lengths in meter.
    :param polys_threshold: The list of minimum numbers of squares (in one group) inside the grid which will get dropped.
    :return:
    """
    if not isinstance(list_sensor_line_lengths, list):
        # keep orientation intact
        # list_sensor_line_lengths = sorted(list_sensor_line_lengths, reverse=True)  # from greatest to smallest value
        print("Something went wrong with the list_sensor_line_lengths import. Expected list.")
        return False

    if not isinstance(polys_threshold, list):
        # keep orientation intact
        # polys_threshold = sorted(polys_threshold, reverse=True)  # from greatest to smallest value
        print("Something went wrong with the polys_threshold import. Expected list.")
        return False

    edge_length_array = np.array(list_sensor_line_lengths)
    poly_threshold_array = np.array(polys_threshold)

    if edge_length_array.shape != poly_threshold_array.shape:
        print("Number defined edge lengths don't match number polygon_threshold. Abort!")
        return False

    for i in edge_length_array:
        # check if negative values
        if i <= 0:
            print("No negative edge length value", str(i), "allowed. Abort!")
            return False

        elif i > 50:
            print("Warning: Grid edge length value greater 50m.\nDepending on the area size you might not get results.")

        # are the edge lengths divider from another?
        if i > np.amin(edge_length_array) and not i % np.amin(edge_length_array) == 0:
            print("Edge_length value", i, "doesn't match, cause it is not the exponentiation of a half",
                  "of the greatest value", str(np.amin(edge_length_array)), "\nThe tiles won't align!")
            return False

    # check if polygon_threshold list contains a negative value and replace it with a reasonable entry
    for poly_thresh in poly_threshold_array:
        if poly_thresh < 0:
            print("The polygon_threshold entry", poly_thresh,
                  "< 0 is invalid. Only zero or positiv values allowed. Abort!")
            return False

    return True


def read_biggest_area_polygon_from_file(dam_file_name):
    dam_geojson_filepath = Path("dams_single_geojsons", dam_file_name + '.geojson')
    gdf_dam = gpd.read_file(dam_geojson_filepath)

    gdf_dam_exploded = gdf_dam.geometry.explode(index_parts=True)  # no index_parts / .tolist()
    biggest_area = max(gdf_dam_exploded, key=lambda a: a.area)

    return biggest_area


def generate_stc_grid_edges_long_lat(scanner_line_widths, selected_area) -> dict:
    # generate tile width and height by calculating the biggest tile size to go for and divide it into the other tile sizes
    # hopefully clears out a mismatch in long/lat max and min values between biggest tile size and smallest

    list_long_lat_tuples = {}
    edge_length_max = max(scanner_line_widths)

    # latitude == width (y diff), longitude == height (x diff)
    tile_width_max, tile_height_max = get_long_lat_diff(edge_length_max * 2, selected_area.centroid.y)

    for edge_length_meter in scanner_line_widths:
        if (edge_length_max * 2) % (edge_length_meter * 2) == 0:
            divider = int((edge_length_max * 2) / (edge_length_meter * 2))
            tile_width = tile_width_max / divider
            tile_height = tile_height_max / divider
            list_long_lat_tuples[f'{edge_length_meter}'] = {"tile_width": tile_width,
                                                            "tile_height": tile_height}
    return list_long_lat_tuples


def generate_offset_list(num_offsets: int, grid_edge_length: dict):
    """
    Create a list of offsets within the boundaries of chosen grid edge length.
    :param num_offsets: number of offsets to calculate extra to origin
    :param grid_edge_length: edge length of the square to search for offset within
    :return: list of tuples (longitude, latitude) which first entry no offset, rest num_offsets * offset
    """

    cell_width, cell_height = grid_edge_length["tile_width"], grid_edge_length["tile_height"]
    offset = []
    rng = np.random.default_rng()

    # how many offsets except none
    if num_offsets <= 0:
        num_offsets = 5

    # generate random values between centroid
    random_long_offsets = rng.uniform(low=0,
                                      high=cell_width,
                                      size=num_offsets)
    random_lat_offsets = rng.uniform(low=0,
                                     high=cell_height,
                                     size=num_offsets)
    # fill offset list
    for i in range(num_offsets):
        offset.append((random_long_offsets[i], random_lat_offsets[i]))

    return offset


def keep_only_relevant_geo_coll_of_single_polygon_geo_coll(coll_single_polyons, polygon_threshold):
    """
    Check if single polygons inside Collection form a group and the groups joined area is below
     polygon_threshold * area of one polygon

    :param coll_single_polyons: Must be Multipolygon of many single Polygon

    :param polygon_threshold: Number of Polygons forming a group which area minimum will get considered relevant

    :return: List of geometry collection polygon groups which don't align and were considered relevant
    """
    print("Searching for irrelevant polygons now!")
    # remove Collection regions which are considered too small by polygon_threshold
    # need to unify at intersecting/touching edges and divide polygons with make_valid(unary_union()) -> see shapely doc
    coll_valid_unions = make_valid(unary_union(coll_single_polyons))
    area_one_polygon = coll_single_polyons.geoms[0].area
    relevant_union_coll = []
    if isinstance(coll_valid_unions, Polygon):
        if coll_valid_unions.area >= (area_one_polygon * polygon_threshold):
            relevant_union_coll.append(coll_valid_unions)
    else:
        print("Found", len(coll_valid_unions.geoms), "valid unified Polygons")
        # num_valid_un_poly = len(coll_valid_unions.geoms)
        for one_valid_union in tqdm(coll_valid_unions.geoms):
            if one_valid_union.area >= (area_one_polygon * polygon_threshold):
                relevant_union_coll.append(one_valid_union)
        print("Only", len(relevant_union_coll), "of them are considered relevant.")

    # Create queues for task input and result output
    task_queue = Queue()
    done_queue = Queue()
    num_of_processes = psutil.cpu_count(logical=False)  # cpu_count() - 1

    # after relevancy check for grouped polygons go for single polygons inside Group of Polys
    list_known_geo_coll_of_single_polys = []

    for idx, one_relevant_coll in enumerate(relevant_union_coll):
        one_task = [idx, keep_relevent_poly_helper, (coll_single_polyons, one_relevant_coll)]
        task_queue.put(one_task)

    # Start worker processes
    for _ in range(num_of_processes):
        Process(target=worker, args=(task_queue, done_queue)).start()

    for _ in tqdm(relevant_union_coll):
        try:
            idx, poly_list = done_queue.get()
            if len(poly_list) > 0:
                list_known_geo_coll_of_single_polys.append(MultiPolygon(poly_list))

        except queue.Empty as e:
            print(e)
        except queue.Full as e:
            print(e)

    # Tell workers to stop, work done
    for _ in range(num_of_processes):
        task_queue.put('STOP')

    task_queue.close()
    done_queue.close()

    return list_known_geo_coll_of_single_polys


def keep_relevent_poly_helper(coll_single_polyons, one_relevant_coll):
    polygon_list = []
    for one_single_poly in coll_single_polyons.geoms:
        # which single Polygon is actually inside a relevant Multipolygon
        if one_relevant_coll.covers(one_single_poly):
            polygon_list.append(one_single_poly)
    return polygon_list


def create_geodataframe_dict(best_offset,
                             dict_square_edge_length_long_lat,
                             grid_edge_length_meter,
                             list_known_geo_coll_of_single_polys):
    gdf_dict = {'tiles_group_identifier': [str(uuid.uuid4()) for _ in list_known_geo_coll_of_single_polys],
                'offset_longitude': best_offset[0],
                'offset_latitude': best_offset[1],
                'tile_width': dict_square_edge_length_long_lat['tile_width'],
                'tile_height': dict_square_edge_length_long_lat['tile_height'],
                'sensor_line_length_meter': grid_edge_length_meter,
                'covered_area': [unary_union(x).area for x in list_known_geo_coll_of_single_polys],
                'geometry': list_known_geo_coll_of_single_polys}
    return gdf_dict


def generate_tile_groups_of_given_edge_length(area_polygon,
                                              specific_area_multipoly,
                                              dict_square_edge_length_long_lat: dict,
                                              grid_edge_length_meter,
                                              polygon_threshold,
                                              known_tiles_gdf: gpd.GeoDataFrame):
    # if general area of interest is not the same as specifically for this scanner line width assigned area
    if not area_polygon == specific_area_multipoly:
        specific_area_multipoly = area_polygon.intersection(specific_area_multipoly)

    # there is no know geometry data available
    if known_tiles_gdf.empty:
        # find offset for biggest tile size first
        offsets = generate_offset_list(5, dict_square_edge_length_long_lat)
        print("First: Find biggest possible grid with a list of random offset!")
        list_biggest_grids = []
        # offset is always in (long, lat)
        for off in offsets:
            grid_geo_coll = processing_geometry_boundary_check(off,
                                                               dict_square_edge_length_long_lat,
                                                               area_polygon,
                                                               specific_area_multipoly,
                                                               [])
            if grid_geo_coll is None:
                print("No grid could be found for biggest square edge length", str(dict_square_edge_length_long_lat),
                      "meter and", str(off), "offset")
            else:
                list_biggest_grids.append((off, grid_geo_coll))

        # search through list_biggest_grids for biggest covered area
        if len(list_biggest_grids) > 0:
            # make unary_union of all determined Polygon and compare the areas, the biggest area wins
            best_offset, geo_coll_single_polyons = max(list_biggest_grids,
                                                       key=lambda a: make_valid(unary_union(a[1])).area)
            if len(geo_coll_single_polyons.geoms) > 0:
                print(len(geo_coll_single_polyons.geoms), "Polygons found in given area!")
                print("Best random offset chosen is", str(best_offset))

            # relevancy check of joined polygons group
            list_relevant_geo_colls = keep_only_relevant_geo_coll_of_single_polygon_geo_coll(
                geo_coll_single_polyons, polygon_threshold)

            gdf_dict = create_geodataframe_dict(best_offset,
                                                dict_square_edge_length_long_lat,
                                                grid_edge_length_meter,
                                                list_relevant_geo_colls)

            gdf_biggest_tile_size = gpd.GeoDataFrame(gdf_dict, crs=4326).set_geometry('geometry')
            return gdf_biggest_tile_size
        else:
            return gpd.GeoDataFrame()

    # there is some known geometry data available
    if not known_tiles_gdf.empty:
        # determine best_offset for aligned tiles, is one hashable column inside known_tiles_gdf
        best_offset = (known_tiles_gdf.head(1).offset_longitude[0], known_tiles_gdf.head(1).offset_latitude[0])

        list_known_geo_coll_of_single_polys = []  # will be list of all known Multipolygons
        for single_geom in known_tiles_gdf.geometry:
            # extract Multipolygon from each GeoSeries in known_tiles_gdf
            list_known_geo_coll_of_single_polys.append(single_geom)

        # get all Polygon of dict_square_edge_length_long_lat inside area_polygon
        grid_geo_coll = processing_geometry_boundary_check(best_offset,
                                                           dict_square_edge_length_long_lat,
                                                           area_polygon,
                                                           specific_area_multipoly,
                                                           list_known_geo_coll_of_single_polys)

        if grid_geo_coll.is_empty:
            print("No grid could be found for biggest square edge length", dict_square_edge_length_long_lat,
                  "meter and", str(best_offset), "offset")
            return gpd.GeoDataFrame()
        else:
            if len(grid_geo_coll.geoms) > 1:
                print(len(grid_geo_coll.geoms), "Polygons found in given area!")
            # group the polygons and reject groups of polygons (by area) which are too small
            list_relevant_geo_colls = keep_only_relevant_geo_coll_of_single_polygon_geo_coll(grid_geo_coll,
                                                                                             polygon_threshold)

            # generate GeoDataframe
            gdf_dict = create_geodataframe_dict(best_offset,
                                                dict_square_edge_length_long_lat,
                                                grid_edge_length_meter,
                                                list_relevant_geo_colls)
            gdf = gpd.GeoDataFrame(gdf_dict, crs=4326).set_geometry('geometry')  # , crs=4326
            return gdf


def generate_grid(task_manager: Grid_Generation_Task_Manager):
    # first we need the task list from the task manager
    task_list = task_manager.extract_tasks()  # the list is sorted from the biggest to the smallest scanner line width

    gdf_collection = gpd.GeoDataFrame()  # collect all results in this geodataframe

    # search starts at biggest tiles, the greatest edge length and relative polygon threshold
    for idx, task in enumerate(task_list):
        gdf_one_tile_size = generate_tile_groups_of_given_edge_length(task_manager.area_multipoly,
                                                                      task.multipolygon,
                                                                      task.dict_stc_tiles_long_lat,
                                                                      task.scanner_line_width,
                                                                      task.polygon_threshold,
                                                                      gdf_collection)
        if gdf_one_tile_size.empty:
            print("Didn't find a grid with", task.get_scanner_line_width(),
                  "square edge length!\nContinuing with smaller one...")
        else:
            print(f'Found grid with tile edge length of {task.get_scanner_line_width()}m')
            gdf_collection = gpd.GeoDataFrame(pandas.concat([gdf_collection,
                                                             gdf_one_tile_size],
                                                            axis=0,
                                                            ignore_index=True),
                                              crs=4326)

    return gdf_collection
