# -*- coding: utf-8 -*-
"""CloudyBoss speech to text audio processor

This module is desgigned to do the entire audio processing for the application.
Once a client is within a session, this program will fork it off to another sub-applicaiton; to
hopefully escape the GIL for true multithreading.

"""

from pocketsphinx.pocketsphinx import Decoder
from subprocess import Popen, PIPE
from logger import logger
from configs import LanguageModel, Configs
from pyaudio import PyAudio, paInt16
from base64 import b64decode
from multiprocessing import Process, Pipe, Lock, current_process
from threading import Thread
from json import loads, dumps
from time import sleep

import wave
import audioop
import io
import jsonpickle
import re

log = logger("AUDIOP")

# py_audio = PyAudio()
# audio_stream = py_audio.open(format=paInt16, frames_per_buffer=2048, channels=1, rate=16000, output=True) 

"""Global module level definitions
logger: log - The module log object so that printed calls can be backtraced to this file

--DEBUGGING FEATURES-- Uncomment the above lines to add realtime audio playback
PyAudio: py_audio - The PyAudio parent object (This should only be used when debugging)
PyAudioStream: audio_stream - The PyAudio sub-stream audio object
"""

class STT(object):
    """Speech To Text processing class
        
        This is a multithreaded wrapper for the pocketsphinx audio N-Gram processing class.
        Create a new STT object for every client that connects to the websocket

        Attributes:
            
    """

    def __init__(self):
        self._is_ready = None
        self._subprocess_callback = None
        self._loaded_model = False
        self._p_out, self._p_in = Pipe() # Create a new multiprocessing Pipe pair
        self._lock = Lock() # Create a mutex lock between the parent process and the subprocess
        self._process = Process(target=self.__worker, args=((self._p_out, self._p_in), log, self._lock)) # Create the subprocess fork
        self._process.start() # Start the subprocess fork

        self._subprocess_t = Thread(target=self.__handle_subprocess)
        self._subprocess_t.setDaemon(True)
        self._subprocess_t.start()

    def __worker(self, pipe, l_log, lock):
        """The core of the STT program, this is the multiprocessed part

        Note:
            Multiprocessing will require a pipe between the parent and child subprocess.
            Since this is the case, the worker subprocess cannot access non-shared variables

        """

        l_log.debug("STT worker started")

        audio_processor = AudioProcessor() # Create a new audio processing object
        config = Decoder.default_config() # Create a new pocketsphinx decoder with the default configuration, which is English
        decoder = None

        def send_json(pipe, to_send):
            """Internal worker method to send a json through the parent socket

            Arguments:
                pipe (:obj: socket): The response pipe to send to the parent process
                to_send (:obj: dict): A dictionary to be sent to the parent socket

            """
            try:
                self.__send_buffered(pipe, to_send)
                #pipe.send(to_send) # Dump the dictionary into a json stirng then send that through the websocket
            except Exception as err:
                l_log.error("Failed to send json! (err: %s)" % str(err))

        def send_error(pipe, error):
            """Internal worker method to send a json error through the parent socket

            Arguments:
                pipe (:obj: socket): The response pipe to send to the parent process
                error (str): The string error message to send

            """
            send_json(pipe, {"error": error}) 

        def load_model(pipe, config, language_model):
            """Internal worker method to load the language model

            Note:
                Some lanaguages take a long time to load. English is by far
                the fastest language to be loaded as a model.
            
            Arguments:
                pipe (:obj: socket): The response pipe to send to the parent process
                language_model (LanguageModel): The language model developed by the parent process
           
            Returns: (Decoder)
                The STT decoder object
            """
            
            if not language_model.is_valid_model():
                l_log.error("The language model %s is invalid!" % str(language_model.name))
                send_error(pipe, "Failed loading language model!")
                return

            # Load the model configurations into pocketsphinx
            config.set_string('-hmm', str(language_model.hmm))
            config.set_string('-lm', str(language_model.lm))
            config.set_string('-dict', str(language_model.dict))
            decoder = Decoder(config)

            send_json(pipe, {"success": True}) # Send a success message to the client

            l_log.info("Set the language model to %s" % str(language_model.name))
            
            return decoder # Return the new decoder

        def process_audio(pipe, decoder, args):
            """Internal worker method to process an audio chunk

            Note:
                The audio chunk is expected to be in base64 format

            Arguments:
                pipe (:obj: socket): The response pipe to send to the parent process
                args (dict): All of the available arguments passed by the parent process
            """
            if decoder is None:
                l_log.error("Language model is not loaded")
                send_error(pipe, "Language model not loaded!")

            l_log.info("Processing audio chunk!")

            audio_chunk = args["audio"] # Retrieve the audio data
            processed_wav = audio_processor.process_chunk(audio_chunk) # Process the base64 wrapped audio data
           
            l_log.info("Recognizing speech...")

            decoder.start_utt() # Start the pocketsphinx listener
            decoder.process_raw(processed_wav, False, False) # Process the audio chunk through the STT engine
            decoder.end_utt() # Stop the pocketsphinx listener

            l_log.info("Done recognizing speech!")

            hypothesis = decoder.hyp() # Get pocketshpinx's hypothesis
            logmath = decoder.get_logmath()

            # Send back the results of the decoding
            if hypothesis is None:
                l_log.info("Silence detected")
                send_json(pipe, {"silence": True})
            else:
                hypothesis_results = {
                    "silence": False if len(hypothesis.hypstr) > 0 else True,
                    "hypothesis": hypothesis.hypstr,
                    "score": hypothesis.best_score,
                    "confidence": logmath.exp(hypothesis.prob)
                }

                l_log.info("Speech detected: %s" % str(hypothesis_results))
                send_json(pipe, hypothesis_results)

        p_out, p_in = pipe
        while True:
            try:
                try:
                    command = self.__get_buffered(p_out) # Wait for a command from the parent process
                    if "set_model" in command["exec"]: # Check to see if our command is to 
                        decoder = load_model(p_out, config, command["args"])
                    elif "process_audio" in command["exec"]:
                        process_audio(p_out, decoder, command["args"])
                    else:
                        l_log.error("Invalid command %s" % str(command))
                        send_error(socket, "Invalid command!")
                except (EOFError, IOError) as err:
                    continue
            except Exception as err:
                l_log.error("Failed recieving command from subprocess (id: %d) (err: %s)" % (current_process().pid, str(err)))


    def __send_to_worker(self, t_exec, to_send):
        """Private method to handle sending to the subprocess worker

        Arguments:
            t_exec (str): The subprocess execution method (ex: set_model or process_audio)
            to_send (:obj: dict): The dictionary arguments to send to the subprocess worker

        """
        ret = self.__send_buffered(self._p_in, {"exec": t_exec, "args": to_send})
        if not ret[0]:
            log.error("Failed to send buffered! (err: %s)" % ret[1])

    def __get_buffered(self, pipe):
        """Private method to handle buffered recieving from a pipe

        Note:
            This concept should work on most sockets

        Arguments:
            pipe (Pipe): The pipe to recieve from

        Returns: (obj)
            The decoded jsonpickle object

        """

        raw_command = ""
        while True: # Load the message into a buffer
            try:
                raw_command += pipe.recv() # Wait for a command from the child process
                if "<!EOF!>" in raw_command:
                    raw_command = raw_command.replace("<!EOF!>", "")
                    break
            except (EOFError, IOError) as err:
                sleep(0.01)
        return jsonpickle.decode(raw_command) # Decode the object

    def __send_buffered(self, pipe, to_send):
        """Private method to handle buffered sending to a pipe

        Note:
            This concept should work on most sockets

        Arguments:
            pipe (Pipe): The pipe to send to
            to_send (obj): Any object you wish to send through the pipe
        """

        def send_pipe(pipe, chunk):
            timeout = 0 # Broken pipe detection
            while True:
                try:
                    pipe.send(chunk)
                    return True
                except (EOFError, IOError) as err:
                    timeout += 1
                    if timeout > 1000: # Don't attempt to send to a broken pipe more than 1000 times
                        return False
                    sleep(0.0005) # Wait 500 nano seconds
                    pass

        try:
            pickled = jsonpickle.encode(to_send) # Encode the object with EOF
            chunks = re.findall(".{1,3000}", pickled) # Chunk the string into a string list
            for chunk in chunks:
                if not send_pipe(pipe, chunk): # Send each chunk individually
                    return (False, "Chunk failed to send!")
            if not send_pipe(pipe, "<!EOF!>"): # Send an EOF to indicate the end of file
                return (False, "EOF failed ot send")
            return (True, "")
        except Exception as err:
            return (False, str(err))

    def __handle_subprocess(self):
        """Private method to handle the return callback from the subprocess

        Note:
            This should run in its own thread
        """
        
        while True:
            try:
                try:
                    command = self.__get_buffered(self._p_in)
                    if self._subprocess_callback is not None:
                        self._subprocess_callback(command)
                    else:
                        log.warning("Subprocess callback is None!")
                except (EOFError, IOError) as err:
                    sleep(0.01) # Wait 10 milliseconds
                    continue
            except Exception as err:
                log.error("Failed recieving command from parent process (err: %s)" % str(err))


    def set_subprocess_callback(self, callback):
        """Method to set the callback of the child process

        Note:
            This function will be called within the parent process thread
        
        Arguments:
            callback (:obj: method): The callback method to handle the subprocess calling

        """
        self._subprocess_callback = callback

    def set_language_model(self, language_model):
        """Method to set the STT object's language model

        Note:
            This will reload the entire language model and might take some time
        
        Arguments:
            language_model (LanguageModel): The loaded language model to be processed for the STT engine
        """
        self.__send_to_worker("set_model", language_model)

    def process_audio_chunk(self, audio_chunk):
        """Method to process an audio chunk

        Note:
            The audio chunk is expected to be in base64 format

        Arguments:
            audio_chunk (str): The base64 wrapped audio chunk to be parsed and sent back to the client
        """
        self.__send_to_worker("process_audio", audio_chunk)

    def is_ready(self, callback = None):
        """Method to return the current state of the language model loading

        Arguments:
            callback (:obj: method) (optional): The callback method to call when the STT has loaded its language model

        Note:
            Call this before doing any processing

        Returns: (bool)
            True if the model is ready False otherwise
        """
        if callback is not None:
            self._is_ready = callback
        return self._loaded_model


