import math


def kn_to_m_s(knots):
    """Convert knots to meters per second."""
    return 0.514444444 * knots


def m_to_lat(meters):
    """Convert meters to degrees latitude (approximate)."""
    return meters / 111111.0


def m_to_lon(meters, latitude):
    """Convert meters to degrees longitude (approximate)."""
    return meters / (math.cos(math.radians(latitude)) * 111111.0)
