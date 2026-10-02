class PaginatedProducts(BaseModel):
    items: list[ProductRead]
    page: int 
    limit: int 
    total: int 
    pages: int