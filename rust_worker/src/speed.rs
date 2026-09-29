//! 刷课节奏档位 —— 用户在下单时选择的三档速度（急速 / 均衡 / 温柔）
//!
//! 设计约束（不可突破的红线）：
//! 平台通过 `beginTime`/`finalTime` 的重叠数量识别并行刷课，历史记录显示阈值约 10 个
//! 并发（见 CHANGELOG 2026-05-24）。因此**任何档位**的课程并发上限都不得超过 8，
//! 急速档只是取到这条上界，而不是无限制并发。
//!
//! 三档定位：
//!   - 急速：课程全量并行（8）、课程间零等待、不做人工错峰 —— 最快，风控风险略高
//!   - 均衡：默认档。中等并发（4）+ 适度错峰，速度与安全的平衡点
//!   - 温柔：单课程串行、课程之间长间隔错峰、每次上报额外随机停顿 —— 最慢，最像真人

use std::time::Duration;

use rand::RngExt;
use serde::{Deserialize, Serialize};

/// 并发上界：平台重叠检测阈值（约 10）之下的安全线
pub const MAX_COURSE_CONCURRENCY: usize = 8;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SpeedMode {
    /// 急速模式：全量并行，刷完立即衔接下一节
    Turbo,
    /// 均衡模式（默认）
    Balanced,
    /// 温柔模式：时间拉长、尽量错开
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
            SpeedMode::Turbo => "急速模式",
            SpeedMode::Balanced => "均衡模式",
            SpeedMode::Gentle => "温柔模式",
        }
    }

    pub fn profile(self) -> SpeedProfile {
        match self {
            SpeedMode::Turbo => SpeedProfile {
                mode: self,
                course_concurrency: MAX_COURSE_CONCURRENCY,
                course_stagger_ms: 0,
                scan_concurrency: MAX_COURSE_CONCURRENCY,
                scan_jitter_ms: 100,
                report_extra_delay_ms: 0,
                report_extra_jitter_ms: 0,
            },
            SpeedMode::Balanced => SpeedProfile {
                mode: self,
                course_concurrency: 4,
                course_stagger_ms: 500,
                scan_concurrency: 6,
                scan_jitter_ms: 800,
                report_extra_delay_ms: 0,
                report_extra_jitter_ms: 0,
            },
            SpeedMode::Gentle => SpeedProfile {
                mode: self,
                course_concurrency: 1,
                course_stagger_ms: 20_000,
                scan_concurrency: 2,
                scan_jitter_ms: 3_000,
                report_extra_delay_ms: 1_500,
                report_extra_jitter_ms: 5_000,
            },
        }
    }
}

/// 档位展开后的一组引擎参数（创建任务时算一次，全流程复用）
#[derive(Debug, Clone, Copy)]
pub struct SpeedProfile {
    pub mode: SpeedMode,
    /// 同时在刷的课程数上限（每课程内部仍串行）
    pub course_concurrency: usize,
    /// 课程任务之间的启动间隔
    pub course_stagger_ms: u64,
    /// 同时扫描的课程数上限
    pub scan_concurrency: usize,
    /// 扫描单课程前的随机抖动上限（错峰首请求）
    pub scan_jitter_ms: u64,
    /// 每次上报前的额外固定间隔
    pub report_extra_delay_ms: u64,
    /// 额外间隔之上的随机抖动上限
    pub report_extra_jitter_ms: u64,
}

impl SpeedProfile {
    /// 课程启动错峰：温柔档在长间隔上再加 ±50% 抖动，避免形成固定节奏
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
        // 急速 快于 均衡 快于 温柔
        assert!(t.course_concurrency >= b.course_concurrency);
        assert!(b.course_concurrency >= g.course_concurrency);
        assert!(t.course_stagger_ms <= b.course_stagger_ms);
        assert!(b.course_stagger_ms <= g.course_stagger_ms);
        assert!(t.scan_concurrency >= g.scan_concurrency);
        assert!(t.report_extra_delay_ms <= g.report_extra_delay_ms);
    }

    #[test]
    fn test_never_exceed_platform_ceiling() {
        // 红线：任何档位的课程并发都不得超过平台重叠检测安全线
        for m in [SpeedMode::Turbo, SpeedMode::Balanced, SpeedMode::Gentle] {
            let p = m.profile();
            assert!(p.course_concurrency <= MAX_COURSE_CONCURRENCY, "{:?}", m);
            assert!(p.course_concurrency >= 1);
            assert!(p.scan_concurrency >= 1 && p.scan_concurrency <= MAX_COURSE_CONCURRENCY);
        }
    }
}
