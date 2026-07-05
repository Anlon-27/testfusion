"""
Selenium自动化测试执行引擎 (已完全弃用)
项目已全面重构至高效的微软 Playwright 自动化架构下。
"""
import logging

logger = logging.getLogger(__name__)


class SeleniumTestEngine:
    """Selenium测试执行引擎 - 已下线"""

    def __init__(self, browser_type='chrome', headless=True):
        raise NotImplementedError("Selenium 引擎已完全弃用下线，请改用 Playwright 引擎。")

    @classmethod
    def check_browser_available(cls, browser_type):
        """保底返回不可用，引导前台转为使用 Playwright"""
        return False, "Selenium 引擎已弃用下线，请选择 Playwright 执行引擎。"
