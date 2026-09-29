//! 后台「支付收款」页的 YPay 管理接口。
//!
//! 对接契约来源（前端，未修改）：
//!   - frontend/src/api/index.ts 的 `ypay:` 段（路径/方法/请求体字段）
//!   - frontend/src/composables/useYpayAdmin.ts / usePayments.ts（响应字段）
//!
//! 本模块只补齐此前从未注册、点了必然 404 的这组路由：
//!   accounts(CRUD) / channel-test / app-qrcode / orders / clear-orders /
//!   close-expired / pay-test create+check / diagnose / reset-connection
//!
//! 硬约束：
//! - 由 api.rs 的 protected 分组 merge，自动带管理员 Bearer 鉴权；不动中间件/AppState。
//! - 响应统一 `{success, message, data}`，不使用历史 `code` 字段。
//! - 本项目**没有**真实渠道协议，也**没有**手机 APP 心跳/会话存储：
//!   凡无法证实的检查项一律 `ok=false` + `level=pending/unsupported` 并在 msg 说明，
//!   绝不返回假成功（见 channel_test / diagnose / reset_connection）。
//! - 所有 SQL 参数化；表名列名严格取自 schema.rs（不新增/不 ALTER 列）。

use std::collections::HashMap;

use axum::extract::{Path, Query, State};
use axum::routing::{get, post, put};
use axum::{Json, Router};
use serde_json::{json, Map, Value};

use crate::AppState;

/// 支付收款后台管理路由（由 api.rs 的 protected 分组 merge）。
pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/ypay/accounts", get(accounts_list).post(accounts_create))
        .route(
            "/api/ypay/accounts/{id}",
            put(accounts_update).delete(accounts_delete),
        )
        .route("/api/ypay/channel-test/{id}", post(channel_test))
        .route("/api/ypay/app-qrcode", get(app_qrcode))
        .route("/api/ypay/orders", get(orders_list))
        .route("/api/ypay/clear-orders", post(clear_orders))
        .route("/api/ypay/close-expired", post(close_expired))
        .route("/api/ypay/pay-test/create/{id}", post(pay_test_create))
        .route("/api/ypay/pay-test/check/{batch_id}", get(pay_test_check))
        // 前端 api/index.ts 用 GET，任务描述写 POST —— 两种都注册，避免方法不一致 405。
        .route("/api/ypay/diagnose", get(diagnose).post(diagnose))
        .route("/api/ypay/reset-connection", post(reset_connection))
}

// ── 通用 ────────────────────────────────────────────────────────────────

/// 统一成功/失败响应（与 api.rs 现有 handler 同形）。
fn ok(data: Value) -> Json<Value> {
    Json(json!({"success": true, "message": "ok", "data": data}))
}
fn ok_msg(message: &str, data: Value) -> Json<Value> {
    Json(json!({"success": true, "message": message, "data": data}))
}
fn err(message: &str) -> Json<Value> {
    Json(json!({"success": false, "message": message}))
}

/// 后台审计日志（对齐 api.rs::log_event，operator='admin'）。
fn log_admin(conn: &rusqlite::Connection, event_type: &str, detail: &str) -> rusqlite::Result<()> {
    let log_id = format!("LOG-{:08X}", rand::random::<u32>());
    conn.execute(
        "INSERT INTO audit_logs (log_id, event_type, operator, detail, order_id, user_id, created_at)
         VALUES (?1, ?2, 'admin', ?3, '', '', ?4)",
        rusqlite::params![log_id, event_type, detail, crate::queue::now_str()],
    )?;
    Ok(())
}

/// 取字符串字段（去首尾空白，缺失→空串）
fn sval(m: &Map<String, Value>, k: &str) -> String {
    m.get(k)
        .and_then(|v| v.as_str())
        .map(|s| s.trim().to_string())
        .unwrap_or_default()
}

/// 取整数字段（缺失→None）
fn ival(m: &Map<String, Value>, k: &str) -> Option<i64> {
    m.get(k).and_then(|v| {
        v.as_i64()
            .or_else(|| v.as_str().and_then(|s| s.trim().parse::<i64>().ok()))
    })
}

// ── ypay_account：行 → JSON ─────────────────────────────────────────────
//
// 字段集与前端编辑弹窗一一对应（openEditAccount 会回填这些字段）。
// 该接口仅管理员可达（protected 分组 Bearer 鉴权）；私钥/cookie 属可编辑配置，
// 需原样回填给管理员，故不做脱敏。
const ACCOUNT_COLS: &str = "id, type, code, name, status, is_status, qr_url, zfb_pid, alipay_appid,
     alipay_public_key, alipay_private_key, cookie, wx_guid, qq, cloud_id,
     qr_type, memo, remark, channel_mode, app_public_cert, alipay_public_cert,
     alipay_root_cert, create_time";

