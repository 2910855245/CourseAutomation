//! 域名监控 — 定期抓取学校首页，解析各教学平台的「名称 + 域名」，
//! 与库里的 `platform_domains` 对比，变化则自动更新并**即时生效**（进程内缓存）。
//!
//! 为什么单独建表而不塞 system_config：域名是「一个平台多名（主域+镜像）」的结构，
//! system_config 的 upsert 无版本号、多写者会丢更新，主备唯一性也无处约束。
//! 监控元信息（首页地址 / 检测间隔 / 上次检测）仍是单写者，放 system_config。
//!
//! 已废弃域名：用户 2026-10-01 确认 `suwankj` 那条首页链接不再使用，只监控 3 个平台。

use std::collections::{HashMap, HashSet};
use std::sync::{Arc, OnceLock, RwLock};
use std::time::Duration;

use anyhow::{Context, Result};
use axum::extract::State;
use axum::routing::{get, post};
use axum::{Json, Router};
use rusqlite::params;
use serde::Serialize;
use serde_json::{json, Value};
use tokio::sync::Mutex as AsyncMutex;

use crate::db::Db;
use crate::platform_client as pc;
use crate::{logs, AppState};

// ── 配置键（system_config）────────────────────────────────────────────────
pub const CFG_URL: &str = "domain_monitor_url";
pub const CFG_INTERVAL_HOURS: &str = "domain_monitor_interval_hours";
pub const CFG_LAST_CHECK_MS: &str = "domain_monitor_last_check_ms";
pub const CFG_LAST_STATUS: &str = "domain_monitor_last_status";

pub const DEFAULT_URL: &str = "https://www.cdcas.edu.cn/";
pub const DEFAULT_INTERVAL_HOURS: i64 = 72;

/// 检测间隔允许范围（小时）：1 小时～30 天。防手滑写成 0 导致死循环抓取
const INTERVAL_MIN: i64 = 1;
const INTERVAL_MAX: i64 = 720;

/// 已知平台：id 语义与 `scan::platform_base_url` 一致（1/2/3 为学校三平台）。
/// 第三个字段是域名家族关键字 —— 域名换了家族认不出时，靠名字兜底。
const KNOWN: &[(i64, &str, &str)] = &[
    (1, "在线课程测评考试平台", "taiskeji"),
    (2, "劳动课程测评考试平台", "duxingkej"),
    (3, "公益课程平台", "chaoxiankeji"),
];

/// 首页上已废弃、不登记不监控的域名家族（用户 2026-10-01 确认 suwankj 没用）
const IGNORED_HOST_KEYWORDS: &[&str] = &["suwankj"];

// ── 进程内缓存 ───────────────────────────────────────────────────────────
//
// `list_platforms` 是**无鉴权公开接口**，读路径必须纯内存、同步、无 await ——
// 绝不能在请求路径里查 DB。写路径只在启动/检测完成后整体换掉 Arc，O(1)。

#[derive(Clone, Debug, PartialEq)]
pub struct PlatformDomain {
    pub website_id: i64,
    pub name: String,
    pub base_url: String,
}

static REGISTRY: OnceLock<RwLock<Arc<HashMap<i64, PlatformDomain>>>> = OnceLock::new();

fn registry() -> &'static RwLock<Arc<HashMap<i64, PlatformDomain>>> {
    REGISTRY.get_or_init(|| RwLock::new(Arc::new(HashMap::new())))
}

fn read_registry<T>(f: impl FnOnce(&HashMap<i64, PlatformDomain>) -> T) -> Option<T> {
    // 锁中毒时退化为「无缓存」，调用方会走静态兜底，不影响可用性
    let g = registry().read().ok()?;
    Some(f(&g))
}

/// 缓存里的平台 base_url（`scan::platform_base_url` 读取）。无缓存 → None
pub fn cached_base_url(website_id: i64) -> Option<String> {
    read_registry(|m| m.get(&website_id).map(|p| p.base_url.clone())).flatten()
}

