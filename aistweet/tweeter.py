import datetime
import fractions
import os
import threading
import time

from atproto import Client, models
from event_scheduler import EventScheduler

import astral
import astral.sun
import pytz
from timezonefinder import TimezoneFinder

try:
    from picamera import PiCamera
except ModuleNotFoundError:
    PiCamera = lambda: None

try:
    import gtts
except ModuleNotFoundError:
    gtts = None

try:
    import board
    import busio
    import adafruit_veml7700
except ModuleNotFoundError:
    adafruit_veml7700 = None

from aistweet.compress import resize_and_compress


class Tweeter(object):
    CAMERA_WARMUP = 1.0
    CAMERA_DELAY = 1.0
    LIGHT_LEVEL_MAX = 50

    def __init__(
        self,
        tracker,
        direction,
        tts=False,
        light=False,
        logging=True,
    ):
        self.tracker = tracker

        self.direction = direction

        self.tts = tts if gtts is not None else False

        self.logging = logging

        self.schedule = {}
        self.scheduler = EventScheduler("tweeter")

        self.lock = threading.RLock()

        # set up location data
        tf = TimezoneFinder()
        self.location = astral.LocationInfo(
            "AIS Station",
            "Earth",
            tf.timezone_at(lat=self.tracker.lat, lng=self.tracker.lon),
            self.tracker.lat,
            self.tracker.lon,
        )

        # set up camera
        self.camera = PiCamera()

        # set up light sensor
        self.light_sensor = None
        if light and adafruit_veml7700 is not None:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.light_sensor = adafruit_veml7700.VEML7700(i2c)

        self.scheduler.start()

        # register callback
        self.tracker.message_callbacks.append(self.check)

    def stop(self):
        self.scheduler.stop()

    def log(self, mmsi, message):
        if self.logging:
            print(f"[{datetime.datetime.now()}] {self.shipname(mmsi)}: {message}")

    def check(self, mmsi, t):
        crossing, depth = self.tracker.crossing(mmsi, self.direction)
        if crossing is None:
            return
        delta = crossing - time.time() - self.CAMERA_WARMUP - self.CAMERA_DELAY
        if 0.0 < delta < 60.0:
            try:
                existing_event = self.schedule.pop(mmsi)
                self.scheduler.cancel(existing_event)
            except (KeyError, ValueError, AttributeError):
                pass
            self.schedule[mmsi] = self.scheduler.enter(
                delta, 1, self.snap_and_tweet, arguments=(mmsi, depth)
            )
            self.log(mmsi, f"scheduled for tweet in {delta} seconds")

    def purge_schedule(self, mmsi):
        try:
            del self.schedule[mmsi]
            self.log(mmsi, "removed from schedule")
        except KeyError:
            pass

    def snap_and_tweet(self, mmsi, depth):
        # only tweet once while this ship is scheduled (60 second cooldown)
        if mmsi in self.schedule and self.schedule[mmsi] is None:
            return
        self.schedule[mmsi] = None

        self.log(mmsi, "ship in view, tweeting...")
        with self.lock:
            # determine whether this is a "large" ship in FOV (horiz. 62.2deg)
            # large if ship length > 0.9 * tan(31.1) * distance to ship
            large = self.tracker.dimensions(mmsi)[0] > (0.542915 * depth)

            # grab the image
            image_path = os.path.join("/tmp", f"{mmsi}.jpg")
            if not self.snap(image_path, large):
                self.log(mmsi, "image capture aborted")
                return
            resize_and_compress(image_path, image_path, 1000000, (1640, 1232))
            self.log(mmsi, f"image captured to {image_path}")

            # set up Bluesky connection
            username = os.getenv("BLUESKY_USERNAME")
            password = os.getenv("BLUESKY_PASSWORD")
            client = Client("https://bsky.social")
            client.login(username, password)

            # create post
            try:
                shipname = self.shipname(mmsi)

                with open(image_path, "rb") as image_file:
                    upload = client.upload_blob(image_file)
                images = [
                    models.AppBskyEmbedImages.Image(alt=shipname, image=upload.blob)
                ]
                embed = models.AppBskyEmbedImages.Main(images=images)

                text = self.generate_text(mmsi)

                url = f"https://www.marinetraffic.com/en/ais/details/ships/mmsi:{mmsi}"
                facets = [
                    {
                        "index": {"byteStart": 9, "byteEnd": 9 + len(shipname)},
                        "features": [
                            {"$type": "app.bsky.richtext.facet#link", "uri": url}
                        ],
                    }
                ]

                client.com.atproto.repo.create_record(
                    models.ComAtprotoRepoCreateRecord.Data(
                        repo=client.me.did,
                        collection=models.ids.AppBskyFeedPost,
                        record=models.AppBskyFeedPost.Record(
                            created_at=client.get_current_time_iso(),
                            text=text,
                            embed=embed,
                            facets=facets,
                        ),
                    )
                )
            except Exception as e:
                self.log(mmsi, f"post error: {e}")

            # clean up the image
            os.remove(image_path)

            # remove event from schedule after a minute
            self.scheduler.enter(60.0, 2, self.purge_schedule, arguments=(mmsi,))

            # announce the ship using TTS
            if self.tts:
                speech_path = os.path.join("/tmp", f"{mmsi}.mp3")
                try:
                    speech = gtts.gTTS(
                        text=self.shipname(mmsi).title(), lang="en", slow=False
                    )
                    speech.save(speech_path)
                    os.system(f"mpg321 -q {speech_path}")
                    os.remove(speech_path)
                except gtts.tts.gTTSError:
                    pass

        self.log(mmsi, "done tweeting")

    def snap(self, path, large):
        if self.camera is None:
            return False

        with self.lock:
            # set zoom based on ship size
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0) if large else (0.25, 0.35, 0.5, 0.5)
            # set exposure mode based on dawn/dusk times
            sun = astral.sun.sun(
                self.location.observer,
                datetime.date.today(),
                tzinfo=self.location.timezone,
            )
            now = self.now()
            if now < sun["dawn"] or now > sun["dusk"]:
                if self.light_sensor is not None:
                    if self.light_sensor.light > self.LIGHT_LEVEL_MAX:
                        return False
                self.camera.resolution = (1640, 1232)
                self.camera.framerate = fractions.Fraction(2, 1)
                self.camera.exposure_mode = "night"
            else:
                self.camera.resolution = (1640, 1232) if large else (3280, 2464)
                self.camera.framerate = fractions.Fraction(30, 1)
                self.camera.exposure_mode = "auto"

            # capture image
            self.camera.start_preview()
            time.sleep(self.CAMERA_WARMUP)
            self.camera.capture(path)
            self.camera.stop_preview()
            return True

    def now(self):
        return pytz.utc.localize(datetime.datetime.utcnow()).astimezone(
            pytz.timezone(self.location.timezone)
        )

    def shipname(self, mmsi):
        return self.tracker[mmsi]["shipname"] or "(Unidentified)"

    def generate_text(self, mmsi):
        text = ""

        flag = self.tracker.flag(mmsi)
        if flag:
            text += f"{flag} "

        ship = self.tracker[mmsi]

        text += self.shipname(mmsi)
        text += f", {self.tracker.ship_type(mmsi)}"

        length, width = self.tracker.dimensions(mmsi)
        if length > 0 and width > 0:
            text += f" ({length} x {width} m)"

        status = self.tracker.status(mmsi)
        if status is not None:
            text += f", {status}"

        destination = ship["destination"]
        if destination:
            text += f", destination: {destination}"

        course = ship["course"]
        speed = ship["speed"]
        if course is not None and speed is not None:
            text += f", course: {course:.1f} \N{DEGREE SIGN} / speed: {speed:.1f} kn"

        return text