fn account_row_to_json(r: &rusqlite::Row) -> rusqlite::Result<Value> {
    Ok(json!({
        "id": r.get::<_, i64>(0)?,
        "type": r.get::<_, Option<String>>(1)?.unwrap_or_default(),
        "code": r.get::<_, Option<String>>(2)?.unwrap_or_default(),
        "name": r.get::<_, Option<String>>(3)?.unwrap_or_default(),
        "status": r.get::<_, i64>(4)?,
        "is_status": r.get::<_, i64>(5)?,
        "qr_url": r.get::<_, Option<String>>(6)?.unwrap_or_default(),
        "zfb_pid": r.get::<_, Option<String>>(7)?.unwrap_or_default(),
        "alipay_appid": r.get::<_, Option<String>>(8)?.unwrap_or_default(),
        "alipay_public_key": r.get::<_, Option<String>>(9)?.unwrap_or_default(),
        "alipay_private_key": r.get::<_, Option<String>>(10)?.unwrap_or_default(),
        "cookie": r.get::<_, Option<String>>(11)?.unwrap_or_default(),
        "wx_guid": r.get::<_, Option<String>>(12)?.unwrap_or_default(),
        "qq": r.get::<_, Option<String>>(13)?.unwrap_or_default(),
        "cloud_id": r.get::<_, Option<String>>(14)?.unwrap_or_default(),
        "qr_type": r.get::<_, Option<String>>(15)?.unwrap_or_default(),
        "memo": r.get::<_, Option<String>>(16)?.unwrap_or_default(),
        "remark": r.get::<_, Option<String>>(17)?.unwrap_or_default(),
        "channel_mode": r.get::<_, i64>(18)?,
        "app_public_cert": r.get::<_, Option<String>>(19)?.unwrap_or_default(),
        "alipay_public_cert": r.get::<_, Option<String>>(20)?.unwrap_or_default(),
        "alipay_root_cert": r.get::<_, Option<String>>(21)?.unwrap_or_default(),
        "create_time": r.get::<_, Option<String>>(22)?.unwrap_or_default(),
    }))
}

fn load_account(conn: &rusqlite::Connection, id: i64) -> rusqlite::Result<Option<Value>> {
    conn.query_row(
        &format!("SELECT {ACCOUNT_COLS} FROM ypay_account WHERE id=?1 AND deleted_at IS NULL"),
        rusqlite::params![id],
        account_row_to_json,
    )
    .map(Some)
    .or_else(|e| match e {
        rusqlite::Error::QueryReturnedNoRows => Ok(None),
        other => Err(other),
    })
}

/// 可更新的字符串列 / 整数列（白名单，杜绝列名注入）
const ACC_STR_COLS: &[&str] = &[
    "type", "code", "name", "qr_url", "zfb_pid", "alipay_appid", "alipay_public_key",
    "alipay_private_key", "cookie", "wx_guid", "qq", "cloud_id", "qr_type", "memo", "remark",
    "app_public_cert", "alipay_public_cert", "alipay_root_cert",
];
const ACC_INT_COLS: &[&str] = &["status", "is_status", "channel_mode"];

// ── GET /api/ypay/accounts ──────────────────────────────────────────────

async fn accounts_list(State(state): State<AppState>) -> Json<Value> {
    let pool = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = pool.get()?;
        let mut stmt = conn.prepare(&format!(
            "SELECT {ACCOUNT_COLS} FROM ypay_account WHERE deleted_at IS NULL \
             ORDER BY create_time DESC, id DESC"
        ))?;
        let rows: Vec<Value> = stmt
            .query_map([], account_row_to_json)?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        Ok(Value::Array(rows))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => ok(data),
        Err(e) => err(&e.to_string()),
    }
}

// ── POST /api/ypay/accounts ─────────────────────────────────────────────

async fn accounts_create(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    let Some(m) = body.as_object() else {
        return err("请求体必须是 JSON 对象");
    };
    let type_ = sval(m, "type");
    let name = sval(m, "name");
    if type_ != "wxpay" && type_ != "alipay" {
        return err("通道类型非法（仅支持 wxpay / alipay）");
    }
    if name.is_empty() {
        return err("通道名称不能为空");
    }
    let code = sval(m, "code");
    let channel_mode = ival(m, "channel_mode").unwrap_or(1);
    // 所有字段先取成 owned，避免把借用的 body 引用移进 'static 闭包
    let f = |k: &str| sval(m, k);
    let (qr_url, zfb_pid, alipay_appid) = (f("qr_url"), f("zfb_pid"), f("alipay_appid"));
    let (alipay_public_key, alipay_private_key) = (f("alipay_public_key"), f("alipay_private_key"));
    let (cookie, wx_guid, qq, cloud_id) = (f("cookie"), f("wx_guid"), f("qq"), f("cloud_id"));
    let (qr_type, memo, remark) = (f("qr_type"), f("memo"), f("remark"));
    let (app_cert, ali_cert, root_cert) =
        (f("app_public_cert"), f("alipay_public_cert"), f("alipay_root_cert"));
    let pool = state.db.clone_pool();
    let detail = format!("新增支付通道 type={type_} code={code} name={name}");
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<i64> {
        let conn = pool.get()?;
        conn.execute(
            "INSERT INTO ypay_account
             (type, code, name, status, is_status, qr_url, zfb_pid, alipay_appid,
              alipay_public_key, alipay_private_key, cookie, wx_guid, qq, cloud_id,
              qr_type, memo, remark, channel_mode, app_public_cert, alipay_public_cert,
              alipay_root_cert, create_time)
             VALUES (?1,?2,?3,0,1,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15,?16,?17,?18,?19,?20)",
            rusqlite::params![
                type_, code, name,
                qr_url, zfb_pid, alipay_appid,
                alipay_public_key, alipay_private_key,
                cookie, wx_guid, qq, cloud_id,
                qr_type, memo, remark, channel_mode,
                app_cert, ali_cert, root_cert, crate::queue::now_str(),
            ],
        )?;
        let id = conn.last_insert_rowid();
        log_admin(&conn, "ypay_account_created", &detail)?;
        Ok(id)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(id) => ok_msg("通道已添加", json!({"id": id})),
        Err(e) => err(&e.to_string()),
    }
}

