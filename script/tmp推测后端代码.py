import json, sys
sys.stdout.reconfigure(encoding='utf-8')

print('='*80)
print('学校平台后端检测代码推测')
print('='*80)

print('''
// 推测的后端检测代码（基于数据分析）
// 这类平台通常是 PHP + ThinkPHP 或 Java + Spring

// =====================================================
// 文件: app/Service/CheatDetectService.php
// =====================================================

class CheatDetectService {

    // 配置阈值
    const PARALLEL_THRESHOLD = 60;      // 并行判定阈值（秒）
    const MIN_DURATION_RATIO = 0.5;     // 最小观看比例
    const MAX_DURATION_RATIO = 3.0;     // 最大观看比例（倍速检测）
    const MAX_VIEW_COUNT = 10;          // 最大观看次数
    const SUSPICIOUS_SCORE = 50;        // 可疑分数阈值

    /**
     * 检测单个视频学习记录是否可疑
     * 调用时机: 用户提交学习进度时 / 定时任务扫描
     */
    public function validateVideoRecord($record, $prevRecord = null) {
        $score = 0;
        $reasons = [];

        // ---- 检测维度1: 时间间隔（权重最高）----
        if ($prevRecord) {
            $gap = abs(strtotime($record['finalTime']) - strtotime($prevRecord['finalTime']));
            if ($gap < self::PARALLEL_THRESHOLD) {
                $score += 40;
                $reasons[] = "parallel: gap={$gap}s";
            }
        }

        // ---- 检测维度2: 观看时长比例 ----
        $videoDuration = $this->parseDuration($record['videoDuration']);
        $viewedDuration = $this->parseDuration($record['viewedDuration']);

        if ($videoDuration > 0) {
            $ratio = $viewedDuration / $videoDuration;

            if ($ratio < self::MIN_DURATION_RATIO) {
                $score += 30;
                $reasons[] = "skip: ratio=" . round($ratio, 2);
            } elseif ($ratio > self::MAX_DURATION_RATIO) {
                $score += 30;
                $reasons[] = "speed_up: ratio=" . round($ratio, 2);
            }
        }

        // ---- 检测维度3: 观看次数 ----
        if ($record['viewCount'] > self::MAX_VIEW_COUNT) {
            $score += 20;
            $reasons[] = "repeat: count={$record['viewCount']}";
        }

        // ---- 检测维度4: 时间跨度 ----
        $beginTime = strtotime($record['beginTime']);
        $finalTime = strtotime($record['finalTime']);
        $timeSpan = abs($finalTime - $beginTime);

        if ($timeSpan < $videoDuration) {
            $score += 10;
            $reasons[] = "impossible_timespan";
        }

        return [
            'score' => $score,
            'suspicious' => $score >= self::SUSPICIOUS_SCORE,
            'reasons' => $reasons
        ];
    }

    /**
     * 检测整个课程的学习记录
     */
    public function validateCourseRecords($records) {
        $suspiciousCount = 0;
        $totalScore = 0;
        $allReasons = [];

        // 按完成时间排序（重要！平台一定是先排序再检测）
        usort($records, function($a, $b) {
            return strtotime($a['finalTime']) - strtotime($b['finalTime']);
        });

        for ($i = 0; $i < count($records); $i++) {
            $prev = $i > 0 ? $records[$i-1] : null;
            $result = $this->validateVideoRecord($records[$i], $prev);

            if ($result['suspicious']) {
                $suspiciousCount++;
            }
            $totalScore += $result['score'];
            $allReasons = array_merge($allReasons, $result['reasons']);
        }

        // 课程级别判定
        $parallelRate = count($records) > 0
            ? $suspiciousCount / count($records) * 100
            : 0;

        return [
            'total_videos' => count($records),
            'suspicious_count' => $suspiciousCount,
            'parallel_rate' => round($parallelRate, 1),
            'total_score' => $totalScore,
            'is_cheating' => $parallelRate > 50 || $totalScore > 1000,
            'reasons' => array_unique($allReasons)
        ];
    }

    private function parseDuration($str) {
        $parts = explode(':', $str);
        if (count($parts) == 3) {
            return intval($parts[0]) * 3600 + intval($parts[1]) * 60 + intval($parts[2]);
        }
        if (count($parts) == 2) {
            return intval($parts[0]) * 60 + intval($parts[1]);
        }
        return 0;
    }
}
''')

print('\n' + '='*80)
print('【数据库表结构推测】')
print('='*80)

