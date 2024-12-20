import csv
import threading
import time
from pkg_resources import resource_filename

import flag
import sqlite3
from pyais.ais_types import AISType
from pyais.stream import UDPReceiver

from aistweet.geometry import center_coordinates, crossing_time_and_depth


class ShipTracker(object):
    STATIC_MSGS = [AISType.STATIC, AISType.STATIC_AND_VOYAGE]
    POSITION_MSGS = [
        AISType.POS_CLASS_A1,
        AISType.POS_CLASS_A2,
        AISType.POS_CLASS_A3,
        AISType.POS_CLASS_B,
    ]

    STATIC_FIELDS = {
        "shipname": "(Unidentified)",
        "shiptype": None,
        "to_bow": 0,
        "to_stern": 0,
        "to_port": 0,
        "to_starboard": 0,
    }
    VOYAGE_FIELDS = {"imo": None, "destination": None, "draught": 0.0}
    POSITION_FIELDS = {
        "lat": None,
        "lon": None,
        "status": None,
        "heading": None,
        "course": None,
        "speed": None,
    }

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

        self.listener = threading.Thread(target=self.run, args=())
        self.listener.daemon = True
        self.listener.start()

    @staticmethod
    def readcsv(filename):
        d = {}
        path = resource_filename("aistweet", f"data/{filename}.csv")
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
                self.ships[mmsi] = {
                    **self.STATIC_FIELDS,
                    **self.VOYAGE_FIELDS,
                    **self.POSITION_FIELDS,
                }
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
            if data["msg_type"] in self.STATIC_MSGS:
                for key in self.STATIC_FIELDS:
                    try:
                        self.ships[mmsi][key] = data[key]
                    except KeyError:
                        pass
                if self.db_file:
                    c.execute(
                        "INSERT OR REPLACE INTO Ships VALUES(?"
                        + ", ?" * len(self.STATIC_FIELDS)
                        + ")",
                        (mmsi,)
                        + tuple([self.ships[mmsi][key] for key in self.STATIC_FIELDS]),
                    )
                    conn.commit()
                if data["msg_type"] == AISType.STATIC_AND_VOYAGE:
                    for key in self.VOYAGE_FIELDS:
                        self.ships[mmsi][key] = data[key]
                        # TODO: eta?

            # handle position reports
            if data["msg_type"] in self.POSITION_MSGS:
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
            return None

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
                    self.ships[mmsi]["to_starboard"] + self.ships[mmsi]["to_port"],
                )
            except TypeError:
                return (0, 0)

    def center_coords(self, mmsi):
        with self.lock:
            lat = self.ships[mmsi]["lat"]
            lon = self.ships[mmsi]["lon"]

            if lat is None or lon is None:
                return None

            to_bow = self.ships[mmsi]["to_bow"] or 0
            to_stern = self.ships[mmsi]["to_stern"] or 0
            to_starboard = self.ships[mmsi]["to_starboard"] or 0
            to_port = self.ships[mmsi]["to_port"] or 0
            heading = self.ships[mmsi]["heading"] or 0

            return center_coordinates(
                lat, lon, to_bow, to_stern, to_starboard, to_port, heading
            )

    def crossing(self, mmsi, direction):
        with self.lock:
            # check for speed above a nominal threhsold
            speed = self.ships[mmsi]["speed"]
            if speed is None or speed < 0.2:
                return None, None

            ship_lat, ship_lon = self.center_coords(mmsi)
            if not (-90.0 < ship_lat < 90.0 and -180.0 < ship_lon < 180.0):
                return None, None

            return crossing_time_and_depth(
                self.lat,
                self.lon,
                direction,
                ship_lat,
                ship_lon,
                self.ships[mmsi]["speed"],
                self.ships[mmsi]["course"],
                self.ships[mmsi]["last_update"],
            )

    def run(self):
        for msg in UDPReceiver(self.host, self.port):
            data = msg.decode().asdict()
            if (
                data is not None
                and "msg_type" in data
                and data["msg_type"] in self.STATIC_MSGS + self.POSITION_MSGS
            ):
                t = time.time()
                mmsi = self.add_message(data, t)
                for callback in self.message_callbacks:
                    callback(mmsi, t)