/// 缓存里的平台显示名（`school_exam::list_platforms` 读取）。
///
/// 注意：**只用于界面显示**，不参与 cookie 落盘文件名 ——
/// 后者由 `session::platform_name_for_url` 按域名家族决定，
/// 改名绝不能让历史 cookie 失效（否则每次改名都要重登）。
pub fn cached_name(website_id: i64) -> Option<String> {
    read_registry(|m| m.get(&website_id).map(|p| p.name.clone())).flatten()
}

/// 从库里重载缓存（启动时、每次检测完成后调用）
pub async fn refresh_cache(db: &Db) -> Result<usize> {
    let pool = db.clone_pool();
    let res = tokio::task::spawn_blocking(move || -> Result<HashMap<i64, PlatformDomain>> {
        let conn = pool.get().context("获取连接失败")?;
        let mut stmt = conn.prepare(
            "SELECT website_id, platform_name, base_url FROM platform_domains
             WHERE is_primary = 1 AND website_id > 0",
        )?;
        let rows = stmt.query_map([], |r| {
            Ok(PlatformDomain {
                website_id: r.get(0)?,
                name: r.get(1)?,
                base_url: r.get(2)?,
            })
        })?;
        let mut m = HashMap::new();
        for row in rows {
            let p = row?;
            m.insert(p.website_id, p);
        }
        Ok(m)
    })
    .await
    .context("spawn_blocking 失败")?;

    let map = res?;
    let n = map.len();
    match registry().write() {
        Ok(mut g) => *g = Arc::new(map),
        Err(p) => *p.into_inner() = Arc::new(map),
    }
    Ok(n)
}

// ── 抓取 / 解析 ─────────────────────────────────────────────────────────

fn resolve_url(base: &str, href: &str) -> Option<String> {
    url::Url::parse(base).ok()?.join(href.trim()).ok().map(|u| u.to_string())
}

fn host_of(u: &str) -> Option<String> {
    url::Url::parse(u).ok()?.host_str().map(|h| h.to_lowercase())
}

/// 首页里的「教学平台」候选链接。首页其余链接（教务处 / 图书馆 / 新闻…）不管 ——
/// 三个平台名都带「平台」二字，据此过滤，避免把整站链接都当平台。
#[derive(Clone, Debug, PartialEq)]
pub struct HomeLink {
    pub name: String,
    pub url: String,
    pub host: String,
}

pub fn parse_home_links(base_url: &str, html: &str) -> Vec<HomeLink> {
    use scraper::{Html, Selector};

    let doc = Html::parse_document(html);
    let sel = Selector::parse("a[href]").unwrap();
    let mut out: Vec<HomeLink> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    for a in doc.select(&sel) {
        let href = a.value().attr("href").unwrap_or("").trim();
        if href.is_empty() || href.starts_with('#') {
            continue;
        }
        let name = a
            .text()
            .collect::<String>()
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ");
        if !name.contains("平台") {
            continue;
        }
        let Some(u) = resolve_url(base_url, href) else { continue };
        let Some(host) = host_of(&u) else { continue };
        if seen.insert(host.clone()) {
            out.push(HomeLink { name, url: u, host });
        }
    }
    out
}

