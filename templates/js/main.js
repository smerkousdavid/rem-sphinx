var ws; 

window.requestAnimationFrame = window.requestAnimationFrame ||
								window.msRequestAnimationFrame ||
								window.mozRequestAnimationFram ||
								window.webkitRequestAnimationFrame;

window.AudioContext = window.AudioContext ||
						window.webkitAudioContext;

navigator.getUserMedia = navigator.getUserMedia ||
							navigator.webkitGetUserMedia ||
							navigator.mozGetUserMedia ||
							navigator.msGetUserMedia;

var a_cx = new AudioContext();

if(a_cx.createScriptProcessor == null) {
	a_cx.createScriptProcessor.createJavaScriptNode;
}

var audio_recorder = null,
	audio_mixer = null,
	audio_in = null,
	audio_in_level = null,
	analyser = null,
	process_node = null,
	audio_level = [],
	is_speaking = false,
	ws_state = 0,
	volume_gain = 0,
	speaking_gain = 0,
	frequency_bin_count = 0,
	remSphinx = null;

$(document).ready(function() {
	audio_mixer = a_cx.createGain();
	
	navigator.getUserMedia({audio: true}, recordAudio, function (error) {
		console.log("error: " + error);
	});
	

	/*ws = new WebSocket("ws://localhost:8000/ws");
	ws.binaryType = "arraybuffer";


	ws.onmessage = function(e) {
		console.log("Raw server response: " + e.data);
		var response = JSON.parse(e.data);
		
		//if(!response.hasOwnProperty("id") || response.id.localeCompare(ws_id) != 0) {
		//	console.log("Missing id property or client mismatch");
		//	setInfo("Client mismatch!");
		//	setSubInfo("The server responded with an invalid id!");
		//	return;
		//}

		if(response.hasOwnProperty("error")) {
			console.log("Server error!");
			setInfo("Server error!");
			setSubInfo("Response message: " + response.error);
			return;
		}

		switch(ws_state) {
			case 0:
				if(response.success) {
					audio_mixer = a_cx.createGain();
					//audio_mixer.connect(a_cx.destination);

					audio_in_level = a_cx.createGain();
					audio_in_level.gain.value = (volume_gain / 100);
					audio_in_level.connect(audio_mixer);

					navigator.getUserMedia({audio: true}, recordAudio, function (error) {
						console.log("error: " + error);
					});
					ws_state = 10;
					setInfo("Waiting...");
					setSubInfo("Adjust the audio gain if necessary");
				} else {
					alert("The server failed!")
					setInfo("Server failed!")
					setSubInfo("Refresh the page!");
				}
				break;
			case 10:
				if(!response.silence) {
					//var n_words = []
					//for(var ind = 0; ind < response.words.length; ind++) {
					//	var word = response.words[ind][0];
					//	if(!word.includes("<") && !word.includes(">")) {
					//		if(word.includes("(")) {
					//			word = word.replace(/\((.*)\)/i, "");
					//		}
					//		n_words.push(word);
					//	} else if(word.includes("<sil>")) {
					//		n_words.push(".");
					//	}
					//}
					//var c_words = "";
					//var p_word = "";
					//for(var ind = 0; ind < n_words.length; ind++) {
					//	var word = n_words[ind];
					//	var prefix = "";
					//	if(word == ".") {
					//		c_words += word;
					//		continue;
					//	} else if(p_word == ".") {
					//		prefix = " ";
					//	}
					//	var next_ind = ind + 1;
					//	if(next_ind < n_words.length) {
					//		if(n_words[next_ind] == ".") {
					//			c_words += prefix + word;
					//		} else {
					//			c_words += prefix + word + " ";
					//		}
					//	} else {
					//		c_words += prefix + word;
					//	}
					//	p_word = word;
					//}
					//
					//c_words += ".";

					var hypothesis = (response.hypothesis) + ". ";

					console.log("Recieved hypothesis: " + hypothesis);
					appendSpokenText(hypothesis);
					setInfo("Waiting...");
					setSubInfo("Adjust the audio gain if necessary");
				} else {
					setInfo("Couldn't catch that!");
					setSubInfo("Try speaking louder or adjusting the gain");
				}
				break;
		}
	};*/

	//Initialize bootstrap elements
	$(".dropdown-toggle").dropdown();

	$("#volume").slider().on("slideStop", function(ev) {
		volume_gain = $("#volume").data("slider").getValue();
		if(remSphinx != null) {
			remSphinx.setVolumeGain(volume_gain);
		} else {
			console.log("NULL!");
		}
		/*if(audio_in_level != null) {
			audio_in_level.gain.value = (volume_gain / 100);
		}*/
	});

	$("#volume-speaking").slider().on("slideStop", function(ev) {
		speaking_gain = $("#volume-speaking").data("slider").getValue();
		if(remSphinx != null) {
			remSphinx.setSpeakingGain(speaking_gain);
		}
	});

	$("#clear-text").on("click", function(ev) {
		clearSpokenText();
		console.log("Cleared spoken text!");
	});

	//Get default values from the sliders
	volume_gain = $("#volume").data("slider").getValue();
	speaking_gain = $("#volume-speaking").data("slider").getValue();

	$(".dropdown-menu li a").click(function() {
		var language = $(this).text();
		$(".btn:first-child").text(language);
		$(".btn:first-child").val(language);
		
		console.log("Language selected: " + language);
		setInfo("Selected " + language);
		setSubInfo("Configuring server for " + language + "...");

		var models = {
			"English": "0",
			"German": "1",
			"French": "2",
			"Russian": "3"
		}

		var model_id = models[language];

		if(remSphinx != null) {
			remSphinx.setLanguageModel(model_id);
		}

		/*ws.send(JSON.stringify({
			model: model_id,
		}));*/

	});

});

