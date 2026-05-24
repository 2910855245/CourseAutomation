from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import get_current_admin
from api.database import db

router = APIRouter(prefix="/api/admin/config", tags=["系统配置"])


class ConfigSet(BaseModel):
    key: str
    value: str


@router.get("")
def get_configs(admin: dict = Depends(get_current_admin)):
    configs = db.config_all()
    return {"code": 0, "data": configs}


@router.post("")
def set_config(payload: ConfigSet, admin: dict = Depends(get_current_admin)):
    ok = db.config_set(payload.key, payload.value)
    if not ok:
        raise HTTPException(status_code=500, detail="配置保存失败")
    db.audit_log("config_updated", operator=admin.get("username", "admin"),
                 detail=f"配置 {payload.key} = {payload.value}")
    return {"code": 0, "message": "配置已更新"}


class TestModelInput(BaseModel):
    model: str = "deepseek-chat"


@router.post("/test-deepseek")
def test_deepseek(payload: TestModelInput = None, admin: dict = Depends(get_current_admin)):
    """检查 DeepSeek API Key 是否可用：openai 模块、API Key、网络连通性"""
    import time
    test_model = (payload.model if payload else None) or "deepseek-chat"
    result = {"openai_module": False, "api_key": "", "key_source": "", "api_ok": False, "error": "", "model": "", "latency_ms": 0}

    # 1. Check openai module
    try:
        import openai  # noqa: F401
        result["openai_module"] = True
    except ImportError:
        result["error"] = "openai 模块未安装，请执行: pip install openai"
        return {"code": -1, "data": result}

    # 2. Get API key (DB first, then env)
    api_key = ""
    try:
        db_key = db.config_get("deepseek_api_key")
        if db_key:
            api_key = db_key
            result["key_source"] = "数据库配置"
    except Exception as e:
        pass
    if not api_key:
        from config import settings
        api_key = settings.deepseek_api_key
        result["key_source"] = "环境变量"
    if not api_key:
        result["error"] = "DeepSeek API Key 未配置"
        return {"code": -1, "data": result}
    result["api_key"] = api_key[:6] + "****" + api_key[-4:] if len(api_key) > 10 else "****"

    # 3. Test API call
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        t0 = time.time()
        resp = client.chat.completions.create(
            model=test_model,
            messages=[{"role": "user", "content": "回复OK"}],
            max_tokens=10,
            timeout=15,
        )
        latency = int((time.time() - t0) * 1000)
        result["api_ok"] = True
        result["model"] = resp.model or "deepseek-chat"
        result["latency_ms"] = latency
    except Exception as e:
        err = str(e)
        if "401" in err or "Unauthorized" in err:
            result["error"] = "API Key 无效或已过期"
        elif "429" in err or "rate" in err.lower():
            result["error"] = "请求频率过高，请稍后再试"
        elif "timeout" in err.lower() or "connect" in err.lower():
            result["error"] = "网络连接超时，无法访问 DeepSeek API"
        else:
            result["error"] = f"API 调用失败: {err[:200]}"

    return {"code": 0, "data": result}