class AudioProcessor(object):
    """General audio processing utilities class

    This class, is just a wrapper for all clients to do generic processing.
    Some handling of 

    Attributes:
        _io (BytesIO): Generic BytesIO object to memory map the wav file

    """

    def __init__(self):
        self._io = None

    def process_chunk(self, audio_chunk):
        """Public method to process an audio chunk received by the server

        Note:
            The current expectation is that the audio chunk is wrapped in base64

        Arguments:
            audio_chunk (str): The base64 wrapped audio chunk to be processed

        Returns: (bytes)
            The raw -- converted -- wav data to be then later processed by the STT engine
        """

        raw_wav = self.__process_base64(audio_chunk) # Unwrap the raw audio data
        processed_wav = self.__process_wave(raw_wav) # Process the wav data to retrieve some basic information
        converted_wav = self.__convert_rate(processed_wav) # Convert the processed wav into a usable format for the STT engine
        return converted_wav

    def __process_wave(self, wav_packet):
        """Private method to load the raw wave data to memory map and get basic data from the raw data

        Arguments:
            wav_packet (bytes): The raw wave data to be loaded into the temporary memory mapped file

        Returns: (dict)
            The the parsed wave data from the temporary mapped file
        """
        
        self._io = io.BytesIO(wav_packet) # Create a memory byte buffer
        w_file = wave.open(self._io) # Open the memory buffer to create a memory mapped file
        w_frames = w_file.getnframes() # Get total wav frame count
        to_ret = {
            "frames": w_frames,
            "data": w_file.readframes(w_frames),
            "rate": w_file.getframerate()
        }
        return to_ret

    def __process_base64(self, base_64):
        """Private method to decode and return the auto data wrapped in the base64 message

        Note:
            This will remove the blob prefix if the data is returned from a browser

        Arguments:
            base_64 (str): The base64 str that needs to be processed

        Returns: (bytes)
            The raw wav data of the base64 wrapped audio
        """
        
        try:
            # Web blob prefix to detect and remove
            audio_prefix = Configs.get_stt()["audio_prefix"]

            if audio_prefix is None:
                raise TypeError("AudioPrefix cannot be none")
        
            return b64decode(base_64.replace(Configs.get_stt()["audio_prefix"], ""))
        except Exception as err:
            log.error("Error processing base64 audio packet: (err: %s)" % str(err))

    def __convert_rate(self, wav_parsed):
        """Private method to handle the processed wav data and convert it into a usuable rate for the STT engine

        Note:
            CMU Sphinx 'highly' recommends that the input sample rate is 16Khz. For the best, and the most accurate, STT results 

        Arguments:
            wav_parsed (dict): The returned dictionary from the process_wav method

        Returns: (bytes)
            The raw, converted, wav data to then be processed through the STT engine
        """
        return audioop.ratecv(wav_parsed["data"], 2, 1, wav_parsed["rate"], 16000, None)[0]