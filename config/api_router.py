from rest_framework.routers import DefaultRouter
from core.api.views import ProductViewSet

router = DefaultRouter()
router.register(r"product", ProductViewSet)

urlpatterns = router.urls
