from rest_framework.routers import DefaultRouter

from core.api.views import ProductViewSet, SupplierViewSet
from core.views import CategoryViewSet

router = DefaultRouter()
router.register(r"product", ProductViewSet)
router.register(r"suppliers", SupplierViewSet, basename="supplier")
router.register(r"categories", CategoryViewSet, basename="category")

urlpatterns = router.urls
