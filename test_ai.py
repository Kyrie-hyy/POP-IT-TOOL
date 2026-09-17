from app.ai.client import ai_client

questions = [
    "飞连连不上",
    "打印机无法打印",
    "BitLocker状态",
    "清理垃圾",
    "检测电脑"
]

for q in questions:
    print("=" * 50)
    print("问题：", q)
    print(ai_client.chat(q))