// ── PUT /api/ypay/accounts/{id} ─────────────────────────────────────────

async fn accounts_update(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(body): Json<Value>,
) -> Json<Value> {
    let Some(m) = body.as_object() else {
        return err("请求体必须是 JSON 对象");
    };
    // 前端保存整表时会带上全部字段；切换启停时只发 {is_status}。故只更新出现的字段。
    let mut sets: Vec<String> = Vec::new();
    let mut vals: Vec<rusqlite::types::Value> = Vec::new();
    for col in ACC_STR_COLS {
        if let Some(v) = m.get(*col) {
            let s = v.as_str().map(str::to_string).unwrap_or_else(|| v.to_string());
            sets.push(format!("{col}=?"));
            vals.push(rusqlite::types::Value::Text(s));
        }
    }
    for col in ACC_INT_COLS {
        if let Some(n) = ival(m, col) {
            sets.push(format!("{col}=?"));
            vals.push(rusqlite::types::Value::Integer(n));
        }
    }
    if sets.is_empty() {
        return err("没有可更新的字段");
    }
    if let Some(n) = ival(m, "is_status") {
        if n != 0 && n != 1 {
            return err("is_status 只能为 0 或 1");
        }
    }
    let change_type = sets.iter().any(|s| s.starts_with("is_status="));
    vals.push(rusqlite::types::Value::Integer(id));
    let sql = format!(
        "UPDATE ypay_account SET {} WHERE id=? AND deleted_at IS NULL",
        sets.join(", ")
    );
    let pool = state.db.clone_pool();
    let detail = if change_type {
        format!("切换支付通道状态 id={id}")
    } else {
        format!("更新支付通道 id={id}")
    };
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<usize> {
        let conn = pool.get()?;
        let n = conn.execute(&sql, rusqlite::params_from_iter(vals.iter()))?;
        if n > 0 {
            log_admin(&conn, "ypay_account_updated", &detail)?;
        }
        Ok(n)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(n) if n > 0 => ok_msg("通道已更新", json!({"id": id})),
        Ok(_) => err("通道不存在或已删除"),
        Err(e) => err(&e.to_string()),
    }
}

// ── DELETE /api/ypay/accounts/{id}（软删）────────────────────────────────

async fn accounts_delete(State(state): State<AppState>, Path(id): Path<i64>) -> Json<Value> {
    let pool = state.db.clone_pool();
    let detail = format!("删除支付通道 id={id}");
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<usize> {
        let conn = pool.get()?;
        let n = conn.execute(
            "UPDATE ypay_account SET deleted_at=?1 WHERE id=?2 AND deleted_at IS NULL",
            rusqlite::params![crate::queue::now_str(), id],
        )?;
        if n > 0 {
            log_admin(&conn, "ypay_account_deleted", &detail)?;
        }
        Ok(n)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(n) if n > 0 => ok_msg("通道已删除", json!({"id": id})),
        Ok(_) => err("通道不存在或已删除"),
        Err(e) => err(&e.to_string()),
    }
}

// ── POST /api/ypay/channel-test/{id}（静态自检，不假装连通）─────────────

/// 通道按 code 需要准备的字段（仅静态可判定项）。
/// 说明：本项检查**只**验证数据库里的配置字段是否齐全/格式合法，
/// 不代表渠道真的可用 —— 真实连通性依赖手机 APP 在线，见下方 pending/unsupported 项。
fn channel_required_fields(code: &str) -> &'static [(&'static str, &'static str)] {
    match code {
        "wxpay_dy" => &[("qr_url", "收款码内容"), ("cookie", "店员版 Cookie")],
        "lkl_wxpay" | "lkl_alipay" => &[("remark", "Authorization 令牌")],
        "alipay_dmf" | "alipay_official" => &[
            ("alipay_appid", "应用 APPID"),
            ("alipay_public_key", "支付宝公钥"),
            ("alipay_private_key", "应用私钥"),
        ],
        "dougong_alipay" | "lebrush_alipay" => &[("qr_url", "收款码内容")],
        "dougong_wxpay" | "lebrush_wxpay" => &[("qr_url", "收款码内容")],
        // 其余（wxpay_software / wxpay_skd / wxpay_cloudzs / 未列出）统一要求收款码内容
        _ => &[("qr_url", "收款码内容")],
    }
}

