from app.agent.agent import POPITAgent


def main():

    agent = POPITAgent()

    print("=" * 50)
    print("POP IT Agent 测试")
    print("=" * 50)

    while True:

        user_input = input("\n请输入问题（输入exit退出）：")

        if user_input.lower() == "exit":
            break

        result = agent.chat(user_input)

        print("\nAgent 返回：")
        print(result)


if __name__ == "__main__":
    main()