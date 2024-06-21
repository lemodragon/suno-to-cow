import plugins
import requests
import json
import time
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
    version="2.4.0",
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
            self.model = self.config["keys"].get("model", "")
            self.open_ai_api_base = self.config["keys"].get("open_ai_api_base", "https://api.openai.com/v1")

            self.suno2cow_enabled = self.config["suno2cow"].get("enabled", "")
            self.suno2cow_service = self.config["suno2cow"].get("service", "")
            self.suno2cow_group = self.config["suno2cow"].get("group", "")
            self.suno2cow_qa_prefix = self.config["suno2cow"].get("qa_prefix", [])
            self.suno2cow_prompt = self.config["suno2cow"].get("prompt", "")

            self.recent_queries = {}
            self.cleanup_interval = 60 * 4  # 4分钟清理一次
            self.last_cleanup_time = time.time()

            logger.info("[suno2cow] inited.")
        except Exception as e:
            logger.warn(f"suno2cow init failed: {e}")

    def cleanup_recent_queries(self):
        current_time = time.time()
        self.recent_queries = {
            query: timestamp
            for query, timestamp in self.recent_queries.items()
            if current_time - timestamp < self.cleanup_interval
        }

    def on_handle_context(self, e_context: EventContext):
        context = e_context["context"]
        if context.type not in [ContextType.TEXT]:
            return

        msg: ChatMessage = e_context["context"]["msg"]
        content = context.content
        isgroup = e_context["context"].get("isgroup", False)

        if self.suno2cow_enabled and any(content.startswith(prefix) for prefix in self.suno2cow_qa_prefix):
            if not isgroup or self.suno2cow_group:
                matched_prefix = next((prefix for prefix in self.suno2cow_qa_prefix if content.startswith(prefix)), None)
                if matched_prefix:
                    self.call_service(content, e_context, matched_prefix)
                return

    def call_service(self, content, e_context, prefix):
        # 检查问题是否已经存在于最近的问题列表中
        if content in self.recent_queries:
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = "已经在拼命制作了..."
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return

        # 将问题添加到最近的问题列表中
        self.recent_queries[content] = time.time()

        # 检查是否需要进行清理
        if time.time() - self.last_cleanup_time > self.cleanup_interval:
            self.cleanup_recent_queries()
            self.last_cleanup_time = time.time()
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.suno2cow_key}'
        }
        user_message = content[len(prefix):].strip()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.suno2cow_prompt},
                {"role": "user", "content": user_message}
            ]
        }
        
        logger.info(f"Sending payload: {payload}")  # 添加日志输出，调试时可以看到完整的payload

        max_retries = 2  # 设置重试次数
        retry_count = 0

        while retry_count < max_retries:
            try:
                api_url = f"{self.open_ai_api_base}/chat/completions"
                response = requests.post(api_url, headers=headers, json=payload)
                response.raise_for_status()  # 如果响应状态不是200，将抛出异常

                response_data = response.json()
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    first_choice = response_data["choices"][0]
                    if "message" in first_choice and "content" in first_choice["message"]:
                        response_content = first_choice["message"]["content"].strip()
                        reply_content = response_content.replace("\\n", "\n")

                        # 新增: 删除包含大量🎵符号的行
                        lines = reply_content.split('\n')
                        new_lines = [line for line in lines if not line.strip().replace('🎵', '').strip() == '']
                        reply_content = '\n'.join(new_lines)

                        reply = Reply()
                        reply.type = ReplyType.TEXT
                        reply.content = remove_markdown(reply_content)
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS
                        return
                    
                else:
                    reply_content = "Content not found or error in response"

                break  # 如果请求成功，退出循环

            except requests.exceptions.RequestException as e:
                logger.error(f"Error calling API: {e}")
                retry_count += 1

                if retry_count >= max_retries:
                    logger.error("Max retries exceeded.")
                    reply = Reply()
                    reply.type = ReplyType.TEXT
                    reply.content = "请求失败，请稍后再试。"
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                    return

                # 等待3分半钟后重试
                time.sleep(210)  # 3分半钟，单位为秒

        # 如果所有重试都失败，返回错误消息
        reply = Reply()
        reply.type = ReplyType.TEXT
        reply.content = "创作过程中遇到了一些问题，请稍后再试。"
        e_context["reply"] = reply
        e_context.action = EventAction.BREAK_PASS

def remove_markdown(text):
    text = text.replace("**", "")
    text = text.replace("### ", "").replace("## ", "").replace("# ", "")
    return text
