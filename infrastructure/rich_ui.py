"""Rich 界面渲染模块 - 替代手写的 ANSI 边框系统"""

import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def _make_rich_progress(pct, width=20, color=None):
    """使用 Rich 官方默认样式渲染进度条

    返回一个可直接放入 Table 的 Renderable 对象
    """
    if color is None:
        color = _pct_color_rich(pct)

    # 使用在 Windows 命令行中支持的字符
    filled = int(width * pct)
    empty = width - filled
    # 使用 '█' 作为填充字符，'░' 作为空字符
    bar = "█" * filled + "░" * empty
    percentage = int(pct * 100)
    
    # 构建并返回 Text 对象，确保正确渲染
    progress_text = Text()
    progress_text.append(f"[{bar}]", style=color)
    progress_text.append(f" {percentage}%", style="bold")
    
    return progress_text

# 全局 Console 实例
console = Console()


def _pct_color_rich(pct):
    """根据进度返回 Rich 颜色"""
    if pct >= 0.99:  # 99% 及以上显示为绿色
        return "green"
    elif pct >= 0.5:
        return "yellow"
    elif pct > 0:
        return "orange3"
    else:
        return "red"


def _exam_pct_color(pct):
    """考试进度蓝色渐变"""
    if pct >= 0.99:
        return "dodger_blue1"
    elif pct >= 0.75:
        return "dodger_blue2"
    elif pct >= 0.5:
        return "steel_blue"
    elif pct >= 0.25:
        return "deep_sky_blue4"
    elif pct > 0:
        return "blue"
    else:
        return "grey50"


def _make_exam_progress(pct, width=20):
    """蓝色渐变色考试进度条"""
    color = _exam_pct_color(pct)
    filled = int(width * pct)
    empty = width - filled
    bar = "█" * filled + "░" * empty
    percentage = int(pct * 100)
    progress_text = Text()
    progress_text.append(f"[{bar}]", style=color)
    progress_text.append(f" {percentage}%", style="bold")
    return progress_text


def _fmt_duration(seconds):
    """格式化秒数为可读时长"""
    if seconds <= 0:
        return "0s"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    elif minutes > 0:
        return f"{minutes}m {secs:02d}s"
    else:
        return f"{secs}s"


def _str_width(s):
    """计算字符串显示宽度（中文算2，英文算1）"""
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ('F', 'W'):
            w += 2
        else:
            w += 1
    return w


def _truncate_width(s, max_width):
    """截断字符串到指定显示宽度，超出加省略号"""
    w = 0
    result = []
    for ch in s:
        cw = 2 if unicodedata.east_asian_width(ch) in ('F', 'W') else 1
        if w + cw > max_width - 1:
            result.append('…')
            break
        result.append(ch)
        w += cw
    return ''.join(result)


