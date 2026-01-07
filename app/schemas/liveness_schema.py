from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator
from pydantic.config import ConfigDict


class LivenessRequest(BaseModel):
    token: str
