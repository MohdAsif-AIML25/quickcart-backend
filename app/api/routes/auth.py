from docket import Depends
from fastapi import dependencies

from app.core.rate_limit import login_rate_limiter

responses={401:{"description":"Invalid credentials"},429:{"description":"Too many attempts"}},dependencies=[Depends(login_rate_limiter)],
   