def render_main_menu(greeting, student_name, website_name,
                     merged_rows,
                     completed_videos, total_videos,
                     total_video_duration, total_viewed_duration,
                     completed_exams, total_exams):
    """全新主菜单——课程与考试融合，居中，混合进度条"""
    term_width = min(console.width or 80, 80)
    inner_width = min(term_width - 6, 74)

    # ── 标题 ──
    title_text = Text()
    title_text.append(f"{greeting}!", style="bold")
    if student_name:
        title_text.append(f" {student_name}", style="bold green")
    title_text.append("     FUCK 文理网课助手     ", style="bold white")
    title_text.append("当前平台: ", style="bold")
    title_text.append(website_name, style="bold green")

    tbl = Table(show_header=False, box=None, padding=(0, 1), collapse_padding=True, width=inner_width)
    tbl.add_column(justify="center")

    tbl.add_row("")

    # ── 双色混合进度条 ──
    if total_exams > 0:
        total_items = total_videos + total_exams
        total_completed = completed_videos + completed_exams
    else:
        total_items = total_videos
        total_completed = completed_videos
    overall_pct = total_completed / total_items if total_items > 0 else 1.0

    bar_width = 30
    green_blocks = int(bar_width * completed_videos / total_items) if total_items > 0 else 0
    blue_blocks = int(bar_width * completed_exams / total_items) if total_items > 0 else 0
    if blue_blocks == 0 and completed_exams > 0:
        blue_blocks = 1
    if green_blocks == 0 and completed_videos > 0:
        green_blocks = 1
    empty_blocks = bar_width - green_blocks - blue_blocks
    if empty_blocks < 0:
        if completed_videos >= completed_exams:
            green_blocks = bar_width - blue_blocks
        else:
            blue_blocks = bar_width - green_blocks
        empty_blocks = 0
    elif empty_blocks > 0 and overall_pct >= 1.0:
        if completed_videos >= completed_exams:
            green_blocks += empty_blocks
        else:
            blue_blocks += empty_blocks
        empty_blocks = 0

    bar_line = Text()
    bar_line.append("总体完成度 [", style="white")
    if green_blocks > 0:
        bar_line.append("█" * green_blocks, style="green")
    if blue_blocks > 0:
        bar_line.append("█" * blue_blocks, style="dodger_blue2")
    if empty_blocks > 0:
        bar_line.append("░" * empty_blocks, style="grey50")
    bar_line.append(f"] {int(overall_pct * 100)}%", style="bold white")
    tbl.add_row(bar_line)
    tbl.add_row("")

    # ── 统计信息 ──
    stats = Text()
    v_h = total_video_duration // 3600
    v_m = (total_video_duration % 3600) // 60
    vh_h = total_viewed_duration // 3600
    vh_m = (total_viewed_duration % 3600) // 60
    if total_videos > 0:
        stats.append(f"课程 {total_videos}视频 {v_h}h{v_m}m  |  ", style="dim")
        stats.append(f"已学 {completed_videos}", style="green")
        stats.append(f"({int(completed_videos/total_videos*100)}%)", style="green")
    else:
        stats.append("课程 --", style="dim")
    stats.append("    ", style="")

    if total_exams > 0:
        stats.append(f"考试 {total_exams}项  |  ", style="dim")
        stats.append(f"已交 {completed_exams}", style="dodger_blue2")
        stats.append(f"({int(completed_exams/total_exams*100)}%)", style="dodger_blue2")
    else:
        stats.append("考试 --", style="dim")
    tbl.add_row(Align.center(stats))
    tbl.add_row("")

    # ── 表头 ──
    sep = "─" * min(inner_width - 2, 72)
    tbl.add_row(Text(sep, style="dim"))

    col_idx = 5
    col_name = 22
    col_video = 22
    col_exam = 17

    hdr_table = Table(show_header=False, box=None, padding=(0, 0), collapse_padding=False, width=inner_width)
    hdr_table.add_column(width=col_idx, justify="center")
    hdr_table.add_column(width=col_name, justify="center")
    hdr_table.add_column(width=col_video, justify="center")
    hdr_table.add_column(width=col_exam, justify="center")
    hdr_table.add_row(
        Text("#", style="bold dim"),
        Text("课程", style="bold dim"),
        Text("视频进度", style="bold dim"),
        Text("考试", style="bold dim"),
    )
    tbl.add_row(hdr_table)
    tbl.add_row(Text(sep, style="dim"))

    if not merged_rows:
        tbl.add_row(Align.center(Text("暂无数据", style="dim")))
    else:
        content = Table(show_header=False, box=None, padding=(0, 0), collapse_padding=False, width=inner_width)
        content.add_column(width=col_idx, justify="center")
        content.add_column(width=col_name, justify="center", no_wrap=True)
        content.add_column(width=col_video, justify="center")
        content.add_column(width=col_exam, justify="center")

        for mr in merged_rows:
            idx = mr['index']
            name = mr['name']
            display_name = _truncate_width(name, col_name)

            v_pct = mr.get('video_pct', 0)
            v_total = mr.get('video_total', 0)
            if v_total > 0:
                vbar_w = 12
                v_filled = int(vbar_w * v_pct)
                v_bar = "█" * v_filled + "░" * (vbar_w - v_filled)
                v_color = _pct_color_rich(v_pct)
                video_cell = Text()
                video_cell.append(f"[{v_bar}]", style=v_color)
                video_cell.append(f" {int(v_pct*100)}%", style="bold")
            else:
                video_cell = Text("--", style="dim")

            e_done = mr.get('exam_done', 0)
            e_total = mr.get('exam_total', 0)
            if e_total > 0:
                if e_done >= e_total:
                    exam_cell = Text(f"{e_done}/{e_total}", style="green")
                else:
                    exam_cell = Text(f"{e_done}/{e_total}", style="dodger_blue2")
            else:
                exam_cell = Text("--", style="dim")

            content.add_row(
                Text(f"[{idx}]", style="dim"),
                Text(display_name, style="white"),
                video_cell,
                exam_cell,
            )
            content.add_row(Text(""), Text(""), Text(""), Text(""))
        tbl.add_row(content)

    tbl.add_row("")

    hint = Text()
    hint.append("输入编号看视频 / ", style="dim italic")
    hint.append("E+编号看考试", style="bold dodger_blue2")
    hint.append(" / S 一键全清 / A AI考试 / N 视频挂机 / R 刷新", style="dim italic")
    hint = Align.center(hint)
    tbl.add_row(hint)
    tbl.add_row("")

    btn1 = Text()
    btn1.append("[S]", style="bold yellow")
    btn1.append(" 一键全清    ", style="white")
    btn1.append("[A]", style="bold dodger_blue2")
    btn1.append(" AI考试    ", style="white")
    btn1.append("[N]", style="bold green")
    btn1.append(" 视频挂机  ", style="white")
    btn1.append("[R]", style="bold yellow")
    btn1.append(" 刷新数据  ", style="white")
    tbl.add_row(Align.center(btn1))

    btn2 = Text()
    btn2.append("[C]", style="bold yellow")
    btn2.append(" 切换平台    ", style="white")
    btn2.append("[L]", style="dim")
    btn2.append(" 切换账号    ", style="white")
    btn2.append("[0]", style="bold red")
    btn2.append(" 退出程序", style="white")
    tbl.add_row(Align.center(btn2))

    panel = Panel(
        tbl,
        title=title_text,
        title_align="center",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
        width=term_width,
    )
    return panel


def render_exam_dashboard(platform_name, pending_count, done_count, total_count, course_groups):
    """渲染考试仪表盘 - 模仿学习仪表盘风格
    
    Args:
        platform_name: 平台名称
        pending_count: 待做数量
        done_count: 已完成数量
        total_count: 总数量
        course_groups: [(section_title, items)] 每个分组 items=[(idx, tag, tag_color, name, status_text, name_color, is_selectable)]
    """
    term_width = min(console.width or 80, 80)
    inner_width = min(term_width - 6, 74)

    # 标题
    title_text = Text()
    title_text.append("考试仪表盘", style="bold cyan")
    title_text.append("     ", style="dim")
    title_text.append("FUCK 文理网课助手     ", style="bold white")
    title_text.append("当前平台: ", style="bold")
    title_text.append(platform_name, style="bold green")

    table = Table(show_header=False, box=None, padding=(0, 1), collapse_padding=True, width=inner_width)
    table.add_column(justify="left")

    table.add_row("")

    pct = done_count / total_count if total_count > 0 else 0
    bar_w = 36
    filled = int(bar_w * pct)
    bar = Text()
    bar.append("█" * filled, style=_pct_color_rich(pct))
    bar.append("░" * (bar_w - filled), style="dim")
    percentage = int(pct * 100)
    progress_line = Text()
    progress_line.append("考试进度: [", style="white")
    progress_line.append(bar)
    progress_line.append(f"] {percentage}%", style="bold")
    table.add_row(Align.center(progress_line))
    table.add_row("")

    stats = Text()
    stats.append(" 待做 ", style="white")
    stats.append(str(pending_count), style="bold yellow")
    stats.append(" 项    已交 ", style="white")
    stats.append(str(done_count), style="bold green")
    stats.append(" 项    总计 ", style="dim")
    stats.append(str(total_count), style="dim")
    stats.append(" 项", style="dim")
    table.add_row(Align.center(stats))
    table.add_row("")

    sep_width = min(inner_width - 4, 70)

    if course_groups:
        for section_title, items in course_groups:
            if not items:
                continue
            table.add_row(Text("─" * sep_width, style="dim"))
            table.add_row(Text(f"[{section_title}]", style="bold white"))
            table.add_row("")

            last_course = None
            for item in items:
                idx, tag, tag_color, name, status_text, name_color, is_selectable, course_name = item

                if course_name != last_course:
                    if last_course is not None:
                        table.add_row("")
                    table.add_row(Text(f"  {course_name}", style="dim cyan"))
                    last_course = course_name

                row_text = Text()
                row_text.append(f"   {str(idx).rjust(2)}. ", style="dim")
                row_text.append(f"[{tag}]", style=tag_color)
                row_text.append(f" {name}", style=name_color)
                if status_text:
                    row_text.append(f" {status_text}", style="dim")
                table.add_row(row_text)

    else:
        table.add_row(Text("暂无待做项目", style="dim"))

    table.add_row("")
    table.add_row(Text("─" * sep_width, style="dim"))
    table.add_row("")

    btn_table = Table(show_header=False, box=None, padding=(0, 1), collapse_padding=True, width=inner_width)
    btn_table.add_column("left", justify="left")
    btn_table.add_column("right", justify="right")
    btn_left = Text()
    btn_left.append("[R]", style="bold yellow")
    btn_left.append(" 刷新    ", style="white")
    btn_left.append("[A]", style="bold cyan")
    btn_left.append(" 全部答题", style="white")
    btn_right = Text()
    btn_right.append("[0]", style="bold red")
    btn_right.append(" 返回主菜单", style="white")
    btn_table.add_row(btn_left, btn_right)
    table.add_row(btn_table)

    panel = Panel(
        table,
        title=title_text,
        title_align="center",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
        width=term_width,
    )
    return panel


