class IntentAnalyzer:
    """
    第一版 Intent Analyzer（Rule-based）

    职责：
    1. 分析用户输入
    2. 返回标准 Intent
    """

    def analyze(self, user_input: str) -> str:

        text = user_input.lower().strip()

        # =========================
        # 网络问题
        # =========================
        if any(keyword in text for keyword in [
            "网络",
            "wifi",
            "无线网",
            "飞连",
            "vpn",
            "上不了网",
            "无法联网",
            "断网",
            "internet",
            "ip",
            "dns",
            "ping",
            "网速",
            "连接失败",
            "连不上网",
            "网络异常",
        ]):
            return "network"

        # =========================
        # 打印机
        # =========================
        if any(keyword in text for keyword in [
            "打印机",
            "打印",
            
            "扫描仪",
            "共享打印机",
            "打印失败",
            "打印不了",
            "无法打印",
            "卡纸",
            "墨盒",
            "硒鼓",
        ]):
            return "printer"

        # =========================
        # BitLocker
        # =========================
        # BitLocker
        if any(k in text for k in [
            "bitlocker",
            "硬盘锁",
            "加密",
            "恢复密钥",
            "恢复密码",
            "查看bitlocker",
            "查看加密",
            "查看状态",
        ]):
            return "bitlocker_status"

        if any(k in text for k in [
            "开启bitlocker",
            "开启加密",
            "启用bitlocker",
        ]):
            return "bitlocker_on"

        if any(k in text for k in [
            "关闭bitlocker",
            "关闭加密",
            "解密",
        ]):
            return "bitlocker_off"

        if any(k in text for k in [
            "暂停bitlocker",
            "暂停加密",
       ]):
            return "bitlocker_suspend"

        if any(k in text for k in [
            "恢复bitlocker",
            "恢复保护",
       ]):
            return "bitlocker_resume"

        # =========================
        # 系统清理
        # =========================
        if any(keyword in text for keyword in [
            "垃圾",
            "清理",
            "缓存",
            "磁盘",
            "临时文件",
            "微信缓存",
            "飞书缓存",
            "空间不足",
            "c盘",
        ]):
            return "cleanup"

        # =========================
        # Windows 工具
        # =========================
        if any(keyword in text for keyword in [
            "控制面板",
            "程序和功能",
            "卸载软件",
            "设备管理器",
            "服务",
            "任务管理器",
            
        ]):
            return "windows_tool"

        # =========================
        # 系统修复
        # =========================
        if any(keyword in text for keyword in [
            "蓝屏",
            "系统修复",
            "更新失败",
            "windows更新",
            "无法启动",
            "卡死",
            "崩溃",
            "修复",
            "sfc",
            "dism",
        ]):
            return "system_repair"

        # =========================
        # 系统健康检测
        # =========================
        if any(keyword in text for keyword in [
            "健康检测",
            "系统检测",
            "检测电脑",
            "检查电脑",
            "电脑健康",
            "健康状态",
        ]):
            return "health"

        # =========================
        # 软件下载
        # =========================
        if any(keyword in text for keyword in [
            "下载软件",
            "软件下载",
            "office",
            "微信",
            "飞书",
            "安装软件",
        ]):
            return "software_download"

        # =========================
        # 屏幕旋转
        # =========================
        if any(keyword in text for keyword in [
            "旋转",
            "横屏",
            "竖屏",
            "显示器",
            "屏幕方向",
        ]):
            return "screen_rotation"

        # =========================
        # 强制卸载
        # =========================
        if any(keyword in text for keyword in [
            "卸载",
            "删除软件",
            "强制卸载",
            "geek",
        ]):
            return "uninstall"

        # =========================
        # 系统健康检测
        # =========================
        if any(keyword in text for keyword in [

             "健康检测",
             "系统健康",
             "检测电脑",
             "检查电脑",
             "电脑健康",

        ]): 

             return "health"



        if any(keyword in text for keyword in [

             "系统修复",
             "修复系统",
             "蓝屏",
             "更新失败",
             "sfc",
             "dism",

        ]):

            return "system_repair"

        # =========================
        # 默认
        # =========================
        return "unknown"