fn push_check(checks: &mut Vec<Value>, name: &str, level: &str, msg: String) {
    // ok 语义：只有 level=="ok" 才算通过；warn/pending/unsupported/error 都算未通过，
    // 前端据此显示红叉，避免「检查不出来的东西被显示成绿色的通过」。
    checks.push(json!({
        "name": name,
        "ok": level == "ok",
        "level": level,
        "msg": msg,
    }));
}

async fn channel_test(State(state): State<AppState>, Path(id): Path<i64>) -> Json<Value> {
    let pool = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Option<Value>> {
        let conn = pool.get()?;
        let Some(acc) = load_account(&conn, id)? else {
            return Ok(None);
        };
        let code = acc["code"].as_str().unwrap_or("").to_string();
        let name = acc["name"].as_str().unwrap_or("").to_string();
        let get = |k: &str| acc.get(k).and_then(Value::as_str).unwrap_or("").trim().to_string();

        let mut checks: Vec<Value> = Vec::new();
        push_check(&mut checks, "通道存在", "ok", format!("id={id} {name}"));

        if name.is_empty() {
            push_check(&mut checks, "通道名称", "error", "未填写通道名称".into());
        } else {
            push_check(&mut checks, "通道名称", "ok", name.clone());
        }

        // 静态必填字段
        for (field, label) in channel_required_fields(&code) {
            if get(field).is_empty() {
                push_check(
                    &mut checks,
                    label,
                    "error",
                    format!("{field} 未配置（该通道必须填写）"),
                );
            } else {
                push_check(&mut checks, label, "ok", "已配置".into());
            }
        }

        // 启停开关（is_status=1 表示后台允许该通道参与收款）
        if acc["is_status"].as_i64().unwrap_or(0) == 1 {
            push_check(&mut checks, "后台启用状态", "ok", "已启用".into());
        } else {
            push_check(
                &mut checks,
                "后台启用状态",
                "warn",
                "该通道已停用（is_status=0），不会参与收款".into(),
            );
        }

        // 云端/官方 SDK 渠道：本项目未实现其 API，如实告知
        if ["wxpay_cloud", "wxpay_jym_cloud", "wxpay_skd"].contains(&code.as_str()) {
            push_check(
                &mut checks,
                "云端接口",
                "unsupported",
                "该云端渠道的 API 未实现，扫码时将回落为静态收款码".into(),
            );
        }

        // 必须在手机 APP 在线才能验的项：明确标注，绝不算通过
        push_check(
            &mut checks,
            "手机 APP 在线心跳",
            "pending",
            "需手机 APP 在线并上报心跳后才能验证，服务端无法主动探测".into(),
        );
        push_check(
            &mut checks,
            "真实渠道连通性",
            "pending",
            "本项目无真实渠道协议，无法在这里发起真实收款验证；请在 APP 端完成支付测试".into(),
        );

        // 二维码：有收款码内容就渲染出来供人工扫码核对（无则不返回）。
        let qr_url = get("qr_url");
        let qr_image = if qr_url.is_empty() {
            Value::Null
        } else if qr_url.starts_with("data:image/") {
            // 已是图片 data URL，直接复用，避免二次渲染爆版本
            Value::String(qr_url.clone())
        } else {
            crate::ypay_qr::render_qr_image_value(&qr_url)
        };

        let all_ok = checks.iter().all(|c| c["ok"].as_bool().unwrap_or(false));
        Ok(Some(json!({
            "account_id": id,
            "code": code,
            "checks": checks,
            "all_ok": all_ok,
            "qr_image": qr_image,
        })))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(Some(data)) => ok(data),
        Ok(None) => err("通道不存在或已删除"),
        Err(e) => err(&e.to_string()),
    }
}

// ── GET /api/ypay/app-qrcode（APP 扫码配对）──────────────────────────────