def render_course_detail(course_name, course_pct, total_viewed, total_dur, completed, total_videos,
                         video_rows, current_page, total_pages, has_prev, has_next):
    """渲染课程详情页 - 与主菜单保持一致的设计语言"""
    # 固定面板宽度，与主菜单保持一致
    term_width = min(console.width or 80, 80)  # 最大宽度80
    inner_width = min(term_width - 6, 74)

    # 标题 - 与主菜单风格一致
    title_text = Text()
    title_text.append(f"{course_name}", style="bold white")
    title_text.append(f" - {course_pct}%", style="green" if course_pct >= 100 else "yellow")

    # 内容表格 - 单列居中布局，与主菜单保持一致
    table = Table(
        show_header=False, 
        box=None, 
        padding=(0, 1), 
        collapse_padding=True, 
        width=inner_width
    )
    table.add_column(justify="center")

    table.add_row("")  # 增加空行，拉开标题与内容的距离

    # 总体进度行 - 与主菜单风格一致
    width = 36
    bar_filled = int(width * course_pct / 100)
    # 使用 '█' 作为填充字符，'░' 作为空字符
    bar = "█" * bar_filled + "░" * (width - bar_filled)
    # 构建 Text 对象
    progress_text = Text()
    progress_text.append("课程进度: ", style="white")
    progress_text.append(f"[{bar}]", style=_pct_color_rich(course_pct / 100))
    progress_text.append(f" {course_pct}%", style="bold")
    table.add_row(progress_text)
    table.add_row("")  # 增加空行

    # 统计信息 - 与主菜单风格一致
    stats_text = Text()
    stats_text.append(f"已学 {_fmt_duration(total_viewed)} / 总计 {_fmt_duration(total_dur)}", style="dim")
    stats_text.append(f"  |  {total_videos}个视频  已完成: {completed}", style="dim")
    table.add_row(stats_text)
    table.add_row("")  # 增加空行

    # 视频列表 - 与主菜单风格一致
    if video_rows:
        # 动态计算列宽，根据 inner_width 分配
        name_width = min(28, max(18, (inner_width - 60) // 2))
        bar_width = 16
        duration_width = 10
        status_width = 10
        idx_width = 6

        # 上分隔线
        sep_width = min(inner_width - 4, 70)
        table.add_row(Text("─" * sep_width, style="dim"))
        
        # 表头
        header_table = Table(
            show_header=True,
            header_style="bold white",
            box=None,
            padding=(0, 1),
            collapse_padding=True,
            width=inner_width,
        )
        header_table.add_column("#", width=idx_width, justify="left")
        header_table.add_column("视频名称", width=name_width, justify="left")
        header_table.add_column("时长", width=duration_width, justify="left")
        header_table.add_column("进度", width=bar_width + 10, justify="left")
        header_table.add_column("状态", width=status_width, justify="left")
        table.add_row(header_table)
        
        # 表头下方的分隔线
        table.add_row(Text("─" * sep_width, style="dim"))
        
        # 内容表格
        content_table = Table(
            show_header=False,
            box=None,
            padding=(0, 1),
            collapse_padding=True,
            width=inner_width,
        )
        content_table.add_column("idx", width=idx_width, justify="left")
        content_table.add_column("name", width=name_width, justify="left")
        content_table.add_column("duration", width=duration_width, justify="left")
        content_table.add_column("progress", width=bar_width + 10, justify="left")
        content_table.add_column("status", width=status_width, justify="left")

        # 在表头和第一行之间添加空行
        content_table.add_row("", "", "", "", "")

        for row in video_rows:
            idx = row['idx']
            name = row['name']
            duration = row['duration']
            pct = row['pct'] / 100.0  # 转为 0-1 小数
            status_text = row['status_text']

            display_name = _truncate_width(name, name_width)

            # 使用与主菜单一致的进度条样式
            progress_bar = _make_rich_progress(pct, width=bar_width)

            if status_text == '已完成':
                status_style = "bold green"
            elif status_text == '进行中':
                status_style = "bold yellow"
            else:
                status_style = "bold red"

            content_table.add_row(
                Text(f"[{idx}]", style="dim"),
                Text(display_name, style="white"),
                Text(_fmt_duration(duration), style="yellow"),
                progress_bar,
                Text(status_text, style=status_style),
            )
            # 每行之间加空行（通过空行实现间距）
            content_table.add_row("", "", "", "", "")
        table.add_row(content_table)
    else:
        table.add_row(Text("暂无视频数据", style="dim"))

    table.add_row("")

    # 分页信息 - 与主菜单风格一致
    page_info = Text(f"第 {current_page}/{total_pages} 页", style="dim")
    table.add_row(page_info)
    table.add_row("")

    # 提示文字 - 与主菜单风格一致
    hint = Text("输入视频编号学习 / S 学习本课全部未完成 / 0 返回", style="dim italic")
    table.add_row(hint)
    table.add_row("")  # 增加空行

    # 底部操作按钮 - 与主菜单风格一致
    buttons = Text()
    if has_prev:
        buttons.append("[P]", style="bold yellow")
        buttons.append(" 上一页  ", style="white")
    if has_next:
        buttons.append("[N]", style="bold yellow")
        buttons.append(" 下一页  ", style="white")
    buttons.append("[S]", style="bold yellow")
    buttons.append(" 学习全部未完成  ", style="white")
    buttons.append("[0]", style="dim")
    buttons.append(" 返回主菜单", style="white")
    table.add_row(buttons)

    # 组装 Panel - 与主菜单保持一致
    panel = Panel(
        table,
        title=title_text,
        title_align="center",  # 标题居中
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
        width=term_width,
    )

    return panel


def render_exam_detail(course_name, exam_pct, total_done, total_pending, total_count,
                       exam_rows, current_page, total_pages, has_prev, has_next):
    """渲染考试详情页 —— 考试只有已交/未做两种状态，不展示空进度条"""
    term_width = min(console.width or 80, 80)
    inner_width = min(term_width - 6, 74)

    title_text = Text()
    title_text.append(f"{course_name}", style="bold white")
    title_text.append(" - ", style="dim")
    pct_text = f"{int(exam_pct * 100)}%"
    title_text.append(pct_text, style="dodger_blue1" if exam_pct >= 0.99 else "steel_blue")

    # 使用单一 Table，避免嵌套表格带来的列宽塌缩
    outer = Table(
        show_header=False,
        box=None,
        padding=(0, 1),
        collapse_padding=True,
        width=inner_width,
    )
    outer.add_column(justify="center")

    outer.add_row("")

    # 总体进度行 - 蓝色渐变
    color = _exam_pct_color(exam_pct)
    filled = int(24 * exam_pct)
    empty = 24 - filled
    bar_line = Text()
    bar_line.append("考试进度: [", style="white")
    bar_line.append("█" * filled + "░" * empty, style=color)
    bar_line.append("] ", style="white")
    bar_line.append(f"{int(exam_pct * 100)}%", style="bold")
    outer.add_row(bar_line)
    outer.add_row("")

    stats_text = Text()
    stats_text.append(f"已交 {total_done} 项    待做 {total_pending} 项    共 {total_count} 项", style="dim")
    outer.add_row(stats_text)
    outer.add_row("")

    if exam_rows:
        col_idx = 8
        col_name = 30
        col_tag = 10
        col_status = 10

        sep_width = min(inner_width - 4, 70)
        outer.add_row(Text("─" * sep_width, style="dim"))

        # 表头 + 内容统一用一个内层表格，Rich 自动对齐
        inner = Table(show_header=True, box=None, padding=(0, 1),
                      collapse_padding=False, width=inner_width,
                      header_style="bold dim")
        inner.add_column("#", width=col_idx, justify="center")
        inner.add_column("名称", width=col_name, justify="left", no_wrap=True)
        inner.add_column("类型", width=col_tag, justify="center")
        inner.add_column("状态", width=col_status, justify="center")

        for row in exam_rows:
            idx = row['idx']
            name = row['name']
            tag = row.get('tag', '考试')
            tag_color = row.get('tag_color', 'magenta')
            is_done = row.get('is_done', False)
            status_text = row.get('status_text', '')

            display_name = _truncate_width(name, col_name)

            # 状态颜色：已完成绿色，已超时灰色，其余灰色
            if is_done:
                s_color = "dim green"
            elif '超时' in status_text:
                s_color = "dim"
            else:
                s_color = "dim"

            if is_done:
                inner.add_row(
                    Text(f"[{idx}]", style="dim"),
                    Text(display_name, style="dim green"),
                    Text(f"[{tag}]", style=f"dim {tag_color}" if tag_color else "dim"),
                    Text(status_text, style=s_color),
                )
            else:
                inner.add_row(
                    Text(f"[{idx}]", style="dim"),
                    Text(display_name, style="dim"),
                    Text(f"[{tag}]", style=f"dim {tag_color}" if tag_color else "dim"),
                    Text(status_text, style=s_color),
                )
        outer.add_row(inner)
    else:
        outer.add_row(Text("暂无考试数据", style="dim"))

    outer.add_row("")

    page_info = Text(f"第 {current_page}/{total_pages} 页", style="dim")
    outer.add_row(page_info)
    outer.add_row("")

    hint = Text("输入编号执行考试 / S 全部答题 / 0 返回", style="dim italic")
    outer.add_row(hint)
    outer.add_row("")

    buttons = Text()
    if has_prev:
        buttons.append("[P]", style="bold yellow")
        buttons.append(" 上一页  ", style="white")
    if has_next:
        buttons.append("[N]", style="bold yellow")
        buttons.append(" 下一页  ", style="white")
    buttons.append("[S]", style="bold yellow")
    buttons.append(" 全部答题  ", style="white")
    buttons.append("[0]", style="dim")
    buttons.append(" 返回主菜单", style="white")
    outer.add_row(buttons)

    panel = Panel(
        outer,
        title=title_text,
        title_align="center",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
        width=term_width,
    )

    return panel


def _pad_width(s, width):
    """按显示宽度填充，中文算2英文算1"""
    sw = _str_width(s)
    pad = max(0, width - sw)
    return s + ' ' * pad


def render_all_in_one_dashboard(video_stats, exam_stats, elapsed,
                                total_duration=0, max_remain=0,
                                model_name="DeepSeek", countdown=0):
    """一键全清仪表盘 —— 继承学习仪表盘 + 考试仪表盘设计语言"""
    import time as _t

    term_w = min(console.width or 80, 100)
    inner_w = term_w - 6

    v_total = video_stats.get('total', 0)
    v_done  = video_stats.get('done', 0)
    v_fail  = video_stats.get('failed', 0)
    v_slots = video_stats.get('slots', [])

    e_total = exam_stats.get('total', 0)
    e_done  = exam_stats.get('done', 0)
    e_fail  = exam_stats.get('failed', 0)
    e_slots = exam_stats.get('slots', [])

    sep = "─" * (inner_w - 2)

    outer = Table(show_header=False, box=None, padding=0, collapse_padding=True, width=inner_w)
    outer.add_column(justify="left")

    # ── 标题栏状态（继承学习仪表盘: ✓done ✗failed /total） ──
    status_parts = []
    if v_total > 0:
        status_parts.append(f"[green]✓{v_done}[/green]")
        status_parts.append(f"[red]✗{v_fail}[/red]")
        status_parts.append(f"[white]/{v_total}视频[/white]")
    if v_total > 0 and e_total > 0:
        status_parts.append("[dim]|[/dim]")
    if e_total > 0:
        status_parts.append(f"[dodger_blue2]✓{e_done}[/dodger_blue2]")
        status_parts.append(f"[red]✗{e_fail}[/red]")
        status_parts.append(f"[white]/{e_total}考试[/white]")
    title = Text("一键全清", style="bold white")
    subtitle = Text.from_markup(" ".join(status_parts))

    # ── 顶部统计信息（继承学习仪表盘: 进度 | 剩余 | 总时长 | 预计完成） ──
    done_items = v_done + e_done
    total_items = v_total + e_total
    remain_items = total_items - done_items

    left_text = f"进度: {done_items}/{total_items} 完成 | 剩余 {remain_items}"
    if total_duration > 0:
        left_text += f" | 总时长 {_fmt_duration(total_duration)}"
    right_text = ""
    if countdown > 0:
        right_text = f"预计完成 {_fmt_duration(int(countdown))}"

    stats = Text()
    stats.append(left_text, style="")
    if right_text:
        pad_len = max(1, len(sep) - _str_width(left_text) - _str_width(right_text))
        stats.append(" " * pad_len, style="")
        stats.append(right_text, style="dim cyan")
    outer.add_row(stats)

    # ── 总进度条（继承学习仪表盘底部进度条风格） ──
    if total_items > 0:
        overall_pct = done_items / total_items
        bar_w = 20
        filled = int(bar_w * overall_pct)
        empty = bar_w - filled
        bar = "█" * filled + "░" * empty
        pct_str = int(overall_pct * 100)

        end_time_str = ""
        if countdown > 0:
            end_time = _t.localtime(_t.time() + countdown)
            end_time_str = _t.strftime("%H:%M", end_time)

        prog_text = Text()
        prog_text.append("总进度: ", style="white")
        prog_text.append(f"[{bar}]", style=_pct_color_rich(overall_pct))
        prog_text.append(f" {pct_str}%", style="bold")
        if end_time_str:
            prog_text.append(f"    预计 {end_time_str} 结束", style="dim cyan")
        prog_text.append("    Ctrl+C 停止", style="dim")
        outer.add_row(prog_text)
    outer.add_row("")

    # ══════════════════════════════════════════════════════════════
    #  视频部分 —— 继承 render_study_dashboard 紧凑表格风格
    # ══════════════════════════════════════════════════════════════
    if v_total > 0 and v_slots:
        outer.add_row(Text(sep, style="dim"))
        v_hdr = Text()
        v_hdr.append(_pad_width("#", 4), style="bold dim")
        v_hdr.append(_pad_width("视频名称", 30), style="bold dim")
        v_hdr.append(_pad_width("时长", 10), style="bold dim")
        v_hdr.append(_pad_width("进度", 22), style="bold dim")
        v_hdr.append(_pad_width("状态", 6), style="bold dim")
        outer.add_row(v_hdr)
        outer.add_row(Text(sep, style="dim"))

        for i, slot in enumerate(v_slots[:10], 1):
            name = slot.get('video_name', '')
            if _str_width(name) > 28:
                name = _truncate_width(name, 28)
            dur = _fmt_duration(slot.get('duration', 0))
            total_viewed = slot.get('viewed', 0) + slot.get('total_time', 0)
            vid_dur = slot.get('duration', 0)
            pct = (total_viewed / vid_dur) if vid_dur > 0 else 0

            bar_w = 18
            if slot.get('failed'):
                bar = "-" * bar_w
                bar_color = "dim"
                status = "失败"
                status_color = "red"
                name_color = "dim"
            elif slot.get('done') or pct >= 0.99:
                bar = "█" * bar_w
                bar_color = "green"
                status = "完成"
                status_color = "green"
                name_color = "white"
                pct = 1.0
            else:
                filled = int(bar_w * pct)
                empty = bar_w - filled
                bar = "█" * filled + "░" * empty
                bar_color = _pct_color_rich(pct)
                status = f"{int(pct*100)}%"
                status_color = bar_color
                name_color = "white"

            row = Text()
            row.append(_pad_width(str(i), 4), style="dim")
            row.append(_pad_width(name, 30), style=name_color)
            row.append(_pad_width(dur, 10), style="yellow")
            row.append(_pad_width(f"[{bar}]", 22), style=bar_color)
            row.append(_pad_width(status, 6), style=status_color)
            outer.add_row(row)

    # ══════════════════════════════════════════════════════════════
    #  考试部分 —— 继承 render_exam_dashboard 蓝色进度风格
    # ══════════════════════════════════════════════════════════════
    if e_total > 0 and e_slots:
        outer.add_row("")
        outer.add_row(Text(sep, style="dim"))

        e_hdr = Text()
        e_hdr.append(_pad_width("#", 4), style="bold dim")
        e_hdr.append(_pad_width("考试/作业", 36), style="bold dim")
        e_hdr.append(_pad_width("进度", 22), style="bold dim")
        e_hdr.append(_pad_width("状态", 6), style="bold dim")
        outer.add_row(e_hdr)
        outer.add_row(Text(sep, style="dim"))

        for i, slot in enumerate(e_slots[:10], 1):
            name = slot.get('name', '')
            if _str_width(name) > 34:
                name = _truncate_width(name, 34)

            bar_w = 18
            if slot.get('failed'):
                bar = "-" * bar_w
                bar_color = "dim"
                status = "失败"
                status_color = "red"
                name_color = "dim"
            elif slot.get('done'):
                bar = "█" * bar_w
                bar_color = "dodger_blue2"
                status = "已交"
                status_color = "dodger_blue2"
                name_color = "white"
            elif slot.get('progress', 0) > 0:
                p = slot['progress']
                filled = int(bar_w * p)
                empty = bar_w - filled
                bar = "█" * filled + "░" * empty
                bar_color = "dodger_blue2"
                status = "处理中"
                status_color = "dodger_blue2"
                name_color = "white"
            else:
                bar = "░" * bar_w
                bar_color = "grey50"
                status = "待做"
                status_color = "dim"
                name_color = "dim"

            row = Text()
            row.append(_pad_width(str(i), 4), style="dim")
            row.append(_pad_width(name, 36), style=name_color)
            row.append(_pad_width(f"[{bar}]", 22), style=bar_color)
            row.append(_pad_width(status, 6), style=status_color)
            outer.add_row(row)

    # ── 底部 ──
    outer.add_row(Text(sep, style="dim"))
    footer = Text()
    footer.append(f"AI: {model_name}", style="dim italic")
    footer.append(" | ", style="dim")
    footer.append("Ctrl+C 停止", style="dim")
    outer.add_row(Align.center(footer))

    return Panel(
        outer,
        title=title,
        subtitle=subtitle,
        subtitle_align="center",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 2),
        width=term_w,
    )


def render_study_dashboard(slots, done_count, failed_count, total_count, refresh_hint, max_remain, max_remain_label, status_hint, total_progress=0, total_duration=0, learning_done_count=0, current_page=1, total_pages=1, page_size=10):
    """渲染学习仪表盘 - 紧凑表格版（修复中文对齐，自动轮播翻页）"""
    import time

    term_width = min(console.width or 80, 80)
    inner_width = term_width - 6

    # 标题栏状态 - 显示上报成功/上报失败/总数
    status_parts = []
    status_parts.append(f"[green]✓{done_count}[/green]")
    status_parts.append(f"[red]✗{failed_count}[/red]")
    status_parts.append(f"[white]/{total_count}[/white]")
    if refresh_hint:
        status_parts.append(f"[dim]{refresh_hint}[/dim]")

    title = Text("学习仪表盘", style="bold white")
    subtitle = Text.from_markup(" ".join(status_parts))

    # 外层表格 - 单列布局
    outer = Table(
        show_header=False,
        box=None,
        padding=0,
        collapse_padding=True,
        width=inner_width,
    )
    outer.add_column(justify="left")

    # 表头分隔线长度（提前定义供顶部统计信息使用）
    sep = "─" * (inner_width - 2)

    # 顶部统计信息 - 紧凑一行（左侧进度，右侧预计完成时长）
    if total_count > 0 and slots:
        completed_count = learning_done_count
        remaining_count = total_count - learning_done_count

        left_text = f"进度: {completed_count}/{total_count} 完成 | 剩余 {remaining_count} | 总时长 {_fmt_duration(total_duration)}"
        if total_pages > 1:
            left_text += f"  (第{current_page}/{total_pages}页)"
        right_text = f"预计完成 {_fmt_duration(max_remain)}" if max_remain > 0 else ""

        stats = Text()
        stats.append(left_text, style="")
        if right_text:
            # 计算需要填充的空格数使右侧对齐到分割线
            pad_len = max(1, len(sep) - _str_width(left_text) - _str_width(right_text))
            stats.append(" " * pad_len, style="")
            stats.append(right_text, style="dim cyan")
        outer.add_row(stats)
        outer.add_row("")

    # 表头分隔线
    outer.add_row(Text(sep, style="dim"))

    # 表头 - 使用固定显示宽度
    header = Text()
    header.append(_pad_width("#", 4), style="bold dim")
    header.append(_pad_width("视频名称", 30), style="bold dim")
    header.append(_pad_width("时长", 10), style="bold dim")
    header.append(_pad_width("进度", 22), style="bold dim")
    header.append(_pad_width("状态", 6), style="bold dim")
    outer.add_row(header)
    outer.add_row(Text(sep, style="dim"))

    if not slots:
        if total_count > 0:
            outer.add_row(Text("  (全部完成!)", style="bold green"))
        else:
            outer.add_row(Text("  (等待启动...)", style="dim"))
    else:
        global_offset = (current_page - 1) * page_size
        for i, slot in enumerate(slots, 1):
            global_idx = global_offset + i
            name = slot['video_name']
            # 按显示宽度截断，中文算2
            if _str_width(name) > 28:
                name = _truncate_width(name, 28)

            dur = _fmt_duration(slot['duration'])
            total = slot['viewed'] + slot['total_time']
            vid_dur = slot['duration']
            pct = (total / vid_dur) if vid_dur > 0 else 0

            # 进度条
            bar_w = 18
            if slot['failed']:
                bar = "-" * bar_w
                bar_color = "dim"
                status = "失败"
                status_color = "red"
                name_color = "dim"
            elif slot['done'] or total >= vid_dur or pct >= 0.99:
                bar = "█" * bar_w
                bar_color = "green"
                status = "完成"
                status_color = "green"
                name_color = "white"
                pct = 1.0
            else:
                filled = int(bar_w * pct)
                empty = bar_w - filled
                bar = "█" * filled + "░" * empty
                bar_color = _pct_color_rich(pct)
                status = f"{int(pct * 100)}%"
                status_color = bar_color
                name_color = "white"

            row = Text()
            row.append(_pad_width(str(global_idx), 4), style="dim")
            row.append(_pad_width(name, 30), style=name_color)
            row.append(_pad_width(dur, 10), style="yellow")
            row.append(_pad_width(f"[{bar}]", 22), style=bar_color)
            row.append(_pad_width(status, 6), style=status_color)
            outer.add_row(row)

    # 底部分隔线
    outer.add_row(Text(sep, style="dim"))

    # 底部总进度 - 使用调用方传入的 total_progress（基于所有视频）
    if total_count > 0:
        bar_w = 20
        filled = int(bar_w * total_progress)
        empty = bar_w - filled
        bar = "█" * filled + "░" * empty
        percentage = int(total_progress * 100)

        end_time_str = ""
        if max_remain > 0:
            end_time = time.localtime(time.time() + max_remain)
            end_time_str = time.strftime("%H:%M", end_time)

        left_str = f"总进度: [{bar}] {percentage}%"

        right_parts = []
        if end_time_str:
            right_parts.append(f"预计 {end_time_str} 结束")
        right_parts.append("Ctrl+C 停止")
        right_str = "  ".join(right_parts)

        total_content_width = _str_width(left_str) + _str_width(right_str)
        mid_pad = max(1, len(sep) - total_content_width)

        footer = Text()
        footer.append("总进度: ", style="white")
        footer.append(f"[{bar}]", style=_pct_color_rich(total_progress))
        footer.append(f" {percentage}%", style="bold")
        footer.append(" " * mid_pad, style="")
        if end_time_str:
            footer.append(f"预计 {end_time_str} 结束", style="dim cyan")
            footer.append("  ", style="")
        footer.append("Ctrl+C 停止", style="dim")
        outer.add_row(footer)

        # 分页信息（多页时显示）
        if total_pages > 1:
            page_info = Text()
            page_info.append(f"第 {current_page}/{total_pages} 页", style="dim")
            page_info.append(" (10秒自动翻页)", style="dim")
            outer.add_row(page_info)

    panel = Panel(
        outer,
        title=title,
        subtitle=subtitle,
        subtitle_align="center",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 2),
        width=term_width,
    )

    return panel


