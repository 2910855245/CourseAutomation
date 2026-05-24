from dataclasses import dataclass


@dataclass
class CourseTask:
    node_id: str
    duration: int = 3600
    report_interval: int = 30
    viewed_duration: int = 0
    course_name: str = ""
    video_name: str = ""