print('''
-- 学习记录表（已有，API返回的字段就是表结构）
CREATE TABLE study_node_record (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    course_id INT NOT NULL,
    node_id INT NOT NULL,           -- 视频ID
    chapter_id INT NOT NULL,
    begin_time DATETIME,            -- 开始学习时间
    final_time DATETIME,            -- 完成时间
    video_duration VARCHAR(20),     -- 视频时长 HH:MM:SS
    duration INT,                   -- 视频时长（秒）
    viewed_duration VARCHAR(20),    -- 已观看时长 HH:MM:SS
    view_count INT DEFAULT 1,       -- 观看次数
    progress DECIMAL(5,2),          -- 进度 0.00-1.00
    error INT DEFAULT 0,            -- 错误标记
    error_message TEXT,
    bid VARCHAR(50),                -- 学习记录唯一标识
    school_id INT,
    ip VARCHAR(45),                 -- 记录IP（可能不返回给前端）
    user_agent TEXT,                -- 浏览器UA（可能不返回给前端）
    created_at DATETIME,
    updated_at DATETIME,
    INDEX idx_user_course (user_id, course_id),
    INDEX idx_final_time (final_time)
);

-- 风控标记表（推测存在）
CREATE TABLE cheat_flags (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    course_id INT,
    node_id INT,
    flag_type VARCHAR(50),          -- parallel / speed_up / skip / repeat
    score INT DEFAULT 0,
    detail JSON,                    -- 详细信息
    status TINYINT DEFAULT 0,       -- 0=待处理 1=已确认 2=已忽略
    created_at DATETIME,
    INDEX idx_user (user_id),
    INDEX idx_status (status)
);
''')

print('\n' + '='*80)
print('【检测流程推测】')
print('='*80)

print('''
                    用户观看视频
                         |
                         v
            ┌---------------------------┐
            |  前端定时上报学习进度       |
            |  POST /user/node/progress  |
            |  每30秒上报一次            |
            └---------------------------┘
                         |
                         v
            ┌---------------------------┐
            |  后端接收并存储记录         |
            |  更新 study_node_record   |
            |  记录 viewed_duration     |
            |  记录 view_count          |
            └---------------------------┘
                         |
                         v
            ┌---------------------------┐
            |  触发检测（两种方式）       │
            |  1. 实时: 上报时立即检测    │
            |  2. 定时: cron定时扫描     │
            └---------------------------┘
                         |
                         v
        ┌-----------------------------------┐
        |  检测维度1: 时间间隔 (权重40)       |
        |                                   |
        |  SELECT prev.final_time,          |
        |         curr.final_time           |
        |  FROM study_node_record curr      |
        |  LEFT JOIN study_node_record prev  |
        |    ON prev.user_id = curr.user_id |
        |    AND prev.course_id = curr.course_id |
        |    AND prev.final_time < curr.final_time |
        |  WHERE ABS(curr.final_time - prev.final_time) < 60 |
        |                                   |
        |  命中 → score += 40              |
        └-----------------------------------┘
                         |
                         v
        ┌-----------------------------------┐
        |  检测维度2: 观看比例 (权重30)       |
        |                                   |
        |  ratio = viewed_duration / video_duration |
        |                                   |
        |  if ratio < 0.5:  跳过/快进       |
        |  if ratio > 3.0:  倍速播放        |
        |                                   |
        |  命中 → score += 30              |
        └-----------------------------------┘
                         |
                         v
        ┌-----------------------------------┐
        |  检测维度3: 观看次数 (权重20)       |
        |                                   |
        |  if view_count > 10:              |
        |    score += 20                    |
        └-----------------------------------┘
                         |
                         v
        ┌-----------------------------------┐
        |  综合判定                          |
        |                                   |
        |  并行率 = 可疑视频数 / 总视频数     |
        |                                   |
        |  if 并行率 > 50%:                 |
        |    标记为作弊，存入 cheat_flags    |
        |                                   |
        |  if 总分 > 2000: 封号             |
        |  if 总分 > 1000: 警告             |
        |  if 总分 > 500:  标记监控          |
        └-----------------------------------┘
                         |
                         v
            ┌---------------------------┐
            |  执行处罚                  │
            |  - 写入 cheat_flags 表    │
            |  - 发送警告通知            │
            |  - 封禁账号               │
            |  - 清空学习记录            │
            └---------------------------┘
''')

print('='*80)
print('【关键推测依据】')
print('='*80)

print('''
1. 为什么推测时间间隔阈值是60秒?
   - 数据中1185个并行对，最大间隔59秒
   - 60秒是一个天然的分界线（1分钟）
   - 正常用户不可能在60秒内看完一个3-20分钟的视频

2. 为什么推测观看比例阈值是0.5和3.0?
   - 57.1%的视频比例在0.95-1.05之间（正常）
   - 比例<0.5意味着没看一半就完成（跳过）
   - 比例>3.0意味着看了3倍时长（倍速或多刷）
   - 数据中确实有216个视频比例>5.0（极异常）

3. 为什么推测观看次数阈值是10?
   - 98.5%的视频观看次数<10次
   - 正常用户最多重复看2-3次
   - 超过10次基本是刷次数

4. 为什么推测是加权评分而不是单一判定?
   - 单一指标容易误判
   - 多维度综合判定更准确
   - 这是风控系统的通用做法
''')
