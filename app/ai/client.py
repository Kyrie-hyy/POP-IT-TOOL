from openai import OpenAI

from app.ai.config import API_KEY, BASE_URL, MODEL
from app.ai.prompts import SYSTEM_PROMPT


class AIClient:

    def __init__(self):

        self.client = OpenAI(
            api_key=API_KEY,
            base_url=BASE_URL,
        )

    # ==================================================
    # Tool 决策（Agent 使用）
    # ==================================================

    def chat_json(self, prompt: str):

        response = self.client.chat.completions.create(

            model=MODEL,

            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            temperature=0

        )

        return response.choices[0].message.content

    # ==================================================
    # 普通聊天（Summary 使用）
    # ==================================================

    def chat_text(self, prompt: str):

        response = self.client.chat.completions.create(

            model=MODEL,

            messages=[
                {
                    "role": "system",
                    "content": "你是一名专业Windows运维工程师，请根据执行结果给出简洁、专业的中文建议。不要JSON，不要Markdown。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            temperature=0.3

        )

        return response.choices[0].message.content


ai_client = AIClient()