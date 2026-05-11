from rest_framework.routers import DefaultRouter
from core.api.views import AuditLogProductViewSet, ProductViewSet

router = DefaultRouter()
router.register(r"product", ProductViewSet)
router.register(
    r"audit-log-products",
    AuditLogProductViewSet,
    basename="audit-log-product",
)

urlpatterns = router.urls