async fn app_qrcode(State(state): State<AppState>) -> Json<Value> {
    let site_url = crate::pay::get_site_url(&state.db).await;
    let pool = state.db.clone_pool();
    let key = tokio::task::spawn_blocking(move || -> Option<String> {
        let conn = pool.get().ok()?;
        conn.query_row(
            "SELECT value FROM ypay_settings WHERE key='key'",
            [],
            |r| r.get::<_, String>(0),
        )
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
    })
    .await
    .unwrap_or(None);
    let Some(key) = key else {
        return err("通讯密钥未配置：请先在「基本配置」中生成并保存通讯密钥，再刷新二维码");
    };

    // 配对 payload（含服务地址与通讯密钥）。APP 扫到后据此连接 heartbeat/push 端点。
    // 密钥只存在于二维码内容里，不单独回显到 JSON。
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0);
    let payload = json!({
        "app": "ypay-monitor",
        "type": "pair",
        "site_url": site_url,
        "key": key,
        "heart_url": format!("{site_url}/api/ypay/vmq/heart"),
        "push_url": format!("{site_url}/api/ypay/vmq/push"),
        "ts": ts,
    });
    match crate::ypay_qr::render_qr_data_url(&payload.to_string()) {
        Some(qr_image) => ok_msg(
            "ok",
            json!({"qr_image": qr_image, "site_url": site_url, "key_set": true}),
        ),
        None => err("配对二维码生成失败（服务地址或密钥过长）"),
    }
}

// ── GET /api/ypay/orders ────────────────────────────────────────────────

const ORDER_COLS: &str = "id, trade_no, out_trade_no, type, name, money, truemoney, qrcode,
     h5_qrurl, status, account_id, notify_url, return_url, ip, create_time, out_time, end_time";

fn order_row_to_json(r: &rusqlite::Row) -> rusqlite::Result<Value> {
    let type_str: String = r.get(3)?;
    Ok(json!({
        "id": r.get::<_, i64>(0)?,
        "trade_no": r.get::<_, String>(1)?,
        "out_trade_no": r.get::<_, String>(2)?,
        "type": type_str,
        "pay_type": crate::ypay_db::type_to_pay_type(&type_str),
        "name": r.get::<_, Option<String>>(4)?.unwrap_or_default(),
        "money": r.get::<_, f64>(5)?,
        "truemoney": r.get::<_, f64>(6)?,
        "qrcode": r.get::<_, Option<String>>(7)?.unwrap_or_default(),
        "h5_qrurl": r.get::<_, Option<String>>(8)?.unwrap_or_default(),
        "status": r.get::<_, i64>(9)?,
        "account_id": r.get::<_, i64>(10)?,
        "notify_url": r.get::<_, Option<String>>(11)?.unwrap_or_default(),
        "return_url": r.get::<_, Option<String>>(12)?.unwrap_or_default(),
        "ip": r.get::<_, Option<String>>(13)?.unwrap_or_default(),
        "create_time": r.get::<_, Option<String>>(14)?.unwrap_or_default(),
        "out_time": r.get::<_, Option<String>>(15)?.unwrap_or_default(),
        "end_time": r.get::<_, Option<String>>(16)?,
    }))
}

async fn orders_list(
    State(state): State<AppState>,
    Query(params): Query<HashMap<String, String>>,
) -> Json<Value> {
    let page = params
        .get("page")
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(1)
        .max(1);
    let limit = params
        .get("limit")
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(20)
        .clamp(1, 200);
    let offset = (page - 1) * limit;
    let status = params.get("status").and_then(|v| v.parse::<i64>().ok());
    let pool = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = pool.get()?;
        let (total, items) = match status {
            Some(st) => {
                let total: i64 = conn.query_row(
                    "SELECT COUNT(*) FROM ypay_order WHERE deleted_at IS NULL AND status=?1",
                    rusqlite::params![st],
                    |r| r.get(0),
                )?;
                let mut stmt = conn.prepare(&format!(
                    "SELECT {ORDER_COLS} FROM ypay_order \
                     WHERE deleted_at IS NULL AND status=?1 ORDER BY create_time DESC, id DESC \
                     LIMIT ?2 OFFSET ?3"
                ))?;
                let rows = stmt
                    .query_map(rusqlite::params![st, limit, offset], order_row_to_json)?
                    .collect::<std::result::Result<Vec<_>, _>>()?;
                (total, rows)
            }
            None => {
                let total: i64 = conn.query_row(
                    "SELECT COUNT(*) FROM ypay_order WHERE deleted_at IS NULL",
                    [],
                    |r| r.get(0),
                )?;
                let mut stmt = conn.prepare(&format!(
                    "SELECT {ORDER_COLS} FROM ypay_order WHERE deleted_at IS NULL \
                     ORDER BY create_time DESC, id DESC LIMIT ?1 OFFSET ?2"
                ))?;
                let rows = stmt
                    .query_map(rusqlite::params![limit, offset], order_row_to_json)?
                    .collect::<std::result::Result<Vec<_>, _>>()?;
                (total, rows)
            }
        };
        Ok(json!({
            "items": items,
            "total": total,
            "page": page,
            "page_size": limit,
            "total_pages": ((total + limit - 1) / limit).max(1),
        }))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => ok(data),
        Err(e) => err(&e.to_string()),
    }
}

// ── POST /api/ypay/clear-orders（软删已完结支付单）──────────────────────

