import json
from pathlib import Path
from collections.abc import Iterator

import sounddevice as sd
from vosk import Model, KaldiRecognizer


class AudioModel:
    def __init__(self):
        model_path = (
            Path(__file__).resolve().parent
            / "vosk_model"
            / "vosk-model-small-de-0.15"
        )

        self.audio_model = Model(str(model_path))
        self.shouldStream = True

    def get_transcription_stream(
        self,
        microphone: sd.RawInputStream
    ) -> Iterator[str]:

        recognizer = KaldiRecognizer(
            self.audio_model,
            microphone.samplerate
        )

        self.shouldStream = True

        while microphone.active and self.shouldStream:
            data, _ = microphone.read(4000)

            if recognizer.AcceptWaveform(bytes(data)):
                text = json.loads(recognizer.Result())["text"]

                if text:
                    yield text
                    
    def stop_transcription_stream(self):
        self.shouldStream = False