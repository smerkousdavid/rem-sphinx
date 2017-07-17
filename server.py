from gevent import monkey; monkey.patch_all()
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.httpserver import HTTPServer
from tornado.websocket import WebSocketHandler
from tornado.web import Application, RequestHandler, StaticFileHandler
from tornado import options
from base64 import b64decode
from json import dumps, loads
from pyaudio import PyAudio, paUInt8, paInt16, paFloat32
from threading import Thread
from os.path import dirname, realpath, join
from subprocess import Popen, PIPE
from pocketsphinx.pocketsphinx import Decoder
from logger import logger
from configs import LanguageModel, Configs
from audio_processor import STT
from threading import Thread

import ssl
import time
import wave
import audioop
import io

SERVER_PORT = 8000

log = logger("SERVER")

CWD = dirname(realpath(__file__))

STATIC_FILE_B_DIR = "%s/templates" % CWD
STATIC_FILE_JS_DIR = "%s/js" % STATIC_FILE_B_DIR
STATIC_FILE_CSS_DIR = "%s/css" % STATIC_FILE_B_DIR
STATIC_FILE_FONTS_DIR = "%s/fonts" % STATIC_FILE_B_DIR
STATIC_FILE_LESS_DIR = "%s/less" % STATIC_FILE_B_DIR

SSL_DIR = "%s/ssl/" % CWD
SSL_OPTIONS = {
        "ssl_version": ssl.PROTOCOL_TLSv1,
        "certfile": SSL_DIR + "server.cert",
        "keyfile": SSL_DIR + "server.key"
}

"""
BASE64_PREFIX = "data:audio/wav;base64,"

MODEL_DIR = "%s/model" % CWD
DATA_DIR = "%s/data" % CWD
LANGUAGE_MODELS = {
    "English": {
        "hmm": "en-us/en-us",
        "lm": "en-us/en-us.lm.bin",
        "dict": "en-us/cmudict-en-us.dict"
    },
    
    "Russian": {
        "hmm": "ru/ru",
        "lm": "ru/ru.lm",
        "dict": "ru/ru.dic"
    },

    "French": {
        "hmm": "fr/fr",
        "lm": "fr/fr.lm.dmp",
        "dict": "fr/fr.dict"
    },

    "German": {
        "hmm": "de/de",
        "lm": "de/cmusphinx-voxforge-de.lm.bin",
        "dict": "de/cmusphinx-voxforge-de.dic" 
    },

    "Hindi": {
        "hmm": "hi/hi",
        "lm": "hi/hindi.lm",
        "dict": "hi/hindi.dic"
    },

    "Mandarin": {
        "hmm": "zh/zh",
        "lm": "zh/zh_broadcastnews_64000_utf8.DMP",
        "dict": "zh/zh_broadcastnews_utf8.dic"
    },

    "Dutch": {
        "hmm": "nl/nl",
        "lm": "nl/voxforge_nl_sphinx.lm.bin",
        "dict": "nl/voxforge_nl_sphinx.dic"
    }
}

SOX_BIN = "sox"

audio = PyAudio()
audio_silence = chr(0) * 4096
stream = audio.open(format=paInt16, frames_per_buffer=2048, channels=1, rate=16000, output=True)
"""

configs = Configs()

