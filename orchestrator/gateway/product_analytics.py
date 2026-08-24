"""Operator-only consent surface for the installation-level fleet heartbeat."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from contracts.models import ProductAnalyticsConsentRequest, ProductAnalyticsStatus
from orchestrator.gateway.auth import is_operator_request
from orchestrator.product_analytics import get_product_analytics

router = APIRouter(prefix="/product-analytics", tags=["product analytics"])


def _require_operator(request: Request) -> None:
    if not is_operator_request(request):
        raise HTTPException(status_code=403, detail="only the laptop operator can do that")


@router.get("", response_model=ProductAnalyticsStatus)
def product_analytics_status(request: Request) -> ProductAnalyticsStatus:
    _require_operator(request)
    return ProductAnalyticsStatus.model_validate(
        get_product_analytics().status(manageable=True)
    )


@router.put("", response_model=ProductAnalyticsStatus)
def update_product_analytics(
    request: Request, consent: ProductAnalyticsConsentRequest
) -> ProductAnalyticsStatus:
    _require_operator(request)
    service = get_product_analytics()
    service.set_consent(consent.allowed)
    return ProductAnalyticsStatus.model_validate(service.status(manageable=True))
