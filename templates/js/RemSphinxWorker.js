importScripts("WavAudioEncoder.min.js", "robust-websocket.js");

var sampleRate = 44100,
	numChannels = 1,
	options = undefined,
	maxBuffers = undefined,
	encoder = undefined,
	bufferCount = 0,
	ws = undefined,
	fileReader = undefined,
	wsState = 0;

//Handle any error messages via the main process/script
function error(message, code) {
	self.postMessage({ command: "error", message: "wav: " + message, code: code });
}


//Setup the worker properties
function init(data) {
	sampleRate = data.config.sampleRate;
	numChannels = data.config.numChannels;
	options = data.options;

	ws = new RobustWebSocket(data.options.address, null, {
		shouldReconnect: function(event, ws) {
			return true;
		},
		
		automaticOpen: false
	});

	ws.onmessage = function(event) {
		var response = JSON.parse(event.data);

		if(response.hasOwnProperty("error")) {
			error(response.error, 1);
			return;
		}

		//By default keyphrases are turned off (double check to see if the flag has been set)
		var keyphrases = false;
		if(response.hasOwnProperty("keyphrases")) {
			keyphrases = response.keyphrases;
		}

		switch(wsState) {
			case 0:
				if(response.success) {
					wsState = 10;
					self.postMessage({
						command: "loaded",
						success: true
					});

					self.postMessage({
						command: "waiting"
					});
				} else {
					error("Server failed to initialize", 2);
					wsState = 0; //Set the server 
					
					self.postMessage({
						command: "loaded",
						success: false
					});
					
					//Restart the connection with the server
					ws.close();
					ws.open();
				}
				break;
			case 10:
				if(response.hasOwnProperty("hypothesis")) {
					if(!response.silence) {
						if(keyphrases) {
							var hypothesis = (response.hypothesis == undefined) ? [{}] : (response.hypothesis);
						} else {
							var hypothesis = (response.hypothesis == undefined) ? "(inaudible)" : (response.hypothesis + ". ");
						}

						self.postMessage({
							command: "hypothesis",
							keyphrases: keyphrases,
							hyp: hypothesis
						});
					} else {
						self.postMessage({
							command: "nocatch"
						});
					}
				} else if(response.hasOwnProperty("partial_hypothesis")) {
					if(!response.partial_silence) { 
						if(response.partial_hypothesis != undefined) {
							self.postMessage({
								command: "partial_hypothesis",
								keyphrases: keyphrases,
								partial_hyp: response.partial_hypothesis
							});
						}
					} else {
						error("Failed loading partial hypothesis!");
					}
				}
				break;
		}
	};

	//The blob wav file handler
	file_reader = new FileReader();

	//Handle the encoded wav blob
	file_reader.onload = function(progress) {
		//Remove the data blob url base64 prefix
		var arr_buff = this.result.replace(/^data:audio\/(wav|mp3);base64,/, "");

		//Send the audio chunk to the server
		ws.send(JSON.stringify({
			audio: arr_buff //Send only the base64 audio chunk
		}));
	}

	ws.open(); //Start the websocket client
}

function setLanguageModel(modelData) {
	wsState = 0; //Set the websocket state to listen for a model set success
	ws.send(JSON.stringify({
		model: modelData.model,
		accent: modelData.accent
	}));
}

function start(bufferSize) {
	//Set the chunking rate at which to return the encoded audio at
	maxBuffers = Math.ceil((options.progressInterval / 1000) * sampleRate / bufferSize);
	
	//Create the initial encoder object
	encoder = new WavAudioEncoder(sampleRate, numChannels);
}

//Tell the server to start listening
function startSpeech() {
	ws.send(JSON.stringify({
		start_speech: true
	}));
}

//Tell the server to either stop or start processing keyphrases
function setKeyphrases(keyphrases) {
	ws.send(JSON.stringify({
		set_keyphrases: keyphrases
	}));
}

//Process an audio chunk
function chunk(buffer) {
	encoder.encode(buffer); //Encode the newly sent buffer
	
	if(bufferCount++ >= maxBuffers) {
		finishChunk(); //Send the audio chunk back to the server
	}
}

//Finish the encoding chunk and send it back to the main process
function finishChunk() {
	var audioBlob = encoder.finish(options.mimeType);
	
	file_reader.readAsDataURL(audioBlob); //Read blob into base64 dataURL

	self.postMessage({
		command: "processed",
		blob: audioBlob
	});

	cleanup();
	//Create a new WavAudioEncoder object to handle the audiochunk
	encoder = new WavAudioEncoder(sampleRate, numChannels);
}

//Tell the server to stop listening
function endSpeech() {
	ws.send(JSON.stringify({
		end_speech: true
	}));
}

//Cleanup all of the encoding objects and reset the buffer limit
function cleanup() {
	encoder = undefined;
	bufferCount = 0;
}

//Handle messages from the main process/script
self.onmessage = function(event) {
	var data = event.data;
	switch(data.command) {
		case "init": init(data);							break;
		case "options": setOptions(data.options);			break;
		case "model": setLanguageModel(data);				break;
		case "start": start(data.bufferSize);				break;
		case "start_speech": startSpeech();					break;
		case "keyphrases": setKeyphrases(data.keyphrases);	break;
		case "chunk": chunk(data.buffer);					break;
		case "end_speech": endSpeech();						break;
		case "shutdown": cleanup();							break;
	}
}
