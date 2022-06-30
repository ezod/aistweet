The Story of the Detroit River Boat Tracker
===========================================

I live in [Windsor], on a street aptly named [Riverside Drive]. A variety of
boats, including much of the shipping traffic of the Great Lakes (yes, we call
thousand-foot lake freighters "boats" here), pass through a segment of the
[Detroit River] approximately 700 meters wide right outside my window. A little
experimentation with software-defined radio led pretty quickly to the creation
of the [Detroit River Boat Tracker], which I think is an interesting case study
of rapid application development involving radio hardware, the Raspberry Pi
platform, and most of all, my beloved Python ecosystem. Let's take a dive into
how `aistweet` and the tracker came into being.

Origins: Discovering AIS
------------------------

I discovered a conspicuous pair of signals at 161.975 MHz and 162.025 MHz during
one of my first explorations of the waterfall pouring out of my new [Nooelec
NESDR SMArt v4] USB dongle, but didn't look up what they were until I noticed
that a particularly strong signal seemed to coincide with a large boat passing
directly across from my house. It turns out that these are the frequencies used
by the [automatic identification system], or AIS, on which vessels broadcast
information about themselves (name, type, destination, dimensions, coordinates,
heading, speed, and more), to be tracked by other vessels and by shore-based
stations.

In order to do anything useful with these signals, I first needed to demodulate
the raw FM transmissions into digital NMEA messages. Fortunately, the perfect
piece of open-source software already exists for this: [rtl-ais]. This simple
utility, written in lovely C, takes care of tuning the SDR dongle directly and
demodulating the transmissions into UDP packets compatible with other AIS
software.

As exciting as it was to see raw NMEA data show up in my terminal, what I really
wanted to see was my own personal map of tracked boats, in the style of
[MarineTraffic]. For this, I used [AIS Dispatcher], which serves up a web app
that consumes the NMEA messages, displays an interactive map, and lets me
dispatch the data on to several online services that aggregate AIS data.

Now, with the minuscule general-purpose telescoping antenna that shipped with my
SDR, I was able to pick up boats a surprising distance up and down the river. It
stood to reason that a larger antenna mounted higher up would perform better, so
I ordered a reasonably-priced Diamond D-130J wide-band discone antenna and set
it up "temporarily" on my balcony (still working on moving it to the chimney).
The routing of the coaxial cable from this location is such that it made sense
to move the SDR dongle and software onto a Raspberry Pi sitting in my office
window, which happens to face the river.

A Boat-Tracking Twitter Bot
---------------------------

And that's where the idea sprung forth, in near full form. I'd stick a [camera
module] on the Raspberry Pi, point it out the window, and write a script that
uses the AIS data to determine when a boat is in view, snap a photo, and tweet
it to a dedicated Twitter account along with the interesting bits of the AIS
data.

The data of interest, therefore, would be the dimensions, coordinates, course,
and speed of the vessel for tracking, as well as its [MMSI], name, type,
status, destination, and perhaps other details for the tweet caption.

Easy enough, right? Of course, filling in the details between these broad
strokes is where it gets interesting, and sometimes the best way to figure them
out is to dive straight into implementation.

Tracking the Boats
------------------

First, I needed a way to decode and parse the raw AIS messages into a more
immediately usable form. For this, I found [pyais], which can listen directly
to the UDP stream from [rtl-ais] and produce convenient, Pythonic objects of
the messages as a [generator].

The first hurdle was that the AIS data of interest for a given vessel actually
comes in over multiple separate messages of different types. In particular,
there is "static" information about the vessel (name, type, dimensions, etc.),
"voyage" information (destination, draught, etc.), and "position" information
(coordinates, heading, course, speed, etc.). This data needs to be aggregated
both to track the vessel for the photo and to compile the tweet caption. Each
new message therefore adds or updates an entry to a dictionary in memory
containing all of the necessary fields, and then triggers any registered
callback function, giving it access to the dictionary. Additionally, the static
vessel information is persisted to disk using Python's built-in [SQLite]
support, to improve cases where a vessel seen during a previous run of the
application did not broadcast its static information in time for a tweet.

The callback function, of course, is going to be interested in two things:
requesting the necessary position data to determine when to snap a photo, and
requesting the interesting data needed for the tweet caption.

The first item is a bit trickier than it seems. The boat needs to be centered
in frame at the moment the photo is taken, but the position messages are only
broadcast [sporadically](https://www.milltechmarine.com/faq.htm#a9) (for boats
moving at typical Detroit River speeds, up to 20 seconds between messages).
Additionally, for generality, any combination of boat heading and camera axis
bearing should be supported. I opted to give the callback access to a method
that calculates, using [geopy] and some [spherical geometry], the actual time
the center of the ship will cross the camera axis. (I had even considered
employing a [Kalman filter] here, but in practice just using the kinematic
state from the most recent position message works well enough.)

