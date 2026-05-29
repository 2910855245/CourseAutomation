from fastapi import APIRouter, HTTPException, Query

from loguru import logger

from api.models import ApiResponse, CourseDetail, CourseInfo, ExamInfo, RefreshCoursesRequest, VideoInfo
from api.services.session_pool import pool as session_pool

router = APIRouter(prefix="/api/courses", tags=["课程查询"])


def _get_session(username: str, password: str, website_id: int):
    try:
        return session_pool.get_or_login(username, password, website_id)
    except Exception as e:
        logger.error("Session获取失败: {}", e)
        raise HTTPException(status_code=401, detail="登录失败，请检查账号信息")


@router.get("/", response_model=ApiResponse)
def list_courses(username: str = Query(...), password: str = Query(...), website_id: int = Query(...)):
    from infrastructure.course_crawler import get_course_list
    info = _get_session(username, password, website_id)
    try:
        result = get_course_list(info.session, website_id)
        courses = result.get("data", []) if isinstance(result, dict) else (result or [])
        items = []
        for c in courses:
            items.append(CourseInfo(
                course_id=c.get("course_id", ""),
                course_name=c.get("name", ""),
                platform=str(website_id),
            ).dict())
        return ApiResponse(data=items)
    except Exception as e:
        logger.error("获取课程列表失败: {}", e)
        raise HTTPException(status_code=500, detail="获取课程列表失败")


@router.post("/refresh", response_model=ApiResponse)
def refresh_courses(req: RefreshCoursesRequest):
    import tempfile

    from infrastructure.course_crawler import get_courses
    from services.course_service import process_single_course
    info = _get_session(req.username, req.password, req.website_id)
    try:
        courses = get_courses(info.session)
        if not courses:
            return ApiResponse(message="未获取到任何课程")
        refreshed = 0
        for c in courses:
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    result = process_single_course(info.session, c, tmpdir, max_workers=8, silent=True)
                if result:
                    refreshed += 1
            except Exception as e:
                pass
        return ApiResponse(message=f"已刷新 {refreshed}/{len(courses)} 门课程")
    except Exception as e:
        logger.error("刷新课程失败: {}", e)
        raise HTTPException(status_code=500, detail="刷新课程失败")


@router.get("/{course_id}", response_model=ApiResponse)
def get_course_detail(course_id: str, username: str = Query(...), password: str = Query(...),
                      website_id: int = Query(...)):
    import tempfile

    from infrastructure.course_crawler import get_courses
    from services.course_service import process_single_course
    info = _get_session(username, password, website_id)
    try:
        courses = get_courses(info.session)
        target = None
        for c in courses:
            if c.get("course_id") == course_id:
                target = c
                break
        if not target:
            raise HTTPException(status_code=404, detail="课程不存在")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = process_single_course(info.session, target, tmpdir, max_workers=8, silent=True)
        if not result:
            raise HTTPException(status_code=404, detail="课程内容获取失败")
        videos = []
        exams = []
        for node in result.get("nodes", []):
            ntype = node.get("node_type", "")
            hidden = node.get("hidden_params", {})
            if ntype == "video":
                videos.append(VideoInfo(
                    node_id=node.get("nodeId", ""),
                    name=node.get("name", ""),
                    duration=int(hidden.get("video-duration", 0)),
                ).dict())
            elif ntype in ("exam", "work"):
                work_id = hidden.get("work_id", "")
                exams.append(ExamInfo(
                    exam_id=node.get("nodeId", ""),
                    name=node.get("name", ""),
                    can_answer=bool(work_id),
                    work_id=work_id or None,
                ).dict())
        return ApiResponse(data=CourseDetail(
            course_id=course_id,
            course_name=target.get("name", ""),
            platform=str(website_id),
            videos=videos,
            exams=exams,
        ).dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取课程详情失败: {}", e)
        raise HTTPException(status_code=500, detail="获取课程详情失败")


@router.get("/{course_id}/videos", response_model=ApiResponse)
def get_course_videos(course_id: str, username: str = Query(...), password: str = Query(...),
                      website_id: int = Query(...)):
    import tempfile

    from infrastructure.course_crawler import get_courses
    from services.course_service import process_single_course
    info = _get_session(username, password, website_id)
    try:
        courses = get_courses(info.session)
        target = None
        for c in courses:
            if c.get("course_id") == course_id:
                target = c
                break
        if not target:
            raise HTTPException(status_code=404, detail="课程不存在")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = process_single_course(info.session, target, tmpdir, max_workers=8, silent=True)
        if not result:
            raise HTTPException(status_code=404, detail="课程内容获取失败")
        videos = []
        for node in result.get("nodes", []):
            if node.get("node_type") == "video":
                hidden = node.get("hidden_params", {})
                videos.append(VideoInfo(
                    node_id=node.get("nodeId", ""),
                    name=node.get("name", ""),
                    duration=int(hidden.get("video-duration", 0)),
                ).dict())
        return ApiResponse(data=videos)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取视频列表失败: {}", e)
        raise HTTPException(status_code=500, detail="获取视频列表失败")


@router.get("/{course_id}/exams", response_model=ApiResponse)
def get_course_exams(course_id: str, username: str = Query(...), password: str = Query(...),
                     website_id: int = Query(...)):
    import tempfile

    from infrastructure.course_crawler import get_courses
    from services.course_service import process_single_course
    info = _get_session(username, password, website_id)
    try:
        courses = get_courses(info.session)
        target = None
        for c in courses:
            if c.get("course_id") == course_id:
                target = c
                break
        if not target:
            raise HTTPException(status_code=404, detail="课程不存在")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = process_single_course(info.session, target, tmpdir, max_workers=8, silent=True)
        if not result:
            raise HTTPException(status_code=404, detail="课程内容获取失败")
        exams = []
        for node in result.get("nodes", []):
            if node.get("node_type") in ("exam", "work"):
                hidden = node.get("hidden_params", {})
                work_id = hidden.get("work_id", "")
                exams.append(ExamInfo(
                    exam_id=node.get("nodeId", ""),
                    name=node.get("name", ""),
                    can_answer=bool(work_id),
                    work_id=work_id or None,
                ).dict())
        return ApiResponse(data=exams)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取考试列表失败: {}", e)
        raise HTTPException(status_code=500, detail="获取考试列表失败")
