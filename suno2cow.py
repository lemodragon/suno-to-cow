import requests
import json
from bridge.reply import Reply, ReplyType
from bridge.context import ContextType
from channel.chat_message import ChatMessage
from plugins import *
from common.log import logger
import os

@plugins.register(
    name="suno2cow",
    desire_priority=8,
    desc="A plugin for music bot to use suno2cow service",
    version="2.2.0",
    author="Fear",
)
class suno2cow(Plugin):
    def __init__(self):
        super().__init__()
        try:
            curdir = os.path.dirname(__file__)
            config_path = os.path.join(curdir, "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            else:
                self.config = super().load_config()

            if not self.config:
                raise Exception("config.json not found")

            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context

            self.suno2cow_key = self.config["keys"].get("open_ai_api_key", "")
            self.model = self.config["keys"].get("model", "gpt-4o")
            self.open_ai_api_base = self.config["keys"].get("open_ai_api_base", "https://api.openai.com/v1")

            self.suno2cow_enabled = self.config["suno2cow"].get("enabled", False)
            self.suno2cow_service = self.config["suno2cow"].get("service", "")
            self.suno2cow_group = self.config["suno2cow"].get("group", True)
            self.suno2cow_qa_prefix = self.config["suno2cow"].get("qa_prefix", "唱")
            self.suno2cow_prompt = self.config["suno2cow"].get("prompt", "")

            logger.info("[suno2cow] inited.")
        except Exception as e:
            logger.warn(f"suno2cow init failed: {e}")

    def on_handle_context(self, e_context: EventContext):
        context = e_context["context"]
        if context.type not in [ContextType.TEXT]:
            return

        msg: ChatMessage = e_context["context"]["msg"]
        content = context.content
        isgroup = e_context["context"].get("isgroup", False)

        if content.startswith(self.suno2cow_qa_prefix) and self.suno2cow_enabled:
            if isgroup and not self.suno2cow_group:
                return
            self.call_service(content, e_context)
            return

    def call_service(self, content, e_context):
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.suno2cow_key}'
        }
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.suno2cow_prompt},
                {"role": "user", "content": content[len(self.suno2cow_qa_prefix):]}
            ]
        })
        try:
            api_url = f"{self.open_ai_api_base}/chat/completions"
            response = requests.post(api_url, headers=headers, data=payload)
            response.raise_for_status()
            response_data = response.json()
            if "choices" in response_data and len(response_data["choices"]) > 0:
                first_choice = response_data["choices"][0]
                if "message" in first_choice and "content" in first_choice["message"]:
                    response_content = first_choice["message"]["content"].strip()
                    reply_content = response_content.replace("\\n", "\n")
            else:
                reply_content = "Content not found or error in response"

        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling new combined api: {e}")
            reply_content = f"An error occurred"

        reply = Reply()
        reply.type = ReplyType.TEXT
        reply.content = f"{remove_markdown(reply_content)}"
        e_context["reply"] = reply
        e_context.action = EventAction.BREAK_PASS

def remove_markdown(text):
    text = text.replace("**", "")
    text = text.replace("### ", "").replace("## ", "").replace("# ", "")
    return text