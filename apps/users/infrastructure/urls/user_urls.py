"""URLs de usuarios."""
from django.urls import path
from apps.users.infrastructure.views import UserProfileView, UserListView

urlpatterns = [
    path('', UserListView.as_view(), name='user_list'),
    path('me/', UserProfileView.as_view(), name='user_profile'),
]
