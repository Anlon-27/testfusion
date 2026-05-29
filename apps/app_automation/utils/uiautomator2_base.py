# -*- coding: utf-8 -*-
"""
uiautomator2 基础类 - 通过 ADB + uiautomator2 控制 Android 设备
"""
import os
import time
import logging
from typing import Optional

import uiautomator2 as u2
from django.conf import settings

logger = logging.getLogger(__name__)


class Uiautomator2Base:
    """uiautomator2 基础类，提供设备连接与基础操作"""

    DEFAULT_CONFIG = {
        'RETRY_COUNT': 3,
        'RETRY_INTERVAL': 5,
        'DEVICE_CONNECT_TIMEOUT': 30,
    }

    def __init__(
        self,
        device_id: Optional[str] = None,
        screenshots_dir: Optional[str] = None,
        username: Optional[str] = None,
    ):
        self.device_id = device_id
        self.is_connected = False
        self.device: Optional[u2.Device] = None

        if screenshots_dir:
            self.screenshots_dir = screenshots_dir
        else:
            self.screenshots_dir = os.path.join(
                settings.MEDIA_ROOT, 'app-automation', 'screenshots', username or 'unknown'
            )

        os.makedirs(self.screenshots_dir, exist_ok=True)
        logger.info(f"初始化 Uiautomator2Base，设备ID: {self.device_id}，截图目录: {self.screenshots_dir}")

    def setup_device(self, config: Optional[dict] = None) -> bool:
        """
        连接设备

        Args:
            config: 配置字典，支持 RETRY_COUNT, RETRY_INTERVAL, DEVICE_CONNECT_TIMEOUT

        Returns:
            是否连接成功
        """
        cfg = {**self.DEFAULT_CONFIG}
        if config:
            cfg.update(config)

        retry_count = cfg['RETRY_COUNT']
        retry_interval = cfg['RETRY_INTERVAL']

        for attempt in range(retry_count):
            try:
                device_str = self.device_id or ''
                logger.info(f"尝试连接设备: {device_str or '默认'} (尝试 {attempt + 1}/{retry_count})")

                self.device = u2.connect(device_str)
                # 验证连接
                info = self.device.info
                logger.info(f"设备已连接: {info.get('productName', 'unknown')}")
                self.is_connected = True
                return True

            except Exception as e:
                logger.error(f"连接设备失败: {e}", exc_info=True)
                if attempt < retry_count - 1:
                    logger.info(f"{retry_interval}秒后重试...")
                    time.sleep(retry_interval)

        logger.error(f"经过 {retry_count} 次尝试后，无法连接设备")
        return False

    def teardown_device(self):
        """断开设备连接"""
        try:
            if self.device:
                self.device.app_stop_all()
                self.device = None
            self.is_connected = False
            logger.info("设备连接已断开")
        except Exception as e:
            logger.error(f"断开设备时出错: {e}", exc_info=True)

    def is_device_connected(self) -> bool:
        """检查设备是否已连接"""
        try:
            if self.device:
                self.device.info  # 轻量验证
                self.is_connected = True
                return True
        except Exception:
            pass
        self.is_connected = False
        return False

    def screenshot(self, name: str) -> str:
        """
        截取屏幕并保存

        Returns:
            截图路径，失败返回空字符串
        """
        if not self.is_device_connected():
            logger.warning("设备未连接，无法截图")
            return ""

        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self.screenshots_dir, f'{name}_{timestamp}.png')
            self.device.screenshot(path)
            logger.info(f"截图已保存: {path}")
            return path
        except Exception as e:
            logger.error(f"截图失败: {e}", exc_info=True)
            return ""

    def open_app(self, package_name: str, retry_count: int = 3, retry_interval: int = 5) -> bool:
        """
        启动应用

        Returns:
            是否启动成功
        """
        if not self.is_connected:
            logger.error("设备未连接，无法启动应用")
            return False

        for attempt in range(retry_count):
            try:
                logger.info(f"启动应用: {package_name} (尝试 {attempt + 1}/{retry_count})")
                self.device.app_start(package_name)
                time.sleep(2)

                if self.is_app_running(package_name):
                    logger.info(f"应用启动成功: {package_name}")
                    return True

                if attempt < retry_count - 1:
                    time.sleep(retry_interval)
            except Exception as e:
                logger.error(f"启动应用失败: {e}", exc_info=True)
                if attempt < retry_count - 1:
                    time.sleep(retry_interval)

        logger.error(f"启动应用 {package_name} 失败")
        return False

    def close_app(self, package_name: str) -> bool:
        """关闭应用"""
        if not self.is_connected:
            return True

        try:
            self.device.app_stop(package_name)
            logger.info(f"应用已关闭: {package_name}")
            return True
        except Exception as e:
            logger.error(f"关闭应用失败: {e}", exc_info=True)
            return False

    def is_app_installed(self, package_name: str) -> bool:
        """检查应用是否已安装"""
        if not self.is_connected:
            return False

        try:
            result = self.device.app_info(package_name)
            installed = result is not None
            logger.info(f"应用 {package_name} {'已安装' if installed else '未安装'}")
            return installed
        except Exception as e:
            logger.error(f"检查应用安装状态失败: {e}", exc_info=True)
            return False

    def is_app_running(self, package_name: str) -> bool:
        """检查应用是否正在运行"""
        if not self.is_connected:
            return False

        try:
            running = self.device.app_current().get('package', '') == package_name
            if not running:
                # 备选：检查进程
                result = self.device.shell(f"pidof {package_name}").output.strip()
                running = bool(result)
            logger.info(f"应用 {package_name} {'运行中' if running else '未运行'}")
            return running
        except Exception as e:
            logger.error(f"检查应用运行状态失败: {e}", exc_info=True)
            return False
