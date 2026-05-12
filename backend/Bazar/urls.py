"""
URL configuration for Bazar project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from django.http import JsonResponse
from django.conf import settings
from django.conf.urls.static import static

def api_root(request):
    return JsonResponse({
        'message': 'BazaarAF API',
        'endpoints': {
            'auth': '/api/auth/',
            'admin': '/admin/',
        }
    })

urlpatterns = [
    # Non-translatable URLs (API endpoints)
    path('api/', include('api.urls')),
    path('', api_root),
] + i18n_patterns(
    # Translatable URLs (admin, main site)
    path('admin/', admin.site.urls),
    prefix_default_language=False,  # Removes default language prefix (e.g., no /en/)
)

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
