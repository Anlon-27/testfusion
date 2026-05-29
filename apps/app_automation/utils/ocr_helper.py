# -*- coding: utf-8 -*-
"""
OCR 工具类 - 基于 EasyOCR
"""
import os
import time
import logging
import hashlib
import re
import subprocess
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageEnhance

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

logger = logging.getLogger(__name__)


class OCRHelper:
    """OCR 辅助类 - 提供图像文字识别功能"""

    _ocr_cache = {}
    _cache_ttl = 2.0
    _cache_max_size = 50

    _easyocr_reader = None

    def __init__(self, languages=None, use_gpu=False):
        if not EASYOCR_AVAILABLE:
            logger.warning("EasyOCR 未安装，OCR 功能将不可用。请运行: pip install easyocr")

        self.languages = languages or ['en']
        self.use_gpu = use_gpu

    @classmethod
    def get_easyocr_reader(cls, languages=None, use_gpu=False):
        if not EASYOCR_AVAILABLE:
            raise ImportError("EasyOCR 未安装，请运行: pip install easyocr")

        if cls._easyocr_reader is None:
            try:
                languages = languages or ['en']
                logger.info(f"初始化 EasyOCR reader (语言: {languages}, GPU: {use_gpu})...")
                logger.info("首次使用会下载模型，可能需要一些时间")
                cls._easyocr_reader = easyocr.Reader(languages, gpu=use_gpu)
                logger.info("EasyOCR reader 初始化完成")
            except Exception as e:
                logger.error(f"EasyOCR 初始化失败: {e}")
                raise
        return cls._easyocr_reader

    @staticmethod
    def _get_image_hash(img) -> str:
        if isinstance(img, Image.Image):
            img_array = np.array(img)
        else:
            img_array = img
        return hashlib.md5(img_array.tobytes()).hexdigest()

    @classmethod
    def _get_cache_key(cls, region: Tuple, img_hash: str) -> Tuple:
        return (tuple(region), img_hash)

    @classmethod
    def _clean_cache(cls):
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in cls._ocr_cache.items()
            if current_time - timestamp > cls._cache_ttl
        ]
        for key in expired_keys:
            cls._ocr_cache.pop(key, None)

        if len(cls._ocr_cache) > cls._cache_max_size:
            sorted_items = sorted(
                cls._ocr_cache.items(),
                key=lambda x: x[1][1]
            )
            for key, _ in sorted_items[:len(sorted_items)//2]:
                cls._ocr_cache.pop(key, None)

    def recognize_text(self, img, min_confidence=0.3, use_cache=True) -> str:
        if not EASYOCR_AVAILABLE:
            logger.error("EasyOCR 未安装，无法进行文字识别")
            return ""

        img_hash = None
        cache_key = None
        if use_cache:
            img_hash = self._get_image_hash(img)
            cache_key = (img_hash,)
            if cache_key in self._ocr_cache:
                result, timestamp = self._ocr_cache[cache_key]
                if time.time() - timestamp < self._cache_ttl:
                    logger.debug(f"使用缓存 OCR 结果: {result}")
                    return result

        try:
            reader = self.get_easyocr_reader(self.languages, self.use_gpu)

            if isinstance(img, Image.Image):
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                width, height = img.size
                if width < 1000 or height < 200:
                    scale_factor = 2
                    img = img.resize(
                        (width * scale_factor, height * scale_factor),
                        Image.LANCZOS
                    )
                    logger.debug(f"图片放大 {scale_factor} 倍以提高识别率")

                img_array = np.array(img)
            else:
                img_array = img
                if len(img_array.shape) == 2:
                    img_array = np.stack([img_array] * 3, axis=-1)

            results = reader.readtext(img_array)

            text_items = []
            for (bbox, text, confidence) in results:
                if float(confidence) >= min_confidence:
                    x_coord = bbox[0][0]
                    text_items.append((x_coord, text, float(confidence)))
                    logger.debug(f"OCR: '{text}', 置信度: {confidence:.2f}, x: {x_coord:.1f}")

            text_items.sort(key=lambda x: x[0])
            texts = [item[1] for item in text_items]
            combined_text = ' '.join(texts)

            if use_cache and cache_key:
                self._ocr_cache[cache_key] = (combined_text, time.time())
                self._clean_cache()

            logger.info(f"OCR 识别结果: '{combined_text}'")
            return combined_text.strip()

        except Exception as e:
            logger.error(f"OCR 识别失败: {e}")
            return ""

    def recognize_number(self, img, allow_comma=True, use_cache=True) -> int:
        text = self.recognize_text(img, use_cache=use_cache)

        text = text.replace('o', '0').replace('O', '0')
        text = text.replace('l', '1').replace('I', '1')
        text = text.replace('?', '1')

        if allow_comma:
            digits = ''.join(filter(lambda x: x.isdigit() or x == ',', text))
            digits = digits.replace(',', '')
        else:
            digits = ''.join(filter(str.isdigit, text))

        try:
            number = int(digits) if digits else 0
            logger.info(f"提取数字: {number}")
            return number
        except ValueError:
            logger.error(f"无法将文本转换为数字: {text}")
            return 0

    @staticmethod
    def _adb_screencap():
        """通过 ADB 实时截图，返回 BGR numpy array"""
        time.sleep(0.3)
        try:
            result = subprocess.run(
                ['adb', 'exec-out', 'screencap', '-p'],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"adb screencap 失败: {result.stderr.decode(errors='ignore')}"
                )
            img_array = np.frombuffer(result.stdout, np.uint8)
            img_cv = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if img_cv is None:
                raise RuntimeError("截图解码失败")
            return img_cv
        except FileNotFoundError:
            raise RuntimeError("未找到 adb 命令，请确保 ADB 已安装并加入 PATH")

    @staticmethod
    def crop_region(
        region: Tuple[int, int, int, int],
        screenshot_path: Optional[str] = None,
        screenshot: Optional[np.ndarray] = None,
    ) -> Image.Image:
        """
        裁剪屏幕指定区域

        Args:
            region: 坐标元组 (x1, y1, x2, y2)
            screenshot_path: 截图文件路径
            screenshot: 已获取的截图（numpy array, BGR格式）
        """
        if screenshot is not None:
            img_cv = screenshot
        elif screenshot_path and os.path.exists(screenshot_path):
            img_cv = cv2.imread(screenshot_path)
        else:
            img_cv = OCRHelper._adb_screencap()

        x1, y1, x2, y2 = region
        cropped = img_cv[y1:y2, x1:x2]

        pil_img = Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))
        pil_img = ImageEnhance.Contrast(pil_img).enhance(2.0)

        return pil_img

    def recognize_region_text(self, region: Tuple[int, int, int, int], screenshot_path: Optional[str] = None) -> str:
        img = self.crop_region(region, screenshot_path)
        return self.recognize_text(img)

    def recognize_region_number(self, region: Tuple[int, int, int, int], screenshot_path: Optional[str] = None) -> int:
        img = self.crop_region(region, screenshot_path)
        return self.recognize_number(img)


_ocr_helper_instance = None


def get_ocr_helper(languages=None, use_gpu=False) -> OCRHelper:
    global _ocr_helper_instance
    if _ocr_helper_instance is None:
        _ocr_helper_instance = OCRHelper(languages=languages, use_gpu=use_gpu)
    return _ocr_helper_instance
