import tweepy


class Tweeter(object):
    def __init__(self, db):
        self.db = db

        # TODO: set up tweepy connection

    def generate_text(self, mmsi):
        text = u"{} ".format(self.db.flag(mmsi))

        ship = self.db[mmsi]

        shipname = ship["shipname"]
        if shipname:
            text += shipname
        else:
            text += "(Unidentified)"

        text += u", {}".format(self.db.ship_type(mmsi))

        length, width = self.db.dimensions(mmsi)
        if length > 0 and width > 0:
            text += u" ({l} x {w} m)".format(l=length, w=width)

        status = self.db.status(mmsi)
        if status is not None:
            text += u", {}".format(status)

        destination = ship["destination"]
        if destination:
            text += u", destination: {}".format(destination)

        course = ship["course"]
        speed = ship["speed"]
        if course is not None and speed is not None:
            text += u", course: {c:.1f} \N{DEGREE SIGN} / speed: {s} kn".format(
                c=course, s=speed
            )

        return text
