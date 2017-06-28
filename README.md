# rem-sphinx
The remote python based speech recognition library/API developed by David Smerkous

###What is it
Rem-Sphinx is a, multi client, python server, that supports STT. It's based off of the CMU Sphinx STT engine and implements an example language support test at 'localhost' port 8000.

###What's unique about it
This is completely opensource and free -- unlike Facebook, Google, and IBM. This will host your own remote STT engine on your (currently linux) supported device. With the sample javascript code, you can implement remote analysis of human speech.


###Current state
This is currently just a demo that has very limited features. A current problem is the speech analysis takes up to 30 seconds depending on the quality and length of the audio "chunk" sent. And again, that's problem number two, the audio is pseudo-realtime, and is base64 chunked depending on speech time. This will, and needs, to be fixed within the near future.


###License
GNU General Public License v3.0
