from pydantic import AwareDatetime, BaseModel, Field, model_validator


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    color: str | None = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$")


class CategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    color: str | None = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$")

    @model_validator(mode="after")
    def validate_update_payload(self):
        if self.name is None and self.color is None:
            raise ValueError("At least one field must be provided")
        return self


class CategoryResponse(BaseModel):
    id: int
    name: str
    color: str
    updated_at: AwareDatetime


class DeleteCategoryResponse(BaseModel):
    id: int
    deleted: bool