async fn clear_orders(State(state): State<AppState>) -> Json<Value> {
    let pool = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<usize> {
        let conn = pool.get()?;
        // 只清已完结（已支付 status=1 / 已关闭 status=-1），未支付(status=0)保留
        let n = conn.execute(
            "UPDATE ypay_order SET deleted_at=?1 WHERE deleted_at IS NULL AND status<>0",
            rusqlite::params![crate::queue::now_str()],
        )?;
        if n > 0 {
            log_admin(&conn, "ypay_orders_cleared", &format!("清除已完结支付单 {n} 条"))?;
        }
        Ok(n)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(n) => ok_msg(&format!("已清除 {n} 条已完结支付订单"), json!({"cleared": n})),
        Err(e) => err(&e.to_string()),
    }
}

// ── POST /api/ypay/close-expired ───────────────────────────────────────
//
// 超时时间取 ypay_settings.close_time（分钟，默认 5）—— 与前端「基本配置」里的
// 「未支付关闭(分钟)」一致；判据用 create_time 早于 cutoff（不复用 ypay_db 里
// 基于 out_time 的旧实现，那套用的是 pay_timeout 秒，口径不同）。

async fn close_expired(State(state): State<AppState>) -> Json<Value> {
    let pool = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<(usize, i64)> {
        let mut conn = pool.get()?;
        let close_minutes = conn
            .query_row(
                "SELECT value FROM ypay_settings WHERE key='close_time'",
                [],
                |r| r.get::<_, String>(0),
            )
            .ok()
            .and_then(|s| s.trim().parse::<i64>().ok())
            .unwrap_or(5)
            .max(1);
        let now = crate::queue::now_str();
        let cutoff = crate::queue::iso_from_secs(
            crate::queue::local_secs().saturating_sub((close_minutes as u64) * 60),
        );
        let tx = conn.transaction()?;
        let trade_nos: Vec<String> = {
            let mut stmt = tx.prepare(
                "SELECT trade_no FROM ypay_order \
                 WHERE deleted_at IS NULL AND status=0 AND create_time < ?1",
            )?;
            let rows = stmt.query_map(rusqlite::params![cutoff], |r| r.get::<_, String>(0))?;
            let mut v = Vec::new();
            for r in rows {
                v.push(r?);
            }
            v
        };
        let count = trade_nos.len();
        for tn in &trade_nos {
            tx.execute(
                "UPDATE ypay_order SET status=-1, end_time=?1 WHERE trade_no=?2",
                rusqlite::params![now, tn],
            )?;
            tx.execute("DELETE FROM ypay_tmp_price WHERE oid=?1", rusqlite::params![tn])?;
        }
        if count > 0 {
            log_admin(
                &tx,
                "ypay_orders_closed",
                &format!("关闭超时未支付订单 {count} 条（{close_minutes} 分钟）"),
            )?;
        }
        tx.commit()?;
        Ok((count, close_minutes))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok((n, cm)) => ok_msg(
            &format!("已关闭 {n} 个超时未支付订单（超时 {cm} 分钟）"),
            json!({"closed": n, "close_time": cm}),
        ),
        Err(e) => err(&e.to_string()),
    }
}

// ── POST /api/ypay/pay-test/create/{id}（按指定通道发起一笔测试支付）────

