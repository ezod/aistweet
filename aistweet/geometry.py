import math
from typing import Tuple

from geopy.distance import distance

from aistweet.units import kn_to_m_s, m_to_lat, m_to_lon


def center_coordinates(
    lat: float,
    lon: float,
    to_bow: float,
    to_stern: float,
    to_starboard: float,
    to_port: float,
    heading: float,
) -> Tuple[float, float]:
    """Calculate the latitude and longitude of a vessel's physical center point."""
    # offset of vessel center in meters relative to vessel coordinate frame
    l_offset = ((to_bow + to_stern) / 2.0) - to_stern
    w_offset = ((to_starboard + to_port) / 2.0) - to_port

    # longitude and latitude offsets rotated by vessel heading
    # (heading is expressed in clockwise degrees from north)
    theta = math.radians(-heading % 360)
    lat_offset = m_to_lat(w_offset * math.sin(theta) + l_offset * math.cos(theta))
    lon_offset = m_to_lon(w_offset * math.cos(theta) - l_offset * math.sin(theta), lat)

    return (lat + lat_offset, lon + lon_offset)


def crossing_time_and_depth(
    camera_lat: float,
    camera_lon: float,
    camera_heading: float,
    vessel_lat: float,
    vessel_lon: float,
    vessel_course: float,
    t: float,
) -> Tuple[float, float]:
    """Calculate the time and depth at which a vessel will cross the camera axis."""
    # convert to radians
    camera_lat_r = math.radians(camera_lat)
    camera_lon_r = math.radians(camera_lon)
    camera_dir_r = math.radians(camera_heading)
    vessel_lat_r = math.radians(vessel_lat)
    vessel_lon_r = math.radians(vessel_lon)
    vessel_dir_r = math.radians(vessel_course)

    try:
        # compute intersection point (http://www.movable-type.co.uk/scripts/latlong.html)
        d_12 = 2.0 * math.asin(
            math.sqrt(
                math.sin((camera_lat_r - vessel_lat_r) / 2.0) ** 2
                + math.cos(camera_lat_r)
                * math.cos(vessel_lat_r)
                * math.sin((camera_lon_r - vessel_lon_r) / 2.0) ** 2
            )
        )

        t_a = math.acos(
            (math.sin(vessel_lat_r) - math.sin(camera_lat_r) * math.cos(d_12))
            / (math.sin(d_12) * math.cos(camera_lat_r))
        )
        t_b = math.acos(
            (math.sin(camera_lat_r) - math.sin(vessel_lat_r) * math.cos(d_12))
            / (math.sin(d_12) * math.cos(vessel_lat_r))
        )

        if math.sin(vessel_lon_r - camera_lon_r) > 0.0:
            t_12 = t_a
            t_21 = math.tau - t_b
        else:
            t_12 = math.tau - t_a
            t_21 = t_b

        a_1 = camera_dir_r - t_12
        a_2 = t_21 - vessel_dir_r
        a_3 = math.acos(
            -math.cos(a_1) * math.cos(a_2)
            + math.sin(a_1) * math.sin(a_2) * math.cos(d_12)
        )
        d_13 = math.atan2(
            math.sin(d_12) * math.sin(a_1) * math.sin(a_2),
            math.cos(a_2) + math.cos(a_1) * math.cos(a_3),
        )

        int_lat_r = math.asin(
            math.sin(camera_lat_r) * math.cos(d_13)
            + math.cos(camera_lat_r) * math.sin(d_13) * math.cos(camera_dir_r)
        )
        int_lon_r = camera_lon_r + math.atan2(
            math.sin(camera_dir_r) * math.sin(d_13) * math.cos(camera_lat_r),
            math.cos(d_13) - math.sin(camera_lat_r) * math.sin(int_lat_r),
        )

        int_lat = math.degrees(int_lat_r)
        int_lon = math.degrees(int_lon_r)

        d = distance((vessel_lat, vessel_lon), (int_lat, int_lon)).m
        depth = distance((self.lat, self.lon), (int_lat, int_lon)).m
    except ValueError:
        return None, None

    return self.ships[mmsi]["last_update"] + d / kn_to_m_s(speed), depth
