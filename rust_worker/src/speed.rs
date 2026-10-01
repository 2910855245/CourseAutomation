//! 刷课节奏档位 —— 用户在下单时选择的三档速度（暴力 / 适中 / 保守）
//!
//! 设计约束（不可突破的红线）：
//! 平台通过 `beginTime`/`finalTime` 的重叠数量识别并行刷课，历史记录显示阈值约 10 个
//! 并发（见 CHANGELOG 2026-05-24）。因此**任何档位**同时在推进的视频会话数都不得超过 8，
//! 暴力档只是取到这条上界，而不是无限制并发。
//!
//! 三档定位：
//!   - 暴力：同时推进 8 路视频会话、无启动等待 —— 最快，风控风险最高
//!   - 适中：默认档。4 路会话 + 每路启动错峰，速度与安全的平衡点
//!   - 保守（纯串行）：一节课刷完立即刷下一节，并发全为 1 是它唯一的收敛点。
//!     没有尾等待、没有长间隔、上报不加额外停顿 —— 串行本身已是最保守的形态，
//!     再靠"白等"凑时长只会白白拖慢订单（用户 2026-09-30 拍板）
//!
//! 落库标识沿用 turbo/balanced/gentle（历史订单与新前端不用迁移数据）。

use std::time::Duration;

use rand::RngExt;
use serde::{Deserialize, Serialize};

/// 并发上界：平台重叠检测阈值（约 10）之下的安全线
pub const MAX_COURSE_CONCURRENCY: usize = 8;

/// 并行档位的墙钟安全比率（保守档不用，见 [`SpeedProfile::wall_ratio`]）
const DEFAULT_WALL_RATIO: f64 = 2.1;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SpeedMode {
    /// 暴力档：全量并行，刷完立即衔接下一节
    Turbo,
    /// 适中档（默认）
    Balanced,
    /// 保守档：严格串行，一节课接一节课
    Gentle,
}

impl Default for SpeedMode {
    fn default() -> Self {
        SpeedMode::Balanced
    }
}

impl SpeedMode {
    /// 落库/传参用的稳定标识（数据库中已存在的老订单值为空 → 视为均衡）
    pub fn as_str(self) -> &'static str {
        match self {
            SpeedMode::Turbo => "turbo",
            SpeedMode::Balanced => "balanced",
            SpeedMode::Gentle => "gentle",
        }
    }

    /// 宽松解析：未知值一律回退均衡（向后兼容空串/历史脏数据）
    pub fn parse(s: &str) -> Self {
        match s.trim().to_lowercase().as_str() {
            "turbo" | "fast" | "extreme" => SpeedMode::Turbo,
            "gentle" | "slow" | "soft" => SpeedMode::Gentle,
            _ => SpeedMode::Balanced,
        }
    }

    /// 展示名（前端也可自行本地化，这里供接口/日志复用）
    pub fn label(self) -> &'static str {
        match self {
            SpeedMode::Turbo => "暴力档",
            SpeedMode::Balanced => "适中档",
            SpeedMode::Gentle => "保守档",
        }
    }

    /// 是否完全串行（一节课接一节课，任何环节都不并行）
    pub fn is_serial(self) -> bool {
        let p = self.profile();
        p.video_concurrency == 1 && p.scan_concurrency == 1
    }

    pub fn profile(self) -> SpeedProfile {
        match self {
            SpeedMode::Turbo => SpeedProfile {
                mode: self,
                video_concurrency: MAX_COURSE_CONCURRENCY,
                course_stagger_ms: 0,
                scan_concurrency: MAX_COURSE_CONCURRENCY,
                scan_jitter_ms: 100,
                report_extra_delay_ms: 0,
                report_extra_jitter_ms: 0,
                wall_ratio: DEFAULT_WALL_RATIO,
            },
            SpeedMode::Balanced => SpeedProfile {
                mode: self,
                video_concurrency: 4,
                course_stagger_ms: 500,
                scan_concurrency: 6,
                scan_jitter_ms: 800,
                report_extra_delay_ms: 0,
                report_extra_jitter_ms: 0,
                wall_ratio: DEFAULT_WALL_RATIO,
            },
            // 保守档：并发全为 1（真串行）+ 微小错峰；无尾等待、无长间隔、无上报停顿
            SpeedMode::Gentle => SpeedProfile {
                mode: self,
                video_concurrency: 1,
                course_stagger_ms: 3_000,
                scan_concurrency: 1,
                scan_jitter_ms: 3_000,
                report_extra_delay_ms: 0,
                report_extra_jitter_ms: 0,
                wall_ratio: 1.0,
            },
        }
    }
}