async fn pay_test_create(State(state): State<AppState>, Path(id): Path<i64>) -> Json<Value> {
    // 段 0：站点地址（用于生成二维码/回调）
    let site_url = crate::pay::get_site_url(&state.db).await;
    let trade_no = crate::pay::generate_trade_no();
    let batch_id = format!("TEST-{}", crate::ypay_db::uuid_hex_upper(12));

    // 段 1：取指定通道（而非随机渠道）+ 浮动价 + 锁价（阻塞）
    let db = state.db.clone();
    let trade_no1 = trade_no.clone();
    let prep = {
        let db = db.clone();
        tokio::task::spawn_blocking(move || -> Option<(Value, f64, u64)> {
            let conn = db.clone_pool().get().ok()?;
            let acc = load_account(&conn, id).ok()??;
            let account_id = acc["id"].as_i64().unwrap_or(0);
            let existing = db.ypay_get_active_prices_sync(account_id);
            let base = crate::pay::compute_floating_price(0.01, &existing);
            let really_price = db.ypay_lock_price_sync(base, &trade_no1)?;
            let timeout = db
                .ypay_setting_get_sync("pay_timeout", "300")
                .parse::<u64>()
                .unwrap_or(300);
            Some((acc, really_price, timeout))
        })
        .await
        .ok()
        .flatten()
    };
    let Some((account, really_price, timeout)) = prep else {
        return err("通道不存在或测试订单锁价失败");
    };

    // 段 2：生成二维码（可能走网络；云端/官方 SDK 未实现会返回空）
    let client = reqwest::Client::new();
    let (qrcode, h5_qrurl) = crate::ypay_qr::generate_qrcode(
        &client,
        &account,
        really_price,
        &trade_no,
        &batch_id,
        &site_url,
    )
    .await;
    if qrcode.is_empty() {
        db.ypay_release_price_sync(really_price);
        let code = account["code"].as_str().unwrap_or("");
        return err(&format!(
            "该通道无法生成测试二维码（code={code} 的动态码未实现或配置缺失），请在 APP 端验证"
        ));
    }

    // 段 3：落库支付单
    let type_str = account["type"].as_str().unwrap_or("").to_string();
    let pay_type = crate::ypay_db::type_to_pay_type(&type_str);
    let name = format!(
        "通道测试-{}",
        account["name"].as_str().unwrap_or("").trim()
    );
    let out_time = crate::pay::iso_after_secs(timeout);
    let created = {
        let db = db.clone();
        let trade_no = trade_no.clone();
        let batch_id = batch_id.clone();
        let qrcode_c = qrcode.clone();
        let h5 = h5_qrurl.clone();
        let name_c = name.clone();
        let type_c = type_str.clone();
        tokio::task::spawn_blocking(move || -> Option<Value> {
            let conn = db.clone_pool().get().ok()?;
            let created = db.ypay_create_order_sync(
                &trade_no,
                &batch_id,
                pay_type,
                &type_c,
                &name_c,
                0.01,
                really_price,
                id,
                &qrcode_c,
                &h5,
                "",
                "",
                "",
                &out_time,
            );
            if created.is_some() {
                let _ = log_admin(
                    &conn,
                    "ypay_pay_test_created",
                    &format!("通道测试支付单 {trade_no} 通道id={id} 实付¥{really_price}"),
                );
            }
            created
        })
        .await
        .ok()
        .flatten()
    };
    let Some(_order) = created else {
        db.ypay_release_price_sync(really_price);
        return err("创建测试支付单失败");
    };

    // 前端 usePayments.startChannelPayTest 读取：qr_image / really_price / batch_id / trade_no
    ok(json!({
        "qr_image": crate::ypay_qr::render_qr_image_value(&qrcode),
        "really_price": really_price,
        "batch_id": batch_id,
        "trade_no": trade_no,
        "pay_type": pay_type,
        "channel_code": account["code"].as_str().unwrap_or(""),
        "channel_name": account["name"].as_str().unwrap_or(""),
    }))
}

// ── GET /api/ypay/pay-test/check/{batch_id} ─────────────────────────────

async fn pay_test_check(
    State(state): State<AppState>,
    Path(batch_id): Path<String>,
    Query(params): Query<HashMap<String, String>>,
) -> Json<Value> {
    // 前端传 out_trade_no（=batch_id）与 trade_no，优先按 trade_no 精确查
    let trade_no = params.get("trade_no").cloned().unwrap_or_default();
    let out_trade_no = params
        .get("out_trade_no")
        .cloned()
        .unwrap_or_else(|| batch_id.clone());
    let pool = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Option<Value>> {
        let conn = pool.get()?;
        let find = |col: &str, val: &str| -> Option<Value> {
            if val.is_empty() {
                return None;
            }
            conn.query_row(
                &format!("SELECT {ORDER_COLS} FROM ypay_order WHERE {col}=?1 AND deleted_at IS NULL"),
                rusqlite::params![val],
                order_row_to_json,
            )
            .ok()
        };
        let order = find("trade_no", &trade_no)
            .or_else(|| find("out_trade_no", &out_trade_no))
            .or_else(|| find("trade_no", &batch_id));
        Ok(order)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(Some(o)) => {
            let status = o["status"].as_i64().unwrap_or(0);
            let expired = status == 0
                && !o["out_time"].as_str().unwrap_or("").is_empty()
                && crate::pay::parse_iso_secs(o["out_time"].as_str().unwrap_or(""))
                    .map(|t| t < crate::queue::local_secs() as i64)
                    .unwrap_or(false);
            ok(json!({
                "paid": status == 1,
                "expired": expired,
                "status": status,
                "trade_no": o["trade_no"],
                "out_trade_no": o["out_trade_no"],
                "really_price": o["truemoney"],
                "create_time": o["create_time"],
                "end_time": o["end_time"],
            }))
        }
        Ok(None) => err("测试订单不存在"),
        Err(e) => err(&e.to_string()),
    }
}

// ── GET/POST /api/ypay/diagnose（只做能证实的检查）──────────────────────

