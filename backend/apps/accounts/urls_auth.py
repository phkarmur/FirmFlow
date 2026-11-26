from django.urls import path
from .views import (LoginView, LogoutView, CurrentUserView, ProfileView, ChangePasswordView,
                    LogoutOthersView, PasswordResetRequestView, PasswordResetConfirmView)

urlpatterns = [
    path('login/', LoginView.as_view(), name='auth_login'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
    path('me/', CurrentUserView.as_view(), name='auth_me'),
    path('profile/', ProfileView.as_view(), name='auth_profile'),
    path('change_password/', ChangePasswordView.as_view(), name='auth_change_password'),
    path('logout_others/', LogoutOthersView.as_view(), name='auth_logout_others'),
    path('password_reset/', PasswordResetRequestView.as_view(), name='auth_password_reset'),
    path('password_reset/confirm/', PasswordResetConfirmView.as_view(), name='auth_password_reset_confirm'),
]
