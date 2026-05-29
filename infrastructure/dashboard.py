import os
import sys
import threading
import time
import unicodedata
import os
from datetime import datetime

from config import COURSE_DIR
from infrastructure.rich_ui import console
from presentation.utils import clear_screen

C = '\033[36m'
G = '\033[32m'
Y = '\033[33m'
W = '\033[37m'
R = '\033[31m'
D = '\033[90m'
RB = '\033[41m\033[37m'
X = '\033[0m'

LOG_FILE = os.path.join(COURSE_DIR, 'study_debug.log')


def sec_fmt(s):
    if s is None or s <= 0:
        return '   0s'
    if s < 60:
        return f'{s:>4d}s'
    m, sec = divmod(s, 60)
    return f'{m:>3d}m{sec:02d}s'


def make_simple_bar(progress, width=18):
    filled = int(width * progress)
    remain = width - filled
    if remain < 0:
        remain = 0
    return f"[{W}{'█' * filled}{D}{'░' * remain}{X}]"


def make_progress_bar_viewed(viewed, total_dur, width=18):
    viewed_pct = min(1.0, viewed / total_dur) if total_dur > 0 else 0
    w = int(width * viewed_pct)
    r = width - w
    return f"[{W}{'█' * w}{D}{'░' * r}{X}]"


import re


def _clean(s):
    # 先移除已知的颜色常量
    s = s.replace(C, '').replace(G, '').replace(Y, '').replace(W, '').replace(R, '').replace(D, '').replace(RB, '').replace(X, '')
    # 再移除 256 色模式的颜色码 \033[38;5;Nm 和 \033[48;5;Nm
    s = re.sub(r'\033\[(\d+;)*\d+m', '', s)
    return s


def _dw(ch):
    w = unicodedata.east_asian_width(ch)
    return 2 if w in ('W', 'F') else 1


def _str_width(s):
    return sum(_dw(c) for c in s)


def _pad(s, width, align_left=True):
    dw = _str_width(s)
    pad = max(0, width - dw)
    if align_left:
        return s + ' ' * pad
    else:
        return ' ' * pad + s