/// 档位展开后的一组引擎参数（创建任务时算一次，全流程复用）
#[derive(Debug, Clone, Copy)]
pub struct SpeedProfile {
    pub mode: SpeedMode,
    /// 同时在推进的视频会话数上限（平台重叠检测口径）。
    /// 刷课按"整单的视频池"调度：槽位满时新视频排队，与旧版"每课程一个槽位、
    /// 课程内部串行"相比，总时长趋近 总工作量 / 并发数，而不是被最长课程拖住。
    pub video_concurrency: usize,
    /// 任务启动间隔：刷课里是两条视频之间的错峰，扫描里是两门课程之间的错峰
    pub course_stagger_ms: u64,
    /// 同时扫描的课程数上限
    pub scan_concurrency: usize,
    /// 扫描单课程前的随机抖动上限（错峰首请求）
    pub scan_jitter_ms: u64,
    /// 每次上报前的额外固定间隔
    pub report_extra_delay_ms: u64,
    /// 额外间隔之上的随机抖动上限
    pub report_extra_jitter_ms: u64,
    /// 墙钟/时长比率：studyTime 报满后仍需把墙撑到 `比率 × 时长` 才算完成
    /// （防 beginTime/finalTime 跨度异常短于视频长度）。急速/均衡 2.1×；
    /// 保守档 1.0 —— 报满即收工、立即衔接下一节，不做尾等待。
    pub wall_ratio: f64,
}

impl SpeedProfile {
    /// 课程启动错峰：温和档在间隔上再加 ±50% 抖动，避免形成固定节奏
    pub async fn sleep_course_stagger(&self) {
        if self.course_stagger_ms == 0 {
            return;
        }
        let ms = if self.mode == SpeedMode::Gentle {
            let half = self.course_stagger_ms / 2;
            rand::rng().random_range(half..=self.course_stagger_ms + half)
        } else {
            self.course_stagger_ms
        };
        tokio::time::sleep(Duration::from_millis(ms)).await;
    }

    pub fn scan_jitter(&self) -> Duration {
        if self.scan_jitter_ms == 0 {
            return Duration::ZERO;
        }
        Duration::from_millis(rand::rng().random_range(0..=self.scan_jitter_ms))
    }
}