The second item is a mere matter of providing convenient access to the
aggregated AIS data, with a few convenience methods to provide more directly
usable information, such as translating ship type and status to human-readable
form, and using [flag] to provide an emoji of the flag of registry from the MID
in the first 3 digits of the [MMSI].

Tweeting the Boats
------------------

On the other side of the fence, the aforementioned callback, for reasons already
covered, can't immediately take the photo and tweet it; nor can it block while
it waits for the appropriate moment, since multiple boats may be bearing down on
the camera axis at the same time. I therefore have the callback add (or update)
an entry in an event scheduler running in a separate thread. Python's built-in
scheduler isn't suitable to keep running continuously, but fortunately, there is
the third-party [event-scheduler] for this use case. When any new AIS message
arrives, the callback gets the crossing time from the tracker (minus the camera
warmup and delay times), and schedules a photo-and-tweet for the appropriate
moment if the boat is soon to cross the camera axis.

The photo itself can appear a bit different depending on a couple of factors.
First, the distance to the boat and the length of the boat are used to determine
the "zoom" (region of interest) of the photo, using projective geometry and the
known horizontal field of view of the [camera module]. Second, the exposure mode
of the camera is normally set to "auto", but is set to "night" instead between
dusk and dawn. This is determined using [astral], to which we feed the
coordinates of the camera, the timezone at those coordinates as obtained from
[timezonefinder], and the current local time using [pytz]. The capture itself
is, of course, handled by [picamera].

The tweet itself is posted using [tweepy], which interfaces with Twitter's API.
The tweet includes the photo of the boat along with a caption including a flag
of registry, some interesting details, and a link to the [MarineTraffic] entry
for the vessel. The tweet is also geotagged to the coordinates of the boat at
the time the photo was taken.

Bonus: Announcing the Boats
---------------------------

After launching the boat tracker, I often found myself checking the Twitter
feed just to get the name of a boat I'd see passing my window. It occurred to
me to add a cheap pair of speakers to the Raspberry Pi, and have it audibly
announce the names of passing boats using [gTTS] and [mpg321]. It sounds just
like my Google Home Mini!

Conclusion
----------

I hope this case study of rapid development of a relatively straightforward and
self-contained application, well-specified at the high level, with the details
filled in by a process of cobbling together open-source Python modules, has been
of some interest to you. There is a vast ecosystem of Python libraries out there
for almost every imaginable thing, no matter how specific, and I hope I've
inspired you to try bringing a high-level idea to fruition by leveraging them!


[AIS Dispatcher]: https://www.aishub.net/ais-dispatcher
[Automatic Identification System]: https://en.wikipedia.org/wiki/Automatic_identification_system
[Detroit River]: https://en.wikipedia.org/wiki/Detroit_River
[Detroit River Boat Tracker]: https://twitter.com/detroitships
[Kalman filter]: https://en.wikipedia.org/wiki/Kalman_filter
[MMSI]: https://en.wikipedia.org/wiki/Maritime_Mobile_Service_Identity
[MarineTraffic]: https://www.marinetraffic.com/
[Nooelec NESDR SMArt v4]: https://www.nooelec.com/store/sdr/sdr-receivers/nesdr-smart-sdr.html
[Riverside Drive]: https://en.wikipedia.org/wiki/Riverside_Drive_(Windsor,_Ontario)
[SQLite]: https://www.sqlite.org/index.html
[Windsor]: https://en.wikipedia.org/wiki/Windsor,_Ontario
[astral]: https://github.com/sffjunkie/astral
[camera module]: https://www.raspberrypi.org/products/camera-module-v2/
[event-scheduler]: https://github.com/phluentmed/event-scheduler
[flag]: https://flag.readthedocs.io/en/latest/
[gTTS]: https://github.com/pndurette/gTTS
[generator]: https://wiki.python.org/moin/Generators
[geopy]: https://github.com/geopy/geopy
[mpg321]: http://mpg321.sourceforge.net/
[picamera]: https://picamera.readthedocs.io/en/release-1.13/
[pyais]: https://github.com/M0r13n/pyais
[pytz]: https://pythonhosted.org/pytz/
[rtl-ais]: https://github.com/dgiardini/rtl-ais
[spherical geometry]: http://www.movable-type.co.uk/scripts/latlong.html
[timezonefinder]: https://github.com/jannikmi/timezonefinder
[tweepy]: https://pypi.org/project/tweepy/