def render_account_menu(accounts, current_username, student_names=None):
    """渲染账号选择菜单 - 显示姓名，最后登录账号高亮"""
    term_width = min(console.width or 75, 75)
    inner_width = term_width - 6

    table = Table(show_header=False, box=None, padding=(0, 1), collapse_padding=True, width=inner_width)
    table.add_column(justify="left")

    student_names = student_names or {}

    for i, acc in enumerate(accounts, 1):
        last_login = acc.get("last_login", "从未登录")
        username = acc.get('username', '')
        student_name = student_names.get(username, '')

        if student_name:
            name_len = len(student_name)
            if name_len == 2:
                masked_name = student_name[0] + "*"
            elif name_len == 3:
                masked_name = student_name[0] + "*" + student_name[-1]
            elif name_len == 4:
                masked_name = student_name[0] + "**" + student_name[-1]
            else:
                masked_name = student_name[0] + "*" + student_name[-1] if name_len > 1 else student_name
            display_name = f"{username}-{masked_name}"
        else:
            display_name = username

        row = Text()
        idx_str = f"{i}.".ljust(4)
        if username == current_username:
            row.append(f"  {idx_str} {display_name}", style="bold green")
            row.append(f"  (最后登录: {last_login})", style="dim")
        else:
            row.append(f"  {idx_str} {display_name}", style="white")
        table.add_row(row)

    table.add_row("")
    left = Text()
    left.append("[N]", style="bold yellow")
    left.append(" 登录其他账号  ", style="white")
    left.append("[D]", style="bold yellow")
    left.append(" 删除账号  ", style="white")
    left.append("[R]", style="bold yellow")
    left.append(" 重新登录    ", style="white")
    left.append("[0]", style="bold red")
    left.append(" 退出程序", style="white")
    table.add_row(Align.center(left))

    panel = Panel(
        table,
        title="账号选择",
        subtitle=f"已保存 {len(accounts)} 个账号",
        subtitle_align="right",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 2),
        width=term_width,
    )
    return panel


