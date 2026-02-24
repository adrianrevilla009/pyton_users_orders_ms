"""URLs de usuarios."""
from django.urls import path
from src.interfaces.api.views.user_views import UserDetailView, UserListView

urlpatterns = [
    path('', UserListView.as_view(), name='user-list'),
    path('<uuid:user_id>/', UserDetailView.as_view(), name='user-detail'),
]