async fn diagnose(State(state): State<AppState>) -> Json<Value> {
    let pool = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = pool.get()?;
        let count = |sql: &str| -> i64 { conn.query_row(sql, [], |r| r.get(0)).unwrap_or(0) };
        let key_set: bool = conn
            .query_row(
                "SELECT COALESCE(NULLIF(value,''),'') <> '' FROM ypay_settings WHERE key='key'",
                [],
                |r| r.get(0),
            )
            .unwrap_or(false);
        let accounts_total = count("SELECT COUNT(*) FROM ypay_account WHERE deleted_at IS NULL");
        let accounts_enabled =
            count("SELECT COUNT(*) FROM ypay_account WHERE deleted_at IS NULL AND is_status=1");
        let accounts_online =
            count("SELECT COUNT(*) FROM ypay_account WHERE deleted_at IS NULL AND status=1");
        let orders_total = count("SELECT COUNT(*) FROM ypay_order WHERE deleted_at IS NULL");
        let last_paid: String = conn
            .query_row(
                "SELECT COALESCE(MAX(end_time),'') FROM ypay_order WHERE status=1",
                [],
                |r| r.get(0),
            )
            .unwrap_or_default();
        let last_order: String = conn
            .query_row(
                "SELECT COALESCE(MAX(create_time),'') FROM ypay_order WHERE deleted_at IS NULL",
                [],
                |r| r.get(0),
            )
            .unwrap_or_default();

        let mut checks: Vec<Value> = Vec::new();
        // 1) 通讯密钥（回调签名/心跳验签的前提）
        push_check(
            &mut checks,
            "通讯密钥",
            if key_set { "ok" } else { "error" },
            if key_set {
                "已配置".into()
            } else {
                "未配置：回调与心跳验签都会失败，请在「基本配置」生成并保存".into()
            },
        );
        // 2) 收款通道数量
        push_check(
            &mut checks,
            "收款通道",
            if accounts_total > 0 { "ok" } else { "warn" },
            format!("共 {accounts_total} 条通道（其中启用 {accounts_enabled} 条）"),
        );
        // 3) 启用通道
        push_check(
            &mut checks,
            "启用通道",
            if accounts_enabled > 0 { "ok" } else { "warn" },
            if accounts_enabled > 0 {
                format!("{accounts_enabled} 条已启用")
            } else {
                "没有已启用通道，下单时无法选到收款渠道".into()
            },
        );
        // 4) 在线通道：由手机 APP 心跳写入 status 标记，服务端无法主动探测
        push_check(
            &mut checks,
            "在线通道(status=1)",
            if accounts_online > 0 { "ok" } else { "warn" },
            format!(
                "当前 {accounts_online} 条标记在线；该标记由手机 APP 心跳写入，需 APP 在线"
            ),
        );
        // 5) 最近一次支付回调（有 status=1 的支付单即说明通道回过款）
        push_check(
            &mut checks,
            "最近支付回调",
            if !last_paid.is_empty() { "ok" } else { "warn" },
            if last_paid.is_empty() {
                "暂无成功回调记录".into()
            } else {
                format!("最近成功回调时间 {last_paid}")
            },
        );
        // 6) 最近支付单
        push_check(
            &mut checks,
            "最近支付单",
            if !last_order.is_empty() { "ok" } else { "warn" },
            if last_order.is_empty() {
                format!("暂无支付单（累计 {orders_total} 条）")
            } else {
                format!("最近支付单 {last_order}（累计 {orders_total} 条）")
            },
        );
        // 7/8) 无法证实项：明确标注，不算通过
        push_check(
            &mut checks,
            "APP 会话状态",
            "pending",
            "服务端不保存手机 APP 会话，无法验证连接是否仍然有效".into(),
        );
        push_check(
            &mut checks,
            "真实渠道连通",
            "unsupported",
            "本项目无真实渠道协议，端到端收款只能由 APP 端支付测试验证".into(),
        );

        let has_error = checks.iter().any(|c| c["level"] == "error");
        let all_ok = !has_error;
        let summary = if !key_set {
            "通讯密钥未配置，支付回调无法验签".to_string()
        } else if accounts_total == 0 {
            "尚未配置任何收款通道".to_string()
        } else if all_ok {
            "基础配置检查通过（真实连通性需在 APP 端验证）".to_string()
        } else {
            "存在需要处理的配置项".to_string()
        };
        Ok(json!({
            "all_ok": all_ok,
            "checks": checks,
            "summary": summary,
            "key_set": key_set,
            "accounts_total": accounts_total,
            "accounts_enabled": accounts_enabled,
            "accounts_online": accounts_online,
            "orders_total": orders_total,
            "last_paid_at": last_paid,
            "last_order_at": last_order,
        }))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => ok(data),
        Err(e) => err(&e.to_string()),
    }
}

// ── POST /api/ypay/reset-connection ────────────────────────────────────
//
// 诚实实现：本项目为无状态服务端，**不保存**手机 APP 的会话/心跳。
// schema 里 ypay_account 唯一与"连接"沾边的列是 status，但它是渠道可用性标记
// （ypay_pick_channel 要求 status=1 才会被选中收款），清掉会直接导致收款失效 ——
// 因此它不是"会话状态"，不能重置。故这里如实返回 success:false + 说明。

async fn reset_connection() -> Json<Value> {
    Json(json!({
        "success": false,
        "message": "无可重置的会话状态：服务端不保存手机 APP 会话；\
                    若提示密钥不匹配，请在「基本配置」重新生成通讯密钥，并在 APP 上重新扫码配对",
    }))
}