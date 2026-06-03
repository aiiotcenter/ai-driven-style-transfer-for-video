from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import include
from django.contrib import admin
from django.urls import path

urlpatterns = [
    # path("", admin.site.urls),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("style_transfer/", include("style_transfer.urls"))
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
