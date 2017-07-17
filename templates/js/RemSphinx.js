(function(window) {

//Method to compare current objects to new one, then combine the two
var extend = function() {
	var target = arguments[0],
		sources = [].slice.call(arguments, 1);
	for(var i = 0; i < sources.length; ++i) {
		var src = sources[i];
		for(key in src) {
			var val = src[key];
			target[key] = typeof val === "object" ?
					extend(typeof target[key] === "object" ? 
					target[key] : {}, val) : val;

		}
	}
	return target
}

//Default configuration
var CONFIGS = {
	workerDir: "js/", //The audioencoding working directory
	numChannels: 1, //Valid options are 1 or 2
	speakingGain: 70, //Set the default speaking gain for the audio level to be at
	minSpeakingTime: 2000, //The minimum amount of time required for the entire chunk to be completed

	options: {
		progressInterval: 500, //Progress interval to send audio chunk (default: 500 millis)
		bufferSize: undefined, //Use the browsers default buffer size
		mimeType: "audio/wav", //Web blob mime type
		address: "ws://localhost:8000/ws", //The server websocket location 
		reconnectInterval: 100, //Attempt to reconnect to the server ever 100 millis
		maxReconnectInterval: 500 //The maximum amount of interval time to reconnect to the server
	}
}

var WORKER_FILE = "RemSphinxWorker.js" //The worker file that off-loads the main processing into a new background process

//RemSphinx constructor
var RemSphinx = function(sourceNode, configs) {
	extend(this, CONFIGS, configs || {}); //Combine the new values of the configuration file
	this.context = sourceNode.context; //Get the AudioContext
	if(this.context.createScriptProcessor == null)
		this.context.createScriptProcessor = this.context.createJavaScriptNode; //Create a new script processor
	this.input = this.context.createGain();
	sourceNode.connect(this.input);
	this.ready = false;
	this.initWorker();
}

//Instance prototype methods
extend(RemSphinx.prototype, {
	isRunning: function() { return this.processor != null; },
	isListening: function() { return (this.listening != null) ? this.listening : false },
	isReady: function() { return (this.ready != null) ? this.ready : false },

	start: function(sourceNode, stream) {
		if(this.isRunning()) {
			return;
		}
		this.processor = this.context.createScriptProcessor(
							this.bufferSize,
							this.numChannels,
							this.numChannels);
		this.input.connect(this.processor);
		
		//Default input volume gain is 70
		this.volumeGain = 70;

		//Greate a new gain to control the audio volume
		this.audioLevel = this.context.createGain();
		this.audioLevel.gain.value = (this.volumeGain / 100);
		this.audioLevel.connect(sourceNode, stream);

		//Disconnect audioIn if it's already created
		if(this.audioIn != null) this.audioIn.disconnect(); 
		//Create a new stream source for the input audio
		this.audioIn = this.context.createMediaStreamSource(stream);
		//Connect the audio gain controller
		this.audioIn.connect(this.audioLevel);

		//Create the audio analyser
		this.analyser = this.context.createAnalyser();
		//Smooth out the data over a time constant
		this.analyser.smoothingTimeConstant = 0.3;
		//The total buffer size for the data
		this.analyser.fftSize = 2048; //Buffer size
	
		//Connect the audio analyser to the main audioIn stream
		this.audioIn.connect(this.analyser);

		//Set a static frequencyBinCount
		this.frequencyBinCount = this.analyser.frequencyBinCount;

		this.startTime = Date.now();
		this.chunkTime = this.startTime;
		this.audioRunLevel = [];
		this.buffer = [];
		this.listening = false;

		//Create a static offset of the object to not confuse the ambiguity of the interpreter
		var _this = this;

		this.processor.connect(this.context.destination);
		this.processor.onaudioprocess = function(event) {
			//Do some preprocessing before sending the audio chunk to be processed
			var uint_arr = new Uint8Array(_this.frequencyBinCount); //Create a new object to hold the gain data
			_this.analyser.getByteFrequencyData(uint_arr); //Get the gain data
			var arr_average = _this.arrayAverage(uint_arr); //Average all of the gain data
			_this.audioRunLevel.push(arr_average); //Push the current audio average to the global array	

			//Check to see if we can start to listen for speech
			//console.log("AVERAGE: " + arr_average);
			if(arr_average > _this.speakingGain && _this.isReady() && !_this.isListening()) {
				_this.listening = true;
				_this.worker.postMessage({ command: "start_speech" });
				_this.onStartSpeech();
			}

			//Check to see if we can end the speech
			if(_this.isReady() && _this.isRunning() && (Date.now() - _this.chunkTime) > _this.minSpeakingTime) {
				var arr_largest_val = _this.arrayLargestValue(_this.audioRunLevel); //Get the largest gain value from the audio run level
				console.log("LARGEST: " + arr_largest_val);
				_this.audioRunLevel.length = 0; //Reset the audioRunLevel array
				
				//If the largest gain value is below the speaking limit, then stop listening for speech
				if(arr_largest_val < _this.speakingGain && _this.isListening()) {
					_this.listening = false;
					_this.worker.postMessage({ command: "end_speech" });
					_this.onEndSpeech();
				}
				
				_this.chunkTime = Date.now(); //Reset the next time to check a chunk
			}

			//Only process and encode chunks when we're listening to text
			if(_this.isListening() && _this.isReady()) {
				for(var ch = 0; ch < _this.numChannels; ++ch) {
					_this.buffer[ch] = event.inputBuffer.getChannelData(ch);
					_this.worker.postMessage({ command: "chunk", buffer: _this.buffer});
				}
			}
		}
		
		this.worker.postMessage({ 
			command: "start",
			bufferSize: this.processor.bufferSize
		});
	},

	setLanguageModel: function(newModel) {
		this.worker.postMessage({ command: "model", model: newModel});
	},

	setVolumeGain: function(gain) {
		this.volumeGain = gain;
		
		if(this.audioLevel != null) {
			this.audioLevel.gain.value = (this.volumeGain / 100);
		}
	},

	setSpeakingGain: function(gain) {
		this.speakingGain = gain;
	},

	arrayAverage: function(array) {
		var values = 0, length = array.length;
		for(var i = 0; i < length; i++) values += array[i];
		return values / length;
	},

	arrayLargestValue: function(array) {
		var highest = 0;
		for(var ind = 0; ind < array.length; ind++) if(array[ind] > highest) highest = array[ind];
		return highest;
	},

	recordingTime: function() {
		return this.isRunning() ? (Date.now() - this.startTime) : null;
	},

	initWorker: function() {
		if(this.worker != null) 
			this.worker.terminate();
		this.worker = new Worker(this.workerDir + WORKER_FILE);
		var _this = this;
		this.worker.onmessage = function(event) {
			var data = event.data;
			switch(data.command) {
					case "processed":
						_this.onProcessedChunk();
						break;
					case "waiting":
						_this.onWaiting();
						break;
					case "loaded":
						_this.onModelLoaded(data.success);
						_this.ready = true;
						break;
					case "hypothesis":
						_this.onHypothesis(data.hyp);
						break;
					case "partial_hypothesis":
						_this.onPartialHypothesis(data.partial_hyp);
						break;
					case "nocatch":
						_this.onNoCatch(data.silence);
						break;
					case "error":
						_this.onError(_this, data.message, data.code);
			}
		};
		this.worker.postMessage({
			command: "init",
			config: {
				sampleRate: this.context.sampleRate,
				numChannels: this.numChannels
			},
			options: this.options
		});
	},

	error: function(message) {
		this.onError(this, "RemSphinx.js:" + message, 0);
	},

	onError: function(recorder, message, code) { console.log(message + "(Code: " + code + ")"); },
	onProcessedChunk: function() { console.log("Audio chunk processed!"); },
	onModelLoaded: function(success) { console.log("LanguageModel loading " + ((success) ? "success!" : "failure!")); },
	onStartSpeech: function() { console.log("Starting to listen!"); },
	onEndSpeech: function() { console.log("Listening stopped!"); },
	onHypothesis: function(hypothesis) {},
	onPartialHypothesis: function(partial_hypothesis) { console.log("Partial hypothesis: " + partial_hypothesis); },
	onNoCatch: function(silence) {},
	onWaiting: function() {}
});

window.RemSphinx = RemSphinx;

})(window);
