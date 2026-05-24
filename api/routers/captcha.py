from fastapi import APIRouter

from api.models import ApiResponse
from api.services.captcha import captcha_service

router = APIRouter(prefix="/api/captcha", tags=["验证码"])


@router.get("/generate", response_model=ApiResponse)
def generate_captcha():
    token, image_b64 = captcha_service.generate()
    return ApiResponse(
        message="验证码已生成",
        data={
            "token": token,
            "image": image_b64,
        },
    )