def render_website_menu(websites, current_id, current_name):
    """渲染平台切换菜单"""
    table = Table(show_header=False, box=None, padding=(0, 1), expand=False, width=28)

    for idx, cfg in websites.items():
        name = cfg.get("name", "未知")
        row = Text()
        row.append(f"{idx}.", style="white")
        if idx == current_id:
            row.append(" [*]", style="green")
            row.append(f" {name}", style="green")
        else:
            row.append(" [ ]", style="dim")
            row.append(f" {name}", style="dim")
        table.add_row(Align.left(row))

    table.add_row("")
    table.add_row(Align.right(Text("[0] 返回主菜单", style="dim")))

    panel = Panel(
        table,
        title="切换学习平台",
        subtitle=f"当前: {current_name}",
        subtitle_align="right",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
        width=36,
    )
    return panel


def render_login_panel(website_name, website_url):
    """渲染登录界面"""
    table = Table(show_header=False, box=None, padding=(0, 1))

    table.add_row(Text("请按以下步骤登录:", style="bold white"))
    table.add_row("")
    table.add_row(Text("1. 打开浏览器，访问以下网址:", style="white"))
    table.add_row(Text(f"   {website_url}", style="bold cyan underline"))
    table.add_row("")
    table.add_row(Text("2. 在浏览器中完成登录", style="white"))
    table.add_row("")
    table.add_row(Text("3. 登录成功后，复制浏览器地址栏中的 URL", style="white"))
    table.add_row("")
    table.add_row(Text("4. 将复制的 URL 粘贴到下方输入框", style="white"))
    table.add_row("")
    table.add_row(Text("提示: URL 通常包含 token 或 session 信息", style="dim"))
    table.add_row(Text("      例如: http://...?token=xxx", style="dim"))
    table.add_row("")

    panel = Panel(
        table,
        title=f"登录到 {website_name}",
        title_align="center",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    return panel


def render_init_progress(step, total_steps, message, website_name=""):
    """渲染初始化进度界面"""
    table = Table(show_header=False, box=None, padding=(0, 1))

    table.add_row(Text(f"正在初始化账号... ({step}/{total_steps})", style="bold white"))
    table.add_row("")
    table.add_row(Text(message, style="white"))
    table.add_row("")

    # 进度条
    pct = step / total_steps if total_steps > 0 else 0
    bar_filled = int(30 * pct)
    bar = "█" * bar_filled + "░" * (30 - bar_filled)
    bar_text = Text()
    bar_text.append(f"[{bar}]", style="cyan")
    bar_text.append(f" {int(pct * 100)}%", style="bold white")
    table.add_row(Align.center(bar_text))

    panel = Panel(
        table,
        title=f"初始化 - {website_name}" if website_name else "初始化",
        title_align="center",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    return panel


def render_delete_account_menu(accounts, current_username='', student_names=None):
    """渲染删除账号菜单 —— 固定宽度，[0] 返回右对齐"""
    term_width = min(console.width or 65, 65)
    inner_width = term_width - 6

    table = Table(show_header=False, box=None, padding=(0, 1), collapse_padding=True, width=inner_width)
    table.add_column(justify="left")

    student_names = student_names or {}

    for i, acc in enumerate(accounts, 1):
        username = acc.get('username', '')
        last_login = acc.get("last_login", "从未登录")
        student_name = student_names.get(username, '')

        if student_name:
            name_len = len(student_name)
            if name_len == 2:
                masked_name = student_name[0] + "*"
            elif name_len == 3:
                masked_name = student_name[0] + "*" + student_name[-1]
            elif name_len >= 4:
                masked_name = student_name[0] + "**" + student_name[-1]
            display_name = f"{username}-{masked_name}"
        else:
            display_name = username

        row = Text()
        idx_str = f"{i}.".ljust(4)
        if username == current_username:
            row.append(f"  {idx_str} {display_name}", style="bold red")
            row.append(f"  (最后登录: {last_login})", style="dim")
        else:
            row.append(f"  {idx_str} {display_name}", style="white")
        table.add_row(row)

    table.add_row("")
    right = Text()
    right.append("[0]", style="bold red")
    right.append(" 返回", style="white")
    table.add_row(Align.right(right))

    panel = Panel(
        table,
        title="删除账号",
        subtitle=f"已保存 {len(accounts)} 个账号",
        subtitle_align="right",
        border_style="red",
        box=box.ROUNDED,
        padding=(1, 2),
        width=term_width,
    )
    return panel


def render_simple_menu(title, items, footer_buttons=None):
    """通用菜单渲染 - 紧凑版本

    items: list of str 或 list of (str, str) 元组 (text, style)
    footer_buttons: Text 对象或 None
    """
    # 进一步减小面板宽度，使其更加紧凑
    term_width = min(console.width or 60, 60)  # 最大宽度60，更加紧凑
    inner_width = min(term_width - 4, 56)
    
    # 使用 Table 布局实现左对齐效果
    table = Table(
        show_header=False, 
        box=None, 
        padding=(0, 1), 
        collapse_padding=True, 
        width=inner_width
    )
    table.add_column(justify="left")
    
    # 标题行 - 左对齐
    title_text = Text(title, style="bold white")
    table.add_row(title_text)
    
    # 内容项 - 左对齐，紧凑排列
    for item in items:
        if isinstance(item, tuple):
            text, style = item
            table.add_row(Text(text, style=style))
        else:
            table.add_row(Text(item, style="white"))
    
    if footer_buttons:
        # 直接添加返回按钮，不使用右对齐
        table.add_row(footer_buttons)
    
    # 组装 Panel - 紧凑版本，减少内边距
    panel = Panel(
        table,
        title=title,
        title_align="center",  # 标题居中
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 2),  # 减少上下内边距
        width=term_width,
    )
    return panel


def render_course_select_menu(courses, get_course_status_fn, study_records):
    """渲染课程选择菜单 - 用于 study_cli"""
    table = Table(show_header=False, box=None, padding=(0, 1))

    for i, course in enumerate(courses, 1):
        course_name = course.get('course_name', '未知课程')
        course_id = course.get('course_id', '未知ID')
        status = get_course_status_fn(course)

        display_progress = status['completion_rate']
        if course_name in study_records:
            course_info = study_records[course_name].get('course_info', {})
            if 'learning_progress' in course_info:
                display_progress = course_info['learning_progress']

        line = Text()
        line.append(f"  {i}. ", style="white")
        line.append(f"{course_name}", style="bold white")
        line.append(f" (ID: {course_id})", style="dim")
        table.add_row(line)

        sub = Text()
        sub.append("     完成率: ", style="dim")
        sub.append(f"{display_progress}", style="yellow")
        sub.append(" | 已完成: ", style="dim")
        sub.append(f"{status['completed']}/{status['total']}", style="green" if status['completed'] >= status['total'] else "yellow")
        table.add_row(sub)

    table.add_row("")
    buttons = Text()
    buttons.append("[0]", style="dim")
    buttons.append(" 返回", style="white")
    table.add_row(Align.right(buttons))

    panel = Panel(
        table,
        title="选择课程",
        title_align="center",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    return panel


def render_settings_menu(settings):
    """渲染学习设置菜单"""
    table = Table(show_header=False, box=None, padding=(0, 1))

    items = [
        (f"1. 模拟速度: {settings['simulation_speed']}x", "white"),
        (f"2. 心跳间隔: {settings['heartbeat_interval']}秒", "white"),
        (f"3. 上报间隔: {settings['report_interval']}秒", "white"),
    ]
    for text, style in items:
        # 高亮数值部分
        parts = text.split(": ")
        if len(parts) == 2:
            row = Text()
            row.append(parts[0] + ": ", style="white")
            row.append(parts[1], style="bold yellow")
            table.add_row(row)
        else:
            table.add_row(Text(text, style=style))

    table.add_row("")
    buttons = Text()
    buttons.append("[0]", style="dim")
    buttons.append(" 返回", style="white")
    table.add_row(Align.center(buttons))

    panel = Panel(
        table,
        title="学习设置",
        title_align="center",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    return panel


def render_task_summary(tasks, batch_num, total_batches, settings):
    """渲染任务确认界面"""
    table = Table(show_header=False, box=None, padding=(0, 1))

    total_duration = sum(task.duration for task in tasks)
    max_duration = max(task.duration for task in tasks) if tasks else 0

    info_items = [
        f"视频数量: {len(tasks)}个",
        f"总时长: {_fmt_duration(total_duration)} ({total_duration // 3600}h{total_duration % 3600 // 60}m)",
        f"最长视频: {_fmt_duration(max_duration)}",
        f"并发数: {len(tasks)}个",
        f"模拟速度: {settings['simulation_speed']}x",
        f"预计完成: {int(max_duration // (60 * settings['simulation_speed']))}.1分钟",
    ]

    for item in info_items:
        table.add_row(Text(f"  {item}", style="white"))

    panel = Panel(
        table,
        title=f"任务确认 (第{batch_num}批/共{total_batches}批)",
        title_align="center",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    return panel


def render_video_list_table(videos, course_name, get_video_progress_fn, study_records):
    """渲染视频列表 - 用于 study_cli"""
    table = Table(
        show_header=True,
        header_style="bold dim",
        box=None,
        padding=(0, 1),
        collapse_padding=True,
    )
    table.add_column("#", width=4, justify="right")
    table.add_column("视频", width=30, justify="left")
    table.add_column("时长", width=10, justify="right")
    table.add_column("进度条", width=22, justify="left")
    table.add_column("状态", width=8, justify="right")

    for i, video in enumerate(videos, 1):
        video_name = video.get('name', '未知视频')
        progress_info = get_video_progress_fn(course_name, video_name, study_records, video)
        viewed = progress_info['viewed']
        duration = progress_info['total']
        pct = int(viewed / duration * 100) if duration > 0 else 0

        bar_filled = int(18 * pct / 100)
        bar = "█" * bar_filled + "░" * (18 - bar_filled)

        if pct >= 100:
            status = Text("完成", style="bold green")
            bar_color = "green"
        else:
            status = Text(f"{pct}%", style="yellow")
            bar_color = "yellow"

        table.add_row(
            Text(str(i), style="dim"),
            Text(_truncate_width(video_name, 30), style="white"),
            Text(_fmt_duration(duration), style="yellow"),
            Text(f"[{bar}]", style=bar_color),
            status,
        )

    panel = Panel(
        table,
        title=f"{course_name} - 视频列表",
        title_align="center",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    return panel
