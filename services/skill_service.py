# services/skill_service.py
import os
from fastapi import FastAPI
from pydantic import BaseModel

from skills.literature         import LiteratureSkill
from skills.amazon             import AmazonSkill
from skills.academic_integrity import AcademicIntegritySkill
from skills.amazon_seller      import AmazonSellerSkill
from skills.general_qa         import GeneralQASkill

REGISTRY = {
    "literature": LiteratureSkill,
    "amazon":     AmazonSkill,
    "integrity":  AcademicIntegritySkill,
    "seller":     AmazonSellerSkill,
    "general":    GeneralQASkill,
}

SKILL_NAME = os.getenv("SKILL_NAME", "literature")
skill = REGISTRY[SKILL_NAME]()

app = FastAPI(title=f"{SKILL_NAME}-agent")


class Query(BaseModel):
    query: str


@app.get("/healthz")
def healthz():
    return {"status": "ok", "skill": SKILL_NAME}


@app.post("/invoke")
def invoke(body: Query):
    return skill(body.query).to_dict()