/// 抓取学校首页。不跟随重定向：域名更换常表现为 301/302 跳新站，
/// 得看到跳转目标才能写进日志。最多手工跟 3 跳。
async fn fetch_homepage(url: &str) -> Result<(String, String)> {
    let client = pc::build_client(true, None);
    let mut target = url.to_string();
    let mut note = String::new();
    for _ in 0..4 {
        pc::wait_rate_limit().await;
        let resp = client
            .get(&target)
            .send()
            .await
            .with_context(|| format!("请求学校首页失败: {target}"))?;
        let status = resp.status().as_u16();
        if (300..400).contains(&status) {
            let loc = resp
                .headers()
                .get("location")
                .and_then(|v| v.to_str().ok())
                .map(|s| s.to_string());
            let Some(loc) = loc else {
                anyhow::bail!("首页返回 {status} 但无 Location 头");
            };
            let next = resolve_url(&target, &loc)
                .ok_or_else(|| anyhow::anyhow!("无法解析跳转地址 {loc}"))?;
            note = format!("{note} -> {next}");
            target = next;
            continue;
        }
        if status != 200 {
            anyhow::bail!("首页返回 HTTP {status}");
        }
        let bytes = resp.bytes().await.context("读取首页失败")?;
        // reqwest 未开 charset feature：首页若为 GB2312 会解出 U+FFFD，
        // 域名（ASCII）照样能解析，名称由 name_ok 护栏挡住不覆盖旧名
        return Ok((String::from_utf8_lossy(&bytes).to_string(), note));
    }
    anyhow::bail!("首页重定向次数过多")
}

// ── 匹配 ────────────────────────────────────────────────────────────────

pub fn is_ignored_host(host: &str) -> bool {
    let h = host.to_lowercase();
    IGNORED_HOST_KEYWORDS.iter().any(|k| h.contains(k))
}

/// 首页链接 → 系统平台 id。None = 未识别的链接（非教学平台），直接忽略不登记。
///
/// 优先级：域名家族 > 平台名。域名家族是硬身份（duxingkej 只可能是劳动平台），
/// 名字是软信息（首页文案可能改版/写错）；两者都认不出才算未识别。
pub fn match_platform(name: &str, host: &str) -> Option<i64> {
    let h = host.to_lowercase();
    for (id, _, kw) in KNOWN {
        if h.contains(kw) {
            return Some(*id);
        }
    }
    let n = name.trim();
    for (id, known, _) in KNOWN {
        if n == *known || n.contains(*known) {
            return Some(*id);
        }
    }
    None
}

/// 名称编码护栏：拿不到像样的中文名就保留旧名，别把乱码写进库
pub fn name_ok(name: &str) -> bool {
    !name.is_empty()
        && !name.contains('\u{FFFD}')
        && name.chars().any(|c| ('\u{4e00}'..='\u{9fff}').contains(&c))
}

fn default_name(website_id: i64) -> String {
    KNOWN
        .iter()
        .find(|(id, _, _)| *id == website_id)
        .map(|(_, n, _)| n.to_string())
        .unwrap_or_default()
}

/// 探测平台是否活着：GET {base}/user/index。无 cookie 时必然是登录页
/// （302/303 跳转，或 200 登录页），DNS 失败 / 5xx / 404 才算死。
async fn probe_alive(base_url: &str) -> (bool, String) {
    pc::wait_rate_limit().await;
    let client = pc::build_client(true, None);
    let url = format!("{}/user/index", base_url.trim_end_matches('/'));
    match client.get(&url).send().await {
        Ok(resp) => {
            let status = resp.status().as_u16();
            let alive = status == 200 || status == 302 || status == 303;
            (alive, format!("HTTP {status}"))
        }
        Err(e) => (false, pc::preview(&e.to_string(), 120)),
    }
}

// ── 库读写 ──────────────────────────────────────────────────────────────

#[derive(Clone, Debug)]
struct Row {
    website_id: i64,
    platform_name: String,
    host: String,
    base_url: String,
    is_primary: bool,
    reachable: i64,
    is_alias: bool,
}

impl Row {
    fn to_json(&self) -> Value {
        json!({
            "website_id": self.website_id,
            "name": self.platform_name,
            "host": self.host,
            "base_url": self.base_url,
            "is_primary": self.is_primary,
            "is_alias": self.is_alias,
            "reachable": self.reachable,
        })
    }
}

