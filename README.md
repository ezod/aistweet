`aistweet`, a Twitter photo bot for Raspberry Pi AIS tracking stations
----------------------------------------------------------------------

aistweet tracks ships via AIS and takes their picture with a Raspberry Pi
camera as they pass by.

Written for and powering the [Detroit River Boat Tracker].

How To Build It
---------------

Things you will need:

  - a [Raspberry Pi]
  - a [Raspberry Pi Camera Module]
  - a USB SDR dongle, such as [Nooelec NESDR Smart v4]
  - a VHF antenna suitable for receiving [AIS] transmissions

Build and install [rtl-ais], and configure it to stream UDP data to the host
and port defined by the aistweet command line.

If you want to also upload your AIS data to other services online and have a
locally-hosted interactive map, you can use [rPiAIS], but note that the image
will need to be upgraded to the Buster release.

It is important to set the latitude, longitude, and direction of your camera
accurately in order for the snapshot timing to work. The direction is measured
in degrees clockwise from north of the camera's center axis.

Command Line
------------
```
usage: aistweet.py [-h] [--host HOST] [--port PORT] [--db DB]
                   [--hashtags HASHTAGS [HASHTAGS ...]]
                   latitude longitude direction consumer_key consumer_secret
                   access_token access_token_secret

Raspberry Pi AIS tracker/camera Twitter bot

positional arguments:
  latitude              AIS station latitude
  longitude             AIS station longitude
  direction             bearing of camera (degrees clockwise from north)
  consumer_key          Twitter consumer key
  consumer_secret       Twitter consumer secret
  access_token          Twitter access token
  access_token_secret   Twitter access token secret

optional arguments:
  -h, --help            show this help message and exit
  --host HOST           host for receiving UDP AIS messages
  --port PORT           port for receiving UDP AIS messages
  --db DB               database file for static ship data
  --hashtags HASHTAGS [HASHTAGS ...]
                        hashtags to add to tweets
  --tts                 announce ship name via Festival TTS
```

Dependencies
------------
  - [astral](https://pypi.org/project/astral/)
  - [emoji-country-flag](https://pypi.org/project/emoji-country-flag/)
  - [event-scheduler](https://pypi.org/project/event-scheduler/)
  - [geopy](https://pypi.org/project/geopy/)
  - [picamera](https://pypi.org/project/picamera/)
  - [pyais](https://pypi.org/project/pyais/)
  - [pytz](https://pypi.org/project/pytz/)
  - [timezonefinder](https://pypi.org/project/timezonefinder/)
  - [tweepy](https://pypi.org/project/tweepy/)
  - [Festival](https://www.cstr.ed.ac.uk/projects/festival/) (optional)


[Detroit River Boat Tracker]: https://twitter.com/detroitships
[AIS]: https://en.wikipedia.org/wiki/Automatic_identification_system
[Nooelec NESDR Smart v4]: https://www.nooelec.com/store/sdr/sdr-receivers/nesdr-smart-sdr.html
[Raspberry Pi]: https://www.raspberrypi.org/
[Raspberry Pi Camera Module]: https://www.raspberrypi.org/products/camera-module-v2/
[rPiAIS]: https://www.aishub.net/rpiais
[rtl-ais]: https://github.com/dgiardini/rtl-ais