class BoxBuilder:
    """统一边框构建系统 - 动态算法版

    核心设计:
    1. 所有内容行传入时不需要手动计算宽度或补空格
    2. BoxBuilder 自动检测最长文本（去掉颜色码后）
    3. 根据最长文本 + 边距 计算 inner 宽度
    4. 构建边框时自动为每行补 pad，确保右侧对齐

    使用方式:
        builder = BoxBuilder()
        builder.set_header_center('左侧标题', '中间信息')
        builder.add_line('[1] 课程名  [████]  99%  10个视频')  # 不需要手动补空格
        print(builder.build())
    """

    def __init__(self, color=C, margin=2):
        self.color = color
        self.margin = margin  # 边距：最长文本两侧额外留出的空格数
        self.reset()

    def reset(self):
        self.lines = []
        self.title = ''
        self.left_info = ''
        self.right_info = ''
        self.center_info = ''
        return self

    def set_title(self, title):
        self.title = title
        return self

    def set_header(self, left='', right=''):
        self.left_info = left
        self.right_info = right
        return self

    def set_header_center(self, left='', center=''):
        self.left_info = left
        self.center_info = center
        return self

    def add_line(self, line):
        self.lines.append(line)
        return self

    def add_lines(self, lines):
        self.lines.extend(lines)
        return self

    def _compute_inner(self):
        """动态计算 inner 宽度 = max(内容最大宽度, 标题栏宽度) + margin"""
        # 计算内容区最大宽度
        max_content_width = 0
        for line in self.lines:
            clean = _clean(line)
            w = _str_width(clean)
            if w > max_content_width:
                max_content_width = w

        # 计算标题栏宽度
        header_width = 0
        if self.center_info:
            left_w = _str_width(self.left_info)
            center_clean = _clean(self.center_info)
            center_w = _str_width(center_clean)
            header_width = left_w + 1 + center_w
        elif self.left_info or self.right_info:
            left_w = _str_width(self.left_info)
            right_w = _str_width(self.right_info)
            header_width = left_w + 1 + right_w
        elif self.title:
            header_width = _str_width(_clean(self.title))

        # inner = 最长文本 + margin（两侧边距）
        inner = max(max_content_width, header_width) + self.margin
        if inner < 30:
            inner = 30
        return inner

    def build(self):
        inner = self._compute_inner()
        C_ = self.color
        result = []
        result.append(C_ + '╔' + '═' * inner + '╗' + X)

        if self.center_info:
            left_w = _str_width(self.left_info)
            center_clean = _clean(self.center_info)
            center_w = _str_width(center_clean)
            mid_pad = inner - left_w - center_w
            if mid_pad < 1:
                mid_pad = 1
            top_line = W + self.left_info + X + ' ' * mid_pad + self.center_info
            clean_top = self.left_info + ' ' * mid_pad + center_clean
            clean_width = _str_width(clean_top)
            top_pad = inner - clean_width
            if top_pad < 0:
                top_pad = 0
            result.append(C_ + '║' + X + top_line + ' ' * top_pad + C_ + '║' + X)
            result.append(C_ + '╠' + '═' * inner + '╣' + X)
        elif self.left_info or self.right_info:
            left_w = _str_width(self.left_info)
            right_w = _str_width(self.right_info)
            mid_pad = inner - left_w - right_w
            if mid_pad < 1:
                mid_pad = 1
            top_line = W + self.left_info + X + ' ' * mid_pad + D + self.right_info + X
            clean_top = self.left_info + ' ' * mid_pad + self.right_info
            top_pad = inner - _str_width(clean_top)
            result.append(C_ + '║' + X + top_line + ' ' * top_pad + C_ + '║' + X)
            result.append(C_ + '╠' + '═' * inner + '╣' + X)
        elif self.title:
            clean_title = _clean(self.title)
            title_w = _str_width(clean_title)
            left_pad = (inner - title_w) // 2
            right_pad = inner - left_pad - title_w
            result.append(C_ + '║' + X + ' ' * left_pad + W + self.title + X + ' ' * right_pad + C_ + '║' + X)
            result.append(C_ + '╠' + '═' * inner + '╣' + X)

        # 中间内容区：自动计算每行的 pad
        for line in self.lines:
            clean = _clean(line)
            line_w = _str_width(clean)
            # 内容区可用宽度 = inner - 2（左右各1空格边距）
            pad = max(0, inner - 2 - line_w)
            result.append(C_ + '║' + X + '  ' + line + ' ' * pad + C_ + '║' + X)

        result.append(C_ + '╚' + '═' * inner + '╝' + X)
        return '\n'.join(result)


def dash_box(lines, label='', color=C):
    """简单边框，兼容旧代码"""
    builder = BoxBuilder(color=color)
    if label:
        builder.set_title(label)
    builder.add_lines(lines)
    return builder.build()


def menu_box(title, items, frame_width=50):
    """菜单边框，兼容旧代码，固定宽度"""
    inner = frame_width - 2
    out = ['\n' + C + '╔' + '═' * inner + '╗' + X]
    left_pad = (inner - _str_width(title)) // 2
    right_pad = inner - left_pad - _str_width(title)
    out.append(C + '║' + X + ' ' * left_pad + W + title + X + ' ' * right_pad + C + '║' + X)
    out.append(C + '╠' + '═' * inner + '╣' + X)
    for s in items:
        pad = inner - 2 - _str_width(_clean(s))
        out.append(C + '║' + X + '  ' + s + ' ' * pad + C + '║' + X)
    out.append(C + '╚' + '═' * inner + '╝' + X)
    return '\n'.join(out)