async fn load_rows(db: &Db) -> Result<Vec<Row>> {
    let pool = db.clone_pool();
    let res = tokio::task::spawn_blocking(move || -> Result<Vec<Row>> {
        let conn = pool.get().context("获取连接失败")?;
        let mut stmt = conn.prepare(
            "SELECT website_id, platform_name, host, base_url, is_primary, reachable, is_alias
             FROM platform_domains ORDER BY website_id, is_primary DESC, host",
        )?;
        let rows = stmt.query_map([], |r| {
            Ok(Row {
                website_id: r.get(0)?,
                platform_name: r.get(1)?,
                host: r.get(2)?,
                base_url: r.get(3)?,
                is_primary: r.get::<_, i64>(4)? != 0,
                reachable: r.get(5)?,
                is_alias: r.get::<_, i64>(6)? != 0,
            })
        })?;
        let mut out = Vec::new();
        for row in rows {
            out.push(row?);
        }
        Ok(out)
    })
    .await
    .context("spawn_blocking 失败")?;
    res
}

async fn cfg_get(db: &Db, key: &str) -> Option<String> {
    let pool = db.clone_pool();
    let key = key.to_string();
    tokio::task::spawn_blocking(move || {
        let conn = pool.get().ok()?;
        crate::queue::config_get_blocking(&conn, &key)
    })
    .await
    .ok()
    .flatten()
}

async fn cfg_get_i64(db: &Db, key: &str) -> Option<i64> {
    cfg_get(db, key).await.and_then(|v| v.trim().parse::<i64>().ok())
}

async fn cfg_set(db: &Db, key: &str, value: &str) {
    if let Err(e) = crate::queue::config_set(db, key, value).await {
        tracing::warn!(error = %e, key, "写域名监控配置失败");
    }
}

async fn interval_hours(db: &Db) -> i64 {
    cfg_get_i64(db, CFG_INTERVAL_HOURS)
        .await
        .filter(|h| (INTERVAL_MIN..=INTERVAL_MAX).contains(h))
        .unwrap_or(DEFAULT_INTERVAL_HOURS)
}

async fn monitor_url(db: &Db) -> String {
    let u = cfg_get(db, CFG_URL).await.unwrap_or_default();
    if u.trim().is_empty() {
        DEFAULT_URL.to_string()
    } else {
        u
    }
}

// ── 检测主流程 ──────────────────────────────────────────────────────────

#[derive(Serialize)]
struct Change {
    website_id: i64,
    kind: String,
    old: String,
    new: String,
}

struct WriteRow {
    website_id: i64,
    name: String,
    host: String,
    base_url: String,
    is_primary: bool,
    alive: bool,
}

struct Detected {
    website_id: i64,
    name: String,
    host: String,
    base_url: String,
    alive: bool,
}

static CHECK_LOCK: OnceLock<AsyncMutex<()>> = OnceLock::new();

fn check_lock() -> &'static AsyncMutex<()> {
    CHECK_LOCK.get_or_init(|| AsyncMutex::new(()))
}

/// 手动「立即检测」入口：占用中直接返回提示 —— 排队会变相连点、放大对学校站的请求
pub async fn trigger_manual(state: &AppState) -> Value {
    match check_lock().try_lock() {
        Ok(_g) => match run_check(state).await {
            Ok(v) => json!({"success": true, "message": "检测完成", "data": v}),
            Err(e) => json!({
                "success": false,
                "message": format!("检测失败：{e}"),
                "data": Value::Null,
            }),
        },
        Err(_) => json!({
            "success": false,
            "message": "已有检测正在进行，请稍后再试",
            "data": Value::Null,
        }),
    }
}

