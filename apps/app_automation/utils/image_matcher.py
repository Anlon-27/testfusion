# -*- coding: utf-8 -*-
"""
图片模板匹配工具 - 基于 OpenCV
基于 OpenCV 模板匹配的图像识别与定位功能
"""
import os
import cv2
import numpy as np
from PIL import Image
import logging

logger = logging.getLogger(__name__)


def find_image_on_screen(
    template_path: str,
    screenshot,
    threshold: float = 0.7,
    return_center: bool = True,
) -> tuple | None:
    """
    在屏幕截图中查找模板图片

    Args:
        template_path: 模板图片路径
        screenshot: 截图数据 (PIL Image 或 numpy array)
        threshold: 匹配阈值 (0~1)
        return_center: 是否返回中心坐标，False 返回匹配区域左上角

    Returns:
        (x, y, confidence) 或 None
    """
    if not os.path.isfile(template_path):
        logger.warning(f"模板图片不存在: {template_path}")
        return None

    template = cv2.imread(template_path)
    if template is None:
        logger.warning(f"无法加载模板图片: {template_path}")
        return None

    if isinstance(screenshot, Image.Image):
        screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    if screenshot is None or screenshot.size == 0:
        logger.warning("截图为空，无法匹配")
        return None

    th, tw = template.shape[:2]
    sh, sw = screenshot.shape[:2]

    if th > sh or tw > sw:
        logger.warning(f"模板 ({tw}x{th}) 大于截图 ({sw}x{sh})，跳过匹配")
        return None

    try:
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            if return_center:
                cx = max_loc[0] + tw // 2
                cy = max_loc[1] + th // 2
                return (cx, cy, float(max_val))
            return (max_loc[0], max_loc[1], float(max_val))

        logger.debug(f"模板匹配失败: 最高置信度 {max_val:.3f} < 阈值 {threshold}")
        return None
    except Exception as e:
        logger.error(f"模板匹配异常: {e}", exc_info=True)
        return None


def multi_scale_match(
    template_path: str,
    screenshot,
    threshold: float = 0.7,
    scales: list = None,
) -> tuple | None:
    """
    多尺度模板匹配，适应不同分辨率

    Args:
        scales: 缩放比例列表，默认 [1.0, 0.8, 0.6]

    Returns:
        最佳匹配 (x, y, confidence, scale) 或 None
    """
    if scales is None:
        scales = [1.0, 0.9, 0.8, 0.7, 0.6]

    if not os.path.isfile(template_path):
        return None

    template = cv2.imread(template_path)
    if template is None:
        return None

    if isinstance(screenshot, Image.Image):
        screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    best = None

    for scale in scales:
        if scale != 1.0:
            new_w = int(template.shape[1] * scale)
            new_h = int(template.shape[0] * scale)
            if new_w < 10 or new_h < 10:
                continue
            scaled = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)
        else:
            scaled = template

        th, tw = scaled.shape[:2]
        sh, sw = screenshot.shape[:2]
        if th > sh or tw > sw:
            continue

        try:
            result = cv2.matchTemplate(screenshot, scaled, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val >= threshold:
                cx = max_loc[0] + tw // 2
                cy = max_loc[1] + th // 2
                if best is None or max_val > best[2]:
                    best = (cx, cy, float(max_val), scale)
        except Exception:
            continue

    return best


def image_exists(template_path: str, screenshot, threshold: float = 0.7) -> bool:
    """判断模板图片是否存在于截图中"""
    return find_image_on_screen(template_path, screenshot, threshold) is not None
