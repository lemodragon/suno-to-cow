import requests
import plugins
import os
import re
import json
import time
import requests
import datetime
import threading
from typing import List
from pathvalidate import sanitize_filename

from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger



@plugins.register(
    name="suno-to-cow",
    desire_priority=99,
    desc="A plugin for summarizing all things",
    version="2.0.0",
    author="Faer",
)

class SunoToCow(Plugin):
    def __init__(self):
        self.config = self.load_config()
        self.suno_api_base = self.config.get("suno_api_base", [])
        self.suno_api_token = self.config.get("suno_api_key", "")
        self.model = self.config.get("model", "")
        self.music_create_prefixes = self.config.get("music_create_prefixes", [])
        self.instrumental_create_prefixes = self.config.get("instrumental_create_prefixes", [])
        self.lyrics_create_prefixes = self.config.get("lyrics_create_prefixes", [])
        self.music_output_dir = self.config.get("music_output_dir", "/tmp")
        self.is_send_lyrics = self.config.get("is_send_lyrics", True)
        self.is_send_covers = self.config.get("is_send_covers", True)

        if not os.path.exists(self.music_output_dir):
            os.makedirs(self.music_output_dir)

    def load_config(self):
        curdir = os.path.dirname(__file__)
        config_path = os.path.join(curdir, "config.json")
        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                logger.warning("config.json not found, using default configuration.")
                return {}
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}

    def handle_message(self, context):
        if context.type != ContextType.TEXT:
            return

        content = context.content
        make_instrumental, make_lyrics = False, False
        music_create_prefix = self._check_prefix(content, self.music_create_prefixes)
        instrumental_create_prefix = self._check_prefix(content, self.instrumental_create_prefixes)
        lyrics_create_prefix = self._check_prefix(content, self.lyrics_create_prefixes)

        if music_create_prefix:
            suno_prompt = content[len(music_create_prefix):].strip()
        elif instrumental_create_prefix:
            make_instrumental = True
            suno_prompt = content[len(instrumental_create_prefix):].strip()
        elif lyrics_create_prefix:
            make_lyrics = True
            suno_prompt = content[len(lyrics_create_prefix):].strip()
        else:
            return

        if not suno_prompt:
            return

        if make_lyrics:
            self._create_lyrics(context, suno_prompt)
        else:
            self._create_music(context, suno_prompt, make_instrumental)

    def _create_music(self, context, suno_prompt, make_instrumental=False):
        custom_mode = False
        if '标题' in suno_prompt and '风格' in suno_prompt:
            custom_mode = True
            # 解析自定义模式输入
            import re
            regex_prompt = r' *标题[:：]?(?P<title>[\S ]*)\n+ *风格[:：]?(?P<tags>[\S ]*)(\n+(?P<lyrics>.*))?'
            match = re.fullmatch(regex_prompt, suno_prompt, re.DOTALL)
            if match:
                title = match.group('title').strip()
                tags = match.group('tags').strip()
                lyrics = match.group('lyrics').strip()
                payload = {
                    "model": self.model,
                    "title": title,
                    "tags": tags,
                    "lyrics": lyrics,
                    "make_instrumental": make_instrumental
                }
            else:
                logger.error("Invalid custom mode input format")
                return
        else:
            # 描述模式
            payload = {
                "model": self.model,
                "prompt": suno_prompt,
                "make_instrumental": make_instrumental
            }

        # 调用你自己的服务生成音乐
        url = f"{self.suno_api_base}/generate_music"
        headers = {
            "Authorization": f"Bearer {self.suno_api_token}",
            "Content-Type": "application/json"
        }
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            # 处理生成的音乐数据
            music_url = data.get("music_url")
            if music_url:
                music_file_path = os.path.join(self.music_output_dir, sanitize_filename(data.get("title", "music")) + ".mp3")
                self._download_file(music_url, music_file_path)
                reply = Reply(ReplyType.AUDIO, music_file_path)
                context.bot.send(reply)
            else:
                logger.error("Music URL not found in response")
        else:
            logger.error(f"Failed to generate music: {response.status_code} - {response.text}")

    def _create_lyrics(self, context, suno_prompt):
        # 调用你自己的服务生成歌词
        url = f"{self.suno_api_base}/generate_lyrics"
        headers = {
            "Authorization": f"Bearer {self.suno_api_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "prompt": suno_prompt
        }
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            # 处理生成的歌词数据
            lyrics = data.get("lyrics")
            if lyrics:
                reply = Reply(ReplyType.TEXT, lyrics)
                context.bot.send(reply)
            else:
                logger.error("Lyrics not found in response")
        else:
            logger.error(f"Failed to generate lyrics: {response.status_code} - {response.text}")

    def _check_prefix(self, content, prefix_list):
        for prefix in prefix_list:
            pattern = r'^{}(?=\S)'.format(re.escape(prefix))
        if re.search(pattern, content):
                return prefix
        return None


    def _download_file(self, file_url, file_path, retry_count=3, timeout=600):
        start_time = datetime.datetime.now()
        while retry_count >= 0:
            try:
                response = requests.get(file_url, allow_redirects=True, stream=True)
                if response.status_code != 200:
                    raise Exception(f"文件下载失败，file_url={file_url}, status_code={response.status_code}")
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)
            except Exception as e:
                logger.error(f"文件下载失败，file_url={file_url}, error={e}")
                retry_count -= 1
                time.sleep(5)
            else:
                break
            elapsed_time = (datetime.datetime.now() - start_time).total_seconds()
            if elapsed_time > timeout:
                logger.error(f"文件下载超时,file_url={file_url}")
                break













