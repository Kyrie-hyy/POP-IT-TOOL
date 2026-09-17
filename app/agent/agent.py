from app.agent.registry import ToolRegistry
from app.agent.planner import Planner
from app.agent.intent import IntentAnalyzer
from app.agent.executor import Executor
from app.agent.formatter import ResultFormatter
from app.logger.logger import logger
from app.ai.ai_planner import ai_planner
from app.ai.summary import ai_summary


class POPITAgent:
    """
    POP IT Agent
    """

    def __init__(self):

        self.registry = ToolRegistry()

        self.intent = IntentAnalyzer()

        self.planner = Planner()

        self.executor = Executor()

        self.formatter = ResultFormatter()

    def chat(self, user_input):

        print(f"收到用户输入：{user_input}")

        logger.user(user_input)

        # ==================================================
        # Step1 AI Planner
        # ==================================================

        ai_plan = ai_planner.create_plan(user_input)

        # ==================================================
        # AI 成功
        # ==================================================

        if ai_plan:

            print("AI Plan =", ai_plan)

            logger.ai(ai_plan)

            plan = self.planner.create_plan(
                ai_plan[0]["tool"],
                user_input,
                ai_plan[0]["action"],
            )

        else:

            # ==================================================
            # Rule Intent
            # ==================================================

            intent = self.intent.analyze(user_input)

            print("intent =", intent)

            if intent == "unknown":

                return [{
                    "success": False,
                    "message": "暂时无法识别该请求。"
                }]

            plan = self.planner.create_plan(
                intent,
                user_input,
            )

        print("plan =", plan)

        logger.plan(plan)

        # ==================================================
        # Execute
        # ==================================================

        results = self.executor.execute(plan)

        logger.execute(results)

        # ==================================================
        # Format
        # ==================================================

        reply = self.formatter.format(results)

        # ==================================================
        # AI Summary
        # ==================================================

        try:

            summary = ai_summary.summarize(
                user_input,
                reply,
            )

            print("summary =", summary)

            reply += "\n\n"
            reply += "━━━━━━━━━━━━━━━━━━\n"
            reply += "🤖 AI 分析建议\n\n"
            reply += summary

        except Exception as e:

            logger.error(e)

            print("AI Summary Error:", e)

        try:

            logger.add_history(

                user=user_input,

                tool=plan[0].tool if plan else "",

                action=plan[0].action if plan else "",

                success=True,

                summary=summary if 'summary' in locals() else ""

           )

        except Exception as e:

            print("Logger Error:", e)

        return reply

    def list_tools(self):

        return self.registry.get_all_schema()