def show_progress_bar(iteration, total, prefix='', suffix='', length=40, fill='█'):
    percent = 100 * (iteration / float(total)) if total > 0 else 100
    filled_length = int(length * iteration // total) if total > 0 else length
    bar = fill * filled_length + '░' * (length - filled_length)
    sys.stdout.write(f'\r{prefix} |{bar}| {percent:.1f}% {suffix}')
    sys.stdout.flush()
    if iteration == total:
        print()


class DashboardDisplay:
    _instance = None
    _init_lock = threading.Lock()

    def __init__(self):
        self._slots = {}
        self._running = False
        self._thread = None
        self._data_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._has_ansi = self._check_ansi()
        self._log_fp = None
        self._status_hint = ''
        self._page_size = 10
        self._current_page = 1
        self._page_timer = 0  # 翻页计时器

    @classmethod
    def instance(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _open_log(self):
        try:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
            self._log_fp = open(LOG_FILE, 'a', encoding='utf-8')
        except Exception as e:
            self._log_fp = None

    def _check_ansi(self):
        if not sys.stdout.isatty():
            return False
        if os.name == 'nt':
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                mode = ctypes.c_uint32()
                h = kernel32.GetStdHandle(-11)
                if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
                    kernel32.SetConsoleMode(h, mode.value | 0x0004)
                    return True
            except Exception as e:
                pass
            return False
        return True

    @staticmethod
    def _dw(ch):
        w = unicodedata.east_asian_width(ch)
        return 2 if w in ('W', 'F') else 1

    @staticmethod
    def _str_width(s):
        return sum(DashboardDisplay._dw(c) for c in s)

    @staticmethod
    def _pad(s, width, align_left=True):
        dw = DashboardDisplay._str_width(s)
        pad = max(0, width - dw)
        if align_left:
            return s + ' ' * pad
        else:
            return ' ' * pad + s

    def register(self, node_id, video_name, video_duration, viewed_duration, report_interval=30):
        with self._data_lock:
            self._slots[node_id] = {
                'video_name': video_name,
                'duration': video_duration,
                'viewed': viewed_duration,
                'total_time': 0,
                'last_viewed': viewed_duration,
                'study_id': 0,
                'done': False,
                'failed': False,
                'interval': report_interval,
                'report_success': False,
            }

    def update(self, node_id, total_time, study_id=0):
        with self._data_lock:
            s = self._slots.get(node_id)
            if s:
                s['total_time'] = total_time
                if study_id:
                    s['study_id'] = study_id

    def mark_done(self, node_id):
        with self._data_lock:
            s = self._slots.get(node_id)
            if s:
                s['done'] = True

    def mark_failed(self, node_id):
        with self._data_lock:
            s = self._slots.get(node_id)
            if s:
                s['failed'] = True

    def mark_report_success(self, node_id):
        with self._data_lock:
            s = self._slots.get(node_id)
            if s:
                s['report_success'] = True

    def all_done(self):
        with self._data_lock:
            if not self._slots:
                return False
            return all(s['done'] or s['failed'] or (s['viewed'] + s['total_time'] >= s['duration']) for s in self._slots.values())

    def _min_active_interval(self):
        with self._data_lock:
            active = [s for s in self._slots.values() if not s['done'] and not s['failed'] and (s['viewed'] + s['total_time'] < s['duration'])]
            if not active:
                return 1
            return 2

    def debug(self, msg):
        ts = datetime.now().strftime('%H:%M:%S')
        line = f"[{ts}] {msg}"
        try:
            if self._log_fp:
                self._log_fp.write(line + '\n')
                self._log_fp.flush()
        except Exception as e:
            pass

    def info(self, msg):
        # 同时写入终端和日志文件
        self._raw_write(X + msg + X + '\n')
        # 写入日志文件
        self.debug(msg)

    def set_status_hint(self, hint):
        with self._data_lock:
            self._status_hint = hint

    def _raw_write(self, text):
        with self._write_lock:
            sys.stdout.write(text)
            sys.stdout.flush()

    def _sec_fmt(self, s):
        if s is None or s == 0:
            return '   0s'
        if s < 60:
            return f'{s:>4d}s'
        m, sec = divmod(s, 60)
        return f'{m:>3d}m{sec:02d}s'

    def _make_bar(self, slot, width=18):
        vid_dur = slot['duration']
        viewed = slot['viewed']
        total = viewed + slot['total_time']
        last = slot['last_viewed']
        old_pct = min(1.0, last / vid_dur) if vid_dur > 0 else 0
        cur_pct = min(1.0, total / vid_dur) if vid_dur > 0 else 0
        new_pct = max(0, cur_pct - old_pct)
        old_w = int(width * old_pct)
        new_w = int(width * new_pct)
        remain = width - old_w - new_w
        if total > last and new_w < 1 and remain > 0:
            new_w = 1
            remain -= 1
        if remain < 0:
            remain = 0
        bar = W + '█' * old_w + R + '█' * new_w + D + '░' * remain + X
        slot['last_viewed'] = total
        return f'[{bar}]'

    def _build_dashboard(self):
        with self._data_lock:
            slots = list(self._slots.values())
        done_count = sum(1 for s in slots if s['report_success'])
        failed_count = sum(1 for s in slots if s['failed'])
        active_slots = [s for s in slots if not s['done'] and not s['failed'] and (s['viewed'] + s['total_time'] < s['duration'])]
        active_count = len(active_slots)

        refresh_hint = f'刷新:{self._min_active_interval()}s' if active_count else ''

        # 固定宽度，确保每次刷新行列数完全一致
        WIDTH = 78
        inner = WIDTH - 2
        lines = []
        lines.append(C + '╔' + '═' * inner + '╗' + X)

        # 标题行：固定格式，确保宽度一致
        title = '  学习仪表盘'
        status_plain = f"✓{done_count} ✗{failed_count} /{len(slots)} {refresh_hint}"
        # 用无颜色版本计算宽度，确保padding准确
        title_width = self._str_width(title)
        status_width = self._str_width(status_plain)
        pad = inner - title_width - status_width
        if pad < 1:
            pad = 1
        # 构建带颜色的标题行，但padding基于无颜色宽度
        status_color = f"{G}✓{done_count}{X} {R}✗{failed_count}{X} /{len(slots)} {D}{refresh_hint}{X}"
        lines.append(C + '║' + X + W + title + X + ' ' * pad + status_color + X + C + '║' + X)

        lines.append(C + '╠' + '═' * inner + '╣' + X)

        # 表头：固定列宽，确保每行总宽度一致
        col1_w = 4   # # + 空格
        col2_w = 26  # 视频名
        col3_w = 9   # 时长
        col4_w = 24  # 进度条
        col5_w = 8   # 状态
        # 计算表头padding使总宽度等于inner
        header_total = col1_w + col2_w + col3_w + col4_w + col5_w
        header_pad = inner - header_total
        if header_pad > 0:
            col4_w += header_pad  # 把多余空间给进度条列

        col1 = self._pad('#', col1_w, True)
        col2 = self._pad('视频', col2_w, True)
        col3 = self._pad('时长', col3_w, False)
        col4 = self._pad('进度条', col4_w, True)
        col5 = self._pad('状态', col5_w, False)
        lines.append(D + ' ' + col1 + col2 + col3 + '  ' + col4 + col5 + X)
        lines.append(' ' + '─' * (inner))

        max_remain = 0
        max_remain_label = ''

        if not slots:
            lines.append(' ' * 25 + '(等待启动...)')
        else:
            for i, slot in enumerate(slots, 1):
                label = slot['video_name']
                dur = self._sec_fmt(slot['duration'])
                total = slot['viewed'] + slot['total_time']
                vid_dur = slot['duration']
                pct = int(total / vid_dur * 100) if vid_dur > 0 else 0
                bar = self._make_bar(slot)

                remain = max(0, vid_dur - total)
                if not slot['done'] and not slot['failed'] and remain > max_remain:
                    max_remain = remain
                    max_remain_label = label

                # 固定列宽构建每一行
                if slot['failed']:
                    status = RB + self._pad('失败', col5_w, False) + X
                    num = D + self._pad(str(i), col1_w, True) + X
                    name_col = D + self._pad(label, col2_w, True) + X
                    dur_col = D + self._pad(dur, col3_w, False) + X
                    bar_col = D + self._pad(f'[{"-" * 18}]', col4_w, True) + X
                elif slot['done'] or total >= vid_dur:
                    status = G + self._pad('完成', col5_w, False) + X
                    num = D + self._pad(str(i), col1_w, True) + X
                    name_col = W + self._pad(label, col2_w, True) + X
                    dur_col = Y + self._pad(dur, col3_w, False) + X
                    bar_col = self._pad(bar, col4_w, True)
                else:
                    status = Y + self._pad(f'{pct}%', col5_w, False) + X
                    num = D + self._pad(str(i), col1_w, True) + X
                    name_col = W + self._pad(label, col2_w, True) + X
                    dur_col = Y + self._pad(dur, col3_w, False) + X
                    bar_col = self._pad(bar, col4_w, True)
                lines.append(f' {num}{name_col}{dur_col}  {bar_col} {status}')

        # 预计剩余行 + 状态提示（右下角）
        lines.append('')
        if max_remain > 0:
            remain_text = f"  预计剩余: {self._sec_fmt(max_remain)}  (最长: {max_remain_label})"
        else:
            remain_text = ' '

        # 组合预计剩余和状态提示，状态提示放在右下角
        with self._data_lock:
            status_hint = self._status_hint

        if status_hint:
            # 计算剩余文本的显示宽度（去掉颜色码）
            remain_clean = _clean(remain_text)
            remain_width = self._str_width(remain_clean)
            hint_clean = _clean(status_hint)
            hint_width = self._str_width(hint_clean)
            # 中间空格数 = inner - remain_width - hint_width
            mid_space = inner - remain_width - hint_width
            if mid_space < 1:
                mid_space = 1
            combined_text = remain_text + ' ' * mid_space + status_hint
        else:
            combined_text = remain_text

        # 确保这行宽度固定
        combined_clean = _clean(combined_text)
        combined_pad = inner - self._str_width(combined_clean)
        if combined_pad < 0:
            combined_pad = 0
        lines.append(combined_text + ' ' * combined_pad)
        lines.append(C + '╚' + '═' * inner + '╝' + X)
        return '\n'.join(lines)

    def _refresh_loop(self):
        """使用 Rich Live 刷新仪表盘 - 增强版（自动轮播翻页）"""
        try:
            from rich.live import Live

            from infrastructure.rich_ui import render_study_dashboard

            with Live(refresh_per_second=2, screen=False, console=console) as live:
                while self._running:
                    with self._data_lock:
                        all_slots = list(self._slots.values())
                        current_page = self._current_page
                        page_size = self._page_size

                    done_count = sum(1 for s in all_slots if s['report_success'])
                    failed_count = sum(1 for s in all_slots if s['failed'])
                    learning_done_count = sum(1 for s in all_slots if s['done'] or (s['viewed'] + s['total_time'] >= s['duration']))

                    # 仅显示未完成的视频（动态剔除已完成/失败的）
                    display_slots = [s for s in all_slots if not s['done'] and not s['failed']]
                    active_count = len(display_slots)
                    refresh_hint = f'刷新:{self._min_active_interval()}s' if active_count else ''

                    # 总体进度（所有视频）
                    total_viewed = 0
                    total_dur = 0
                    for slot in all_slots:
                        t = slot['viewed'] + slot['total_time']
                        total_viewed += min(t, slot['duration'])
                        total_dur += slot['duration']
                    total_progress = total_viewed / total_dur if total_dur > 0 else 0

                    # 全局最长剩余（从所有未完成的视频中找）
                    max_remain = 0
                    max_remain_label = ''
                    for slot in display_slots:
                        total = slot['viewed'] + slot['total_time']
                        vid_dur = slot['duration']
                        remain = max(0, vid_dur - total)
                        if remain > max_remain:
                            max_remain = remain
                            max_remain_label = slot['video_name']

                    # 分页计算（基于 display_slots）
                    if not display_slots:
                        total_pages = 1
                        page_slots = []
                    else:
                        total_pages = max(1, (len(display_slots) + page_size - 1) // page_size)
                        if current_page > total_pages:
                            current_page = total_pages
                            with self._data_lock:
                                self._current_page = total_pages
                        start_idx = (current_page - 1) * page_size
                        end_idx = min(start_idx + page_size, len(display_slots))
                        page_slots = display_slots[start_idx:end_idx]

                    with self._data_lock:
                        status_hint = self._status_hint

                    panel = render_study_dashboard(
                        slots=page_slots,
                        done_count=done_count,
                        failed_count=failed_count,
                        learning_done_count=learning_done_count,
                        total_count=len(all_slots),
                        refresh_hint=refresh_hint,
                        max_remain=max_remain,
                        max_remain_label=max_remain_label,
                        total_progress=total_progress,
                        total_duration=total_dur,
                        status_hint=status_hint,
                        current_page=current_page,
                        total_pages=total_pages,
                        page_size=page_size,
                    )
                    live.update(panel)

                    # 自动翻页逻辑：每10秒切换一页
                    self._page_timer += self._min_active_interval()
                    if self._page_timer >= 10 and total_pages > 1:
                        self._page_timer = 0
                        with self._data_lock:
                            self._current_page += 1
                            if self._current_page > total_pages:
                                self._current_page = 1

                    if self.all_done():
                        self._running = False
                        return
                    time.sleep(self._min_active_interval())
        except Exception as e:
            # 即使出现异常，也使用简单的 Rich 渲染，而不是回退到旧版刷新
            while self._running:
                with self._data_lock:
                    all_slots = list(self._slots.values())
                    current_page = self._current_page
                    page_size = self._page_size

                done_count = sum(1 for s in all_slots if s['report_success'])
                failed_count = sum(1 for s in all_slots if s['failed'])
                learning_done_count = sum(1 for s in all_slots if s['done'] or (s['viewed'] + s['total_time'] >= s['duration']))

                display_slots = [s for s in all_slots if not s['done'] and not s['failed']]
                active_count = len(display_slots)
                refresh_hint = f'刷新:{self._min_active_interval()}s' if active_count else ''

                total_viewed = 0
                total_dur = 0
                for slot in all_slots:
                    t = slot['viewed'] + slot['total_time']
                    total_viewed += min(t, slot['duration'])
                    total_dur += slot['duration']
                total_progress = total_viewed / total_dur if total_dur > 0 else 0

                max_remain = 0
                max_remain_label = ''
                for slot in display_slots:
                    total = slot['viewed'] + slot['total_time']
                    vid_dur = slot['duration']
                    remain = max(0, vid_dur - total)
                    if remain > max_remain:
                        max_remain = remain
                        max_remain_label = slot['video_name']

                if not display_slots:
                    total_pages = 1
                    page_slots = []
                else:
                    total_pages = max(1, (len(display_slots) + page_size - 1) // page_size)
                    if current_page > total_pages:
                        current_page = total_pages
                        with self._data_lock:
                            self._current_page = total_pages
                    start_idx = (current_page - 1) * page_size
                    end_idx = min(start_idx + page_size, len(display_slots))
                    page_slots = display_slots[start_idx:end_idx]

                with self._data_lock:
                    status_hint = self._status_hint

                panel = render_study_dashboard(
                    slots=page_slots,
                    done_count=done_count,
                    failed_count=failed_count,
                    learning_done_count=learning_done_count,
                    total_count=len(all_slots),
                    refresh_hint=refresh_hint,
                    max_remain=max_remain,
                    max_remain_label=max_remain_label,
                    total_progress=total_progress,
                    total_duration=total_dur,
                    status_hint=status_hint,
                    current_page=current_page,
                    total_pages=total_pages,
                    page_size=page_size,
                )
                clear_screen()
                console.print(panel)

                # 自动翻页逻辑：每10秒切换一页
                self._page_timer += self._min_active_interval()
                if self._page_timer >= 10 and total_pages > 1:
                    self._page_timer = 0
                    with self._data_lock:
                        self._current_page += 1
                        if self._current_page > total_pages:
                            self._current_page = 1

                if self.all_done():
                    self._running = False
                    return
                time.sleep(self._min_active_interval())

    def _refresh_loop_legacy(self):
        first_frame = True
        total_lines = 0
        while self._running:
            frame = self._build_dashboard()
            with self._write_lock:
                if first_frame:
                    sys.stdout.write(frame + '\n')
                    sys.stdout.flush()
                    total_lines = frame.count('\n') + 1
                    first_frame = False
                else:
                    if self._has_ansi:
                        sys.stdout.write('\033[s')
                        sys.stdout.write('\033[9999D')
                        sys.stdout.write(f'\033[{total_lines}A')
                        sys.stdout.write(frame)
                        sys.stdout.write('\033[u')
                        sys.stdout.flush()
                    else:
                        os.system('cls')
                        sys.stdout.write(frame + '\n')
                        sys.stdout.flush()
            if self.all_done():
                self._running = False
                return
            time.sleep(self._min_active_interval())

    def start(self):
        if self._running:
            return
        self._open_log()
        # 重置状态（保留已注册的视频）
        with self._data_lock:
            self._status_hint = ''
        self._running = True
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        # 等待线程结束
        if self._thread:
            try:
                self._thread.join(timeout=5)  # 5秒超时
            except Exception as e:
                pass
            self._thread = None
        # 关闭日志文件
        if self._log_fp:
            try:
                self._log_fp.close()
            except Exception as e:
                pass
        # 重置状态
        self._slots.clear()
        self._status_hint = ''
        self._current_page = 1
        self._page_timer = 0