class ClientHandler(WebSocketHandler):
    def allow_draft76(self):
        return True

    def check_origin(self, origin):
        return True

    def open(self):
        self._id = 0
        self._model = 0
        self._state = 0
        self._stt = STT() # Create the new Speech To Text object
        self._stt.set_subprocess_callback(self.__handle_subprocess)
        log.info("Connected to %s" % self.request.remote_ip)

    def __handle_subprocess(self, command):
        self.__send_json(command)

    def __handle_model(self, model_data):
        global configs
        log.info("Client sent language model! %s" % str(model_data))
        language_model = configs.get_stt_data(model_data["model"])
        self._stt.set_language_model(language_model)
        self._state = 10
    
    def __handle_audio_chunk(self, audio_chunk):
        log.info("Client sent audio chunk!")
        self._stt.process_audio_chunk(audio_chunk)

    def __handle_start_audio(self):
        log.info("Client started to speak!")
        self._stt.start_audio_proc()
        self._state = 20

    def __handle_stop_audio(self):
        log.info("Client stopped speaking!")
        self._stt.stop_audio_proc()
        self._state = 10

    """
    def __handle_wav_packet(self, audio_packet):
        wav_file = wave.open(io.BytesIO(audio_packet), 'r')
        wav_frame_count = wav_file.getnframes()
        to_ret = {
            "frames": wav_file.getnframes(),
            "data": wav_file.readframes(wav_frame_count),
            "rate": wav_file.getframerate()
        }
        wav_file.close()
        return to_ret

    def __handle_audio_packet(self, audio_packet):
        log.info("Client sent audio chunk!")
        audio = audio_packet["audio"]
        no_padding = message.replace(BASE64_PREFIX, "") if BASE64_PREFIX in audio else audio
        decoded_audio = b64decode(no_padding)
        wav_data = self.__handle_wav_packet(decoded_audio)
        wav_frames = wav_data["frames"]
        wav_raw_data = wav_data["data"]
        wav_rate = wav_data["rate"]

        wav_converted = audioop.ratecv(wav_raw_data, 2, 1, wav_rate, 16000, None)[0]
       #self.__change_rate(wav_raw_data, 1, wav_rate, 16000) # audioop.ratecv(wav_data, 2, 1, wav_rate, 16000, None)[0]
        
        self._decoder.start_utt()
        self._decoder.process_raw(wav_converted, False, False)
        self._decoder.end_utt()

        if self._decoder.hyp() is None:
            self.__send_json({"words": False})
        else:
            words = [[seg.word, seg.prob] for seg in self._decoder.seg()]
            print("Words: %s" % str(words))
            # stream.write(wav_converted)
            self.__send_json({"words": words})

    def __change_rate(self, input_audio, channels, current_rate, output_rate):
        to_run = [SOX_BIN, 
                    "-V",
                    "-t", "raw",
                    "-b", "16",
                    "-e", "signed",
                    "-c", str(channels),
                    "-r", str(current_rate),
                    "-",
                    "-t", "wav",
                    "-r", str(output_rate),
                    "-"]
        pipe = Popen(to_run, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        out, err = pipe.communicate(input=input_audio)
        if len(err) > 0:
            log.error("Sample rate conversion failed! (err: %s)" % err)
        return out
    """

    def on_message(self, message):
        log.debug("Recieved packet")
        j_obj = {}
        try:
            j_obj = loads(message)
        except Exception as err:
            #log.error("Failed decoding packet! (err: %s)" % str(err))
            self.__send_error(err)
            return

        if "model" in j_obj:
            self.__handle_model(j_obj)
        elif "start_speech" in j_obj and self._state == 10:
            self.__handle_start_audio()
        elif "start_speech" in j_obj and self._state < 10:
            self.__send_error("The language model is not currently set!")
        elif "audio" in j_obj and self._state == 20:
            self.__handle_audio_chunk(j_obj)
        elif "audio" in j_obj and self._state < 20:
            self.__send_error("The language model is not currentl set, and/or the start speech command hasn't been sent!")
        elif "end_speech" in j_obj and self._state == 20:
            self.__handle_stop_audio()
        elif "end_speech" in j_obj and self._state != 20:
            self.__send_error("Unecessary end speech has been called!")

    def __set_model(self, model):
        log.info("Setting model to %s" % model)
        try:
            self._model_config = LANGUAGE_MODELS[model]
        except KeyError as err:
            log.error("Couldn't set model %s (err: %s)" % (model, str(err)))
            return False
        self._config = Decoder.default_config()
        print(join(MODEL_DIR, self._model_config["lm"]))
        self._config.set_string('-hmm', join(MODEL_DIR, self._model_config["hmm"]))
        self._config.set_string('-lm', join(MODEL_DIR, self._model_config["lm"]))
        self._config.set_string('-dict', join(MODEL_DIR, self._model_config["dict"]))
        self._decoder = Decoder(self._config)
        log.info("Model set!")
        return True

    def __send_error(self, error):
        self.__send_json({"error": str(error)})

    def __send_json(self, to_write):
        try:
            to_write["id"] = self._id # Send the preassigned id to make sure it's the correct client
            self.write_message(dumps(to_write))
        except Exception as err:
            log.error("Failed sending %s to client!" % to_write)

    def on_close(self):
        log.info("Closed connection to %s" % self.request.remote_ip)

log.debug("Initializing websocket server")

class IndexPageHandler(RequestHandler):
    def get(self):
        self.render("index.html")

class AudioServer(Application):
    def __init__(self):
        handlers = [
            (r'/', IndexPageHandler),
            (r'/ws', ClientHandler),
            (r'/js/(.*)', StaticFileHandler, {'path': STATIC_FILE_JS_DIR}),
            (r'/css/(.*)', StaticFileHandler, {'path': STATIC_FILE_CSS_DIR}),
            (r'/fonts/(.*)', StaticFileHandler, {'path': STATIC_FILE_FONTS_DIR}),
            (r'/less/(.*)', StaticFileHandler, {'path': STATIC_FILE_LESS_DIR})
        ]

        settings = {
                "template_path": "templates"
        }

        Application.__init__(self, handlers, **settings)

if __name__ == "__main__":
    options.parse_command_line()
    application = AudioServer()
    server = HTTPServer(application) # , ssl_options=SSL_OPTIONS)
    server.listen(SERVER_PORT)
    log.info("Listening on port %d" % SERVER_PORT)
    IOLoop.instance().start()
