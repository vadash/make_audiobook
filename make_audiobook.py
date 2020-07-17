#!/usr/bin/env python3
"""
To use:
1. install/set-up the google cloud api and dependencies listed on https://github.com/GoogleCloudPlatform/python-docs-samples/tree/master/texttospeech/cloud-client
2. install pandoc and pypandoc, also tqdm
3. create and download a service_account.json ("Service account key") from https://console.cloud.google.com/apis/credentials
4. run GOOGLE_APPLICATION_CREDENTIALS=service_account.json python make_audiobook.py book_name.epub
"""
import re
import sys
import time
from datetime import datetime as dt
from pathlib import Path

from google.cloud import texttospeech
from tqdm import tqdm

import pypandoc

# see https://cloud.google.com/text-to-speech/quotas
MAX_REQUESTS_PER_MINUTE = 200
MAX_CHARS_PER_MINUTE = 135000


def book_to_text(book_file):
    try:
        return pypandoc.convert_file(book_file, "plain", extra_args=["--wrap=none"])
    except RuntimeError:
        print("Format not recognized. Treating as plain text...")
        with open(book_file, encoding="utf-8") as book:
            return book.read()


def clean_text_chunk(text_chunk):
    # remove _italics_
    text_chunk = re.sub(r"_", " ", text_chunk)
    # remove --- hyphens for footnotes
    text_chunk = re.sub(r"(\-{3,})", "Footnote:", text_chunk)
    return text_chunk


class Narrator:
    def __init__(self, voice_name="en-US-Wavenet-F"):
        self.client = texttospeech.TextToSpeechClient()
        self.voice = texttospeech.VoiceSelectionParams(
            language_code="en-US", name=voice_name
        )
        self.audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )
        # rate limit stuff
        self._minute = -1
        self._requests_this_minute = 0
        self._chars_this_minute = 0

    def print_voice_names(self, lang="en"):
        print("Available voices for language {}:".format(lang))
        for voice in self.client.list_voices().voices:
            if voice.name.startswith(lang):
                print(voice.name)

    def _rate_limit(self):
        if (
            self._requests_this_minute > MAX_REQUESTS_PER_MINUTE
            or self._chars_this_minute > MAX_CHARS_PER_MINUTE
        ):
            while dt.now().minute == self._minute:
                time.sleep(5)
        if dt.now().minute != self._minute:
            self._minute = dt.now().minute
            self._requests_this_minute = 0
            self._chars_this_minute = 0

    def _text_chunk_to_audio_chunk(self, text_chunk):
        self._rate_limit()
        input_text = texttospeech.SynthesisInput(text=text_chunk)
        # Perform the text-to-speech request on the text input with the selected
        # voice parameters and audio file type
        response = self.client.synthesize_speech(
            input=input_text,
            voice=self.voice,
            audio_config=self.audio_config
        )
        self._requests_this_minute += 1
        self._chars_this_minute += len(text_chunk)
        return response.audio_content

    def text_to_mp3(self, text, file_dest):
        assert file_dest.suffix == ".mp3"
        lines = text.splitlines()
        with file_dest.open("wb") as out:
            for i, text_chunk in enumerate(tqdm(lines, desc=file_dest.stem)):
                # skip empty lines
                if text_chunk:
                    text_chunk = clean_text_chunk(text_chunk)
                    audio_chunk = self._text_chunk_to_audio_chunk(text_chunk)
                    # this is fine because mp3s can be concatenated naively and still work
                    out.write(audio_chunk)


def main():
    if not sys.argv[1:]:
        print(
            "Usage: GOOGLE_APPLICATION_CREDENTIALS=service_account.json {} book_name.epub".format(
                sys.argv[0]
            )
        )
        sys.exit(1)
    narrator = Narrator()

    #narrator.print_voice_names()

    for book_file in sys.argv[1:]:
        text = book_to_text(book_file)
        mp3_path = Path(book_file).with_suffix(".mp3")
        narrator.text_to_mp3(text, mp3_path)
        print("Generated mp3", mp3_path)

        # I have another script that uploads to overcast...
        # import subprocess as sp
        # sp.call("upload.py '" + str(mp3_path) + "'", shell=True)


if __name__ == "__main__":
    main()