/// 请求前的档位节奏：先过全局限速门（所有任务共享 ≥0.5s），再叠加本档位的额外间隔。
///
/// 额外停顿只加不减 —— 这样同一进程里并行跑着的其它订单，其节奏不会被某个
/// 急速订单悄悄拖快（急速档的提速来自并发与错峰，而不是突破全局闸门）。
pub async fn pace(profile: &SpeedProfile) {
    crate::platform_client::wait_rate_limit().await;
    let jitter = if profile.report_extra_jitter_ms > 0 {
        rand::rng().random_range(0..=profile.report_extra_jitter_ms)
    } else {
        0
    };
    let extra = profile.report_extra_delay_ms + jitter;
    if extra > 0 {
        tokio::time::sleep(Duration::from_millis(extra)).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_fallback() {
        assert_eq!(SpeedMode::parse("turbo"), SpeedMode::Turbo);
        assert_eq!(SpeedMode::parse("TURBO"), SpeedMode::Turbo);
        assert_eq!(SpeedMode::parse("gentle"), SpeedMode::Gentle);
        // 空串与脏数据都回退均衡，保证老订单行为不变
        assert_eq!(SpeedMode::parse(""), SpeedMode::Balanced);
        assert_eq!(SpeedMode::parse("unknown"), SpeedMode::Balanced);
    }

    #[test]
    fn test_round_trip() {
        for m in [SpeedMode::Turbo, SpeedMode::Balanced, SpeedMode::Gentle] {
            assert_eq!(SpeedMode::parse(m.as_str()), m);
        }
    }

    #[test]
    fn test_profile_ordering() {
        let t = SpeedMode::Turbo.profile();
        let b = SpeedMode::Balanced.profile();
        let g = SpeedMode::Gentle.profile();
        // 暴力 快于 适中 快于 保守
        assert!(t.video_concurrency >= b.video_concurrency);
        assert!(b.video_concurrency >= g.video_concurrency);
        assert!(t.course_stagger_ms <= b.course_stagger_ms);
        assert!(b.course_stagger_ms <= g.course_stagger_ms);
        assert!(t.scan_concurrency >= g.scan_concurrency);
        assert!(t.report_extra_delay_ms <= g.report_extra_delay_ms);
        // 墙钟比率：保守档 1.0（无尾等待），并行档保留 2.1× 安全余量
        assert!(g.wall_ratio <= b.wall_ratio);
        assert!(b.wall_ratio <= t.wall_ratio);
    }

    #[test]
    fn test_conservative_mode_is_fully_serial() {
        // 保守档的卖点就是"一节课一节课来"：视频与扫描都必须串行
        let g = SpeedMode::Gentle.profile();
        assert_eq!(g.video_concurrency, 1, "保守档视频并发必须为 1");
        assert_eq!(g.scan_concurrency, 1, "保守档扫描并发必须为 1");
        assert!(SpeedMode::Gentle.is_serial());
        assert!(!SpeedMode::Balanced.is_serial());
        assert!(!SpeedMode::Turbo.is_serial());
    }

    #[test]
    fn test_serial_mode_has_no_tail_wait() {
        // 用户 2026-09-30 拍板：纯串行不为墙钟凑数 —— studyTime 报满立即收工，
        // 直接衔接下一节；长间隔与上报停顿同样去掉，"串行"只体现在并发为 1
        let g = SpeedMode::Gentle.profile();
        assert_eq!(g.wall_ratio, 1.0, "保守档报满即完成，无 2.1× 尾等待");
        assert_eq!(g.report_extra_delay_ms, 0);
        assert_eq!(g.report_extra_jitter_ms, 0);
        assert!(g.course_stagger_ms <= 5_000, "两节之间只留微小错峰，不做长等待");
        // 并行档位的安全余量不受影响
        assert!(SpeedMode::Turbo.profile().wall_ratio >= 2.0);
        assert!(SpeedMode::Balanced.profile().wall_ratio >= 2.0);
    }

    #[test]
    fn test_labels_are_new_wording() {
        assert_eq!(SpeedMode::Gentle.label(), "保守档");
        assert_eq!(SpeedMode::Balanced.label(), "适中档");
        assert_eq!(SpeedMode::Turbo.label(), "暴力档");
    }

    #[test]
    fn test_never_exceed_platform_ceiling() {
        // 红线：任何档位同时推进的视频会话都不得超过平台重叠检测安全线
        for m in [SpeedMode::Turbo, SpeedMode::Balanced, SpeedMode::Gentle] {
            let p = m.profile();
            assert!(p.video_concurrency <= MAX_COURSE_CONCURRENCY, "{:?}", m);
            assert!(p.video_concurrency >= 1);
            assert!(p.scan_concurrency >= 1 && p.scan_concurrency <= MAX_COURSE_CONCURRENCY);
        }
    }
}