/// 抓首页 → 解析 → 匹配 → 探测 → 落库 → 刷新缓存 → 写日志，返回本次变更报告
pub async fn run_check(state: &AppState) -> Result<Value> {
    let url = monitor_url(&state.db).await;
    logs::info(logs::CAT_DOMAIN, "", "", format!("域名检测开始：抓取 {url}"));

    let (html, redirect_note) = match fetch_homepage(&url).await {
        Ok(v) => v,
        Err(e) => {
            let msg = e.to_string();
            logs::warn(logs::CAT_DOMAIN, "", "", format!("域名检测失败：{msg}"));
            cfg_set(&state.db, CFG_LAST_CHECK_MS, &logs::now_ms().to_string()).await;
            cfg_set(&state.db, CFG_LAST_STATUS, &format!("failed: {msg}")).await;
            return Err(e);
        }
    };
    if !redirect_note.is_empty() {
        logs::warn(logs::CAT_DOMAIN, "", "", format!("学校首页发生跳转：{redirect_note}"));
    }

    let mut errors: Vec<String> = Vec::new();
    let current = load_rows(&state.db).await.unwrap_or_default();

    // 解析 + 过滤已废弃域名 + 逐个匹配、探测。
    // 认不出的链接（教务/资产/学工等行政平台）不登记、不探测，只记一行汇总 ——
    // 后台只需要看到 3 个教学平台的真实域名，其余都是噪声。
    let mut detected: Vec<Detected> = Vec::new();
    let mut unrecognized: Vec<String> = Vec::new();
    for l in parse_home_links(&url, &html) {
        if is_ignored_host(&l.host) {
            logs::info(logs::CAT_DOMAIN, "", "", format!("忽略已废弃域名 {}（{}）", l.host, l.name));
            continue;
        }
        let Some(id) = match_platform(&l.name, &l.host) else {
            unrecognized.push(format!("{}（{}）", l.host, l.name));
            continue;
        };
        let (alive, note) = probe_alive(&l.url).await;
        if !alive {
            errors.push(format!("{} 探测失败（{note}）", l.host));
        }
        detected.push(Detected {
            website_id: id,
            name: l.name,
            host: l.host,
            base_url: l.url.trim_end_matches('/').to_string(),
            alive,
        });
    }
    if !unrecognized.is_empty() {
        logs::info(
            logs::CAT_DOMAIN,
            "",
            "",
            format!("未识别链接（已忽略，不登记）：{}", unrecognized.join("、")),
        );
    }

    if detected.is_empty() {
        let msg = "首页未解析到任何教学平台链接".to_string();
        logs::warn(logs::CAT_DOMAIN, "", "", &msg);
        cfg_set(&state.db, CFG_LAST_CHECK_MS, &logs::now_ms().to_string()).await;
        cfg_set(&state.db, CFG_LAST_STATUS, &format!("failed: {msg}")).await;
        anyhow::bail!(msg);
    }

    // ── 主备决策 ──
    // 防抖动：当前主域仍可达且仍在首页列表里 → 保持不动；
    // 只有它「从首页消失」或「不可达」时才切到某个可达的备用域。
    let mut changes: Vec<Change> = Vec::new();
    let mut write_rows: Vec<WriteRow> = Vec::new();
    let mut rebuilt_ids: Vec<i64> = Vec::new();

    for (id, _default, _) in KNOWN {
        let det: Vec<&Detected> = detected.iter().filter(|d| d.website_id == *id).collect();
        if det.is_empty() {
            logs::warn(
                logs::CAT_DOMAIN,
                "",
                "",
                format!("首页未找到平台 {id}（{}），保持现有域名不变", default_name(*id)),
            );
            continue;
        }
        let cur_primary = current
            .iter()
            .find(|r| r.website_id == *id && r.is_primary)
            .map(|r| r.host.clone());
        let primary = match &cur_primary {
            Some(h) if det.iter().any(|d| d.host == *h && d.alive) => h.clone(),
            _ => det
                .iter()
                .find(|d| d.alive)
                .map(|d| d.host.clone())
                .unwrap_or_else(|| det[0].host.clone()),
        };
        if let Some(old) = &cur_primary {
            if *old != primary {
                let new_name = det.iter().find(|d| d.host == primary).map(|d| d.name.clone());
                changes.push(Change {
                    website_id: *id,
                    kind: "primary".to_string(),
                    old: old.clone(),
                    new: primary.clone(),
                });
                logs::warn(
                    logs::CAT_DOMAIN,
                    "",
                    "",
                    format!("平台 {id} 主域切换：{old} -> {primary}（{}）", new_name.unwrap_or_default()),
                );
            }
        } else {
            changes.push(Change {
                website_id: *id,
                kind: "primary".to_string(),
                old: String::new(),
                new: primary.clone(),
            });
            logs::info(logs::CAT_DOMAIN, "", "", format!("平台 {id} 首次登记主域 {primary}"));
        }

        rebuilt_ids.push(*id);
        for d in det {
            let is_primary = d.host == primary;
            // 名称护栏：乱码不覆盖旧名（域名是 ASCII，仍正常更新）
            let mut name = d.name.clone();
            if !name_ok(&name) {
                name = current
                    .iter()
                    .find(|r| r.website_id == *id && r.host == d.host)
                    .map(|r| r.platform_name.clone())
                    .unwrap_or_else(|| default_name(*id));
                errors.push(format!("{} 名称疑似乱码，保留旧名", d.host));
                logs::warn(logs::CAT_DOMAIN, "", "", format!("{} 名称疑似乱码，保留旧名", d.host));
            } else if let Some(prev) = current.iter().find(|r| r.website_id == *id && r.host == d.host) {
                if prev.platform_name != name {
                    changes.push(Change {
                        website_id: *id,
                        kind: "name".to_string(),
                        old: prev.platform_name.clone(),
                        new: name.clone(),
                    });
                    logs::info(
                        logs::CAT_DOMAIN,
                        "",
                        "",
                        format!("平台 {id} 名称更正：{} -> {name}", prev.platform_name),
                    );
                }
            }
            write_rows.push(WriteRow {
                website_id: *id,
                name,
                host: d.host.clone(),
                base_url: d.base_url.clone(),
                is_primary,
                alive: d.alive,
            });
        }
    }

    // ── 落库（单事务）──
    let pool = state.db.clone_pool();
    let ts = crate::queue::now_str();
    let ids = rebuilt_ids.clone();
    let rows = write_rows;
    let res = tokio::task::spawn_blocking(move || -> Result<()> {
        let mut conn = pool.get().context("获取连接失败")?;
        let tx = conn.transaction()?;
        {
            // 已知平台整组重建：首页是唯一真源（旧主域若已从首页消失就该退场）
            let mut del_id = tx.prepare("DELETE FROM platform_domains WHERE website_id = ?1")?;
            let mut ins = tx.prepare(
                "INSERT INTO platform_domains
                    (website_id, platform_name, host, base_url, is_primary, reachable,
                     is_alias, last_checked_at, updated_at)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?8)
                 ON CONFLICT(website_id, host) DO UPDATE SET
                    platform_name = excluded.platform_name,
                    base_url = excluded.base_url,
                    is_primary = excluded.is_primary,
                    reachable = excluded.reachable,
                    is_alias = excluded.is_alias,
                    last_checked_at = excluded.last_checked_at,
                    updated_at = excluded.updated_at",
            )?;
            for id in &ids {
                del_id.execute(params![id])?;
            }
            // 清理历史遗留的待确认行（老版本检测写入的 website_id=0）
            tx.execute("DELETE FROM platform_domains WHERE website_id = 0", [])?;
            for r in &rows {
                ins.execute(params![
                    r.website_id,
                    r.name,
                    r.host,
                    r.base_url,
                    r.is_primary as i64,
                    if r.alive { 1i64 } else { 0i64 },
                    (!r.is_primary) as i64,
                    ts,
                ])?;
            }
        }
        tx.commit()?;
        Ok(())
    })
    .await
    .context("spawn_blocking 失败")?;
    res?;

    let n = refresh_cache(&state.db).await.unwrap_or(0);
    let report = json!({
        "ok": true,
        "homepage": url,
        "redirect": redirect_note,
        "detected": detected.iter().map(|d| json!({
            "website_id": d.website_id,
            "name": d.name,
            "host": d.host,
            "base_url": d.base_url,
            "alive": d.alive,
        })).collect::<Vec<_>>(),
        "changes": changes,
        "errors": errors,
        "cached_platforms": n,
    });
    logs::info_detail(
        logs::CAT_DOMAIN,
        "",
        "",
        format!(
            "域名检测完成：解析 {} 条链接，变更 {} 项，缓存 {n} 个平台",
            report["detected"].as_array().map(|a| a.len()).unwrap_or(0),
            report["changes"].as_array().map(|a| a.len()).unwrap_or(0),
        ),
        report.clone(),
    );
    cfg_set(&state.db, CFG_LAST_CHECK_MS, &logs::now_ms().to_string()).await;
    cfg_set(&state.db, CFG_LAST_STATUS, &format!("ok: {} 项变更", report["changes"].as_array().map(|a| a.len()).unwrap_or(0))).await;
    Ok(report)
}

