from rest_framework.routers import DefaultRouter

from core.api.views import ProductViewSet, SupplierViewSet

router = DefaultRouter()
router.register(r"product", ProductViewSet)
router.register(r"suppliers", SupplierViewSet, basename="supplier")

urlpatterns = router.urls
