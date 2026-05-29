from loguru import logger
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.auth import get_optional_user
from api.models import ApiResponse
from services.scan_service import scan_all_platforms, scan_platform

router = APIRouter(prefix="/api/courses", tags=["课程扫描"])



@router.get("/platforms", response_model=ApiResponse)
def list_platforms():
    """获取平台列表（从 domain_monitor 统一数据源读取）"""
    from api.services.domain_monitor import get_active_platforms
    platforms = get_active_platforms()
    items = [{"id": wid, "name": info["name"], "base_url": info["base_url"]}
             for wid, info in platforms.items()]
    return ApiResponse(data=items)


class ScanRequest(BaseModel):
    username: str = Field(..., min_length=1, description="平台学号")
    password: str = Field(..., min_length=1, description="平台密码")
    include_records: bool = Field(default=True, description="是否包含学习记录(较慢)")


class ReloginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="平台学号")
    password: str = Field(..., min_length=1, description="平台新密码")
    website_id: int = Field(..., description="平台ID")
    include_records: bool = Field(default=True, description="是否包含学习记录(较慢)")


@router.post("/scan", response_model=ApiResponse)
def scan_platforms(req: ScanRequest, current_user: dict = Depends(get_optional_user)):
    results = scan_all_platforms(req.username, req.password, req.include_records)

    total_courses = sum(len(r["courses"]) for r in results)
    ok_platforms = sum(1 for r in results if r["status"] == "ok")

    return ApiResponse(
        message=f"扫描完成: {ok_platforms}/{len(results)} 个平台登录成功, 共 {total_courses} 门课程",
        data={"platforms": results},
    )


@router.post("/relogin", response_model=ApiResponse)
def relogin_platform(req: ReloginRequest, current_user: dict = Depends(get_optional_user)):
    """单平台重新登录（用于密码错误后重试）"""
    from api.services.session_pool import pool as session_pool
    session_pool.remove(req.username, req.website_id)

    result = scan_platform(req.username, req.password, req.website_id, req.include_records)
    return ApiResponse(
        message=f"平台{'登录成功' if result['status'] == 'ok' else '登录失败'}",
        data={"platform": result},
    )


class ChaoxingScanRequest(BaseModel):
    username: str = Field(..., min_length=1, description="学习通账号（手机号）")
    password: str = Field(..., min_length=1, description="学习通密码")


@router.post("/scan/chaoxing", response_model=ApiResponse)
def scan_chaoxing(req: ChaoxingScanRequest, current_user: dict = Depends(get_optional_user)):
    """学习通账号密码扫描"""
    from services.scan_service import scan_chaoxing

    result = scan_chaoxing(req.username, req.password)

    total_courses = len(result.get("courses", []))
    status = result.get("status", "error")

    if status == "ok":
        return ApiResponse(
            message=f"学习通扫描完成，共 {total_courses} 门课程",
            data={"platform": result},
        )
    else:
        return ApiResponse(
            code=400,
            message=result.get("error", "扫描失败"),
            data={"platform": result},
        )


class ChaoxingDiscussRequest(BaseModel):
    username: str = Field(..., min_length=1, description="学习通账号")
    password: str = Field(..., min_length=1, description="学习通密码")
    course_id: str = Field(..., min_length=1, description="课程ID")
    class_id: str = Field(..., min_length=1, description="班级ID")
    knowledge_id: str = Field(default="", description="知识点ID（可选）")
    title: str = Field(default="", description="讨论标题（可选，use_ai时自动生成）")
    content: str = Field(default="", description="讨论内容（可选，use_ai时自动生成）")
    use_ai: bool = Field(default=True, description="是否使用AI生成内容")
    course_name: str = Field(default="", description="课程名（AI生成用）")


@router.post("/chaoxing/discuss", response_model=ApiResponse)
def post_chaoxing_discuss(req: ChaoxingDiscussRequest, current_user: dict = Depends(get_optional_user)):
    """学习通发表讨论（支持AI生成内容）"""
    from infrastructure.chaoxing_session import ChaoxingSession
    from infrastructure.chaoxing_discuss import get_discuss_bbsid, post_discussion

    # 登录
    session = ChaoxingSession()
    if not session.login(req.username, req.password):
        return ApiResponse(code=400, message="学习通登录失败，请检查账号密码")

    # 获取讨论区bbsid
    bbsid = get_discuss_bbsid(session, req.course_id, req.class_id, req.knowledge_id)
    if not bbsid:
        return ApiResponse(code=400, message="获取讨论区失败")

    # 发表讨论
    result = post_discussion(
        session, req.course_id, req.class_id, bbsid,
        content=req.content, title=req.title,
        use_ai=req.use_ai, course_name=req.course_name,
    )

    if result.get('success'):
        return ApiResponse(
            message="讨论发表成功",
            data={
                "title": result.get('title', ''),
                "content": result.get('content', ''),
                "topic_id": result.get('topic_id', 0),
            },
        )
    else:
        return ApiResponse(
            code=400,
            message=result.get('error', '发表失败'),
        )


class ChaoxingPointsRequest(BaseModel):
    username: str = Field(..., min_length=1, description="学习通账号")
    password: str = Field(..., min_length=1, description="学习通密码")
    course_id: str = Field(..., min_length=1, description="课程ID")
    class_id: str = Field(..., min_length=1, description="班级ID")


@router.post("/chaoxing/points", response_model=ApiResponse)
def get_chaoxing_points(req: ChaoxingPointsRequest, current_user: dict = Depends(get_optional_user)):
    """学习通查询积分状态和规则"""
    from infrastructure.chaoxing_session import ChaoxingSession
    from infrastructure.chaoxing_points import ScoreRuleParser, PointsExecutor

    # 登录
    session = ChaoxingSession()
    if not session.login(req.username, req.password):
        return ApiResponse(code=400, message="学习通登录失败，请检查账号密码")

    # 获取积分规则
    rule = ScoreRuleParser.fetch_rules(session, req.course_id, req.class_id)

    # 获取积分状态
    executor = PointsExecutor(session, req.course_id, req.class_id, rule)
    status = executor.get_status()

    return ApiResponse(
        data={
            "rule": {
                "target": rule.target,
                "daily_limit": rule.daily_limit,
                "video_min": rule.video_min,
                "items": [
                    {
                        "score_type": item.score_type,
                        "name": item.name,
                        "rate": item.rate,
                        "daily_cap": item.daily_cap,
                        "min_total": item.min_total,
                    }
                    for item in rule.items
                ],
            },
            "status": {
                "total": status.total,
                "day_score": status.day_score,
                "study_days": status.study_days,
                "items": {
                    str(st): {"day": item.day, "total": item.total}
                    for st, item in status.items.items()
                },
                "remaining_today": executor.get_remaining_today(status),
                "is_done": executor.check_done(status),
            },
        },
    )
