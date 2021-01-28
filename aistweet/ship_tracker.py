import csv
import math
import threading
import time
from pkg_resources import resource_filename

import flag
import geopy
from pyais.stream import UDPStream

from aistweet.units import m_to_lat, m_to_lon


class ShipTracker(object):
    STATIC_MSGS = [5, 24]
    POSITION_MSGS = [1, 2, 3, 18]
    STATIC_FIELDS = [
        "shipname",
        "imo",
        "shiptype",
        "destination",
        "draught",
        "to_bow",
        "to_stern",
        "to_port",
        "to_starboard",
    ]
    POSITION_FIELDS = ["lat", "lon", "status", "heading", "course", "speed"]

    def __init__(self, host, port, latitude, longitude):
        self.host = host
        self.port = port

        self.lat = latitude
        self.lon = longitude

        self.ships = {}

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
            # create a new ship entry if necessary
            if not mmsi in self.ships:
                self.ships[mmsi] = {
                    "ais_class": "B" if data["type"] in [18, 24] else "A"
                }
                for key in self.STATIC_FIELDS + self.POSITION_FIELDS:
                    self.ships[mmsi][key] = None
                self.ships[mmsi]["last_update"] = None

            # handle static messages
            if data["type"] in self.STATIC_MSGS:
                for key in self.STATIC_FIELDS:
                    self.ships[mmsi][key] = data[key]
                # TODO: eta?

            # handle position reports
            if data["type"] in self.POSITION_MSGS:
                for key in self.POSITION_FIELDS:
                    self.ships[mmsi][key] = data[key]
                self.ships[mmsi]["last_update"] = t

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
            if speed < 0.2:
                return None

            ship_lat, ship_lon = self.center_coords(mmsi)
            ship_dir = self.ships[mmsi]["course"]

            # compute intersection point (http://www.movable-type.co.uk/scripts/latlong.html)
            d_12 = 2.0 * math.asin(
                math.sqrt(
                    math.sin((self.lat - ship_lat) / 2.0) ** 2
                    + math.cos(self.lat)
                    * math.cos(ship_lat)
                    * math.sin((self.lon - ship_lon) / 2.0) ** 2
                )
            )

            t_a = math.acos(
                (math.sin(ship_lat) - math.sin(self.lat) * math.cos(d_12))
                / (math.sin(d_12) * math.cos(self.lat))
            )
            t_b = math.acos(
                (math.sin(self.lat) - math.sin(ship_lat) * math.cos(d_12))
                / (math.sin(d_12) * math.cos(ship_lat))
            )

            if math.sin(ship_lon - self.lon) > 0.0:
                t_12 = t_a
                t_21 = math.tau - t_b
            else:
                t_12 = math.tau - t_a
                t_21 = t_b

            a_1 = math.radians(direction) - t_12
            a_2 = t_21 - math.radians(ship_dir)
            a_3 = math.acos(
                -math.cos(a_1) * math.cos(a_2)
                + math.sin(a_1) * math.sin(a_2) * math.cos(d_12)
            )
            d_13 = math.atan2(
                math.sin(d_12) * math.sin(a_1) * math.sin(a_2),
                math.cos(a_2) + math.cos(a_1) * math.cos(a_3),
            )

            int_lat = math.asin(
                math.sin(self.lat) * math.cos(d_13)
                + math.cos(self.lat)
                * math.sin(d_13)
                * math.cos(math.radians(direction))
            )
            int_lon = self.lon + math.atan2(
                math.sin(math.radians(direction)) * math.sin(d_13) * math.cos(self.lat),
                math.cos(d_13) - math.sin(self.lat) * math.sin(int_lat),
            )

            # time when the ship will reach the intersection point
            d = geopy.distance.distance((ship_lat, ship_lon), (int_lat, int_lon)).m
            return self.ships[mmsi]["last_update"] + d / kn_to_m_s(speed)

    def run(self):
        for msg in UDPStream(self.host, self.port):
            data = msg.decode()
            if data["type"] in self.STATIC_MSGS + self.POSITION_MSGS:
                t = time.time()
                mmsi = self.add_message(data, t)
                for callback in self.message_callbacks:
                    callback(mmsi, t)
