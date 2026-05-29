# -*- coding: utf-8 -*-
"""
UI Flow 执行器 - 将 UI Flow JSON 转换为 uiautomator2 动作并执行
"""
import os
import time
import logging
import json
import re
import copy
from typing import Any, Dict, List, Optional

import uiautomator2 as u2
import cv2
import numpy as np
from PIL import Image
from django.conf import settings

from ..utils.image_matcher import find_image_on_screen, image_exists

try:
    from ..utils.ocr_helper import get_ocr_helper
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    import allure
    ALLURE_AVAILABLE = True
except ImportError:
    ALLURE_AVAILABLE = False

logger = logging.getLogger(__name__)


class UiFlowRunner:
    """将 ui_flow 转换为 uiautomator2 动作并执行"""

    def __init__(
        self,
        device_id: Optional[str] = None,
        image_base_dir: Optional[str] = None,
        username: Optional[str] = None,
    ):
        self.device_id = device_id
        self._device: Optional[u2.Device] = None

        if image_base_dir:
            self.image_base_dir = image_base_dir
        else:
            self.image_base_dir = os.path.join(
                settings.BASE_DIR, 'apps', 'app_automation', 'Template'
            )

        self.screenshots_dir = os.path.join(
            settings.MEDIA_ROOT, 'app-automation', 'screenshots', username or 'unknown'
        )

        os.makedirs(self.image_base_dir, exist_ok=True)
        os.makedirs(self.screenshots_dir, exist_ok=True)

        self.context: Dict[str, Any] = {
            'global': {},
            'local': {},
            'outputs': {},
        }

        self.runtime: Dict[str, Any] = {
            'retry_times': 3,
            'retry_interval': 0.5,
        }

        self._ocr_helper = None

        logger.info(f"初始化 UiFlowRunner，设备ID: {self.device_id}，图片目录: {self.image_base_dir}")

    # ── 设备管理 ──────────────────────────────────────────────

    def _get_device(self) -> u2.Device:
        """获取或连接设备"""
        if self._device is None:
            self._device = u2.connect(self.device_id or '')
            # 验证连接
            _ = self._device.info
            logger.info(f"uiautomator2 设备已连接: {self.device_id}")
        return self._device

    # ── 执行入口 ──────────────────────────────────────────────

    def run(
        self,
        ui_flow: List[Dict[str, Any]],
        variables: Optional[List[Dict[str, Any]]] = None,
        runtime: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if not isinstance(ui_flow, list):
            raise ValueError("ui_flow 必须是列表")

        self._init_context(variables, runtime)

        total_steps = len(ui_flow)
        passed_steps = 0
        failed_steps = 0

        logger.info(f"开始执行 UI Flow，共 {total_steps} 个步骤")

        for idx, step in enumerate(ui_flow, 1):
            step_name = step.get('name', step.get('type', 'unknown'))

            if progress_callback:
                try:
                    progress_callback(idx, total_steps, step_name, 'running')
                except Exception:
                    pass

            try:
                logger.info(f"执行步骤 {idx}/{total_steps}: {step_name}")
                step_title = f"步骤{idx}-{step_name}"
                if ALLURE_AVAILABLE:
                    with allure.step(step_title):
                        self._execute_step(step)
                else:
                    self._execute_step(step)
                passed_steps += 1

                if progress_callback:
                    try:
                        progress_callback(idx, total_steps, step_name, 'passed')
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f"步骤 {idx} 执行失败: {e}", exc_info=True)
                failed_steps += 1
                self._attach_allure(f"步骤{idx}-{step.get('name', step.get('type', 'unknown'))}-error", step)

                if progress_callback:
                    try:
                        progress_callback(idx, total_steps, step_name, 'failed')
                    except Exception:
                        pass

                if runtime and runtime.get('stop_on_error', False):
                    raise

        logger.info(f"UI Flow 执行完成，通过: {passed_steps}，失败: {failed_steps}")

        return {
            'total': total_steps,
            'passed': passed_steps,
            'failed': failed_steps,
            'outputs': self.context.get('outputs', {}),
        }

    def _init_context(self, variables=None, runtime=None):
        self.context = {'global': {}, 'local': {}, 'outputs': {}}
        if runtime:
            self.runtime.update(runtime)
        if variables:
            self._load_variables(variables)

    def _load_variables(self, variables: List[Dict[str, Any]]):
        for item in variables:
            if not isinstance(item, dict):
                continue
            name = item.get('name')
            if not name:
                continue
            scope = str(item.get('scope', 'local')).lower()
            value = item.get('value')
            self._set_variable(name, value, scope)

    def _set_variable(self, name: str, value: Any, scope: str = 'local'):
        if scope not in self.context:
            scope = 'local'
        self.context[scope][name] = value

    def _get_variable(self, name: str, scope: Optional[str] = None) -> Any:
        if scope:
            return self.context.get(scope, {}).get(name)
        for s in ['local', 'global', 'outputs']:
            if name in self.context.get(s, {}):
                return self.context[s][name]
        return None

    def _render_value(self, value: Any) -> Any:
        if isinstance(value, str):
            pattern = re.compile(r'\{\{\s*([^}]+)\s*\}\}|\$\{\s*([^}]+)\s*\}')

            def replace_var(match):
                var_name = match.group(1) or match.group(2)
                var_value = self._get_variable(var_name.strip())
                return str(var_value) if var_value is not None else ''

            return pattern.sub(replace_var, value)
        elif isinstance(value, dict):
            return {k: self._render_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._render_value(item) for item in value]
        return value

    # ── 步骤执行 ──────────────────────────────────────────────

    def _execute_step(self, step: Dict[str, Any]):
        action_type = step.get('type', '')
        action = action_type.lower() if action_type else ''
        step = self._render_value(step)

        config = step.get('config')
        if isinstance(config, dict):
            for key, value in config.items():
                if key not in step:
                    step[key] = value

        retry_times = int(step.get('retry_times', 0))
        retry_interval = float(step.get('retry_interval', self.runtime.get('retry_interval', 0.5)))

        if retry_times > 0:
            last_error = None
            for attempt in range(1 + retry_times):
                try:
                    self._dispatch_step(step, action)
                    return
                except Exception as e:
                    last_error = e
                    if attempt < retry_times:
                        logger.warning(
                            f"步骤 '{step.get('name', action)}' 第 {attempt+1} 次失败，"
                            f"{retry_interval}s 后重试 (剩余 {retry_times - attempt - 1} 次): {e}"
                        )
                        time.sleep(retry_interval)
            raise last_error
        else:
            self._dispatch_step(step, action)

    def _dispatch_step(self, step: Dict[str, Any], action: str):
        if step.get('kind') == 'custom':
            self._execute_custom_component(step)
            return

        action_map = {
            'click': self._action_click,
            'touch': self._action_click,
            'input': self._action_input,
            'swipe': self._action_swipe,
            'double_click': self._action_double_click,
            'long_press': self._action_long_press,
            'drag': self._action_drag,
            'swipe_to': self._action_swipe_to,
            'image_exists_click': self._action_image_exists_click,
            'image_exists_click_chain': self._action_image_exists_click_chain,
            'set_variable': self._action_set_variable,
            'unset_variable': self._action_unset_variable,
            'extract_output': self._action_extract_output,
            'screenshot': self._action_screenshot,
            'api_request': self._action_api_request,
            'wait': self._action_wait,
            'sleep': self._action_wait,
            'if': self._action_if,
            'loop': self._action_loop,
            'sequence': self._action_sequence,
            'try': self._action_try,
            'assert': self._action_assert,
            'foreach_assert': self._action_foreach_assert,
        }

        handler = action_map.get(action)
        if handler:
            handler(step)
        else:
            if self._try_execute_as_custom(step, action):
                return
            logger.warning(f"未知的动作类型: {action} (步骤: {step.get('name', 'unknown')})")

    # ── 自定义组件 ────────────────────────────────────────────

    def _load_custom_component_defs(self) -> Dict[str, Any]:
        if not hasattr(self, '_custom_defs_cache'):
            try:
                from ..models import AppCustomComponent
                defs = {}
                for comp in AppCustomComponent.objects.filter(enabled=True):
                    defs[comp.type] = {
                        'name': comp.name,
                        'steps': comp.steps or [],
                        'schema': comp.schema or {},
                        'default_config': comp.default_config or {},
                    }
                self._custom_defs_cache = defs
                logger.debug(f"已加载 {len(defs)} 个自定义组件定义")
            except Exception as e:
                logger.warning(f"加载自定义组件定义失败: {e}")
                self._custom_defs_cache = {}
        return self._custom_defs_cache

    def _execute_custom_component(self, step: Dict[str, Any]):
        comp_type = step.get('type', '')
        comp_name = step.get('name', comp_type)

        sub_steps = step.get('steps')

        if not sub_steps:
            defs = self._load_custom_component_defs()
            comp_def = defs.get(comp_type)
            if not comp_def:
                raise ValueError(f"自定义组件 '{comp_type}' 未找到，请检查是否已创建并启用")
            sub_steps = comp_def.get('steps', [])

        if not sub_steps or not isinstance(sub_steps, list):
            logger.warning(f"自定义组件 '{comp_name}' 没有步骤，跳过")
            return

        sub_steps = copy.deepcopy(sub_steps)

        comp_config = step.get('config', {})
        if isinstance(comp_config, dict):
            for key, value in comp_config.items():
                if key not in ('type', 'name', 'kind', 'steps'):
                    self._set_variable(key, value, 'local')

        logger.info(f"展开自定义组件 '{comp_name}' ({comp_type})，共 {len(sub_steps)} 个子步骤")

        for sub_idx, sub_step in enumerate(sub_steps, 1):
            sub_name = sub_step.get('name', sub_step.get('type', 'unknown'))
            logger.info(f"  自定义组件子步骤 {sub_idx}/{len(sub_steps)}: {sub_name}")
            self._execute_step(sub_step)

    def _try_execute_as_custom(self, step: Dict[str, Any], action: str) -> bool:
        defs = self._load_custom_component_defs()
        if action in defs:
            step['kind'] = 'custom'
            self._execute_custom_component(step)
            return True
        return False

    # ── 截图 / Allure ─────────────────────────────────────────

    def _safe_filename(self, text: str) -> str:
        safe = re.sub(r'[^0-9a-zA-Z_\-]+', '_', str(text))
        return safe.strip('_') or "step"

    def _capture_screenshot(self, name_prefix: str) -> Optional[str]:
        try:
            filename = f"{self._safe_filename(name_prefix)}_{int(time.time())}.png"
            full_path = os.path.join(self.screenshots_dir, filename)
            self._get_device().screenshot(full_path)
            if os.path.exists(full_path):
                return full_path
        except Exception:
            logger.exception("截图失败")
        return None

    def _attach_allure(self, name: str, step: Optional[Dict] = None):
        if not ALLURE_AVAILABLE:
            return
        if step is not None:
            try:
                allure.attach(
                    json.dumps(step, ensure_ascii=False, indent=2),
                    name=f"{name}-step",
                    attachment_type=allure.attachment_type.JSON,
                )
            except Exception:
                logger.exception("Allure JSON 附件写入失败")
        path = self._capture_screenshot(name)
        if path:
            try:
                allure.attach.file(path, name=name, attachment_type=allure.attachment_type.PNG)
            except Exception:
                logger.exception("Allure 截图附件写入失败")

    # ── 截图辅助（给其他方法用）─────────────────────────────────

    def _take_screenshot_cv(self):
        """截取屏幕并返回 BGR numpy array"""
        d = self._get_device()
        pil_img = d.screenshot()  # returns PIL Image
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    # ── 选择器解析 ──────────────────────────────────────────────

    def _resolve_selector(self, step: Dict[str, Any]) -> Optional[Dict]:
        """
        解析选择器。返回 dict 格式：
          image:   {'type': 'image', 'path': ..., 'threshold': ...}
          pos:     {'type': 'pos', 'x': ..., 'y': ...}
          region:  {'type': 'region', 'x1': ..., 'y1': ..., 'x2': ..., 'y2': ...}
          None: 解析失败
        """
        element_id = step.get('element_id')
        if element_id:
            return self._resolve_element_by_id(element_id)

        selector_type = step.get('selector_type', 'image')
        selector = step.get('selector', '')

        if selector_type == 'image':
            if not selector:
                logger.warning(f"图片选择器的 selector 为空: {step.get('name', step.get('type', 'unknown'))}")
                return None

            image_scope = step.get('image_scope', 'common')
            image_path = os.path.join(self.image_base_dir, image_scope, selector)

            if not os.path.isfile(image_path):
                logger.warning(f"图片文件不存在: {image_path}")
                return None

            threshold = step.get('image_threshold', 0.7)
            return {'type': 'image', 'path': image_path, 'threshold': float(threshold)}

        elif selector_type == 'pos':
            if isinstance(selector, str):
                parts = [p.strip() for p in selector.split(',')]
                if len(parts) >= 2:
                    return {'type': 'pos', 'x': int(parts[0]), 'y': int(parts[1])}
            elif isinstance(selector, (list, tuple)) and len(selector) >= 2:
                return {'type': 'pos', 'x': int(selector[0]), 'y': int(selector[1])}
            logger.warning(f"无效的坐标格式: {selector}")
            return None

        elif selector_type == 'region':
            if isinstance(selector, str):
                parts = [p.strip() for p in selector.split(',')]
                if len(parts) >= 4:
                    return {
                        'type': 'region',
                        'x1': int(parts[0]), 'y1': int(parts[1]),
                        'x2': int(parts[2]), 'y2': int(parts[3]),
                    }
            elif isinstance(selector, (list, tuple)) and len(selector) >= 4:
                return {
                    'type': 'region',
                    'x1': int(selector[0]), 'y1': int(selector[1]),
                    'x2': int(selector[2]), 'y2': int(selector[3]),
                }
            logger.warning(f"无效的区域格式: {selector}")
            return None

        logger.warning(f"未知的选择器类型: {selector_type}")
        return None

    def _resolve_element_by_id(self, element_id: int) -> Optional[Dict]:
        """从数据库加载元素，返回与 _resolve_selector 一致的 dict"""
        try:
            from apps.app_automation.models import AppElement

            element = AppElement.objects.filter(id=element_id, is_active=True).first()
            if not element:
                logger.warning(f"未找到元素: element_id={element_id}")
                return None

            element.increment_usage()

            if element.element_type == 'image':
                image_rel_path = element.config.get('image_path', '')
                if not image_rel_path:
                    return None
                image_path = os.path.join(self.image_base_dir, image_rel_path)
                if not os.path.isfile(image_path):
                    return None
                threshold = element.config.get('image_threshold', 0.7)
                return {'type': 'image', 'path': image_path, 'threshold': float(threshold)}

            elif element.element_type == 'pos':
                return {
                    'type': 'pos',
                    'x': element.config.get('x'),
                    'y': element.config.get('y'),
                }

            elif element.element_type == 'region':
                return {
                    'type': 'region',
                    'x1': element.config.get('x1'),
                    'y1': element.config.get('y1'),
                    'x2': element.config.get('x2'),
                    'y2': element.config.get('y2'),
                }

        except Exception as e:
            logger.error(f"解析元素失败: element_id={element_id}, 错误: {e}", exc_info=True)
        return None

    # ── 图片查找 ──────────────────────────────────────────────

    def _find_image_on_screen(self, sel: Dict, screenshot_cv=None):
        """在屏幕截图中查找图片，返回 (x, y, confidence) 或 None"""
        if sel['type'] != 'image':
            return None
        if screenshot_cv is None:
            screenshot_cv = self._take_screenshot_cv()
        return find_image_on_screen(
            sel['path'],
            screenshot_cv,
            threshold=sel.get('threshold', 0.7),
        )

    def _image_exists_on_screen(self, sel: Dict) -> bool:
        """判断图片是否存在于屏幕上"""
        if sel['type'] != 'image':
            return False
        try:
            screenshot = self._take_screenshot_cv()
            return find_image_on_screen(sel['path'], screenshot, threshold=sel.get('threshold', 0.7)) is not None
        except Exception:
            return False

    # ── 获取点击坐标 ──────────────────────────────────────────

    def _get_click_point(self, sel: Dict):
        """
        从选择器解析出点击坐标 (x, y)
        对于 image 类型，实时截屏并做模板匹配
        """
        if sel['type'] == 'pos':
            return (sel['x'], sel['y'])

        if sel['type'] == 'image':
            result = self._find_image_on_screen(sel)
            if result:
                return (result[0], result[1])
            raise ValueError(f"未在屏幕上找到图片: {sel.get('path')}")

        raise ValueError(f"无法从此选择器类型获取点击坐标: {sel.get('type')}")

    # ── 基础动作 ──────────────────────────────────────────────

    def _action_click(self, step: Dict[str, Any]):
        """点击"""
        target = self._resolve_selector(step)
        if target is None:
            raise ValueError(f"步骤 '{step.get('name', 'unknown')}' 无法解析选择器")
        x, y = self._get_click_point(target)
        logger.info(f"点击坐标: ({x}, {y})")
        self._get_device().click(x, y)

    def _action_double_click(self, step: Dict[str, Any]):
        """双击"""
        target = self._resolve_selector(step)
        if target:
            x, y = self._get_click_point(target)
            logger.info(f"双击坐标: ({x}, {y})")
            self._get_device().double_click(x, y)

    def _action_swipe(self, step: Dict[str, Any]):
        """滑动"""
        start = step.get('start')
        end = step.get('end')
        duration = step.get('duration', 0.5)

        if not start and not end:
            selector = step.get('selector')
            if selector:
                if isinstance(selector, str):
                    locator = json.loads(selector)
                else:
                    locator = selector
                if isinstance(locator, list) and len(locator) >= 2:
                    start = tuple(locator[0])
                    end = tuple(locator[1])

        if isinstance(start, str):
            start = tuple(int(x) for x in start.split(','))
        if isinstance(end, str):
            end = tuple(int(x) for x in end.split(','))

        if not start or not end:
            raise ValueError(f"Missing start or end coordinates for swipe: start={start}, end={end}")

        logger.info(f"滑动: {start} -> {end}")
        self._get_device().swipe(start[0], start[1], end[0], end[1], duration=duration)

    def _action_wait(self, step: Dict[str, Any]):
        """等待：有 selector 时等待元素出现，没有时纯等待 timeout 秒"""
        target = self._resolve_selector(step)
        timeout = step.get('timeout', step.get('duration', 3))

        if target and target['type'] == 'image':
            deadline = time.time() + timeout
            while time.time() < deadline:
                if self._image_exists_on_screen(target):
                    logger.info(f"图片已出现")
                    return
                time.sleep(0.5)
            logger.warning(f"等待图片超时 ({timeout}s): {target.get('path')}")
        else:
            logger.info(f"等待 {timeout} 秒")
            time.sleep(timeout)

    def _action_snapshot(self, step: Dict[str, Any]):
        """截图"""
        name = step.get('name', f'snapshot_{int(time.time())}')
        filename = f"{name}.png"
        filepath = os.path.join(self.screenshots_dir, filename)
        logger.info(f"截图保存: {filepath}")
        self._get_device().screenshot(filepath)

    def _action_input(self, step: Dict[str, Any]):
        """输入文本"""
        target = self._resolve_selector(step)
        value = step.get('value', '')

        from apps.core.variable_resolver import resolve_variables
        value = resolve_variables(value)

        send_enter = step.get('send_enter', False)
        d = self._get_device()

        if target:
            x, y = self._get_click_point(target)
            d.click(x, y)
            time.sleep(0.3)

        logger.info(f"输入文本: {value}")
        d.send_keys(value)

        if send_enter:
            time.sleep(0.2)
            d.press("enter")
            logger.info("发送回车键")

    def _action_text(self, step: Dict[str, Any]):
        """输入文本（旧版兼容）"""
        value = step.get('text', '')
        logger.info(f"输入文本: {value}")
        self._get_device().send_keys(value)

    def _action_set_variable(self, step: Dict[str, Any]):
        name = step.get('name')
        value = step.get('value')
        scope = step.get('scope', 'local')
        if name:
            self._set_variable(name, value, scope)
            logger.info(f"设置变量: {scope}.{name} = {value}")

    def _action_unset_variable(self, step: Dict[str, Any]):
        name = step.get('name')
        scope = step.get('scope', 'local')
        if name and scope in self.context and name in self.context[scope]:
            del self.context[scope][name]
            logger.info(f"删除变量: {scope}.{name}")

    def _action_extract_output(self, step: Dict[str, Any]):
        source = step.get('source', '')
        path = step.get('path', '')
        name = step.get('name')
        scope = step.get('scope', 'local')

        if not name:
            raise ValueError("extract_output 需要 name 参数")
        if not source:
            raise ValueError("extract_output 需要 source 参数")

        source_value = self._get_variable(source)
        if source_value is None:
            parts = source.split('.', 1)
            if len(parts) == 2 and parts[0] in self.context:
                source_value = self.context[parts[0]].get(parts[1])

        if source_value is None:
            raise ValueError(f"来源变量不存在: {source}")

        if path:
            current = source_value
            for key in self._parse_path(path):
                if isinstance(current, dict):
                    current = current.get(key)
                elif isinstance(current, (list, tuple)):
                    try:
                        current = current[int(key)]
                    except (ValueError, IndexError):
                        current = None
                else:
                    current = None
                if current is None:
                    raise ValueError(f"提取失败: 路径 '{path}' 在 '{key}' 处找不到值")
            extracted = current
        else:
            extracted = source_value

        self._set_variable(name, extracted, scope)
        logger.info(f"提取成功: {source}.{path} -> {scope}.{name} = {extracted}")

    @staticmethod
    def _parse_path(path: str) -> List[str]:
        keys = []
        for part in path.split('.'):
            if '[' in part:
                base, rest = part.split('[', 1)
                if base:
                    keys.append(base)
                for idx_part in rest.split('['):
                    idx_part = idx_part.rstrip(']')
                    if idx_part:
                        keys.append(idx_part)
            else:
                if part:
                    keys.append(part)
        return keys

    def _action_screenshot(self, step: Dict[str, Any]):
        self._action_snapshot(step)

    def _action_long_press(self, step: Dict[str, Any]):
        """长按"""
        target = self._resolve_selector(step)
        duration = step.get('duration', 2)
        if target:
            x, y = self._get_click_point(target)
            logger.info(f"长按: ({x}, {y}), 时长: {duration}秒")
            self._get_device().long_click(x, y, duration=duration)

    def _action_drag(self, step: Dict[str, Any]):
        """拖拽"""
        def _resolve_sel(s):
            cfg = {
                'selector': s,
                'selector_type': step.get('start_selector_type', 'image'),
                'image_scope': step.get('image_scope', 'common'),
            }
            sel = self._resolve_selector(cfg)
            if sel and sel['type'] in ('image', 'pos'):
                return self._get_click_point(sel)
            return None

        start_pt = _resolve_sel(step.get('start_selector'))
        end_pt = _resolve_sel(step.get('end_selector'))
        duration = step.get('duration', 0.8)

        if start_pt and end_pt:
            logger.info(f"拖拽: {start_pt} -> {end_pt}")
            self._get_device().swipe(
                start_pt[0], start_pt[1],
                end_pt[0], end_pt[1],
                duration=duration,
            )

    def _action_swipe_to(self, step: Dict[str, Any]):
        """滑动直到目标元素出现"""
        target_cfg = {
            'selector': step.get('target_selector'),
            'selector_type': step.get('target_selector_type', 'image'),
            'image_scope': step.get('image_scope', 'common'),
        }
        target = self._resolve_selector(target_cfg)

        direction = step.get('direction', 'up')
        max_swipes = step.get('max_swipes', 5)
        interval = step.get('interval', 0.5)

        d = self._get_device()

        for i in range(max_swipes):
            if target and target['type'] == 'image':
                if self._image_exists_on_screen(target):
                    logger.info("找到目标元素，停止滑动")
                    return

            logger.info(f"第 {i+1}/{max_swipes} 次滑动: {direction}")
            w, h = d.window_size()

            if direction == 'up':
                d.swipe(w // 2, int(h * 0.7), w // 2, int(h * 0.3))
            elif direction == 'down':
                d.swipe(w // 2, int(h * 0.3), w // 2, int(h * 0.7))
            elif direction == 'left':
                d.swipe(int(w * 0.7), h // 2, int(w * 0.3), h // 2)
            elif direction == 'right':
                d.swipe(int(w * 0.3), h // 2, int(w * 0.7), h // 2)

            time.sleep(interval)

        logger.warning(f"滑动 {max_swipes} 次后仍未找到目标元素")

    def _action_image_exists_click(self, step: Dict[str, Any]):
        """主定位存在则点击主定位，否则点击备用定位"""
        def _build_sel(s, s_type, scope, thresh):
            return self._resolve_selector({
                'selector': s,
                'selector_type': s_type or 'image',
                'image_scope': scope or 'common',
                'image_threshold': thresh or 0.7,
            })

        main = _build_sel(
            step.get('selector'), step.get('selector_type'),
            step.get('image_scope'), step.get('image_threshold'),
        )
        fallback = _build_sel(
            step.get('fallback_selector'), step.get('fallback_selector_type'),
            step.get('fallback_image_scope'), step.get('fallback_image_threshold'),
        )

        d = self._get_device()

        if main and self._image_exists_on_screen(main):
            x, y = self._get_click_point(main)
            logger.info("主定位存在，点击主定位")
            d.click(x, y)
        elif fallback:
            x, y = self._get_click_point(fallback)
            logger.info("主定位不存在，点击备用定位")
            d.click(x, y)

    def _action_image_exists_click_chain(self, step: Dict[str, Any]):
        """主定位存在则依次点击主定位和备用定位，否则只点击备用定位"""
        def _build_sel(s, s_type, scope):
            return self._resolve_selector({
                'selector': s,
                'selector_type': s_type or 'image',
                'image_scope': scope or 'common',
            })

        main = _build_sel(
            step.get('selector'), step.get('selector_type'), step.get('image_scope'),
        )
        fallback = _build_sel(
            step.get('fallback_selector'), step.get('fallback_selector_type'),
            step.get('fallback_image_scope'),
        )

        d = self._get_device()

        if main and self._image_exists_on_screen(main):
            x, y = self._get_click_point(main)
            logger.info("主定位存在，依次点击主定位和备用定位")
            d.click(x, y)
            time.sleep(0.5)

        if fallback:
            x, y = self._get_click_point(fallback)
            d.click(x, y)

    # ── API 请求 ──────────────────────────────────────────────

    def _action_api_request(self, step: Dict[str, Any]):
        import requests as req_lib

        method = step.get('method', 'GET').upper()
        url = self._render_value(step.get('url', ''))
        headers = step.get('headers', {})
        params = step.get('params', {})
        json_data = step.get('json', {})
        data = step.get('data', {})
        timeout = step.get('timeout', 10)
        save_as = step.get('save_as', '')
        scope = step.get('scope', 'local')
        response_type = step.get('response_type', 'auto')
        expected_status = step.get('expected_status')
        extracts = step.get('extracts', [])

        if not url:
            raise ValueError("api_request 缺少 url 参数")

        if isinstance(headers, dict):
            headers = {k: self._render_value(v) if isinstance(v, str) else v for k, v in headers.items()}
        if isinstance(params, dict):
            params = {k: self._render_value(v) if isinstance(v, str) else v for k, v in params.items()}

        logger.info(f"HTTP请求: {method} {url}")

        try:
            response = req_lib.request(
                method=method, url=url,
                headers=headers, params=params,
                json=json_data if json_data else None,
                data=data if data else None,
                timeout=timeout,
            )
        except Exception as e:
            logger.error(f"HTTP请求失败: {e}")
            raise

        body = self._parse_response_body(response, response_type)

        result = {
            'status_code': response.status_code,
            'headers': dict(response.headers),
            'body': body,
        }

        logger.info(f"HTTP响应: {response.status_code}")

        if expected_status is not None:
            if response.status_code != int(expected_status):
                raise AssertionError(
                    f"HTTP状态码断言失败: 期望 {expected_status}, 实际 {response.status_code}"
                )

        if save_as:
            self._set_variable(save_as, result, scope)

        if extracts and isinstance(extracts, list):
            for extract in extracts:
                if not isinstance(extract, dict):
                    continue
                e_path = extract.get('path', '')
                e_name = extract.get('name', '')
                e_scope = extract.get('scope', scope)
                if not e_name:
                    continue

                current = result
                try:
                    for key in self._parse_path(e_path):
                        if isinstance(current, dict):
                            current = current[key]
                        elif isinstance(current, (list, tuple)):
                            current = current[int(key)]
                        else:
                            raise KeyError(key)
                except (KeyError, IndexError, ValueError, TypeError) as e:
                    raise ValueError(f"api_request extracts 提取失败: path='{e_path}' 在 '{key}' 处出错: {e}")
                self._set_variable(e_name, current, e_scope)
                logger.info(f"api_request 提取: {e_path} -> {e_scope}.{e_name} = {current}")

    @staticmethod
    def _parse_response_body(response, response_type: str = 'auto'):
        if response_type == 'json':
            try:
                return response.json()
            except Exception:
                return response.text
        elif response_type == 'text':
            return response.text
        elif response_type == 'binary':
            import base64
            return base64.b64encode(response.content).decode('ascii')
        else:
            content_type = response.headers.get('Content-Type', '')
            if 'json' in content_type or 'javascript' in content_type:
                try:
                    return response.json()
                except Exception:
                    return response.text
            return response.text

    # ── 控制流 ──────────────────────────────────────────────

    def _action_if(self, step: Dict[str, Any]):
        left = self._render_value(step.get('left', ''))
        right = self._render_value(step.get('right', ''))
        operator = step.get('operator', '==')
        then_steps = step.get('then_steps', [])
        else_steps = step.get('else_steps', [])

        condition = self._eval_condition(left, operator, right)
        logger.info(f"条件判断: {left} {operator} {right} = {condition}")

        if condition:
            for sub_step in then_steps:
                self._execute_step(sub_step)
        else:
            for sub_step in else_steps:
                self._execute_step(sub_step)

    @staticmethod
    def _eval_condition(left, operator: str, right) -> bool:
        op = operator.strip().lower()

        if op == '==':
            return str(left) == str(right)
        if op == '!=':
            return str(left) != str(right)

        if op in ('>', '>=', '<', '<='):
            try:
                l_val, r_val = float(left), float(right)
            except (ValueError, TypeError):
                return False
            if op == '>':
                return l_val > r_val
            if op == '>=':
                return l_val >= r_val
            if op == '<':
                return l_val < r_val
            return l_val <= r_val

        if op == 'in':
            return str(left) in str(right)
        if op in ('not in', 'not_in'):
            return str(left) not in str(right)
        if op == 'contains':
            return str(right) in str(left)
        if op in ('notcontains', 'not_contains'):
            return str(right) not in str(left)

        if op in ('regex', 'match'):
            try:
                return bool(re.search(str(right), str(left)))
            except re.error:
                return False

        if op in ('truthy', 'exists'):
            return bool(left)
        if op in ('falsy', 'not_exists'):
            return not bool(left)

        if op == 'startswith':
            return str(left).startswith(str(right))
        if op == 'endswith':
            return str(left).endswith(str(right))

        logger.warning(f"未知的条件操作符: {operator}，默认返回 False")
        return False

    def _action_loop(self, step: Dict[str, Any]):
        mode = step.get('mode', 'count')
        steps = step.get('steps', [])
        max_loops = step.get('max_loops', 10)
        interval = step.get('interval', 0)

        if mode == 'count':
            times = step.get('times', 1)
            logger.info(f"计数循环: {times} 次")
            for i in range(times):
                logger.info(f"循环第 {i+1}/{times} 次")
                for sub_step in steps:
                    self._execute_step(sub_step)
                if interval > 0:
                    time.sleep(interval)

        elif mode == 'foreach':
            items = step.get('items', [])
            item_var = step.get('item_var', 'item')
            item_scope = step.get('item_scope', 'local')

            logger.info(f"遍历循环: {len(items)} 个元素")
            for idx, item in enumerate(items):
                logger.info(f"循环第 {idx+1}/{len(items)} 次, {item_var}={item}")
                self._set_variable(item_var, item, item_scope)
                for sub_step in steps:
                    self._execute_step(sub_step)
                if interval > 0:
                    time.sleep(interval)

        elif mode == 'condition':
            left = step.get('left', '')
            operator = step.get('operator', '==')
            right = step.get('right', '')

            logger.info(f"条件循环: {left} {operator} {right}")
            loop_count = 0
            while loop_count < max_loops:
                left_val = self._render_value(left)
                right_val = self._render_value(right)

                condition = False
                if operator == '==':
                    condition = left_val == right_val
                elif operator == '!=':
                    condition = left_val != right_val

                if not condition:
                    break

                loop_count += 1
                logger.info(f"条件循环第 {loop_count} 次")
                for sub_step in steps:
                    self._execute_step(sub_step)
                if interval > 0:
                    time.sleep(interval)

    def _action_sequence(self, step: Dict[str, Any]):
        steps = step.get('steps', [])
        logger.info(f"顺序执行 {len(steps)} 个子步骤")
        for sub_step in steps:
            self._execute_step(sub_step)

    def _action_try(self, step: Dict[str, Any]):
        try_steps = step.get('try_steps', [])
        catch_steps = step.get('catch_steps', [])
        finally_steps = step.get('finally_steps', [])
        error_var = step.get('error_var', 'error')
        error_scope = step.get('error_scope', 'local')

        logger.info("执行 try 块")
        try:
            for sub_step in try_steps:
                self._execute_step(sub_step)
        except Exception as e:
            logger.warning(f"捕获异常: {e}")
            self._set_variable(error_var, str(e), error_scope)
            for sub_step in catch_steps:
                self._execute_step(sub_step)
        finally:
            logger.info("执行 finally 块")
            for sub_step in finally_steps:
                self._execute_step(sub_step)

    # ── 断言 ──────────────────────────────────────────────

    def _action_assert(self, step: Dict[str, Any]):
        assert_type = step.get('assert_type', 'text')
        timeout = float(step.get('timeout', 0))
        retry_interval = float(step.get('retry_interval', 1))

        assert_map = {
            'text': self._assert_text,
            'number': self._assert_number,
            'regex': self._assert_regex,
            'range': self._assert_range,
            'exists': self._assert_exists,
            'image': self._assert_image,
        }

        handler = assert_map.get(assert_type)
        if not handler:
            raise ValueError(f"未知的断言类型: {assert_type}，支持: {', '.join(assert_map.keys())}")

        if timeout <= 0:
            handler(step)
            return

        deadline = time.time() + timeout
        last_error = None
        attempt = 0
        while True:
            attempt += 1
            try:
                handler(step)
                if attempt > 1:
                    logger.info(f"断言在第 {attempt} 次尝试后通过")
                return
            except (AssertionError, Exception) as e:
                last_error = e
                if time.time() >= deadline:
                    break
                remaining = deadline - time.time()
                wait_time = min(retry_interval, remaining)
                if wait_time > 0:
                    logger.debug(f"断言未通过 (第 {attempt} 次)，{wait_time:.1f}s 后重试: {e}")
                    time.sleep(wait_time)

        raise last_error

    # ── OCR 辅助 ──────────────────────────────────────────

    def _parse_ocr_region(self, step: Dict[str, Any]) -> tuple:
        selector = step.get('ocr_selector') or step.get('selector')
        selector_type = step.get('ocr_selector_type') or step.get('selector_type', 'region')

        if not selector:
            raise ValueError("断言需要 selector 或 ocr_selector 参数")
        if selector_type != 'region':
            raise ValueError(f"OCR 断言仅支持 selector_type=region，当前: {selector_type}")

        if isinstance(selector, str):
            parts = [int(p.strip()) for p in selector.split(',')]
            if len(parts) != 4:
                raise ValueError(f"region 格式错误: {selector}")
            return tuple(parts)
        elif isinstance(selector, (list, tuple)) and len(selector) >= 4:
            return tuple(int(x) for x in selector[:4])
        raise ValueError(f"无法解析 region: {selector}")

    def _ocr_recognize_text(self, region: tuple) -> str:
        ocr = self._get_ocr_helper()
        return ocr.recognize_region_text(region)

    def _ocr_recognize_number(self, region: tuple) -> int:
        ocr = self._get_ocr_helper()
        return ocr.recognize_region_number(region)

    def _get_ocr_helper(self):
        if self._ocr_helper is None:
            if not OCR_AVAILABLE:
                raise RuntimeError("OCR 功能不可用，请安装: pip install easyocr opencv-python")
            self._ocr_helper = get_ocr_helper(languages=['en'], use_gpu=False)
        return self._ocr_helper

    # ── 断言实现 ──────────────────────────────────────────

    def _assert_text(self, step: Dict[str, Any]):
        if not OCR_AVAILABLE:
            raise RuntimeError("文本断言需要 OCR 支持")
        region = self._parse_ocr_region(step)
        expected = step.get('expected', '')
        match_mode = step.get('match_mode', 'contains')

        actual_text = self._ocr_recognize_text(region)

        if match_mode == 'exact':
            passed = actual_text == expected
        elif match_mode == 'contains':
            passed = expected in actual_text
        elif match_mode == 'regex':
            passed = re.search(expected, actual_text) is not None
        else:
            raise ValueError(f"不支持的 match_mode: {match_mode}")

        if not passed:
            raise AssertionError(f"文本断言失败: 期望 '{expected}' ({match_mode}), 实际 '{actual_text}'")

        logger.info(f"文本断言成功: '{expected}' ({match_mode}) 匹配 '{actual_text}'")

    def _assert_number(self, step: Dict[str, Any]):
        if not OCR_AVAILABLE:
            raise RuntimeError("数值断言需要 OCR 支持")
        region = self._parse_ocr_region(step)
        expected_raw = step.get('expected', '0')

        try:
            expected_num = int(str(expected_raw).replace(',', '').replace(' ', ''))
        except (ValueError, TypeError):
            raise ValueError(f"number 断言的期望值无法转为数字: {expected_raw}")

        actual_num = self._ocr_recognize_number(region)

        if actual_num != expected_num:
            raise AssertionError(f"数值断言失败: 期望 {expected_num}, 实际 {actual_num}")

        logger.info(f"数值断言成功: 期望 {expected_num}, 实际 {actual_num}")

    def _assert_regex(self, step: Dict[str, Any]):
        if not OCR_AVAILABLE:
            raise RuntimeError("正则断言需要 OCR 支持")
        region = self._parse_ocr_region(step)
        pattern = step.get('expected', '')

        if not pattern:
            raise ValueError("regex 断言需要在 expected 字段填写正则表达式")

        actual_text = self._ocr_recognize_text(region)
        match = re.search(pattern, actual_text)

        if not match:
            raise AssertionError(f"正则断言失败: 模式 '{pattern}' 未匹配到文本 '{actual_text}'")

        logger.info(f"正则断言成功: 模式 '{pattern}' 匹配到 '{match.group()}'")

    def _assert_range(self, step: Dict[str, Any]):
        if not OCR_AVAILABLE:
            raise RuntimeError("范围断言需要 OCR 支持")
        region = self._parse_ocr_region(step)

        min_val = step.get('min')
        max_val = step.get('max')

        if min_val is None and max_val is None:
            raise ValueError("range 断言需要至少设置 min 或 max 之一")

        try:
            min_num = int(str(min_val).replace(',', '').replace(' ', '')) if min_val is not None else None
        except (ValueError, TypeError):
            raise ValueError(f"range 断言的 min 值无法转为数字: {min_val}")
        try:
            max_num = int(str(max_val).replace(',', '').replace(' ', '')) if max_val is not None else None
        except (ValueError, TypeError):
            raise ValueError(f"range 断言的 max 值无法转为数字: {max_val}")

        actual_num = self._ocr_recognize_number(region)

        if min_num is not None and actual_num < min_num:
            raise AssertionError(f"范围断言失败: 实际值 {actual_num} 小于最小值 {min_num}")
        if max_num is not None and actual_num > max_num:
            raise AssertionError(f"范围断言失败: 实际值 {actual_num} 大于最大值 {max_num}")

        range_desc = f"[{min_num if min_num is not None else '-∞'}, {max_num if max_num is not None else '+∞'}]"
        logger.info(f"范围断言成功: 实际值 {actual_num} 在范围 {range_desc} 内")

    def _assert_exists(self, step: Dict[str, Any]):
        """存在性断言：判断图片元素是否存在于屏幕上"""
        target = self._resolve_selector(step)
        if target is None:
            raise ValueError("exists 断言无法解析选择器")

        expected_exists = step.get('expected_exists', True)

        result = self._image_exists_on_screen(target)

        if expected_exists and not result:
            raise AssertionError("期望元素存在，但实际不存在")
        elif not expected_exists and result:
            raise AssertionError("期望元素不存在，但实际存在")

        logger.info(f"存在性断言成功: 期望存在={expected_exists}, 实际存在={result}")

    def _assert_image(self, step: Dict[str, Any]):
        """图片断言：在屏幕上查找期望图片是否存在"""
        expected_image = step.get('expected', '')
        image_scope = step.get('expected_image_scope') or step.get('image_scope', 'common')
        threshold = step.get('image_threshold', 0.7)

        if not expected_image:
            raise ValueError("image 断言需要在 expected 字段填写图片文件名")

        image_path = os.path.join(self.image_base_dir, image_scope, expected_image)

        if not os.path.isfile(image_path):
            raise ValueError(f"期望图片文件不存在: {image_path}")

        sel = {'type': 'image', 'path': image_path, 'threshold': float(threshold)}
        result = self._image_exists_on_screen(sel)

        if not result:
            raise AssertionError(f"图片断言失败: 未在屏幕上找到图片 '{expected_image}' (阈值: {threshold})")

        logger.info(f"图片断言成功: 在屏幕上找到图片 '{expected_image}'")

    # ── foreach_assert ────────────────────────────────────────

    def _action_foreach_assert(self, step: Dict[str, Any]):
        if not OCR_AVAILABLE:
            logger.warning("foreach_assert 需要 OCR 支持，请安装 easyocr")
            return

        try:
            config = step.get('config', {})

            expected_list = config.get('expected_list', [])
            max_loops = config.get('max_loops', 5)
            interval = config.get('interval', 0.5)
            timeout = config.get('timeout', 5)
            match_mode = config.get('match_mode', 'contains')
            assert_type = config.get('assert_type', 'text')

            click_sel_config = {
                'selector': config.get('click_selector'),
                'selector_type': config.get('click_selector_type', 'image'),
                'image_scope': config.get('image_scope', 'common'),
                'image_threshold': config.get('image_threshold', 0.7),
            }
            click_target = self._resolve_selector(click_sel_config)

            ocr_selector = config.get('ocr_selector')
            ocr_selector_type = config.get('ocr_selector_type', 'region')

            if not click_target:
                raise ValueError("foreach_assert 需要有效的 click_selector")
            if not ocr_selector:
                raise ValueError("foreach_assert 需要 ocr_selector 参数")

            if ocr_selector_type == 'region':
                if isinstance(ocr_selector, str):
                    parts = [int(p.strip()) for p in ocr_selector.split(',')]
                    if len(parts) != 4:
                        raise ValueError(f"OCR region 格式错误: {ocr_selector}")
                    ocr_region = tuple(parts)
                else:
                    ocr_region = tuple(ocr_selector)
            else:
                raise ValueError("foreach_assert 仅支持 ocr_selector_type=region")

            ocr = self._get_ocr_helper()

            matched_count = 0
            min_match = int(step.get('min_match', 1) or 0)
            d = self._get_device()

            for i in range(max_loops):
                logger.info(f"循环点击断言 第 {i+1}/{max_loops} 次")

                x, y = self._get_click_point(click_target)
                d.click(x, y)
                time.sleep(interval)

                if assert_type == 'number':
                    actual_value = ocr.recognize_region_number(ocr_region)
                else:
                    actual_value = ocr.recognize_region_text(ocr_region)

                matched = False
                for expected in expected_list:
                    if assert_type == 'number':
                        expected_num = int(str(expected).replace(',', ''))
                        if actual_value == expected_num:
                            matched = True
                            break
                    else:
                        if match_mode == 'exact':
                            if actual_value == expected:
                                matched = True
                                break
                        elif match_mode == 'contains':
                            if expected in actual_value:
                                matched = True
                                break

                if matched:
                    matched_count += 1
                    logger.info(f"第 {i+1} 次匹配成功: {actual_value}")
                else:
                    logger.warning(f"第 {i+1} 次未匹配: {actual_value}")

            logger.info(f"循环点击断言完成: 共 {max_loops} 次，匹配 {matched_count} 次")
            if matched_count < min_match:
                raise AssertionError(
                    f"循环点击断言失败: 期望至少匹配 {min_match} 次，实际 {matched_count} 次"
                )

        except Exception as e:
            logger.error(f"foreach_assert 执行失败: {e}")
            raise