// ── 定时循环 ────────────────────────────────────────────────────────────

/// 到期才抓（`domain_monitor_last_check_ms` 生效），且首次到期先等 60~180s 抖动 ——
/// 否则频繁重启部署会让每次启动都去打学校站点。
pub async fn monitor_loop(state: Arc<AppState>) {
    let mut first = true;
    loop {
        let interval = interval_hours(&state.db).await;
        let interval_ms = interval * 3_600_000;
        let last = cfg_get_i64(&state.db, CFG_LAST_CHECK_MS).await.unwrap_or(0);
        let now = logs::now_ms();
        if last > 0 && now < last + interval_ms {
            let remain = (last + interval_ms - now).max(1000) as u64;
            tokio::time::sleep(Duration::from_millis(remain.min(interval_ms as u64))).await;
            continue;
        }
        if first {
            first = false;
            let jitter = 60 + rand::random::<u64>() % 121;
            tokio::time::sleep(Duration::from_secs(jitter)).await;
            // 抖动期间可能已被手动检测回写 last_check，重新确认是否仍到期
            let last = cfg_get_i64(&state.db, CFG_LAST_CHECK_MS).await.unwrap_or(0);
            if last > 0 && logs::now_ms() < last + interval_ms {
                continue;
            }
        }
        let _g = check_lock().lock().await;
        if let Err(e) = run_check(&state).await {
            tracing::warn!(error = %e, "域名自动检测失败");
        }
    }
}