function setInfo(set_text) {
	$("#info").text(set_text);
}

function setSubInfo(set_text) {
	$("#sub-info").text(set_text);
}

function appendSpokenText(append_text) {
	$("#spoken-text-area").text($("#spoken-text-area").text() + append_text);
}

function clearSpokenText() {
	$("#spoken-text-area").text("");
}

/*function randomId() {
	var text = "", possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
	for(var i = 0; i < 128; i++) {
		text += possible.charAt(Math.floor(Math.random() * possible.length));
	}
	return text;
}

function averageArray(array) {
	var values = 0, length = array.length;
	for(var i = 0; i < length; i++) values += array[i];
	return values / length;
}

function highestArray(array) {
	var highest = 0;
	for(var ind = 0; ind < array.length; ind++) if(array[ind] > highest) highest = array[ind];
	return highest;
}*/

/*
function onGotAudioIn(stream) {
	if(audio_in != null) {
		audio_in.disconnect();
	}
	audio_in = a_cx.createMediaStreamSource(stream);
	audio_in.connect(audio_in_level);

	analyser = a_cx.createAnalyser();
	analyser.smoothingTimeConstant = 0.3;
	analyser.fftSize = 2048;

	audio_in.connect(analyser);

	frequency_bin_count = analyser.frequencyBinCount;
	setInterval(function() {
		var array = new Uint8Array(frequency_bin_count);
		analyser.getByteFrequencyData(array);
		var average = averageArray(array);
		audio_level.push(average);
		if(average > speaking_gain && !audio_recorder.isRecording()) {
			console.log("Starting to record!");
			audio_recorder.startRecording();
			setInfo("Speak...");
			setSubInfo("We're still listening");
		}
		//console.log("Volume level: " + average);
	}, 20);

	setInterval(function() {
		var highest = highestArray(audio_level);
		audio_level.length = 0; //Reset audio level
		//Make sure the recording is at least two seconds long
		if(highest < speaking_gain && audio_recorder.isRecording() && audio_recorder.recordingTime() > 2) {
			console.log("Finished speaking");
			audio_recorder.finishRecording();
			setInfo("Processing...");
			setSubInfo("Please wait for the server to finish processing...");
		}
		console.log("Highest volume level: " + highest);
	}, 3000);

}*/

function recordAudio(stream) {
	//onGotAudioIn(stream);
	
	remSphinx = new RemSphinx(audio_mixer);

	remSphinx.onStartSpeech = function() {
		setInfo("Listening...");
		setSubInfo("Keep talking!");
	}

	remSphinx.onEndSpeech = function() {
		setInfo("Processing...");
		setSubInfo("Pleae wait while the server is processing the speech data");
	}

	remSphinx.onWaiting = function() {
		setInfo("Waiting...");
		setSubInfo("Adjust the gain settings if RemSphinx can't hear you");
	}

	remSphinx.onHypothesis = function(hypothesis) {
		setInfo("Waiting...");
		setSubInfo("Adjust the gain settings if RemSphinx can't hear you");
		console.log("Recieved hypothesis: " + hypothesis);
		appendSpokenText(hypothesis);
	}

	remSphinx.onPartialHypothesis = function(partial_hypothesis) {
		setInfo("Listening...");
		setSubInfo(partial_hypothesis);
	}

	remSphinx.onNoCatch = function(silence) {
		setInfo("Couldn't catch that!");
		setSubInfo("Adjust the gain settings if RemSphinx can't hear you");
	}


	remSphinx.start(audio_mixer, stream);
	
	/*audio_recorder = new WebAudioRecorder(audio_mixer, {
		workerDir: 'js/',
		numChannels: 1,
		encoding: 'wav',
		options: {
			encodeAfterRecord: false,
			bufferSize: 2048,
			progressInterval: 300,
			timeLimit: 30
		}
	});*/

	/*audio_recorder.onError = function(recorder, message) {
		console.log("Recording error: " + message);
	}

	audio_recorder.onComplete = function(recorder, blob) {
		console.log("Blob complete: " + blob);
		var uint_arr = null;
		var arr_buff = null;
		console.log("Converting...");
		var file_reader = new FileReader();
		file_reader.onload = function(progress) {
			arr_buff = this.result.replace(/^data:audio\/(wav|mp3);base64,/, "");
			ws.send(JSON.stringify({
				audio: arr_buff
			}));
		}
		file_reader.readAsDataURL(blob); //ArrayBuffer(blob);
		file_reader.result;
	}*/
}
