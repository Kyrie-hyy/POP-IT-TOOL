from app.ai.client import ai_client


class AISummary:

    def summarize(self, user_input, results):

        prompt = f"""
用户的问题：

{user_input}

执行结果：

{results}

请根据执行结果，
生成一段简洁专业的中文总结。

要求：

1. 不超过100字

2. 告诉用户做了什么

3. 是否成功

4. 是否建议重启

不要Markdown。
"""

        return ai_client.chat_text(prompt)


ai_summary = AISummary()