// ── HTTP 接口（挂在 api.rs 的 protected 组，随附管理员鉴权）──────────────

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/admin/domain-monitor", get(monitor_get))
        .route("/api/admin/domain-monitor/check", post(monitor_check))
        .route("/api/admin/domain-monitor/interval", post(monitor_set_interval))
}

async fn snapshot(state: &AppState) -> Value {
    let rows = load_rows(&state.db).await.unwrap_or_default();
    json!({
        "platforms": rows.iter().map(|r| r.to_json()).collect::<Vec<_>>(),
        "last_check": cfg_get_i64(&state.db, CFG_LAST_CHECK_MS).await.unwrap_or(0),
        "last_status": cfg_get(&state.db, CFG_LAST_STATUS).await.unwrap_or_default(),
        "interval_hours": interval_hours(&state.db).await,
        "monitor_url": monitor_url(&state.db).await,
    })
}

async fn monitor_get(State(state): State<AppState>) -> Json<Value> {
    Json(json!({"success": true, "message": "ok", "data": snapshot(&state).await}))
}

async fn monitor_check(State(state): State<AppState>) -> Json<Value> {
    Json(trigger_manual(&state).await)
}

#[derive(serde::Deserialize)]
struct IntervalReq {
    hours: i64,
}

async fn monitor_set_interval(
    State(state): State<AppState>,
    Json(req): Json<IntervalReq>,
) -> Json<Value> {
    let h = req.hours.clamp(INTERVAL_MIN, INTERVAL_MAX);
    match crate::queue::config_set(&state.db, CFG_INTERVAL_HOURS, &h.to_string()).await {
        Ok(_) => Json(json!({
            "success": true,
            "message": format!("检测间隔已设为 {h} 小时"),
            "data": {"interval_hours": h},
        })),
        Err(e) => Json(json!({
            "success": false,
            "message": format!("保存失败：{e}"),
            "data": Value::Null,
        })),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r##"
<html><body>
  <a href="https://cdcass.taiskeji.com/">在线课程测评考试平台</a>
  <a href="https://cdcas.duxingkej.com/">劳动课程测评考试平台</a>
  <a href="https://cdcas.chaoxiankeji.com/">公益课程平台</a>
  <a href="https://cdcas.suwankj.com">在线课程测评考试平台</a>
  <a href="/jwc/index.html">教务处</a>
  <a href="#">回到顶部</a>
</body></html>"##;

    #[test]
    fn test_parse_home_links_only_platforms() {
        let links = parse_home_links("https://www.cdcas.edu.cn/", SAMPLE);
        // 4 条平台链接被解析出来（suwankj 在后续过滤阶段剔除），教务处/锚点不算
        assert_eq!(links.len(), 4);
        assert_eq!(links[0].host, "cdcass.taiskeji.com");
        assert_eq!(links[0].name, "在线课程测评考试平台");
        assert!(is_ignored_host("cdcas.suwankj.com"));
        assert!(!is_ignored_host("cdcas.duxingkej.com"));
    }

    #[test]
    fn test_match_platform_host_first_then_name() {
        // 域名家族优先
        assert_eq!(match_platform("随便写的名字", "cdcas.duxingkej.com"), Some(2));
        // 家族认不出时靠名字（域名整体换家族的场景）
        assert_eq!(match_platform("公益课程平台", "newbrand.example.com"), Some(3));
        assert_eq!(match_platform("在线课程测评考试平台", "newbrand.example.com"), Some(1));
        // 都认不出 → 未识别，绝不静默归号
        assert_eq!(match_platform("某某平台", "unknown.example.com"), None);
    }

    #[test]
    fn test_name_guard_keeps_cjk_only() {
        assert!(name_ok("劳动课程测评考试平台"));
        assert!(!name_ok(""));
        assert!(!name_ok("\u{FFFD}\u{FFFD}\u{FFFD}"));
        assert!(!name_ok("taiskeji platform"));
    }

    #[test]
    fn test_resolve_relative_href() {
        assert_eq!(
            resolve_url("https://www.cdcas.edu.cn/", "//cdcas.suwankj.com").as_deref(),
            Some("https://cdcas.suwankj.com/")
        );
        assert_eq!(
            host_of("https://CDCASS.Taiskeji.com/").as_deref(),
            Some("cdcass.taiskeji.com")
        );
    }

    /// 缓存为空时必须回退到静态表，且学习通 id=4 绝不能落到平台 1 的兜底
    #[test]
    fn test_base_url_static_fallback() {
        if std::env::var("RUST_TEST_BASE_URL").is_ok() {
            return;
        }
        assert_eq!(crate::scan::platform_base_url(4), "https://mooc1.chaoxing.com");
        assert_eq!(crate::scan::platform_base_url(2), "https://cdcas.duxingkej.com");
        assert_eq!(crate::scan::platform_base_url(99), "https://cdcass.taiskeji.com");
    }

    /// E2E mock 平台的最高优先钩子不能被缓存/静态表削弱
    #[test]
    fn test_env_override_top_priority() {
        std::env::set_var("RUST_TEST_BASE_URL", "http://127.0.0.1:9/mock");
        assert_eq!(crate::scan::platform_base_url(1), "http://127.0.0.1:9/mock");
        assert_eq!(crate::scan::platform_base_url(4), "http://127.0.0.1:9/mock");
        std::env::remove_var("RUST_TEST_BASE_URL");
    }
}