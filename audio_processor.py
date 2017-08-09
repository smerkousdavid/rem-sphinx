# -*- coding: utf-8 -*-
"""RemSphinx speech to text audio processor

This module is desgigned to do the entire audio processing for the application.
Once a client is within a session, this program will fork it off to another sub-applicaiton; to
hopefully escape the GIL for true multithreading.

Developed By: David Smerkous
"""

from logger import logger
from configs import LanguageModel, Configs
from text_processor import TextProcessor
from pocketsphinx.pocketsphinx import Decoder
from pyaudio import PyAudio, paInt16
from base64 import b64decode
from multiprocessing import Process, Pipe, Lock, Event, current_process
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
        self._shutdown_event = Event() # Create an event to handle the STT shutdown
        self._process = Process(target=self.__worker, args=((self._p_out, self._p_in), log)) # Create the subprocess fork
        self._process.start() # Start the subprocess fork

        self._subprocess_t = Thread(target=self.__handle_subprocess)
        self._subprocess_t.setDaemon(True)
        self._subprocess_t.start()

    def __worker(self, pipe, l_log):
        """The core of the STT program, this is the multiprocessed part

        Note:
            Multiprocessing will require a pipe between the parent and child subprocess.
            Since this is the case, the worker subprocess cannot access non-shared variables

        """

        l_log.debug("STT worker started")

        audio_processor = AudioProcessor() # Create a new audio processing object
        text_processor = TextProcessor() # Remember that we can't load the text processor nltk model until the nltk model is set from the client language
        config = Decoder.default_config() # Create a new pocketsphinx decoder with the default configuration, which is English
        decoder = None
        nltk_model = None
        mutex_flags = { "keyphrases": { "use": False } }
        shutdown_flags = { "shutdown": False, "decoder": None }

        def send_json(pipe, to_send):
            """Internal worker method to send a json through the parent socket

            Arguments:
                pipe (:obj: socket): The response pipe to send to the parent process
                to_send (:obj: dict): A dictionary to be sent to the parent socket

            """
            try:
                ret = self.__send_buffered(pipe, to_send) # Send the message passed by argument back to the parent process
                if not ret[0]:
                    l_log.error("Failed to send buffered message to the parent process! (err: %s)" % ret[1])
            except Exception as err:
                l_log.error("Failed to send json! (err: %s)" % str(err))

        def send_error(pipe, error):
            """Internal worker method to send a json error through the parent socket

            Arguments:
                pipe (:obj: socket): The response pipe to send to the parent process
                error (str): The string error message to send

            """
            send_json(pipe, {"error": error}) 

        def load_models(pipe, config, models):
            """Internal worker method to load the language model

            Note:
                Some lanaguages take a long time to load. English is by far
                the fastest language to be loaded as a model.
            
            Arguments:
                pipe (:obj: socket): The response pipe to send to the parent process
                models (dict): The language and nltk models developed by the parent process
           
            Returns: (Decoder)
                The STT decoder object and the nltk model

            """
            
            language_model = models["language_model"]
            nltk_model = models["nltk_model"]

            if False in [language_model.is_valid_model(), nltk_model.is_valid_model()]:
                l_log.error("The language model %s is invalid!" % str(language_model.name))
                send_error(pipe, "Failed loading language model!")
                return

            # Load the model configurations into pocketsphinx
            config.set_string('-hmm', str(language_model.hmm))
            config.set_string('-lm', str(language_model.lm))
            config.set_string('-dict', str(language_model.dict))
            decoder = Decoder(config)

            send_json(pipe, {"success": True}) # Send a success message to the client

            l_log.debug("Set the language model to %s" % str(language_model.name))
            
            return decoder, nltk_model # Return the new decoder and nltk model

        def process_text(pipe, text, is_final, args):
            """Internal worker method to process the Speech To Text phrase

            Arguments:
                pipe (:obj: socket): The response pipe to send to the parent process
                text (str): The spoken text to further process
                is_final (boo): If the text being processed is the final text else it's a partial result
                args (dict): Any other flags specifically required for a final or partial speech result
            """

            generate_keyphrases = mutex_flags["keyphrases"]["use"]
            keyphrases = []

            if generate_keyphrases:
                text_processor.generate_keyphrases(text) # Generate keyphrases from the given text
                keyphrases_list = text_processor.get_keyphrases()

                for keyphrase in keyphrases_list:
                    to_append_keyphrase = {
                        "score": keyphrase[0],
                        "keyphrase": keyphrase[1]
                    }
                    keyphrases.append(to_append_keyphrase)
            else:
                keyphrases = text # Don't do any processing and just pass the text into the keyphrases

            # Generate the json to be sent back to the client
            hypothesis_results = args
            hypothesis_results["keyphrases"] = generate_keyphrases
            if is_final:
                hypothesis_results["hypothesis"] = keyphrases
            else:
                hypothesis_results["partial_hypothesis"] = keyphrases

            print(hypothesis_results)

            # Send the results back to the client
            send_json(pipe, hypothesis_results)

        def start_audio(pipe, decoder, args):
            """Internal worker method to start the audio processing chunk sequence

            Note:
                This must be called before the process_audio method or the STT engine will not process the audio chunks

            Arguments:
                pipe (:obj: socket): The response pipe to send to the parent process
                decoder (Decoder): The pocketsphinx decoder to control the STT engine
                args (dict): All of the available arguments passed by the parent process

            """

            if decoder is None:
                l_log.error("Language model is not loaded")
                send_error(pipe, "Language model not loaded!")
                send_json(pipe, {"decoder": False})
                return
           
            l_log.debug("Starting the audio processing...")

            decoder.start_utt() # Start the pocketsphinx listener

            # Tell the client that the decoder has successfully been loaded
            send_json(pipe, {"decoder": True})

        def process_audio(pipe, decoder, args):
            """Internal worker method to process an audio chunk

            Note:
                The audio chunk is expected to be in base64 format

            Arguments:
                pipe (:obj: socket): The response pipe to send to the parent process
                decoder (Decoder): The pocketsphinx decoder to control the STT engine
                args (dict): All of the available arguments passed by the parent process

            """
            if decoder is None:
                l_log.error("Language model is not loaded")
                send_error(pipe, "Language model not loaded!")
                return

            l_log.debug("Processing audio chunk!")

            audio_chunk = args["audio"] # Retrieve the audio data
            processed_wav = audio_processor.process_chunk(audio_chunk) # Process the base64 wrapped audio data
           
            l_log.debug("Recognizing speech...")

            decoder.process_raw(processed_wav, False, False) # Process the audio chunk through the STT engine

            hypothesis = decoder.hyp() # Get pocketshpinx's hypothesis

            # Send back the results of the decoding
            if hypothesis is None:
                l_log.debug("Silence detected")
                send_json(pipe, {"partial_silence": True, "partial_hypothesis": None})
            else:
                hypothesis_results = {
                    "partial_silence": False if len(hypothesis.hypstr) > 0 else True,
                }

                l_log.debug("Partial speech detected: %s" % str(hypothesis.hypstr))
                process_text(pipe, hypothesis.hypstr, False, hypothesis_results)

            l_log.debug("Done decoding speech from audio chunk!")

        def stop_audio(pipe, decoder, args):
            """Internal worker method to stop the audio processing chunk sequence

            Note:
                This must be called after the process_audio method or the STT engine will continue to listen for audio chunks

            Arguments:
                pipe (:obj: socket): The response pipe to send to the parent process
                decoder (Decoder): The pocketsphinx decoder to control the STT engine
                args (dict): All of the available arguments passed by the parent process

            """

            if decoder is None:
                l_log.error("Language model is not loaded")
                send_error(pipe, "Language model not loaded!")
                send_json({"decoder": False})
                return

            l_log.debug("Stopping the audio processing...")

            decoder.end_utt() # Stop the pocketsphinx listener

            l_log.debug("Done recognizing speech!")

            hypothesis = decoder.hyp() # Get pocketshpinx's hypothesis
            logmath = decoder.get_logmath()

            # Send back the results of the decoding
            if hypothesis is None:
                l_log.debug("Silence detected")
                send_json(pipe, {"silence": True, "hypothesis": None})
            else:
                hypothesis_results = {
                    "silence": False if len(hypothesis.hypstr) > 0 else True,
                    "score": hypothesis.best_score,
                    "confidence": logmath.exp(hypothesis.prob)
                }

                l_log.debug("Speech detected: %s" % str(hypothesis.hypstr))
                process_text(pipe, hypothesis.hypstr, True, hypothesis_results)

        def shutdown_thread(self, l_log):
            """Worker method to handle the checking of a shutdown call

            Note:
                To reduce overhead, this thread will only be called every 100 milliseconds

            """
            while not shutdown_flags["shutdown"]:
                try:
                    if self._shutdown_event.is_set():
                        l_log.debug("Shutting down worker thread!")
                        shutdown_flags["shutdown"] = True # Exit the main loop
                        if shutdown_flags["decoder"] is not None:
                            try:
                                shutdown_flags["decoder"].end_utt()
                            except Exception as err:
                                l_log.debug("STT decoder object returned a non-zero status")
                        else:
                            l_log.warning("The decoder object is already None!")

                        break
                    sleep(0.1)
                except Exception as err:
                    l_log.error("Failed shutting down worker thread! (err: %s)" % str(err))

        shutdown_t = Thread(target=shutdown_thread, args=(self, l_log,))
        shutdown_t.setDaemon(True)
        shutdown_t.start()

        p_out, p_in = pipe
        while not shutdown_flags["shutdown"]:
            try:
                try:
                    command = self.__get_buffered(p_out) # Wait for a command from the parent process
                    if "set_models" in command["exec"]: # Check to see if our command is to 
                        decoder, nltk_model = load_models(p_out, config, command["args"])
                        text_processor.set_nltk_model(nltk_model) # Set the text processor nltk model
                        shutdown_flags["decoder"] = decoder
                    elif "start_audio" in command["exec"]:
                        start_audio(p_out, decoder, command["args"])
                    elif "process_audio" in command["exec"]:
                        process_audio(p_out, decoder, command["args"])
                    elif "stop_audio" in command["exec"]:
                        stop_audio(p_out, decoder, command["args"])
                    elif "set_keyphrases" in command["exec"]:
                        mutex_flags["keyphrases"] = command["args"]
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

    def set_models(self, language_model, nltk_model):
        """Method to set the STT object's language model

        Note:
            This will reload the entire language model and might take some time
        
        Arguments:
            language_model (LanguageModel): The loaded language model to be processed for the STT engine
            nltk_model (NLTKModel): The loaded nltk model to be processed for the text processing object
        """
        self.__send_to_worker("set_models", {"language_model": language_model, "nltk_model": nltk_model})

    def process_audio_chunk(self, audio_chunk):
        """Method to process an audio chunk

        Note:
            The audio chunk is expected to be in base64 format

        Arguments:
            audio_chunk (str): The base64 wrapped audio chunk to be parsed and sent back to the client
        """
        self.__send_to_worker("process_audio", audio_chunk)

    def start_audio_proc(self):
        """Method to start the audio processing

        Note:
            This must be called before the process_audio_chunk method

        """
        self.__send_to_worker("start_audio", {})

    def stop_audio_proc(self):
        """Method to stop the audio processing

        Note:
            This must be called after the series of process_audio_chunk method calls

        """
        self.__send_to_worker("stop_audio", {})

    def set_keyphrases(self, keyphrases):
        """Method to set the keyphrases flag
        
        Arguments:
            keyphrases (dict): The keyphraeses flags
        """
        self.__send_to_worker("set_keyphrases", keyphrases)

    def shutdown(self):
        """Method to shutdown and cleanup the STT engine object

        Note:
            The shutdown will not happen immediately, and this function might lag the entire
            process out for a few hundred milliseconds
        """
        self._shutdown_event.set() # Set the multiprocessing shutdown_event to set

        def terminate_soon(self):
            try:
                sleep(1) # Wait a second for the subprocess to clean itself
                self._process.terminate() # Destroy the entire subprocess
            except Exception as err:
                log.error("Failed terminating worker subprocess! (err: %s)" % str(err)) 

        # Wait for the subprocess to retrieve the shutdown event and then destroy the subprocess
        terminate_soon_t = Thread(target=terminate_soon, args=(self,))
        terminate_soon_t.setDaemon(True)
        terminate_soon_t.start()

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
        """P0ublic method to process an audio chunk received by the server

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
