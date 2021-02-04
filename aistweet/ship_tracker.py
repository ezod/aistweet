import csv
import math
import threading
import time
from pkg_resources import resource_filename

import flag
import sqlite3
from geopy.distance import distance
from pyais.ais_types import AISType
from pyais.stream import UDPStream

from aistweet.units import kn_to_m_s, m_to_lat, m_to_lon


class ShipTracker(object):
    STATIC_MSGS = [AISType.STATIC, AISType.STATIC_AND_VOYAGE]
    POSITION_MSGS = [
        AISType.POS_CLASS_A1,
        AISType.POS_CLASS_A2,
        AISType.POS_CLASS_A3,
        AISType.POS_CLASS_B,
    ]

    STATIC_FIELDS = [
        "shipname",
        "shiptype",
        "to_bow",
        "to_stern",
        "to_port",
        "to_starboard",
    ]
    VOYAGE_FIELDS = ["imo", "destination", "draught"]
    POSITION_FIELDS = ["lat", "lon", "status", "heading", "course", "speed"]

    def __init__(self, host, port, latitude, longitude, db_file=None):
        self.host = host
        self.port = port

        self.lat = latitude
        self.lon = longitude

        self.ships = {}

        self.db_file = db_file
        if self.db_file:
            conn = sqlite3.connect(self.db_file)
            c = conn.cursor()
            c.execute(
                "CREATE TABLE IF NOT EXISTS Ships(mmsi INTEGER PRIMARY KEY, "
                "shipname TEXT, shiptype INTEGER, to_bow INTEGER, to_stern INTEGER, "
                "to_port INTEGER, to_starboard INTEGER)"
            )
            conn.commit()
            conn.close()

        self.countries = self.readcsv("mid")
        self.shiptypes = self.readcsv("shiptype")
        self.statuses = self.readcsv("status")

        self.message_callbacks = []

        self.lock = threading.RLock()

        listener = threading.Thread(target=self.run, args=())
        listener.daemon = True
        listener.start()

    @staticmethod
    def readcsv(filename):
        d = {}
        path = resource_filename("aistweet", "data/{}.csv".format(filename))
        with open(path, newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                d[int(row[0])] = row[1]
        return d

    @property
    def coordinates(self):
        return (self.lat, self.lon)

    def add_message(self, data, t):
        # get the MMSI
        mmsi = int(data["mmsi"])

        with self.lock:
            # open database connection
            if self.db_file:
                conn = sqlite3.connect(self.db_file)
                c = conn.cursor()

            # create a new ship entry if necessary
            if not mmsi in self.ships:
                self.ships[mmsi] = {}
                for key in (
                    self.STATIC_FIELDS + self.VOYAGE_FIELDS + self.POSITION_FIELDS
                ):
                    self.ships[mmsi][key] = None
                self.ships[mmsi]["last_update"] = None
                # try to retrieve cached static data
                if self.db_file:
                    c.execute("SELECT * FROM Ships WHERE mmsi = ?", (mmsi,))
                    row = c.fetchone()
                    if row:
                        for key in self.STATIC_FIELDS:
                            row = row[1:]
                            self.ships[mmsi][key] = row[0]

            # handle static messages
            if data["type"] in self.STATIC_MSGS:
                for key in self.STATIC_FIELDS:
                    self.ships[mmsi][key] = data[key]
                if self.db_file:
                    c.execute(
                        "INSERT OR REPLACE INTO Ships VALUES(?"
                        + ", ?" * len(self.STATIC_FIELDS)
                        + ")",
                        (mmsi,)
                        + tuple([self.ships[mmsi][key] for key in self.STATIC_FIELDS]),
                    )
                    conn.commit()
                if data["type"] == AISType.STATIC_AND_VOYAGE:
                    for key in self.VOYAGE_FIELDS:
                        self.ships[mmsi][key] = data[key]
                        # TODO: eta?

            # handle position reports
            if data["type"] in self.POSITION_MSGS:
                for key in self.POSITION_FIELDS:
                    try:
                        self.ships[mmsi][key] = data[key]
                    except KeyError:
                        pass
                self.ships[mmsi]["last_update"] = t

        conn.close()
        return mmsi

    def __getitem__(self, mmsi):
        with self.lock:
            return self.ships[mmsi]

    def flag(self, mmsi):
        try:
            return flag.flag(self.countries[int(str(mmsi)[:3])])
        except KeyError:
            return flag.flag("ZZ")

    def ship_type(self, mmsi):
        with self.lock:
            try:
                return self.shiptypes[self.ships[mmsi]["shiptype"]]
            except KeyError:
                return "Unknown Type"

    def status(self, mmsi):
        with self.lock:
            try:
                return self.statuses[self.ships[mmsi]["status"]]
            except KeyError:
                return None

    def dimensions(self, mmsi):
        with self.lock:
            try:
                return (
                    self.ships[mmsi]["to_bow"] + self.ships[mmsi]["to_stern"],
                    self.ships[mmsi]["to_port"] + self.ships[mmsi]["to_starboard"],
                )
            except TypeError:
                return (0, 0)

    def center_coords(self, mmsi):
        with self.lock:
            lat = self.ships[mmsi]["lat"]
            lon = self.ships[mmsi]["lon"]

            if lat is None or lon is None:
                return None

            # offset of ship center in meters relative to ship coordinate frame
            length, width = self.dimensions(mmsi)
            l_offset = (length / 2.0) - (self.ships[mmsi]["to_stern"] or 0)
            w_offset = (width / 2.0) - (self.ships[mmsi]["to_port"] or 0)

            # longitude and latitude offsets rotated by ship heading
            # (heading is expressed in clockwise degrees from north)
            theta = math.radians(-(self.ships[mmsi]["heading"] or 0) % 360)
            lat_offset = m_to_lat(
                w_offset * math.sin(theta) + l_offset * math.cos(theta)
            )
            lon_offset = m_to_lon(
                w_offset * math.cos(theta) - l_offset * math.sin(theta), lat
            )

            return (lat + lat_offset, lon + lon_offset)

    def crossing_time(self, mmsi, direction):
        with self.lock:
            # check for speed above a nominal threhsold
            speed = self.ships[mmsi]["speed"]
            if speed is None or speed < 0.2:
                return None

            ship_lat, ship_lon = self.center_coords(mmsi)
            ship_dir = self.ships[mmsi]["course"]

            # convert to radians
            self_lat_r = math.radians(self.lat)
            self_lon_r = math.radians(self.lon)
            self_dir_r = math.radians(direction)
            ship_lat_r = math.radians(ship_lat)
            ship_lon_r = math.radians(ship_lon)
            ship_dir_r = math.radians(ship_dir)

            # compute intersection point (http://www.movable-type.co.uk/scripts/latlong.html)
            d_12 = 2.0 * math.asin(
                math.sqrt(
                    math.sin((self_lat_r - ship_lat_r) / 2.0) ** 2
                    + math.cos(self_lat_r)
                    * math.cos(ship_lat_r)
                    * math.sin((self_lon_r - ship_lon_r) / 2.0) ** 2
                )
            )

            t_a = math.acos(
                (math.sin(ship_lat_r) - math.sin(self_lat_r) * math.cos(d_12))
                / (math.sin(d_12) * math.cos(self_lat_r))
            )
            t_b = math.acos(
                (math.sin(self_lat_r) - math.sin(ship_lat_r) * math.cos(d_12))
                / (math.sin(d_12) * math.cos(ship_lat_r))
            )

            if math.sin(ship_lon_r - self_lon_r) > 0.0:
                t_12 = t_a
                t_21 = math.tau - t_b
            else:
                t_12 = math.tau - t_a
                t_21 = t_b

            a_1 = self_dir_r - t_12
            a_2 = t_21 - ship_dir_r
            a_3 = math.acos(
                -math.cos(a_1) * math.cos(a_2)
                + math.sin(a_1) * math.sin(a_2) * math.cos(d_12)
            )
            d_13 = math.atan2(
                math.sin(d_12) * math.sin(a_1) * math.sin(a_2),
                math.cos(a_2) + math.cos(a_1) * math.cos(a_3),
            )

            int_lat_r = math.asin(
                math.sin(self_lat_r) * math.cos(d_13)
                + math.cos(self_lat_r) * math.sin(d_13) * math.cos(self_dir_r)
            )
            int_lon_r = self_lon_r + math.atan2(
                math.sin(self_dir_r) * math.sin(d_13) * math.cos(self_lat_r),
                math.cos(d_13) - math.sin(self_lat_r) * math.sin(int_lat_r),
            )

            int_lat = math.degrees(int_lat_r)
            int_lon = math.degrees(int_lon_r)

            # time when the ship will reach the intersection point
            d = distance((ship_lat, ship_lon), (int_lat, int_lon)).m
            return self.ships[mmsi]["last_update"] + d / kn_to_m_s(speed)

    def run(self):
        for msg in UDPStream(self.host, self.port):
            data = msg.decode()
            if data["type"] in self.STATIC_MSGS + self.POSITION_MSGS:
                t = time.time()
                mmsi = self.add_message(data, t)
                for callback in self.message_callbacks:
                    callback(mmsi, t)
