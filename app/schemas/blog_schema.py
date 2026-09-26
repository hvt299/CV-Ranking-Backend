from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class BlogCategory(str, Enum):
    INTERVIEW = "interview"
    CV_WRITING = "cv_writing"
    CAREER_PATH = "career_path"
    HR_CORNER = "hr_corner"

class BlogCreate(BaseModel):
    title: str = Field(..., description="Tiêu đề bài viết")
    category: BlogCategory = Field(..., description="Danh mục bài viết")
    thumbnail_url: str = Field(..., description="Ảnh bìa bài viết")
    content_html: str = Field(..., description="Nội dung bài viết (HTML/Rich Text)")
    author_name: str = Field(default="Ban Biên Tập", description="Tên tác giả")
    is_published: bool = Field(default=True, description="Đăng ngay hay lưu nháp")

class BlogUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[BlogCategory] = None
    thumbnail_url: Optional[str] = None
    content_html: Optional[str] = None
    author_name: Optional[str] = None
    is_published: Optional[bool] = None