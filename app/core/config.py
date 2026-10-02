# --- Database (Task 2) ---
database_url: str = (
        "postgresql+psycopg://quickcart:quickcart_dev_password@localhost:5433/quickcart"
    )

# -----------Auth-----------
    # --- Auth (Task 3) ---
jwt_secret_key: str = Field(min_length=32)   # required: app refuses to start without it
jwt_algorithm: str = "HS256"
access_token_expire_minutes: int = Field(default=15, gt=0)
refresh_token_expire_days: int = Field(default=7, gt=0)